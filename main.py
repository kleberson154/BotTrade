import datetime
import sys
import io
import os
import time
import gc
from queue import Queue
from threading import Thread

from src.connection import get_websocket_session, get_http_session
from src.strategy import TradingStrategy
from src.risk_manager import RiskManager
from src.execution import ExecutionManager
from src.logger import setup_logger
from src.notifier import TelegramNotifier

from dotenv import load_dotenv

# --- CONFIGURAÇÃO DE AMBIENTE ---
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
fuso_brasilia = datetime.timezone(datetime.timedelta(hours=-3))
load_dotenv()

# --- VARIÁVEIS GLOBAIS ---
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
_mode = os.getenv("BYBIT_MODE", "demo").lower()
IS_TESTNET = _mode == "testnet"
IS_DEMO = _mode == "demo"
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT").split(",")
ULTIMO_CHECK_VIVO = 0 
SALDO_INICIAL_DIA = None
ULTIMO_ORDER_ID_PROCESSADO = None
ULTIMO_CHECK_CALOR = 0
COIN_CONFIGS = {
    "BTCUSDT":  {"atr_mult": 1.5, "min_pnl_be": 0.004, "dist_respiro": 0.010, "min_adx": 22, "invert_signal": False},
    "ETHUSDT":  {"atr_mult": 1.6, "min_pnl_be": 0.005, "dist_respiro": 0.012, "min_adx": 24, "invert_signal": False, "use_regime_filter": True, "allow_short": False},
    "SOLUSDT":  {"atr_mult": 2.6, "min_pnl_be": 0.004, "dist_respiro": 0.024, "min_adx": 36, "invert_signal": True},
    "XRPUSDT":  {"atr_mult": 2.0, "min_pnl_be": 0.0035, "dist_respiro": 0.012, "min_adx": 30, "invert_signal": True},
    "AVAXUSDT": {"atr_mult": 2.6, "min_pnl_be": 0.004, "dist_respiro": 0.024, "min_adx": 36, "invert_signal": True},
}

strategies = {}
for symbol in SYMBOLS:
    strat = TradingStrategy(symbol=symbol, notifier=notifier)
    
    # Injeta as configs específicas se existirem no dicionário
    config = COIN_CONFIGS.get(symbol, {})
    for key, value in config.items():
        setattr(strat, key, value) # Isso sobrescreve os defaults da classe
        
    strategies[symbol] = strat

# --- INICIALIZAÇÃO DE COMPONENTES GLOBAIS ---
notifier = TelegramNotifier()
log = setup_logger()
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
message_queue = Queue()

MASTERS = ["BTCUSDT", "ETHUSDT"]
for m in MASTERS:
    if m not in strategies:
        strategies[m] = TradingStrategy(symbol=m, notifier=notifier)

cache_balance = {"total": 0, "avail": 0, "last_update": 0}
cache_positions = {"data": [], "last_update": 0}

# =========================================================
# 1. LÓGICA PRINCIPAL DE SINAIS E ESTRATÉGIA
# =========================================================

def handle_signal_logic(message):
    if "data" not in message: return
    
    topic = message.get("topic", "")
    parts = topic.split('.')
    symbol = parts[-1]
    timeframe = parts[1]
    
    # --- A) ATUALIZAÇÃO DOS DADOS (O que você já faz) ---
    strat = strategies.get(symbol)
    if not strat: return
    
    candle = message["data"][0]
    tf_key = "1m" if timeframe == "1" else "15m"
    strat.add_new_candle(tf_key, {
        "open": float(candle["open"]),
        "close": float(candle["close"]),
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "timestamp": int(candle["start"]),
        "volume": float(candle["volume"])
    })

    # --- B) CÁLCULO DO FAROL (Global) ---
    # Só recalculamos o sentimento se o candle de 15m do BTC ou ETH for atualizado
    sentimento = get_market_sentiment()

    # --- C) LÓGICA DE EXECUÇÃO (Apenas Moedas na Whitelist) ---
    if tf_key == "1m":
        current_price = float(candle["close"])
        is_confirmado = candle.get("confirm", False)

        # 1. Proteção de Posição Ativa
        if strat.is_positioned:
            status = strat.monitor_protection(current_price)
            if status == "UPDATE_SL":
                update_remote_sl(symbol, strat.sl_price)
            elif status == "PARTIAL_EXIT":
                execute_partial_tp(symbol, strat, current_price)

        # 2. Busca por Entrada (Passando o sentimento do Farol)
        elif is_confirmado and symbol in SYMBOLS:
            # Chame o check_signal passando o sentimento calculado
            signal, current_atr = strat.check_signal(market_sentiment=sentimento)
            
            if signal in ["BUY", "SELL"]:
                log.info(f"🎯 SINAL {signal} em {symbol} | Sentimento: {sentimento}")
                execute_new_trade(symbol, signal, current_price, current_atr)

