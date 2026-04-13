import datetime
import sys
import io
import os
import time
import gc
import pandas as pd
from queue import Queue
from threading import Thread

from src.connection import get_websocket_session, get_http_session
from src.strategy import TradingStrategy
from src.risk_manager import RiskManager
from src.execution import ExecutionManager
from src.logger import setup_logger
from src.notifier import TelegramNotifier
from src.market_cycles import MarketCycleAnalyzer

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
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,XRPUSDT,NEARUSDT,LINKUSDT,SUIUSDT,OPUSDT,IRYUSDT,HYPEUSDT,AVAXUSDT,SOLUSDT,ADAUSDT,DOTUSDT,LYNUSDT,TAVEUSDT").split(",")
ULTIMO_CHECK_VIVO = 0 
SALDO_INICIAL_DIA = None
ULTIMO_ORDER_ID_PROCESSADO = None
ULTIMO_CHECK_CALOR = 0
LAST_HOLD_LOG = {}
LAST_REGIME_LOG = 0
REGIME_COLD_THRESHOLD = 0.0010  # ATR% abaixo disso é frio

# --- MARKET CYCLES ANALYZER (NEW) ---
market_cycles = MarketCycleAnalyzer()

# --- CONFIGURAÇÕES VALIDADAS NO BACKTEST (PnL +47.6%) + 8 NOVAS MOEDAS ---
COIN_CONFIGS = {
    "BTCUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "XRPUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "NEARUSDT": {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "LINKUSDT": {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 30, "invert_signal": True, "use_regime_filter": True, "allow_short": False, "signal_check_interval": 6},
    "SUIUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "OPUSDT":   {"atr_multiplier_sl": 2.0, "min_pnl_be": 0.005, "distancia_respiro": 0.018, "min_adx": 32, "invert_signal": False, "use_regime_filter": True, "allow_short": False, "signal_check_interval": 6},
    "IRYUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "HYPEUSDT": {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "AVAXUSDT": {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "SOLUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "ADAUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "DOTUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "LYNUSDT":  {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
    "TAVEUSDT": {"atr_multiplier_sl": 1.8, "min_pnl_be": 0.005, "distancia_respiro": 0.015, "min_adx": 28, "invert_signal": True, "use_regime_filter": True, "signal_check_interval": 6},
}

# --- BEST PERFORMERS ONLY (6 coins: 30.87% WR, +20.27% PnL) ---

notifier = TelegramNotifier()
strategies = {}
for symbol in SYMBOLS:
    strat = TradingStrategy(symbol=symbol, notifier=notifier)
    config = COIN_CONFIGS.get(symbol, {})
    for key, value in config.items():
        setattr(strat, key, value) 
    strategies[symbol] = strat

# --- INICIALIZAÇÃO DE COMPONENTES GLOBAIS ---
log = setup_logger()
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
message_queue = Queue()

MASTERS = ["BTCUSDT"]  # Only master signals from active coins
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

    sentimento = get_market_sentiment()

    if tf_key == "1m":
        current_price = float(candle["close"])
        timestamp_candle = int(candle["start"]) / 60000 # em minutos
        is_confirmado = candle.get("confirm", False)

        # 1. Proteção de Posição Ativa
        if strat.is_positioned:
            status = strat.monitor_protection(current_price)
            if status == "UPDATE_SL":
                update_remote_sl(symbol, strat.sl_price)
            elif status == "PARTIAL_EXIT":
                execute_partial_tp(symbol, strat, current_price)

        # 2. Busca por Entrada (Passando o sentimento e respeitando o intervalo do Backtest)
        elif is_confirmado and symbol in SYMBOLS:
            # Respeita o signal_check_interval definido no COIN_CONFIGS
            interval = getattr(strat, "signal_check_interval", 5)
            if int(timestamp_candle) % interval != 0:
                return

            signal, current_atr = strat.check_signal(market_sentiment=sentimento)

            if signal in ["BUY", "SELL"]:
                log.info(f"🎯 SINAL {signal} em {symbol} | Sentimento: {sentimento}")
                execute_new_trade(symbol, signal, current_price, current_atr)
            else:
                now_ts = time.time()
                last_ts = LAST_HOLD_LOG.get(symbol, 0)
                if now_ts - last_ts >= 300:
                    reason = getattr(strat, "last_hold_reason", "sem motivo detalhado")
                    log.info(f"⏸️ [{symbol}] HOLD | {reason}")
                    LAST_HOLD_LOG[symbol] = now_ts

# =========================================================
# 2. FUNÇÕES DE EXECUÇÃO E API
# =========================================================

def execute_new_trade(symbol, signal, price, atr):
    get_cached_data()
    if len(cache_positions['data']) >= risk_mgr.max_positions: return
    if cache_balance['avail'] < 5.0: return 

    try:
        strat = strategies[symbol]
        side = "Buy" if signal == "BUY" else "Sell"
        
        # 1. Ajusta leverage baseado no regime atual
        regime = strat.current_regime  # Obtém regime da estratégia
        risk_mgr.set_leverage_for_regime(regime)
        
        # 1.5. MARKET CYCLES: Ajusta leverage baseado em dominância BTC
        cycle_adjustment = market_cycles.get_dominance_signal_adjustment()
        market_cycle_mode = cycle_adjustment['risk_mode']
        leverage_factor_cycle = cycle_adjustment['leverage_factor']
        log.info(f"📊 Market Cycle: {market_cycle_mode} | Leverage factor: {leverage_factor_cycle}x")
        
        # 1.6. FIBONACCI CONFIDENCE: Ajusta leverage baseado em proximidade a níveis Fibo
        fibo_confidence_boost = getattr(strat, 'fibo_confidence', 0.0)
        leverage_factor_fibo = 1.0 + fibo_confidence_boost  # Boost ou redução
        log.info(f"📐 Fibonacci Level: {leverage_factor_fibo:.2f}x leverage multiplier")
        
        # 2. Parâmetros de Risco com leverage dinâmico
        base_lev, qty = risk_mgr.get_dynamic_risk_params(price, price * 0.985, cache_balance['total'])
        lev_mult = risk_mgr.get_leverage_multiplier()
        lev = int(base_lev * lev_mult * leverage_factor_cycle * leverage_factor_fibo)  # Aplicar ambos ajustes
        log.info(f"🎯 Leverage: {base_lev} * {lev_mult} * {leverage_factor_cycle} * {leverage_factor_fibo:.2f} = {lev}x")
        
        # SL adaptativo baseado no ATR_MULTIPLIER do backtest
        atr_mult = getattr(strat, "atr_multiplier_sl", 1.8)
        dist_sl = (atr / price) * atr_mult
        sl = price * (1 - dist_sl) if side == "Buy" else price * (1 + dist_sl)
        
        # 3. TP Dinâmico baseado em Regime + Volatilidade + ADX
        # Obter ATR% e ADX da estratégia se disponível
        ind = {}
        try:
            ind = strat.calculate_indicators(strat.data_1m.tail(100), strat.data_15m.tail(250)) if hasattr(strat, 'data_1m') else {}
        except:
            ind = {}
        
        atr_pct = ind.get('atr_pct', 0.0015)  # Default: 0.15%
        adx = ind.get('adx_1m', 22)  # Default: 22
        tp_dinamic = risk_mgr.calculate_dynamic_tp(price, side, atr_pct, adx, regime=regime)
        
        q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))

        prepare_leverage(symbol, lev)
        
        # 4. Envio da Ordem
        order = session.place_order(
            category="linear", symbol=symbol, side=side, orderType="Market",
            qty=qty_str, 
            takeProfit=str(round(tp_dinamic, p_prec)), 
            stopLoss=str(round(sl, p_prec)),
            tpOrderType="Market", slOrderType="Market", tpslMode="Full"
        )

        if order['retCode'] == 0:
            strat.is_positioned = True
            strat.side = signal
            strat.entry_price = price
            strat.sl_price = sl
            strat.current_qty = float(qty)
            strat.partial_taken = False
            
            # 🎯 ESTRATÉGIA 1: Setup SMC com Fibonacci Targets
            try:
                swing_high = ind.get('swing_high', price * 1.02)
                swing_low = ind.get('swing_low', price * 0.98)
                executor.setup_smc_management_with_fibonacci(
                    symbol, signal, price, atr, 
                    swing_high=swing_high, 
                    swing_low=swing_low
                )
            except Exception as e:
                log.warning(f"⚠️ Fibonacci setup falhou para {symbol}: {e}")
                # Fallback: usar setup SMC normal
                executor.setup_smc_management(symbol, signal, price, sl, tp_dinamic * 0.618, tp_dinamic * 0.809, tp_dinamic)
            
            tp_pct = abs((tp_dinamic - price) / price) * 100
            notifier.send_message(f"🚀 *{symbol} {side}* | {lev}x | Qty: {qty_str}\n🛡️ SL: {round(sl, p_prec)} | 🎯 TP: {round(tp_dinamic, p_prec)} (DYN: +{tp_pct:.1f}%)")
            
    except Exception as e:
        log.error(f"Erro abertura {symbol}: {e}")

