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

# --- CONFIGURAÇÕES DE RELATÓRIO ---
ULTIMO_CHECK_VIVO = 0 

# --- INICIALIZAÇÃO DE COMPONENTES ---
log = setup_logger()
strategies = {symbol: TradingStrategy(symbol=symbol) for symbol in SYMBOLS}
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
notifier = TelegramNotifier()
message_queue = Queue()

LAST_ORDER_TIME = {symbol: None for symbol in SYMBOLS}
SALDO_INICIAL_DIA = None
ULTIMO_RELATORIO_DATA = None

def prepare_leverage(symbol, leverage_value):
    """Seta a alavancagem na Bybit antes da operação"""
    try:
        session.set_leverage(
            category="linear",
            symbol=symbol,
            buyLeverage=str(leverage_value),
            sellLeverage=str(leverage_value)
        )
        log.info(f"⚙️ Alavancagem ajustada: {symbol} @ {leverage_value}x")
    except Exception as e:
        if "110043" not in str(e): # Ignora erro se já estiver na alavancagem correta
            log.error(f"❌ Erro alavancagem {symbol}: {e}")

def handle_signal_logic(message):
    topic = message.get("topic", "")
    parts = topic.split('.')
    timeframe = parts[1] 
    symbol = parts[-1]
    
    candle = message["data"][0]
    current_price = float(candle["close"])
    timestamp = int(candle["start"])
    
    if int(time.time()) % 60 == 0: 
        log.debug(f"🕒 [WATCH] {symbol}: {current_price}")
    
    strat = strategies.get(symbol)
    if not strat: return

    tf_key = "1m" if timeframe == "1" else "15m"
    dados_candle = {
        "close": current_price,
        "high": float(candle["high"]),   
        "low": float(candle["low"]),     
        "timestamp": timestamp
    }
    strat.add_new_candle(tf_key, dados_candle)
    
    if tf_key == "1m":
        # 1. PROTEÇÃO DE POSIÇÕES EXISTENTES
        try:
            positions = session.get_positions(category="linear", symbol=symbol)
            for pos in positions['result']['list']:
                size = float(pos.get('size', 0))
                if size != 0:
                    entry_price = float(pos.get('avgPrice'))
                    side_pos = pos.get('side')
                    current_sl = float(pos.get('stopLoss', 0))
                    
                    atr_now = strat.calculate_atr(strat.data_1m, 14).iloc[-1]
                    trailing_dist = atr_now * 1.5 
                    p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))[1]

                    if side_pos == "Buy":
                        if current_price >= entry_price * 1.015 and current_sl < entry_price:
                            new_sl = entry_price + (entry_price * 0.001)
                            executor.update_stop_loss(symbol, round(new_sl, p_prec))
                            notifier.send_message(f"🛡️ *Break-even:* {symbol}")
                    elif side_pos == "Sell":
                        if current_price <= entry_price * 0.985 and current_sl > entry_price:
                            new_sl = entry_price - (entry_price * 0.001)
                            executor.update_stop_loss(symbol, round(new_sl, p_prec))
                            notifier.send_message(f"🛡️ *Break-even:* {symbol}")
        except Exception as e:
            log.error(f"Erro na proteção de {symbol}: {e}")

        # 2. VERIFICAÇÃO DE SINAL
        signal, current_atr = strat.check_signal()
        if signal in ["BUY", "SELL"]:
            # Trava de 1 sinal por minuto
            current_minute = datetime.now().minute
            if hasattr(strat, 'last_signal_min') and strat.last_signal_min == current_minute:
                return 
            strat.last_signal_min = current_minute
            
            side = "Buy" if signal == "BUY" else "Sell"
            
            if not executor.has_open_position(symbol):
                # Verifica limites de conta
                pos_resp = session.get_positions(category="linear", settleCoin="USDT")
                active_positions = [p for p in pos_resp['result']['list'] if float(p['size']) != 0]

                if len(active_positions) >= 3:
                    log.warning(f"⚠️ Limite de 3 posições atingido. Ignorando {symbol}")
                    return

                # Busca Saldo para Risco Dinâmico
                balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                balance = float(balance_resp['result']['list'][0]['coin'][0]['walletBalance'])
                
                # --- CÁLCULO DINÂMICO ---
                # 1. Calcula SL e TP adaptativos primeiro
                sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, current_price, current_atr)
                
                # 2. Calcula Alavancagem e Qty baseados no SL
                # Nota: Use 0.02 para 2% de risco por trade
                lev, qty = risk_mgr.get_dynamic_risk_params(current_price, sl, balance, risk_pct=0.02)
                
                # 3. Ajuste de Alavancagem na Corretora
                prepare_leverage(symbol, lev)
                
                # 4. Execução Market
                p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))[1] # Precisão de preço
                q_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))[0] # Precisão de quantidade

                if qty > 0:
                    try:
                        order = session.place_order(
                            category="linear",
                            symbol=symbol,
                            side=side,
                            orderType="Market",
                            qty=str(round(qty, q_prec)),
                            takeProfit=str(round(tp, p_prec)),
                            stopLoss=str(round(sl, p_prec)),
                            tpOrderType="Market",
                            slOrderType="Market",
                            tpslMode="Full"
                        )
                        if order['retCode'] == 0:
                            LAST_ORDER_TIME[symbol] = time.time()
                            notifier.send_message(
                                f"🚀 *Execução Market: {symbol}*\n"
                                f"Lado: {side} | Alav: {lev}x\n"
                                f"Preço: {current_price}\n"
                                f"SL: {sl} | TP: {tp}"
                            )
                        else:
                            log.error(f"❌ Falha Bybit: {order['retMsg']}")
                    except Exception as e:
                        log.error(f"Erro ao abrir ordem market: {e}")

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
        message_queue.put(message)

