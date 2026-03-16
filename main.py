import time
import datetime
from src.connection import get_websocket_session, get_http_session
from src.strategy import TradingStrategy
from src.risk_manager import RiskManager
from src.execution import ExecutionManager
from src.logger import setup_logger
from src.notifier import TelegramNotifier

import sys
import io
import os
from dotenv import load_dotenv

# Garante que o terminal aceite UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY", "")
API_SECRET = os.getenv("BYBIT_API_SECRET", "")
LEVERAGE = int(os.getenv("LEVERAGE", "5"))

_mode = os.getenv("BYBIT_MODE", "demo").lower()
IS_TESTNET = _mode == "testnet"
IS_DEMO = _mode == "demo"

SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT").split(",")
WS_RECONNECT_BASE_SECONDS = int(os.getenv("WS_RECONNECT_BASE_SECONDS", "5"))
WS_RECONNECT_MAX_SECONDS = int(os.getenv("WS_RECONNECT_MAX_SECONDS", "60"))

SALDO_INICIAL_DIA = None
ULTIMO_RELATORIO_DATA = None

# Dicionário para rastrear o tempo da última ordem por símbolo
LAST_ORDER_TIME = {symbol: None for symbol in SYMBOLS}
WS_RECONNECT_ATTEMPTS = 0
WS_LAST_RECONNECT_TS = 0

log = setup_logger()
strategies = {symbol: TradingStrategy(symbol=symbol) for symbol in SYMBOLS}
risk_mgr = RiskManager()
session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
executor = ExecutionManager(session)
notifier = TelegramNotifier()

notifier.send_message("🤖 *Bot Online!* \nSincronizando dados históricos...")

def on_message(message):
    topic = message.get("topic", "")
  
    if "data" in message:
        parts = topic.split('.')
        timeframe = parts[1] 
        symbol = parts[-1]
        
        candle = message["data"][0]
        current_price = float(candle["close"])
        timestamp = int(candle["start"])
        
        strat = strategies.get(symbol)
        if not strat: return

        # Atualiza dados do candle
        tf_key = "1m" if timeframe == "1" else "15m"
        dados_candle = {
            "close": current_price,
            "high": float(candle["high"]),   
            "low": float(candle["low"]),     
            "timestamp": timestamp
        }
        strat.add_new_candle(tf_key, dados_candle)
        
        # 3. LÓGICA DE PROTEÇÃO: BREAK-EVEN + TRAILING STOP (No 1m)
        if tf_key == "1m":
            positions = session.get_positions(category="linear", symbol=symbol)
            for pos in positions['result']['list']:
                size = float(pos.get('size', 0))
                if size != 0:
                    entry_price = float(pos.get('avgPrice'))
                    side_pos = pos.get('side')
                    current_sl = float(pos.get('stopLoss', 0))
                    
                    # Cálculo de volatilidade para o Trailing
                    # O respiro é de 1.5x o ATR atual
                    atr_now = strat.calculate_atr(strat.data_1m, 14).iloc[-1]
                    trailing_dist = atr_now * 1.5 
                    p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))[1]

                    if side_pos == "Buy":
                        # Break-even
                        if current_price >= entry_price * 1.015 and current_sl < entry_price:
                            new_sl = entry_price + (entry_price * 0.001)
                            executor.update_stop_loss(symbol, round(new_sl, p_prec))
                            notifier.send_message(f"🛡️ *Break-even:* {symbol}")

                        # Trailing Stop
                        elif current_price > entry_price * 1.025:
                            potential_sl = current_price - trailing_dist
                            if potential_sl > current_sl + (current_price * 0.001):
                                executor.update_stop_loss(symbol, round(potential_sl, p_prec))
                                log.info(f"📈 Trailing {symbol}: {round(potential_sl, p_prec)}")

                    elif side_pos == "Sell":
                        # Break-even
                        if current_price <= entry_price * 0.985 and current_sl > entry_price:
                            new_sl = entry_price - (entry_price * 0.001)
                            executor.update_stop_loss(symbol, round(new_sl, p_prec))
                            notifier.send_message(f"🛡️ *Break-even:* {symbol}")

                        # Trailing Stop
                        elif current_price < entry_price * 0.975:
                            potential_sl = current_price + trailing_dist
                            if potential_sl < current_sl - (current_price * 0.001):
                                executor.update_stop_loss(symbol, round(potential_sl, p_prec))

            # 4. VERIFICAÇÃO DE SINAL (Apenas no 1m)
            signal, current_atr = strat.check_signal()
            
            if signal in ["BUY", "SELL"]:
                side = "Buy" if signal == "BUY" else "Sell"
                
                if not executor.has_open_position(symbol):
                    # Trava de ativos simultâneos
                    pos_resp = session.get_positions(category="linear", settleCoin="USDT")
                    active_positions = [p for p in pos_resp['result']['list'] if float(p['size']) != 0]

                    if len(active_positions) >= 3:
                        log.warning(f"⚠️ Limite de 3 ativos atingido. Ignorando {symbol}")
                        return

                    # Execução
                    balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                    balance = float(balance_resp['result']['list'][0]['coin'][0]['walletBalance'])
                    
                    qty = risk_mgr.calculate_position_size(symbol, balance, current_price, leverage=LEVERAGE)
                    sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, current_price, current_atr)
                    
                    try:
                        order = session.place_order(
                            category="linear", symbol=symbol, side=side, orderType="Limit",
                            price=str(current_price), qty=str(qty), takeProfit=str(tp), stopLoss=str(sl),
                            tpOrderType="Market", slOrderType="Market", timeInForce="PostOnly"
                        )
                        if order['retCode'] == 0:
                            LAST_ORDER_TIME[symbol] = time.time()
                            notifier.send_message(f"✅ *Limit:* {symbol}\nLado: {side}\nPreço: {current_price}")
                    except Exception as e:
                        log.error(f"Erro ao abrir ordem: {e}")