# ... (Mantenha as demais funções: execute_partial_tp, update_remote_sl, get_market_sentiment, get_cached_data, etc., conforme seu código original)

def execute_partial_tp(symbol, strat, current_price):
    if strat.partial_taken: return
    try:
        log.info(f"💰 Alvo Parcial em {symbol} ({current_price})")
        q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_to_close = strat.current_qty * 0.5
        qty_str = str(int(qty_to_close)) if q_prec == 0 else str(round(qty_to_close, q_prec))
        side_close = "Sell" if strat.side == "BUY" else "Buy"
        res = session.place_order(category="linear", symbol=symbol, side=side_close, orderType="Market", qty=qty_str, reduceOnly=True)
        if res['retCode'] == 0:
            strat.partial_taken = True
            strat.current_qty -= float(qty_str)
            new_sl = strat.entry_price * (1.0005 if strat.side == "BUY" else 0.9995)
            strat.sl_price = new_sl
            update_remote_sl(symbol, new_sl)
            notifier.send_message(f"✅ *{symbol}* Parcial de 50%!\n🛡️ Stop movido para o Zero.")
    except Exception as e:
        log.error(f"Erro na parcial de {symbol}: {e}")

def update_remote_sl(symbol, new_sl):
    try:
        _, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        session.set_trading_stop(category="linear", symbol=symbol, stopLoss=str(round(new_sl, p_prec)), tpslMode="Full")
    except Exception as e:
        if "110001" not in str(e): log.error(f"Erro update SL {symbol}: {e}")

