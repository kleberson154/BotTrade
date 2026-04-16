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
from src.tp_cascade_manager import TPCascadeManager
from src.market_sentiment import MarketSentimentAnalyzer

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
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,XRPUSDT,NEARUSDT,LINKUSDT,SUIUSDT,OPUSDT,ETHUSDT,AVAXUSDT,SOLUSDT,ADAUSDT,DOTUSDT").split(",")
ULTIMO_CHECK_VIVO = 0 
SALDO_INICIAL_DIA = None
ULTIMO_ORDER_ID_PROCESSADO = None
ULTIMO_CHECK_CALOR = 0
LAST_HOLD_LOG = {}
LAST_REGIME_LOG = 0
REGIME_COLD_THRESHOLD = 0.0010  # ATR% abaixo disso é frio

# --- MARKET CYCLES ANALYZER (NEW) ---
market_cycles = MarketCycleAnalyzer()

# --- MARKET SENTIMENT ANALYZER ---
sentiment_analyzer = MarketSentimentAnalyzer()

# --- ESTRATÉGIAS INICIALIZADAS COM ANÁLISE DINÂMICA ---
notifier = TelegramNotifier()
strategies = {}
for symbol in SYMBOLS:
    strat = TradingStrategy(symbol=symbol, notifier=notifier)
    strategies[symbol] = strat

