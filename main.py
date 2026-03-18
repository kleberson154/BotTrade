import sys
import io
import os
import time
import gc
from datetime import timezone, timedelta
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
    
fuso_brasilia = timezone(timedelta(hours=-3))
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

# --- INICIALIZAÇÃO DE COMPONENTES GLOBAIS ---
notifier = TelegramNotifier()
log = setup_logger()
strategies = {symbol: TradingStrategy(symbol=symbol, notifier=notifier) for symbol in SYMBOLS}
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
message_queue = Queue()

cache_balance = {"total": 0, "avail": 0, "last_update": 0}
cache_positions = {"data": [], "last_update": 0}

# =========================================================
# 1. LÓGICA PRINCIPAL DE SINAIS E ESTRATÉGIA
# =========================================================

def handle_signal_logic(message):
    """Processa dados do WebSocket e decide entradas/saídas"""
    if "data" not in message: return
    
    topic = message.get("topic", "")
    parts = topic.split('.')
    timeframe = parts[1] 
    symbol = parts[-1]
    
    candle = message["data"][0]
    current_price = float(candle["close"])
    strat = strategies.get(symbol)
    if not strat: return

    tf_key = "1m" if timeframe == "1" else "15m"
    strat.add_new_candle(tf_key, {
        "close": current_price,
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "timestamp": int(candle["start"]),
        "volume": float(candle["volume"])
    })
    
    if tf_key == "1m":
        # --- A) MONITORAMENTO DE POSIÇÃO ATIVA ---
        if strat.is_positioned:
            status = strat.monitor_protection(current_price)
            
            if status == "UPDATE_SL":
                update_remote_sl(symbol, strat.sl_price)
            elif status == "PARTIAL_EXIT":
                execute_partial_tp(symbol, strat, current_price)
        
        # --- B) BUSCA POR NOVOS SINAIS ---
        else:
            signal, current_atr = strat.check_signal()
            if signal in ["BUY", "SELL"]:
                execute_new_trade(symbol, signal, current_price, current_atr)

# =========================================================
# 2. FUNÇÕES DE EXECUÇÃO E API
# =========================================================

def execute_new_trade(symbol, signal, price, atr):
    """Abre nova operação com gestão de risco e trava anti-liquidação"""
    get_cached_data() 
    if len(cache_positions['data']) >= risk_mgr.max_positions: return
    if cache_balance['avail'] < 2.0: return

    try:
        side = "Buy" if signal == "BUY" else "Sell"
        # Calcula alavancagem primeiro (para blindar o SL contra liquidação)
        lev, qty = risk_mgr.get_dynamic_risk_params(price, price * 0.985, cache_balance['total'])
        sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, price, atr, lev)
        
        q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))

        prepare_leverage(symbol, lev)
        
        order = session.place_order(
            category="linear", symbol=symbol, side=side, orderType="Market",
            qty=qty_str, takeProfit=str(round(tp, p_prec)), stopLoss=str(round(sl, p_prec)),
            tpOrderType="Market", slOrderType="Market", tpslMode="Full"
        )

        if order['retCode'] == 0:
            strat = strategies[symbol]
            strat.is_positioned = True
            strat.side = signal
            strat.entry_price = price
            strat.sl_price = sl
            strat.partial_taken = False
            notifier.send_message(f"🚀 *Trade Aberto:* {symbol}\nLado: {side} | Alav: {lev}x\nQty: {qty_str}")
    except Exception as e:
        log.error(f"Erro abertura {symbol}: {e}")

def execute_partial_tp(symbol, strat, current_price):
    """Executa a venda de 50% da posição para garantir lucro"""
    try:
        pos_resp = session.get_positions(category="linear", symbol=symbol)
        if pos_resp['retCode'] == 0 and pos_resp['result']['list']:
            pos = pos_resp['result']['list'][0]
            current_qty = float(pos.get('size', 0))
            if current_qty > 0:
                q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
                qty_to_close = str(round(current_qty / 2, q_prec))
                
                side_exit = "Sell" if strat.side == "BUY" else "Buy"
                session.place_order(
                    category="linear", symbol=symbol, side=side_exit,
                    orderType="Market", qty=qty_to_close, reduceOnly=True
                )
                strat.partial_taken = True
                notifier.send_message(f"💰 *Partial TP:* {symbol} (50% fechado)")
                
                pnl_estimado = (abs(strat.entry_price - current_price) / strat.entry_price) * (float(qty_to_close) * strat.entry_price)
                risk_mgr.update_dashboard(symbol, pnl_estimado)
    except Exception as e:
        log.error(f"Erro parcial {symbol}: {e}")

def update_remote_sl(symbol, new_sl):
    try:
        _, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        session.set_trading_stop(
            category="linear", symbol=symbol,
            stopLoss=str(round(new_sl, p_prec)), tpslMode="Full"
        )
        log.info(f"🛡️ SL Atualizado ({symbol}): {new_sl}")
    except Exception as e:
        log.error(f"Erro ao atualizar Stop: {e}")

# =========================================================
# 3. AUXILIARES DE DADOS E WEBSOCKET
# =========================================================

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
            strategies[symbol].sync_position(side=p['side'], entry_price=p['avgPrice'], sl_price=p['stopLoss'], tp_price=p['takeProfit'])

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
                candles = hist['result']['list']
                candles.reverse()
                strat.load_historical_data(tf, candles)
        log.info(f"✅ Pronto: {symbol}")
    
    sync_open_positions()

    worker_thread = Thread(target=process_queue, daemon=True)
    worker_thread.start()

    ws = create_and_subscribe_websocket()
    notifier.send_message("🤖 Bot Ativo - Monitorando sinais...")

    while True:
        try:
            timestamp_atual = time.time()
            get_cached_data()
            check_closed_trades()
            
            # Heartbeat a cada 15 min (900 seg)
            if timestamp_atual - ULTIMO_CHECK_VIVO >= 900:
                if SALDO_INICIAL_DIA is None: SALDO_INICIAL_DIA = cache_balance['total']
                pnl_dia = risk_mgr.get_total_pnl()
                status_fila = "⚠️ ATRASADO" if message_queue.qsize() > 50 else "Normal"
                emoji_pnl = "📈" if pnl_dia >= 0 else "📉"
                
                notifier.send_message(
                    f"🤖 *Heartbeat*\n"
                    f"💰 Saldo: ${cache_balance['total']:.2f}\n"
                    f"{emoji_pnl} PnL Dia: ${pnl_dia:.2f}\n"
                    f"📡 Fila: {message_queue.qsize()} ({status_fila})"
                )
                ULTIMO_CHECK_VIVO = timestamp_atual
            
            if not ws.is_connected():
                log.warning("⚠️ WS Offline. Reconectando...")
                ws = create_and_subscribe_websocket()
                
            gc.collect() # Limpeza de lixo na memória da Oracle
            time.sleep(15) 
            
        except KeyboardInterrupt: break
        except Exception as e:
            log.error(f"Erro Loop: {e}")
            time.sleep(5)