def get_market_sentiment():
    try:
        results = []
        for symbol in ["BTCUSDT", "XRPUSDT"]:  # Updated: use only active coins (BTC + XRP)
            strat = strategies.get(symbol)
            if strat is None or strat.data_15m is None or len(strat.data_15m) < 20: continue
            df = strat.data_15m
            ema_20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
            current_price = df['close'].iloc[-1]
            results.append("UP" if current_price > ema_20 else "DOWN")
        if all(r == "UP" for r in results) and len(results) == 2: return "BULLISH"
        elif all(r == "DOWN" for r in results) and len(results) == 2: return "BEARISH"
        return "NEUTRAL"
    except Exception as e:
        log.error(f"Erro no Farol: {e}"); return "NEUTRAL"

def get_cached_data(force=False):
    global cache_balance, cache_positions
    now = time.time()
    
    # Função interna para evitar o crash com strings vazias
    def safe_float(val):
        try:
            if val is None or str(val).strip() == "":
                return 0.0
            return float(val)
        except:
            return 0.0

    if force or (now - cache_balance['last_update'] > 10):
        try:
            # 1. Busca Saldo
            b_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if b_resp['retCode'] == 0:
                # A estrutura da Bybit pode variar, garantindo acesso seguro:
                list_data = b_resp['result'].get('list', [])
                if list_data:
                    coins = list_data[0].get('coin', [])
                    if coins:
                        coin = coins[0]
                        total = safe_float(coin.get('walletBalance'))
                        avail = safe_float(coin.get('availableToWithdraw'))
                        
                        # Se o disponível vier zerado mas o total existir, assume-se margem livre
                        if avail == 0 and total > 0:
                            avail = total * 0.95 

                        cache_balance = {
                            "total": total, 
                            "avail": avail, 
                            "last_update": now
                        }
            
            # 2. Busca Posições
            p_resp = session.get_positions(category="linear", settleCoin="USDT")
            if p_resp['retCode'] == 0:
                raw_positions = p_resp['result'].get('list', [])
                # Filtra apenas o que tem tamanho real
                active_pos = [p for p in raw_positions if safe_float(p.get('size')) != 0]
                
                cache_positions = {"data": active_pos, "last_update": now}
                
                # 3. Sincroniza estado das instâncias TradingStrategy
                active_symbols = [p['symbol'] for p in active_pos]
                for s in strategies:
                    if s not in active_symbols:
                        strategies[s].is_positioned = False

        except Exception as e:
            log.error(f"Erro ao atualizar cache de dados: {e}")

