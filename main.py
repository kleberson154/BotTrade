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
    try:
        current_price = float(candle["close"])
        timestamp = int(candle["start"])
    except (ValueError, KeyError):
        return # Ignora se os dados do candle vierem mal formatados

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
        # 1. PROTEÇÃO (Trailing Stop / Break-even)
        # Omitido aqui para brevidade, mantenha sua lógica de proteção se desejar
        
        # 2. VERIFICAÇÃO DE SINAL
        signal, current_atr = strat.check_signal()
        if signal in ["BUY", "SELL"]:
            current_minute = datetime.now().minute
            if hasattr(strat, 'last_signal_min') and strat.last_signal_min == current_minute:
                return 
            
            # --- TRAVAS DE SEGURANÇA PARA BANCA PEQUENA ---
            try:
                # A. Verifica posições abertas
                pos_resp = session.get_positions(category="linear", settleCoin="USDT")
                active_positions = [p for p in pos_resp['result']['list'] if float(p['size'] or 0) != 0]
                
                if len(active_positions) >= risk_mgr.max_positions:
                    return

                # B. Verifica se já está posicionado NESTE símbolo
                if any(p['symbol'] == symbol for p in active_positions):
                    return

                # C. Busca saldo real disponível
                balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                coin_info = balance_resp['result']['list'][0]['coin'][0]
                
                # Usamos float(val or 0) para evitar o erro de string vazia ''
                available_balance = float(coin_info.get('availableToWithdraw') or 0)
                wallet_balance = float(coin_info.get('walletBalance') or 0)

                log.info(f"💰 Saldo Identificado: Total ${wallet_balance:.2f} | Disponível ${available_balance:.2f}")

                if available_balance < 2.0: # Se tiver menos de $2 livre, não opera
                    log.warning(f"⚠️ Saldo insuficiente para {symbol}: ${available_balance}")
                    return

                # --- CÁLCULO DE PARÂMETROS ---
                side = "Buy" if signal == "BUY" else "Sell"
                sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, current_price, current_atr)
                lev, qty = risk_mgr.get_dynamic_risk_params(current_price, sl, wallet_balance)

                # --- EXECUÇÃO ---
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
                    notifier.send_message(f"✅ *Ordem Aberta:* {symbol}\nLado: {side}\nAlav: {lev}x | Qty: {qty_str}")
                else:
                    log.error(f"❌ Erro Bybit ({symbol}): {order['retMsg']}")

            except Exception as e:
                log.error(f"Erro na lógica de execução {symbol}: {e}")
                
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