# --- WEBSOCKET E WARM-UP ---
def handle_error(error): log.error(f"🌐 WebSocket: {error}")

def subscribe_market_streams(ws_client):
    for symbol in SYMBOLS:
        ws_client.kline_stream(interval=1, symbol=symbol, callback=on_message)
        ws_client.kline_stream(interval=15, symbol=symbol, callback=on_message)

def create_and_subscribe_websocket():
    ws_client = get_websocket_session(testnet=IS_TESTNET)
    ws_client.on_error = handle_error
    subscribe_market_streams(ws_client)
    return ws_client

def reconnect_websocket(old_ws):
    global WS_RECONNECT_ATTEMPTS, WS_LAST_RECONNECT_TS

    now = time.time()
    backoff_seconds = min(WS_RECONNECT_MAX_SECONDS, WS_RECONNECT_BASE_SECONDS * (2 ** WS_RECONNECT_ATTEMPTS))
    elapsed = now - WS_LAST_RECONNECT_TS

    if elapsed < backoff_seconds:
        wait_left = int(backoff_seconds - elapsed)
        log.warning(f"⚠️ WebSocket desconectado. Aguardando {wait_left}s para reconectar...")
        return old_ws

    if old_ws is not None:
        try:
            old_ws.exit()
        except Exception as exit_error:
            log.warning(f"⚠️ Falha ao encerrar WS antigo: {exit_error}")

    log.warning(f"⚠️ Reconectando WebSocket (tentativa {WS_RECONNECT_ATTEMPTS + 1})...")
    WS_LAST_RECONNECT_TS = now
    WS_RECONNECT_ATTEMPTS += 1

    return create_and_subscribe_websocket()

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

ws = create_and_subscribe_websocket()

# --- LOOP PRINCIPAL ---
while True:
    try:
        agora = datetime.datetime.now()
        timestamp_atual = time.time()
        
        # LIMPEZA DE ORDENS PARA CADA SÍMBOLO
        for symbol in SYMBOLS:
            if LAST_ORDER_TIME.get(symbol) is not None:
                if timestamp_atual - LAST_ORDER_TIME[symbol] > 120:
                    if not executor.has_open_position(symbol):
                        success = executor.cancel_all_pending_orders(symbol)
                        if success:
                            log.info(f"🧹 Limpeza: {symbol}")
                    LAST_ORDER_TIME[symbol] = None
        
        # Saldo Inicial e Relatório
        if SALDO_INICIAL_DIA is None:
            balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            SALDO_INICIAL_DIA = float(balance_resp['result']['list'][0]['coin'][0]['walletBalance'])
            ULTIMO_RELATORIO_DATA = agora.date()

        if agora.hour == 20 and agora.minute == 0 and ULTIMO_RELATORIO_DATA != agora.date():
            balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
            saldo_atual = float(balance_resp['result']['list'][0]['coin'][0]['walletBalance'])
            pnl = saldo_atual - SALDO_INICIAL_DIA
            pnl_pct = (pnl / SALDO_INICIAL_DIA) * 100
            notifier.send_report(saldo_atual, pnl, pnl_pct, 0)
            ULTIMO_RELATORIO_DATA = agora.date()
            SALDO_INICIAL_DIA = saldo_atual 
        
        if not ws.is_connected():
            ws = reconnect_websocket(ws)
        elif WS_RECONNECT_ATTEMPTS > 0:
            log.info("✅ WebSocket reconectado e estável.")
            WS_RECONNECT_ATTEMPTS = 0
        
        time.sleep(10)
        
    except KeyboardInterrupt:
        try:
            ws.exit()
        except Exception:
            pass
        break
    except Exception as e:
        log.error(f"Erro loop: {e}")
        time.sleep(5)