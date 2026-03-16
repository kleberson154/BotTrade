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
LEVERAGE = int(os.getenv("LEVERAGE", "5"))
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

LAST_ORDER_TIME = {symbol: None for symbol in SYMBOLS}
SALDO_INICIAL_DIA = None
ULTIMO_RELATORIO_DATA = None

# --- LÓGICA DE PROCESSAMENTO (FORA DO WEBSOCKET) ---

def handle_signal_logic(message):
    """
    Aqui fica toda a lógica pesada que antes travava o WebSocket.
    """
    topic = message.get("topic", "")
    parts = topic.split('.')
    timeframe = parts[1] 
    symbol = parts[-1]
    
    candle = message["data"][0]
    current_price = float(candle["close"])
    timestamp = int(candle["start"])
    
    strat = strategies.get(symbol)
    if not strat: return

    # 1. Atualiza dados do candle
    tf_key = "1m" if timeframe == "1" else "15m"
    dados_candle = {
        "close": current_price,
        "high": float(candle["high"]),   
        "low": float(candle["low"]),     
        "timestamp": timestamp
    }
    strat.add_new_candle(tf_key, dados_candle)
    
    # 2. LÓGICA DE PROTEÇÃO (Apenas no 1m)
    if tf_key == "1m":
        try:
            # CHAMADA HTTP: Se fosse no on_message, causaria timeout no ping/pong
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
                        elif current_price > entry_price * 1.025:
                            potential_sl = current_price - trailing_dist
                            if potential_sl > current_sl + (current_price * 0.001):
                                executor.update_stop_loss(symbol, round(potential_sl, p_prec))

                    elif side_pos == "Sell":
                        if current_price <= entry_price * 0.985 and current_sl > entry_price:
                            new_sl = entry_price - (entry_price * 0.001)
                            executor.update_stop_loss(symbol, round(new_sl, p_prec))
                            notifier.send_message(f"🛡️ *Break-even:* {symbol}")
                        elif current_price < entry_price * 0.975:
                            potential_sl = current_price + trailing_dist
                            if potential_sl < current_sl - (current_price * 0.001):
                                executor.update_stop_loss(symbol, round(potential_sl, p_prec))
        except Exception as e:
            log.error(f"Erro na proteção de {symbol}: {e}")

        # 3. VERIFICAÇÃO DE SINAL
        signal, current_atr = strat.check_signal()
        if signal in ["BUY", "SELL"]:
            # --- NOVA TRAVA: Evita duplicar ordens no mesmo minuto ---
            current_minute = datetime.now().minute
            if hasattr(strat, 'last_signal_min') and strat.last_signal_min == current_minute:
                return # Já tentou operar neste minuto, ignora
            strat.last_signal_min = current_minute
            
            side = "Buy" if signal == "BUY" else "Sell"
            
            if not executor.has_open_position(symbol):
                # Outra chamada HTTP pesada
                pos_resp = session.get_positions(category="linear", settleCoin="USDT")
                active_positions = [p for p in pos_resp['result']['list'] if float(p['size']) != 0]

                if len(active_positions) >= 3:
                    log.warning(f"⚠️ Limite atingido. Ignorando {symbol}")
                    return

                balance_resp = session.get_wallet_balance(accountType="UNIFIED", coin="USDT")
                balance = float(balance_resp['result']['list'][0]['coin'][0]['walletBalance'])
                
                qty = risk_mgr.calculate_position_size(symbol, balance, current_price, leverage=LEVERAGE)
                sl, tp = risk_mgr.get_sl_tp_adaptive(symbol, side, current_price, current_atr)
                
                try:
                    # Pega o saldo disponível real (free margin)
                    free_balance = float(balance_resp['result']['list'][0]['coin'][0]['availableToWithdraw'])
                    order_margin_required = (qty * current_price) / LEVERAGE

                    if order_margin_required > free_balance:
                        log.warning(f"⚠️ Saldo insuficiente para {symbol}. Requerido: {order_margin_required}, Livre: {free_balance}")
                        return
                except:
                    pass # Se falhar a leitura do saldo, segue com tentativa de ordem
                
                try:
                    order = session.place_order(
                        category="linear", symbol=symbol, side=side, orderType="Limit",
                        price=str(current_price), qty=str(qty), takeProfit=str(tp), stopLoss=str(sl),
                        tpOrderType="Market", slOrderType="Market", tpslMode="Full", timeInForce="PostOnly"
                    )
                    if order['retCode'] == 0:
                        LAST_ORDER_TIME[symbol] = time.time()
                        notifier.send_message(f"✅ *Limit Order:* {symbol}\nLado: {side}\nPreço: {current_price}")
                except Exception as e:
                    log.error(f"Erro ao abrir ordem: {e}")

def process_queue():
    """Consome as mensagens da fila infinitamente"""
    while True:
        message = message_queue.get()
        if message is None: break
        try:
            handle_signal_logic(message)
        except Exception as e:
            log.error(f"Erro no processamento da fila: {e}")
        message_queue.task_done()

# --- COMPONENTES DO WEBSOCKET ---

def on_message(message):
    """Extremamente rápido: apenas coloca na fila e libera o WS"""
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
    # --- VALIDAÇÃO DE DADOS ---
    print("📊 Validando indicadores...")
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        if len(strat.data_1m) >= 14:
            # Tenta calcular o ATR
            test_atr = strat.calculate_atr(strat.data_1m, 14).iloc[-1]
            if test_atr > 0:
                log.info(f"✅ {symbol} ATR: {test_atr:.4f} | Preço: {strat.data_1m['close'].iloc[-1]}")
            else:
                log.error(f"❌ {symbol} ATR inválido (Zero ou Negativo)!")
        else:
            log.warning(f"⚠️ {symbol} dados insuficientes para ATR (Candles: {len(strat.data_1m)})")

# Inicia a Thread de processamento antes de abrir o WebSocket
worker_thread = Thread(target=process_queue, daemon=True)
worker_thread.start()

ws = create_and_subscribe_websocket()
notifier.send_message("🚀 *Bot Operando com Fila e Thread separada!*")

# --- LOOP PRINCIPAL (Monitoramento e Relatórios) ---
while True:
    try:
        agora = datetime.now(fuso_brasilia)
        timestamp_atual = time.time()
        
        # Limpeza de ordens
        for symbol in SYMBOLS:
            if LAST_ORDER_TIME.get(symbol) is not None:
                if timestamp_atual - LAST_ORDER_TIME[symbol] > 120:
                    if not executor.has_open_position(symbol):
                        if executor.cancel_all_pending_orders(symbol):
                            log.info(f"🧹 Limpeza: {symbol}")
                    LAST_ORDER_TIME[symbol] = None
        
        # Relatório de PnL às 20h
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
        
        # Monitor de Conexão
        if not ws.is_connected():
            log.warning("⚠️ WebSocket offline. Reconectando...")
            ws = create_and_subscribe_websocket()
            
        time.sleep(10) # Loop de baixa frequência para o monitor
        
    except KeyboardInterrupt:
        break
    except Exception as e:
        log.error(f"Erro loop principal: {e}")
        time.sleep(5)
    finally:
        # Força a limpeza de memória a cada 10 segundos
        gc.collect()