# =========================================================
# 2. FUNÇÕES DE EXECUÇÃO E API
# =========================================================

def execute_new_trade(symbol, signal, price, atr):
    """Abre nova operação com TP longo (Trend Following)"""
    get_cached_data() 
    if len(cache_positions['data']) >= risk_mgr.max_positions: return
    if cache_balance['avail'] < 5.0: return # Mínimo para margem

    try:
        side = "Buy" if signal == "BUY" else "Sell"
        # 1. Parâmetros de Risco
        lev, qty = risk_mgr.get_dynamic_risk_params(price, price * 0.985, cache_balance['total'])
        sl, _ = risk_mgr.get_sl_tp_adaptive(symbol, side, price, atr, lev)
        
        # 2. TP de Segurança (Longo para deixar correr)
        tp_longo = price * (1.20 if side == "Buy" else 0.80)
        
        q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))

        prepare_leverage(symbol, lev)
        
        # 3. Envio da Ordem
        order = session.place_order(
            category="linear", symbol=symbol, side=side, orderType="Market",
            qty=qty_str, 
            takeProfit=str(round(tp_longo, p_prec)), 
            stopLoss=str(round(sl, p_prec)),
            tpOrderType="Market", slOrderType="Market", tpslMode="Full"
        )

        if order['retCode'] == 0:
            strat = strategies[symbol]
            strat.is_positioned = True
            strat.side = signal
            strat.entry_price = price
            strat.sl_price = sl
            strat.current_qty = float(qty) # Salva para a parcial
            strat.partial_taken = False
            
            notifier.send_message(f"🚀 *{symbol} {side}* | {lev}x | Qty: {qty_str}\n🛡️ SL inicial: {round(sl, p_prec)}")
            
    except Exception as e:
        log.error(f"Erro abertura {symbol}: {e}")

def execute_partial_tp(symbol, strat, current_price):
    """Fecha 50% e move SL para o Breakeven"""
    if strat.partial_taken: return

    try:
        log.info(f"💰 Alvo Parcial em {symbol} ({current_price})")
        
        q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_to_close = strat.current_qty * 0.5
        qty_str = str(int(qty_to_close)) if q_prec == 0 else str(round(qty_to_close, q_prec))

        side_close = "Sell" if strat.side == "BUY" else "Buy"
        
        # 1. Fecha metade a mercado
        res = session.place_order(
            category="linear", symbol=symbol, side=side_close,
            orderType="Market", qty=qty_str, reduceOnly=True
        )

        if res['retCode'] == 0:
            strat.partial_taken = True
            strat.current_qty -= float(qty_str)
            
            # 2. Move SL para o Zero (Break-even) + taxa
            new_sl = strat.entry_price * (1.0005 if strat.side == "BUY" else 0.9995)
            strat.sl_price = new_sl
            update_remote_sl(symbol, new_sl)
            
            notifier.send_message(f"✅ *{symbol}* Parcial de 50%!\n🛡️ Stop movido para o Zero.")
            
    except Exception as e:
        log.error(f"Erro na parcial de {symbol}: {e}")