def check_closed_trades():
    global ULTIMO_ORDER_ID_PROCESSADO
    try:
        resp = session.get_closed_pnl(category="linear", limit=1)
        if resp['retCode'] == 0 and resp['result']['list']:
            last_trade = resp['result']['list'][0]
            order_id = last_trade['orderId']
            if order_id != ULTIMO_ORDER_ID_PROCESSADO:
                pnl = float(last_trade['closedPnl'])
                risk_mgr.update_dashboard(last_trade['symbol'], pnl)
                ULTIMO_ORDER_ID_PROCESSADO = order_id
    except Exception as e: log.error(f"Erro closed trades: {e}")

def sync_historical_pnl(risk_mgr):
    """Sincroniza histórico de PnL desde o reset_timestamp ou 18/03 como fallback."""
    try:
        # Determina a data de início (reset_timestamp ou 18/03)
        if risk_mgr.reset_timestamp:
            start_ts = int(risk_mgr.reset_timestamp.timestamp() * 1000)
            start_date_display = risk_mgr.reset_timestamp.strftime("%Y-%m-%d")
        else:
            start_date_display = "2026-03-18"
            start_ts = int(datetime.datetime.strptime(start_date_display, "%Y-%m-%d").timestamp() * 1000)
        
        processed_orders = set()
        log.info(f"🔄 Sincronizando histórico PnL desde {start_date_display} para {len(SYMBOLS)} moedas ativas: {', '.join(SYMBOLS)}")
        
        for symbol in SYMBOLS:
            resp = session.get_closed_pnl(category="linear", symbol=symbol, startTime=start_ts, limit=100)
            if resp['retCode'] == 0:
                trades_count = 0
                for t in reversed(resp['result']['list']):
                    order_id = t['orderId']
                    if order_id not in processed_orders:
                        pnl_bruto = float(t['closedPnl'])
                        fees = (float(t['cumEntryValue']) + float(t['cumExitValue'])) * 0.0006
                        pnl_liquido = pnl_bruto - fees
                        risk_mgr.stats['total_trades'] += 1
                        if pnl_liquido > 0: risk_mgr.stats['wins'] += 1
                        elif pnl_liquido > -0.15: risk_mgr.stats['protected'] = risk_mgr.stats.get('protected', 0) + 1
                        else: risk_mgr.stats['losses'] += 1
                        risk_mgr.stats['pnl_history'][symbol] = risk_mgr.stats['pnl_history'].get(symbol, 0) + pnl_liquido
                        risk_mgr.total_pnl_bruto += pnl_bruto
                        risk_mgr.total_fees += fees
                        processed_orders.add(order_id)
                        trades_count += 1
                log.info(f"  ✅ {symbol}: {trades_count} trades sincronizados")
        
        if risk_mgr.stats['total_trades'] > 0:
            log.info(f"📊 Total após sincronização: {risk_mgr.stats['total_trades']} trades, WR: {(risk_mgr.stats['wins']/risk_mgr.stats['total_trades']*100):.1f}%")
    except Exception as e: log.error(f"Erro sync pnl: {e}")

def prepare_leverage(symbol, leverage_value):
    try: session.set_leverage(category="linear", symbol=symbol, buyLeverage=str(leverage_value), sellLeverage=str(leverage_value))
    except Exception as e:
        if "110043" not in str(e): log.error(f"Erro alavancagem {symbol}: {e}")

def sync_open_positions():
    get_cached_data(force=True)
    for p in cache_positions['data']:
        symbol = p['symbol']
        if symbol in strategies:
            strat = strategies[symbol]
            strat.current_qty = abs(float(p.get('size', 0))) 
            strat.sync_position(side=p['side'], entry_price=p['avgPrice'], sl_price=p['stopLoss'], tp_price=p['takeProfit'])

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
            try: message_queue.get_nowait(); message_queue.task_done()
            except: pass
        message_queue.put(message)

def create_and_subscribe_websocket():
    ws_client = get_websocket_session(testnet=IS_TESTNET)
    for symbol in SYMBOLS:
        ws_client.kline_stream(interval=1, symbol=symbol, callback=on_message)
        ws_client.kline_stream(interval=15, symbol=symbol, callback=on_message)
    return ws_client

