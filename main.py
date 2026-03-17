import sys
import io
import os
import time
import gc
from datetime import datetime, timezone, timedelta
from queue import Queue
from threading import Thread

from src.connection import get_websocket_session, get_http_session
from src.strategy import TradingStrategy
from src.risk_manager import RiskManager
from src.execution import ExecutionManager
from src.logger import setup_logger
from src.notifier import TelegramNotifier

from dotenv import load_dotenv

# Garante que o terminal aceite UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    
fuso_brasilia = timezone(timedelta(hours=-3))
load_dotenv()

# --- CONFIGURAÇÕES ---
API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
_mode = os.getenv("BYBIT_MODE", "demo").lower()
IS_TESTNET = _mode == "testnet"
IS_DEMO = _mode == "demo"
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT").split(",")

# --- INICIALIZAÇÃO DE COMPONENTES ---
log = setup_logger()
strategies = {symbol: TradingStrategy(symbol=symbol) for symbol in SYMBOLS}
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
notifier = TelegramNotifier()
message_queue = Queue()

# --- GESTÃO DE CACHE (CRÍTICO PARA PERFORMANCE) ---
cache_balance = {"total": 0, "avail": 0, "last_update": 0}
cache_positions = {"data": [], "last_update": 0}
ULTIMO_CHECK_VIVO = 0 
SALDO_INICIAL_DIA = None

notifier.send_message("🤖 Bot Ativo - Monitorando sinais e posições...")

def get_cached_data(force=False):
    """Atualiza saldo e posições com tratamento para strings vazias"""
    global cache_balance, cache_positions
    now = time.time()
    
    if force or (now - cache_balance['last_update'] > 10):
        try:
            # 1. Busca Saldo
            b_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            if b_resp['retCode'] == 0:
                coin = b_resp['result']['list'][0]['coin'][0]
                
                # Tratamento seguro para conversão de string/None para float
                def safe_float(val):
                    try:
                        return float(val) if val and str(val).strip() != "" else 0.0
                    except:
                        return 0.0

                total = safe_float(coin.get('walletBalance'))
                avail = safe_float(coin.get('availableToWithdraw'))
                
                # Correção para cache da conta Demo
                calc_avail = avail if avail > 0 else (total * 0.95)
                
                cache_balance = {
                    "total": total,
                    "avail": calc_avail,
                    "last_update": now
                }
            
            # 2. Busca Posições
            p_resp = session.get_positions(category="linear", settleCoin="USDT")
            if p_resp['retCode'] == 0:
                # Filtra apenas posições que realmente têm tamanho (size)
                active_pos = []
                for p in p_resp['result']['list']:
                    p_size = safe_float(p.get('size'))
                    if p_size != 0:
                        active_pos.append(p)

                cache_positions = {
                    "data": active_pos,
                    "last_update": now
                }
                
                # Sincroniza estado das estratégias
                active_symbols = [p['symbol'] for p in active_pos]
                for s in strategies:
                    if s not in active_symbols:
                        strategies[s].is_positioned = False

        except Exception as e:
            log.error(f"Erro ao atualizar cache: {e}")

def prepare_leverage(symbol, leverage_value):
    try:
        session.set_leverage(
            category="linear", symbol=symbol,
            buyLeverage=str(leverage_value), sellLeverage=str(leverage_value)
        )
        log.info(f"⚙️ Alavancagem ajustada: {symbol} @ {leverage_value}x")
    except Exception as e:
        if "110043" not in str(e): 
            log.error(f"❌ Erro alavancagem {symbol}: {e}")
            
def sync_open_positions():
    log.info("🔄 Sincronizando posições iniciais...")
    get_cached_data(force=True)
    for p in cache_positions['data']:
        symbol = p['symbol']
        if symbol in strategies:
            strat = strategies[symbol]
            strat.sync_position(
                side=p['side'], entry_price=p['avgPrice'],
                sl_price=p['stopLoss'], tp_price=p['takeProfit']
            )
            log.info(f"✅ Sincronizado: {symbol} | SL: {p['stopLoss']}")