def update_remote_sl(symbol, new_sl):
    """Atualiza o Stop Loss na Bybit (Trailing)"""
    try:
        _, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        session.set_trading_stop(
            category="linear", symbol=symbol,
            stopLoss=str(round(new_sl, p_prec)), tpslMode="Full"
        )
        log.info(f"🛡️ SL Remoto Atualizado: {symbol} -> {new_sl}")
    except Exception as e:
        if "110001" not in str(e): # Ignora erro de posição já fechada
            log.error(f"Erro update SL {symbol}: {e}")

# =========================================================
# 3. AUXILIARES DE DADOS E WEBSOCKET
# =========================================================

def get_market_sentiment():
    """
    Lê os dados de 15m armazenados nas estratégias do BTC e ETH.
    """
    try:
        results = []
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            strat = strategies.get(symbol)
            if strat is None or strat.data_15m is None or len(strat.data_15m) < 20:
                continue
            
            df = strat.data_15m
            ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            
            results.append("UP" if current_price > ema_20 else "DOWN")

        # Lógica do Farol
        if all(r == "UP" for r in results) and len(results) == 2:
            return "BULLISH"
        elif all(r == "DOWN" for r in results) and len(results) == 2:
            return "BEARISH"
        return "NEUTRAL"
            
    except Exception as e:
        log.error(f"Erro no Farol: {e}")
        return "NEUTRAL"

def get_cached_data(force=False):
    global cache_balance, cache_positions
    now = time.time()
    if force or (now - cache_balance['last_update'] > 10):
        try:
            b_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if b_resp['retCode'] == 0:
                coin = b_resp['result']['list'][0]['coin'][0]
                def safe_float(val):
                    try: return float(val) if val and str(val).strip() != "" else 0.0
                    except: return 0.0

                total = safe_float(coin.get('walletBalance'))
                avail = safe_float(coin.get('availableToWithdraw'))
                cache_balance = {"total": total, "avail": avail if avail > 0 else (total * 0.95), "last_update": now}
            
            p_resp = session.get_positions(category="linear", settleCoin="USDT")
            if p_resp['retCode'] == 0:
                active_pos = [p for p in p_resp['result']['list'] if float(p.get('size', 0)) != 0]
                cache_positions = {"data": active_pos, "last_update": now}
                
                # Sincroniza estado das estratégias (limpa se a posição foi fechada manualmente)
                active_symbols = [p['symbol'] for p in active_pos]
                for s in strategies:
                    if s not in active_symbols: strategies[s].is_positioned = False

        except Exception as e:
            log.error(f"Erro cache: {e}")

def check_closed_trades():
    global ULTIMO_ORDER_ID_PROCESSADO
    try:
        # Pega apenas o último trade fechado
        resp = session.get_closed_pnl(category="linear", limit=1)
        
        if resp['retCode'] == 0 and resp['result']['list']:
            last_trade = resp['result']['list'][0]
            order_id = last_trade['orderId'] # ID único do trade
            
            # SÓ ATUALIZA SE FOR UM TRADE NOVO
            if order_id != ULTIMO_ORDER_ID_PROCESSADO:
                pnl = float(last_trade['closedPnl'])
                symbol = last_trade['symbol']
                
                # Atualiza o dashboard de verdade
                risk_mgr.update_dashboard(symbol, pnl)
                
                # Salva o ID para não repetir no próximo loop
                ULTIMO_ORDER_ID_PROCESSADO = order_id
                log.info(f"📊 Novo trade contabilizado: {symbol} PnL: {pnl}")
    except Exception as e:
        log.error(f"Erro ao checar trades fechados: {e}")
    