# --- INICIALIZAÇÃO DE COMPONENTES GLOBAIS ---
log = setup_logger()
risk_mgr = RiskManager(account_balance=100.0)  # Será atualizado após primeira leitura de balance
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
            # Monitorar cascata de TPs
            status = strat.check_cascade_tp(current_price)
            if status and isinstance(status, dict) and status.get('action') == 'CLOSE_PARTIAL':
                # TP foi atingido - executar close parcial
                execute_partial_tp(symbol, strat, current_price)
                # Atualizar SL remoto conforme novo stop loss
                update_remote_sl(symbol, status.get('new_sl', strat.sl_price))

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
        
        # 1. Fetch BTC Dominância
        btc_dominance = market_cycles.fetch_btc_dominance()
        if btc_dominance is None:
            btc_dominance = 50
        
        # 2. Calcular sentimento de mercado
        volatility = (atr / price) if price > 0 else 0.001
        
        # Estimar RSI simples (14 períodos)
        if len(strat.data_1m) >= 14:
            delta = strat.data_1m['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi_value = 100 - (100 / (1 + rs.iloc[-1]))
            if pd.isna(rsi_value):
                rsi_value = 50
        else:
            rsi_value = 50
        
        # Volume ratio (atual vs média 20 candles)
        if len(strat.data_1m) >= 20:
            avg_vol_20 = strat.data_1m['volume'].tail(20).mean()
            curr_vol = strat.data_1m['volume'].iloc[-1]
            volume_ratio = curr_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0
        else:
            volume_ratio = 1.0
        
        # Calcular sentimento
        sentiment_data = sentiment_analyzer.calculate_sentiment(
            btc_dominance=btc_dominance,
            volatility_pct=volatility,
            rsi_daily=rsi_value,
            volume_ratio=volume_ratio,
            market_phase=strat.current_regime,
            atr_history=strat.data_1m
        )
        
        log.info(f"📊 {sentiment_analyzer.get_sentiment_message(sentiment_data)}")
        
        # 3. Determina regime (COLD, LATERAL, NORMAL, HOT)
        regime = strat.current_regime
        regime_params = {
            "COLD": strat.regime_params_cold,
            "LATERAL": strat.regime_params_lateral,
            "NORMAL": strat.regime_params_normal,
            "HOT": strat.regime_params_hot,
        }.get(regime, strat.regime_params_normal)
        
        # 4. Leverage baseado no regime + sentimento
        base_leverage = int(regime_params.get("leverage", 10.0))
        sentiment_mult = sentiment_data['leverage_multiplier']
        lev = max(1, int(base_leverage * sentiment_mult))
        
        # 5. SL FIXO baseado em ATR multiplier (não dinâmico)
        atr_mult = regime_params.get("atr_multiplier_sl", 1.8)
        dist_sl = (atr / price) * atr_mult
        sl = price * (1 - dist_sl) if side == "Buy" else price * (1 + dist_sl)
        
        # 6. Calcular quantity com risco máximo 2%
        qty = risk_mgr.get_dynamic_risk_params(price, sl, cache_balance['total'])[1]
        
        # 7. CASCATA DE TPS (3 níveis)
        strat.tp_cascade = TPCascadeManager(
            symbol=symbol,
            side="LONG" if side == "Buy" else "SHORT",
            entry=price,
            initial_sl=sl,
            account_balance=cache_balance['total'],
            leverage=lev
        )
        strat.tp_cascade.calculate_scalp_tps(market_volatility=regime)
        
        # 8. Usar TP1 para a ordem (será gerenciado em cascata)
        tp1_price = strat.tp_cascade.tp_levels[0].tp_price
        
        q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))

        prepare_leverage(symbol, lev)
        
        # 9. Envio da Ordem com SL fixo e TP1 da cascata
        order = session.place_order(
            category="linear", symbol=symbol, side=side, orderType="Market",
            qty=qty_str, 
            takeProfit=str(round(tp1_price, p_prec)), 
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
            
            # Log dos 3 TPs
            tp1 = strat.tp_cascade.tp_levels[0].tp_price
            tp2 = strat.tp_cascade.tp_levels[1].tp_price
            tp3 = strat.tp_cascade.tp_levels[2].tp_price
            
            tp1_pct = abs((tp1 - price) / price) * 100
            
            # Notificação Mack com sentimento
            score_info = strat.last_score_result or {"score": 0, "total_indicators": 0}
            strength = min(float(score_info.get("score", 0)) / float(score_info.get("total_indicators", 1)), 1.0)
            
            notifier.notify_signal_mack(
                symbol=symbol,
                side=side.upper(),
                entry=price,
                sl=sl,
                tp=tp1,  # TP1 como principal
                leverage=lev,
                profile=sentiment_data['profile'],  # Profile baseado em sentimento
                strength=strength,
                rationale=[
                    f"[SENTIMENT] {sentiment_data['emoji']} {sentiment_data['emotion']}",
                    f"[REGIME] {regime}",
                    f"[SCORE] {score_info.get('score', 0)}/{score_info.get('total_indicators', 0)}"
                ],
                partials=[
                    {"tp": tp1, "percent": 50, "action": "CLOSE_PARTIAL", "desc": "TP1"},
                    {"tp": tp2, "percent": 30, "action": "CLOSE_PARTIAL", "desc": "TP2"},
                    {"tp": tp3, "percent": 20, "action": "CLOSE_FINAL", "desc": "TP3"},
                ]
            )
            
            # Enviar mensagem de sentimento
            notifier.send_message(sentiment_analyzer.get_sentiment_message(sentiment_data))
    except Exception as e:
        log.error(f"Erro na abertura de {symbol}: {e}")

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
                        # 💰 Sincronizar balance com RiskManager
                        risk_mgr.update_compliance(total)
            
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

def sync_historical_pnl():
    try:
        start_date_display = "2026-04-13"
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
            # 🔄 RECALCULA o regime em tempo real dentro do termômetro
            regime = strat.detect_market_regime(df)
            
            # Obtém threshold baseado no regime recalculado
            regime_params = {
                "COLD": strat.regime_params_cold,
                "LATERAL": strat.regime_params_lateral,
                "NORMAL": strat.regime_params_normal,
                "HOT": strat.regime_params_hot,
            }.get(regime, strat.regime_params_normal)
            threshold = regime_params.get("min_volatilidade_pct", 0.0012)
            
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
    log.info("📥 Warm-up Inicial...")
    log.info("✅ Stats resetados - WR check desativado")
    for symbol in SYMBOLS:
        strat = strategies[symbol]
        for tf, tf_id in [("1m", 1), ("15m", 15)]:
            hist = session.get_kline(category="linear", symbol=symbol, interval=tf_id, limit=200)
            if hist['retCode'] == 0:
                formatted = []
                for c in hist['result']['list']:
                    try:
                        if len(c) >= 6:
                            formatted.append({
                                "timestamp": int(c[0]), 
                                "open": float(c[1]), 
                                "high": float(c[2]), 
                                "low": float(c[3]), 
                                "close": float(c[4]), 
                                "volume": float(c[5])
                            })
                    except (ValueError, IndexError) as e:
                        log.warning(f"Skipping malformed candle for {symbol}: {e}")
                        continue
                formatted.reverse()
                if formatted:
                    strat.load_historical_data(tf, formatted)
    sync_open_positions()
    Thread(target=process_queue, daemon=True).start()
    ws = create_and_subscribe_websocket()
    sync_historical_pnl()
    debug_sanity_check()
    start_bot()