def handle_signal_logic(message):
    if "data" not in message: return
    
    topic = message.get("topic", "")
    parts = topic.split('.')
    timeframe = parts[1] 
    symbol = parts[-1]
    now_ts = time.time()
    
    candle = message["data"][0]
    current_price = float(candle["close"])
    strat = strategies.get(symbol)
    if not strat: return

    tf_key = "1m" if timeframe == "1" else "15m"
    strat.add_new_candle(tf_key, {
        "close": current_price,
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "timestamp": int(candle["start"])
    })
    
    if tf_key == "1m":
        # 1. PROTEÇÃO (Usa dados locais, sem chamar API se não mudar nada)
        if strat.is_positioned:
            if strat.monitor_protection(current_price) == "UPDATE_SL":
                try:
                    _, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
                    session.set_trading_stop(
                        category="linear", symbol=symbol,
                        stopLoss=str(round(strat.sl_price, p_prec)), tpslMode="Full"
                    )
                    notifier.send_message(f"🛡️ SL Atualizado ({symbol}) - SL: {strat.sl_price}")
                except Exception as e:
                    log.error(f"Erro ao atualizar Stop: {e}")
        
        # 2. VERIFICAÇÃO DE SINAL
        signal, current_atr = strat.check_signal()
        if signal in ["BUY", "SELL"]:
            current_minute = datetime.now().minute
            if hasattr(strat, 'last_signal_min') and strat.last_signal_min == current_minute:
                return 

            # Atualiza cache antes de decidir a entrada
            get_cached_data()

            # TRAVAS
            if len(cache_positions['data']) >= risk_mgr.max_positions: return
            if any(p['symbol'] == symbol for p in cache_positions['data']): return
            if cache_balance['avail'] < 1.0: return

            # EXECUÇÃO
            try:
                side = "Buy" if signal == "BUY" else "Sell"
                sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, current_price, current_atr)
                lev, qty = risk_mgr.get_dynamic_risk_params(current_price, sl, cache_balance['total'])

                q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
                qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))
                if float(qty_str) <= 0: return

                prepare_leverage(symbol, lev)
                
                order = session.place_order(
                    category="linear", symbol=symbol, side=side, orderType="Market",
                    qty=qty_str, takeProfit=str(round(tp, p_prec)), stopLoss=str(round(sl, p_prec)),
                    tpOrderType="Market", slOrderType="Market", tpslMode="Full"
                )

                if order['retCode'] == 0:
                    strat.last_signal_min = current_minute
                    strat.is_positioned = True
                    strat.side = signal
                    strat.entry_price = current_price
                    strat.sl_price = sl
                    strat.be_activated = False 
                    notifier.send_message(f"✅ *Ordem Aberta:* {symbol}\nLado: {side}\nAlav: {lev}x")
                    get_cached_data(force=True) # Força atualização após abrir
                else:
                    log.error(f"❌ Erro Bybit ({symbol}): {order['retMsg']}")
            except Exception as e:
                log.error(f"Erro na execução {symbol}: {e}")

def process_queue():
    while True:
        message = message_queue.get()
        if message is None: break
        try:
            handle_signal_logic(message)
        except Exception as e:
            log.error(f"Erro processamento fila: {e}")
        message_queue.task_done()

def on_message(message):
    if "data" in message:
        # Se a fila passar de 50 mensagens, removemos a mais antiga antes de por a nova
        # Isso garante que o bot nunca opere com preço "atrasado"
        if message_queue.qsize() > 50:
            try:
                message_queue.get_nowait()
                message_queue.task_done()
            except:
                pass
        message_queue.put(message)

def subscribe_market_streams(ws_client):
    for symbol in SYMBOLS:
        ws_client.kline_stream(interval=1, symbol=symbol, callback=on_message)
        ws_client.kline_stream(interval=15, symbol=symbol, callback=on_message)

def create_and_subscribe_websocket():
    ws_client = get_websocket_session(testnet=IS_TESTNET)
    subscribe_market_streams(ws_client)
    return ws_client

# --- START ---
log.info("📥 Warm-up...")
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

while True:
    try:
        timestamp_atual = time.time()
        
        # HEARTBEAT & CACHE REFRESH (30 seg para cache, 30 min para telegram)
        get_cached_data()

        if timestamp_atual - ULTIMO_CHECK_VIVO >= 900:
            if SALDO_INICIAL_DIA is None: SALDO_INICIAL_DIA = cache_balance['total']
            pnl_dia = cache_balance['total'] - SALDO_INICIAL_DIA
            
            status_fila = "⚠️ ATRASADO" if message_queue.qsize() > 50 else "Normal"
            msg = (
                f"🤖 *Bot Heartbeat*\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💰 Saldo: ${cache_balance['total']:.2f} | PnL: ${pnl_dia:.2f}\n"
                f"📡 Fila: {message_queue.qsize()} msgs ({status_fila})"
            )
            notifier.send_message(msg)
            ULTIMO_CHECK_VIVO = timestamp_atual
        
        if not ws.is_connected():
            log.warning("⚠️ WS Offline. Reconectando...")
            ws = create_and_subscribe_websocket()
            
        time.sleep(10)
        
    except KeyboardInterrupt: break
    except Exception as e:
        log.error(f"Erro Loop: {e}")
        time.sleep(5)