def sync_historical_pnl(start_date="2026-03-18"):
    try:
        start_ts = int(datetime.datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        log.info(f"🔍 Sincronizando histórico e categorizando desde {start_date}...")

        processed_orders = set()
        total_recuperado = 0
        
        # Resetamos as estatísticas para não duplicar ao reiniciar
        risk_mgr.stats['wins'] = 0
        risk_mgr.stats['losses'] = 0
        risk_mgr.stats['protected'] = 0
        risk_mgr.stats['total_trades'] = 0
        risk_mgr.total_fees = 0.0

        for symbol in SYMBOLS:
            resp = session.get_closed_pnl(category="linear", symbol=symbol, startTime=start_ts, limit=100)
            
            if resp['retCode'] == 0:
                for t in reversed(resp['result']['list']):
                    order_id = t['orderId']
                    
                    if order_id not in processed_orders:
                        pnl_bruto = float(t['closedPnl'])
                        # Taxas aproximadas de abertura e fechamento
                        fees = (float(t['cumEntryValue']) + float(t['cumExitValue'])) * 0.0006
                        pnl_liquido = pnl_bruto - fees
                        
                        # --- LÓGICA DE CATEGORIZAÇÃO RETROATIVA ---
                        risk_mgr.stats['total_trades'] += 1
                        if pnl_liquido > 0:
                            risk_mgr.stats['wins'] += 1
                        elif pnl_liquido > -0.15: # Onde entram os seus -0.01 da AVAX
                            risk_mgr.stats['protected'] = risk_mgr.stats.get('protected', 0) + 1
                        else:
                            risk_mgr.stats['losses'] += 1
                        # ------------------------------------------

                        risk_mgr.stats['pnl_history'][symbol] = risk_mgr.stats['pnl_history'].get(symbol, 0) + pnl_liquido
                        risk_mgr.total_pnl_bruto += pnl_bruto
                        risk_mgr.total_fees += fees
                        
                        processed_orders.add(order_id)
                        total_recuperado += 1
        
        log.info(f"✅ Sincronização concluída: {total_recuperado} trades organizados.")
    except Exception as e:
        log.error(f"❌ Erro na sincronização: {e}")

def prepare_leverage(symbol, leverage_value):
    try:
        session.set_leverage(category="linear", symbol=symbol, buyLeverage=str(leverage_value), sellLeverage=str(leverage_value))
    except Exception as e:
        if "110043" not in str(e): log.error(f"Erro alavancagem {symbol}: {e}")

def sync_open_positions():
    log.info("🔄 Sincronizando posições iniciais...")
    get_cached_data(force=True)
    for p in cache_positions['data']:
        symbol = p['symbol']
        if symbol in strategies:
            strat = strategies[symbol]
            # Adicione o size aqui para a parcial funcionar após restart
            strat.current_qty = abs(float(p.get('size', 0))) 
            strat.sync_position(side=p['side'], entry_price=p['avgPrice'], 
                               sl_price=p['stopLoss'], tp_price=p['takeProfit'])

def process_queue():
    while True:
        message = message_queue.get()
        if message is None: break
        try: handle_signal_logic(message)
        except Exception as e: log.error(f"Erro fila: {e}")
        message_queue.task_done()

def on_message(message):
    if "data" in message:
        if message_queue.qsize() > 50:
            try:
                message_queue.get_nowait()
                message_queue.task_done()
            except: pass
        message_queue.put(message)

def create_and_subscribe_websocket():
    ws_client = get_websocket_session(testnet=IS_TESTNET)
    for symbol in SYMBOLS:
        ws_client.kline_stream(interval=1, symbol=symbol, callback=on_message)
        ws_client.kline_stream(interval=15, symbol=symbol, callback=on_message)
    return ws_client

def check_market_heat():
    """Mostra quais moedas estão esquentando e perto do Filtro Sniper"""
    log.info("🔥 --- TERMÔMETRO DE VOLATILIDADE ---")
    threshold = 0.0012  # Seu filtro atual
    
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        df = strat.data_1m
        
        if df is not None and len(df) >= 20:
            recent = df.tail(20)
            # Cálculo da volatilidade real (corpo das velas)
            volat = (abs(recent['close'] - recent['open']) / recent['open']).mean()
            
            # Cálculo de progresso para o gatilho
            percent_of_threshold = (volat / threshold) * 100
            
            # Status Visual
            if volat >= threshold:
                status = "✅ DISPARADO (Operando)"
            elif percent_of_threshold > 80:
                status = "🟠 QUASE LÁ (Esquentando)"
            else:
                status = "❄️ FRIO (Lateral)"
                
            log.info(f"{symbol:10} | Volat: {volat:.5f} ({percent_of_threshold:5.1f}%) | {status}")
        else:
            log.warning(f"{symbol:10} | ⚠️ Aguardando mais dados...")
    log.info("-------------------------------------")

def start_bot():
    # Adicionamos as globais que estavam faltando para o dashboard funcionar
    global ULTIMO_CHECK_VIVO, SALDO_INICIAL_DIA, ws, cache_balance, message_queue, risk_mgr, ULTIMO_CHECK_CALOR
    
    erros_seguidos = 0
    
    try:
        while True:
            try:
                timestamp_atual = time.time()
                get_cached_data()
                check_closed_trades()
                
                if timestamp_atual - ULTIMO_CHECK_VIVO >= 3600:
                    notifier.send_heartbeat(risk_mgr, cache_balance, message_queue)
                    ULTIMO_CHECK_VIVO = timestamp_atual
                    
                if timestamp_atual - ULTIMO_CHECK_CALOR >= 1800:
                    check_market_heat()
                    ULTIMO_CHECK_CALOR = timestamp_atual

                # Verificação de conexão do WebSocket
                if not ws.is_connected():
                    log.warning("⚠️ WS Offline. Reconectando...")
                    ws = create_and_subscribe_websocket()

                gc.collect() 
                erros_seguidos = 0 
                time.sleep(15) 

            except KeyboardInterrupt: 
                log.info("Parada manual detectada.")
                break
            except Exception as e:
                erros_seguidos += 1
                log.error(f"Erro Loop ({erros_seguidos}/5): {e}")
                time.sleep(5)
                
                if erros_seguidos > 5:
                    raise Exception("Múltiplos erros no loop interno. Reiniciando bot...")

    except Exception as e:
        print(f"❌ Erro Crítico: {e}")
        import sys
        sys.exit(1)
    
    
# =========================================================
# 0. TESTE DE SANIDADE E FUNÇÕES AUXILIARES
# =========================================================    
def debug_sanity_check():
    log.info("🔍 --- TESTE DE SANIDADE DO SISTEMA ---")
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        df = strat.data_1m
        if df is not None and not df.empty:
            has_open = 'open' in df.columns
            last_price = df['close'].iloc[-1]
            # Simula o cálculo da volatilidade
            recent = df.tail(20)
            volat = (abs(recent['close'] - recent['open']) / recent['open']).mean() if has_open else 0
            
            status = "✅ OK" if has_open and volat > 0 else "❌ FALHA"
            log.info(f"Symbol: {symbol} | Open Col: {has_open} | Volat: {volat:.5f} | Status: {status}")
        else:
            log.warning(f"Symbol: {symbol} | ⚠️ Sem dados no DataFrame 1m")
    log.info("🔍 ------------------------------------")

# =========================================================
# 4. START DO BOT (BLOCO FINAL)
# =========================================================

if __name__ == "__main__":
    log.info("📥 Warm-up Inicial...")
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        for tf, tf_id in [("1m", 1), ("15m", 15)]:
            hist = session.get_kline(category="linear", symbol=symbol, interval=tf_id, limit=200)
            if hist['retCode'] == 0:
                candles_raw = hist['result']['list']
                
                # Formatamos os dados corretamente antes de enviar para a Strategy
                formatted_candles = []
                for c in candles_raw:
                    formatted_candles.append({
                        "timestamp": int(c[0]),
                        "open": float(c[1]),   # <--- AGORA O OPEN ESTÁ AQUI
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5])
                    })
                
                # A Bybit manda do mais novo para o antigo, precisamos inverter
                formatted_candles.reverse()
                strat.load_historical_data(tf, formatted_candles)
                
        log.info(f"✅ Pronto: {symbol}")
    
    sync_open_positions()

    worker_thread = Thread(target=process_queue, daemon=True)
    worker_thread.start()

    ws = create_and_subscribe_websocket()
    notifier.send_message("🤖 Bot Ativo - Monitorando sinais...")
    sync_historical_pnl("2026-03-18")
    debug_sanity_check()
    start_bot()