def check_market_heat():
    global ULTIMO_CHECK_CALOR, LAST_REGIME_LOG
    log.info("🔥 --- TERMÔMETRO DE VOLATILIDADE ---")
    
    num_cold = 0
    num_lateral = 0
    num_normal = 0
    num_hot = 0
    
    for symbol in SYMBOLS:
        strat = strategies.get(symbol)
        if not strat: continue
        df = strat.data_1m
        if df is not None and len(df) >= 30:
            threshold = getattr(strat, "min_volatilidade_pct", 0.0012)
            recent = df.tail(30)
            tr = pd.concat([
                recent['high'] - recent['low'],
                (recent['high'] - recent['close'].shift()).abs(),
                (recent['low'] - recent['close'].shift()).abs()
            ], axis=1).max(axis=1)
            atr_pct = tr.rolling(14).mean().iloc[-1] / recent['close'].iloc[-1]
            if pd.isna(atr_pct):
                continue
            pct = (atr_pct / threshold) * 100 if threshold > 0 else 0
            regime = strat.current_regime
            
            if regime == "COLD":
                num_cold += 1
                status = "🧊 FRIO"
            elif regime == "LATERAL":
                num_lateral += 1
                status = "〰️ LATERAL"
            elif regime == "HOT":
                num_hot += 1
                status = "🔥 QUENTE"
            else:
                num_normal += 1
                status = "✅ NORMAL"
            
            log.info(f"{symbol:10} | ATR%: {atr_pct:.5f} ({pct:5.1f}%) | {status}")
    
    log.info("-------------------------------------")
    now_ts = time.time()
    if now_ts - LAST_REGIME_LOG >= 600:  # 10 minutos
        total, wins, prot, wr, sr, pnl_net = risk_mgr.get_performance_stats()
        log.info(f"📊 REGIME SUMMARY | Cold:{num_cold} Lateral:{num_lateral} Normal:{num_normal} Hot:{num_hot}")
        log.info(f"💰 PERFORMANCE | WR:{wr:.1f}% | Trades:{total} | PnL:{pnl_net:+.2f}")
        LAST_REGIME_LOG = now_ts

def start_bot():
    global ULTIMO_CHECK_VIVO, ws, cache_balance, message_queue, risk_mgr, ULTIMO_CHECK_CALOR
    erros_seguidos = 0
    while True:
        try:
            timestamp_atual = time.time()
            get_cached_data()
            check_closed_trades()
            if timestamp_atual - ULTIMO_CHECK_VIVO >= 3600 * 6:
                notifier.send_heartbeat(risk_mgr, cache_balance, message_queue)
                ULTIMO_CHECK_VIVO = timestamp_atual
            if timestamp_atual - ULTIMO_CHECK_CALOR >= 1800:
                check_market_heat()
                ULTIMO_CHECK_CALOR = timestamp_atual
            if not ws.is_connected(): ws = create_and_subscribe_websocket()
            gc.collect(); erros_seguidos = 0; time.sleep(15)
        except KeyboardInterrupt: break
        except Exception as e:
            erros_seguidos += 1
            log.error(f"Erro Loop ({erros_seguidos}/5): {e}"); time.sleep(5)
            if erros_seguidos > 5: sys.exit(1)

def debug_sanity_check():
    log.info("🔍 --- TESTE DE SANIDADE ---")
    for symbol in SYMBOLS:
        strat = strategies.get(symbol)
        if not strat: continue
        log.info(f"{symbol}: Invert={getattr(strat, 'invert_signal', False)} | ATR={getattr(strat, 'atr_multiplier_sl', 1.8)}")

if __name__ == "__main__":
    # Resetar stats de performance (WR check removido)
    risk_mgr.stats = {
        'wins': 0,
        'losses': 0,
        'protected': 0,
        'total_trades': 0,
        'pnl_history': {}
    }
    log.info("📥 Warm-up Inicial...")
    log.info("✅ Stats resetados - WR check desativado")
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        for tf, tf_id in [("1m", 1), ("15m", 15)]:
            hist = session.get_kline(category="linear", symbol=symbol, interval=tf_id, limit=200)
            if hist['retCode'] == 0:
                formatted = [{"timestamp": int(c[0]), "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in hist['result']['list']]
                formatted.reverse()
                strat.load_historical_data(tf, formatted)
    sync_open_positions()
    Thread(target=process_queue, daemon=True).start()
    ws = create_and_subscribe_websocket()
    sync_historical_pnl(risk_mgr)
    debug_sanity_check()
    start_bot()