def subscribe_market_streams(ws_client):
    for symbol in SYMBOLS:
        ws_client.kline_stream(interval=1, symbol=symbol, callback=on_message)
        ws_client.kline_stream(interval=15, symbol=symbol, callback=on_message)

def create_and_subscribe_websocket():
    ws_client = get_websocket_session(testnet=IS_TESTNET)
    subscribe_market_streams(ws_client)
    return ws_client

# --- INICIALIZAÇÃO ---
print("📥 Warm-up...")
for symbol in SYMBOLS:
    strat = strategies[symbol]
    for tf, tf_id in [("1m", 1), ("15m", 15)]:
        hist = session.get_kline(category="linear", symbol=symbol, interval=tf_id, limit=200)
        if hist['retCode'] == 0:
            candles = hist['result']['list']
            candles.reverse()
            strat.load_historical_data(tf, candles)
    print(f"✅ Pronto: {symbol}")

worker_thread = Thread(target=process_queue, daemon=True)
worker_thread.start()

ws = create_and_subscribe_websocket()

while True:
    try:
        agora = datetime.now(fuso_brasilia)
        timestamp_atual = time.time()
        
        # HEARTBEAT 30 MIN
        if timestamp_atual - ULTIMO_CHECK_VIVO >= 1800:
            try:
                balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                if balance_resp['retCode'] == 0:
                    coin_data = balance_resp['result']['list'][0]['coin'][0]
                    saldo_total = float(coin_data['walletBalance'])
                    if SALDO_INICIAL_DIA is None: SALDO_INICIAL_DIA = saldo_total
                    pnl_dia = saldo_total - SALDO_INICIAL_DIA
                    
                    msg = (
                        f"🤖 *Bot Heartbeat (30 min)*\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"💰 Saldo: ${saldo_total:.2f} | PnL: ${pnl_dia:.2f}\n"
                        f"📡 Fila: {message_queue.qsize()} msgs"
                    )
                    notifier.send_message(msg)
                    ULTIMO_CHECK_VIVO = timestamp_atual
            except Exception as e:
                log.error(f"Erro heartbeat: {e}")
        
        # MONITOR DE CONEXÃO
        if not ws.is_connected():
            log.warning("⚠️ WS Offline. Reconectando...")
            ws = create_and_subscribe_websocket()
            
        time.sleep(10)
        
    except KeyboardInterrupt: break
    except Exception as e:
        log.error(f"Erro Loop: {e}")
        time.sleep(5)
    finally:
        gc.collect()