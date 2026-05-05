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
from src.logger import setup_logger
from src.notifier import TelegramNotifier
from src.market_cycles import MarketCycleAnalyzer
from src.market_sentiment import MarketSentimentAnalyzer
from src.indicators import TechnicalIndicators

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
ULTIMO_CHECK_CALOR = 0
LAST_HOLD_LOG = {}
LAST_REGIME_LOG = 0
REGIME_COLD_THRESHOLD = 0.0010  # ATR% abaixo disso é frio
ULTIMO_ORDER_ID_PROCESSADO = None
ULTIMO_CHECK_VIVO = 0

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
message_queue = Queue()

cache_balance = {"total": 0, "avail": 0, "last_update": 0}
cache_positions = {"data": [], "last_update": 0}

# =========================================================
# 1. LÓGICA PRINCIPAL DE SINAIS E ESTRATÉGIA
# =========================================================

def process_signal_message(message):
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
            evaluate_open_position(symbol, strat, current_price, sentimento)
            return

        # 2. Busca por Entrada (Passando o sentimento e respeitando o intervalo do Backtest)
        elif is_confirmado and symbol in SYMBOLS:
            # Respeita o signal_check_interval definido no COIN_CONFIGS
            interval = getattr(strat, "signal_check_interval", 5)
            if int(timestamp_candle) % interval != 0:
                return

            signal, current_atr = strat.check_signal(market_sentiment=sentimento)

            if signal in ["BUY", "SELL"]:
                log.info(f"🎯 SINAL {signal} em {symbol} | Sentimento: {sentimento}")
                place_market_trade(symbol, signal, current_price, current_atr)
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

def normalize_order_quantity(symbol, price, qty, leverage=10):
    """Ajusta a quantidade para a precisão e valida saldo disponível."""
    q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
    
    # 1. NOTIONAL MÍNIMO BYBIT: ~5 USDT
    notional = price * qty
    min_notional = 5.0
    if notional < min_notional:
        adjusted_qty = max(0.1, min_notional / price)
        adjusted_qty = int(adjusted_qty) if q_prec == 0 else round(adjusted_qty, q_prec)
        if price * adjusted_qty < min_notional:
            return False, adjusted_qty, f"Notional {notional:.2f} USDT < mínimo {min_notional} USDT"
    
    # 2. Ajusta precisão
    qty_final = int(qty) if q_prec == 0 else round(qty, q_prec)
    if qty_final <= 0:
        return False, qty_final, "Quantidade <= 0"
    
    # 3. Valida margem usando saldo disponível inteiro
    available_for_new = cache_balance['avail']
    margin_needed = (price * qty_final) / float(leverage)
    log.debug(f"   [VALIDAÇÃO {symbol}] Margem: precisa={margin_needed:.2f}, available={available_for_new:.2f} (total={cache_balance['total']:.2f})")
    if margin_needed > available_for_new:
        qty_reduced = (available_for_new * float(leverage)) / price
        qty_reduced = int(qty_reduced) if q_prec == 0 else round(qty_reduced, q_prec)
        if qty_reduced <= 0:
            reason = f"❌ Margem insuficiente: precisa {margin_needed:.2f} USDT, disponível {available_for_new:.2f} USDT"
            log.warning(reason)
            return False, qty_final, reason
        adjusted_notional = price * qty_reduced
        if adjusted_notional < min_notional:
            reason = f"❌ Quantidade reduzida muito baixa: notional {adjusted_notional:.2f} USDT < mínimo {min_notional} USDT"
            log.warning(reason)
            return False, qty_final, reason
        reason = f"Quantidade reduzida: {qty:.2f} → {qty_reduced:.2f} (margem: precisa {margin_needed:.2f}, tem {available_for_new:.2f})"
        log.info(f"⚠️ {symbol} {reason}")
        return True, qty_reduced, reason
    return True, qty_final, "OK"

def place_market_trade(symbol, signal, price, atr):
    get_cached_data()
    if len(cache_positions['data']) >= risk_mgr.max_positions:
        log.info(f"⏭️ {symbol} ignorado: posições máximas ({len(cache_positions['data'])}) alcançadas")
        return
    if cache_balance['avail'] < 5.0:
        log.warning(f"⏭️ {symbol} ignorado: saldo disponível {cache_balance['avail']:.2f} USDT < 5 USDT")
        return

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
        _, qty = risk_mgr.calculate_trade_quantity(price, sl, cache_balance['total'])
        
        # 7. Calcular TP único baseado em ATR (2-3% de ganho)
        tp_mult = regime_params.get("atr_multiplier_tp", 2.0)
        tp_distance = (atr / price) * tp_mult
        tp_price = price * (1 + tp_distance) if side == "Buy" else price * (1 - tp_distance)
        
        q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        
        # 🛡️ VALIDAÇÃO DE QUANTIDADE ANTES DE ENVIAR
        log.info(f"[{symbol}] Validando ordem: price={price:.6f}, qty={qty:.2f}")
        log.info(f"   Saldo: total={cache_balance['total']:.2f}, avail={cache_balance['avail']:.2f}")
        is_valid_qty, validated_qty, reason = normalize_order_quantity(symbol, price, qty, lev)
        
        if not is_valid_qty:
            log.warning(f"❌ {symbol} REJEITADO: Quantidade inválida - {reason}")
            log.warning(f"   Calculada: {qty:.6f} | Ajustada: {validated_qty:.6f}")
            return
        
        qty_str = str(int(validated_qty)) if q_prec == 0 else str(validated_qty)

        prepare_leverage(symbol, lev)
        
        # 8. Envio da Ordem com SL fixo e TP único
        log.info(f"📤 Tentando enviar ordem: {symbol} {side} qty={qty_str} price={price:.6f} (notional={float(qty_str)*price:.2f} USDT)")
        log.info(f"   TP: {tp_price:.6f} | SL: {sl:.6f}")
        order = session.place_order(
            category="linear", symbol=symbol, side=side, orderType="Market",
            qty=qty_str, 
            takeProfit=str(round(tp_price, p_prec)), 
            stopLoss=str(round(sl, p_prec)),
            tpOrderType="Market", slOrderType="Market", tpslMode="Full"
        )

        if order['retCode'] == 0:
            strat.is_positioned = True
            strat.side = signal
            strat.entry_price = price
            strat.tp_price = tp_price
            strat.sl_price = sl
            strat.current_qty = float(validated_qty)
            strat.entry_timestamp = time.time()
            strat.breakeven_moved = False
            
            # Calcular força do sinal para notificação
            score_info = strat.last_score_result or {"score": 0, "total_indicators": 0}
            strength = min(float(score_info.get("score", 0)) / float(score_info.get("total_indicators", 1)), 1.0)
            
            # Notificação com novo formato (1 TP apenas)
            notifier.notify_trade_opened(
                symbol=symbol,
                side=side.upper(),
                entry=price,
                sl=sl,
                tp=tp_price,
                leverage=lev,
                profile=sentiment_data['profile'],
                strength=strength,
                rationale=[
                    f"[SENTIMENT] {sentiment_data['emoji']} {sentiment_data['emotion']}",
                    f"[REGIME] {regime}",
                    f"[SCORE] {score_info.get('score', 0)}/{score_info.get('total_indicators', 0)}"
                ]
            )
    except Exception as e:
        log.error(f"Erro na abertura de {symbol}: {e}")


def evaluate_open_position(symbol, strat, current_price, market_sentiment):
    try:
        strat._sync_dataframes()
        if strat.data_1m is None or len(strat.data_1m) < 20 or strat.data_15m is None or len(strat.data_15m) < 20:
            return

        entry = strat.entry_price
        sl = strat.sl_price
        tp = getattr(strat, 'tp_price', 0)
        qty = getattr(strat, 'current_qty', 0.0)
        side = strat.side
        if entry <= 0 or sl <= 0 or tp <= 0 or qty <= 0 or side not in ["BUY", "SELL"]:
            return

        is_long = side == "BUY"
        dist_tp = abs(tp - entry)
        dist_sl = abs(entry - sl)
        if dist_tp <= 0 or dist_sl <= 0:
            return

        current_profit = (current_price - entry) if is_long else (entry - current_price)
        current_drawdown = (entry - current_price) if is_long else (current_price - entry)
        pct_path = max(0.0, min(1.0, current_profit / dist_tp)) if current_profit > 0 else 0.0
        loss_pct = max(0.0, min(1.0, current_drawdown / dist_sl)) if current_drawdown > 0 else 0.0
        open_minutes = (time.time() - getattr(strat, 'entry_timestamp', time.time())) / 60.0

        rsi_1m = TechnicalIndicators.calculate_rsi(strat.data_1m['close']).iloc[-1]
        adx_1m = TechnicalIndicators.calculate_adx(strat.data_1m).iloc[-1]
        ema_20_1m = TechnicalIndicators.calculate_ema(strat.data_1m['close'], 20).iloc[-1]
        ema_50_15m = TechnicalIndicators.calculate_ema(strat.data_15m['close'], 50).iloc[-1]
        volume_momentum = TechnicalIndicators.calculate_volume_momentum(strat.data_1m, 5)

        price_near_tp = pct_path >= 0.85
        price_halfway = pct_path >= 0.50
        weak_momentum = (
            (is_long and current_price < ema_20_1m and rsi_1m < 50) or
            (not is_long and current_price > ema_20_1m and rsi_1m > 50)
        )
        trend_lost = adx_1m < 18
        weak_volume = volume_momentum < 0.85
        has_fade = weak_momentum and (trend_lost or weak_volume)

        # ====== REGRA 1: fechar se estiver perto do TP e o momentum estiver perdendo força
        if price_near_tp and pct_path >= 0.7 and has_fade:
            close_open_position(symbol, strat, "Perda de força perto do TP")
            return

        # ====== OPÇÃO A: mover SL para breakeven quando estiver em lucro significativo
        if price_halfway and current_profit > 0 and not getattr(strat, 'breakeven_moved', False):
            move_stop_loss_to_breakeven(symbol, strat)
            return

        # ====== REGRA 2: proteger trade antiga com pouco progresso
        if open_minutes >= 120 and pct_path < 0.25 and not getattr(strat, 'breakeven_moved', False):
            move_stop_loss_to_breakeven(symbol, strat)
            return

        # ====== REGRA 3: fechar se o mercado virou contra a posição e o drawdown está crescendo
        if loss_pct >= 0.7 and has_fade:
            close_open_position(symbol, strat, "Reversão clara e perda potencial grande")
            return

    except Exception as e:
        log.error(f"Erro avaliando posição aberta em {symbol}: {e}")


def move_stop_loss_to_breakeven(symbol, strat, buffer_pct=0.0005):
    try:
        if strat.entry_price <= 0 or strat.sl_price <= 0:
            return

        is_long = strat.side == "BUY"
        new_sl = strat.entry_price * (1 + buffer_pct) if is_long else strat.entry_price * (1 - buffer_pct)
        _, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))

        response = session.set_trading_stop(
            category="linear",
            symbol=symbol,
            stopLoss=str(round(new_sl, p_prec)),
            tpslMode="Full"
        )

        if response.get('retCode') == 0:
            strat.sl_price = new_sl
            strat.breakeven_moved = True
            notifier.send_message(
                f"🛡️ {symbol} SL movido para breakeven ({new_sl:.4f}) após gestão ativa de posição."
            )
            log.info(f"[{symbol}] SL movido para breakeven: {new_sl:.8f}")
        else:
            log.warning(f"[{symbol}] Falha ao mover SL para breakeven: {response}")
    except Exception as e:
        log.error(f"Erro movendo SL para breakeven em {symbol}: {e}")


def close_open_position(symbol, strat, reason):
    try:
        q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
        qty = strat.current_qty
        if qty <= 0:
            return

        qty_str = str(int(qty)) if q_prec == 0 else str(round(qty, q_prec))
        side_close = "Sell" if strat.side == "BUY" else "Buy"
        response = session.place_order(
            category="linear",
            symbol=symbol,
            side=side_close,
            orderType="Market",
            qty=qty_str,
            reduceOnly=True
        )

        if response.get('retCode') == 0:
            strat.is_positioned = False
            strat.current_qty = 0.0
            strat.side = None
            strat.entry_price = 0.0
            strat.sl_price = 0.0
            strat.tp_price = 0.0
            strat.breakeven_moved = False
            notifier.send_message(
                f"❌ {symbol} fechado por gestão ativa: {reason}"
            )
            log.info(f"[{symbol}] Posição fechada por gestão ativa: {reason}")
            get_cached_data(force=True)
        else:
            log.warning(f"[{symbol}] Falha ao fechar posição por gestão ativa: {response}")
    except Exception as e:
        log.error(f"Erro fechando posição em {symbol}: {e}")

# Nota: TP e SL são gerenciados automaticamente pela Bybit através das ordens
# Não é necessário executar closes parciais manuais

def get_market_sentiment():
    try:
        results = []
        for symbol in ["BTCUSDT"]:  # Bitcoin only
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
                        risk_mgr.sync_account_balance(total)
            
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
                symbol = last_trade['symbol']
                risk_mgr.record_trade_result(symbol, pnl)
                ULTIMO_ORDER_ID_PROCESSADO = order_id
                # ✅ Notificar trade fechado
                notifier.notify_trade_closed(last_trade)
                log.info(f"📢 Notificação enviada para trade fechado em {symbol}")
    except Exception as e: log.error(f"Erro closed trades: {e}")

def sync_historical_pnl():
    global ULTIMO_ORDER_ID_PROCESSADO
    try:
        start_date_display = "2026-05-05 12:00:00"
        start_ts = int(datetime.datetime.strptime(start_date_display, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
        
        processed_orders = set()
        last_processed_order_id = None
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
                        risk_mgr.total_pnl += pnl_liquido
                        risk_mgr.total_fees += fees
                        processed_orders.add(order_id)
                        trades_count += 1
                        last_processed_order_id = order_id
                log.info(f"  ✅ {symbol}: {trades_count} trades sincronizados")
        
        if last_processed_order_id is not None:
            ULTIMO_ORDER_ID_PROCESSADO = last_processed_order_id

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
        try: process_signal_message(message)
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
            atr_pct = TechnicalIndicators.calculate_atr_pct(recent)
            if pd.isna(atr_pct):
                continue
            # 🔧 CORREÇÃO: atr_pct já é decimal (0.00086), multiplicar por 100 pra exibir como %
            atr_pct_display = atr_pct * 100
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
            
            log.info(f"{symbol:10} | ATR%: {atr_pct_display:.2f}% | Ratio: {pct:.1f}x | {status}")
    
    log.info("-------------------------------------")
    now_ts = time.time()
    if now_ts - LAST_REGIME_LOG >= 600:  # 10 minutos
        total, wins, prot, wr, sr, pnl_net = risk_mgr.get_performance_summary()
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
            if timestamp_atual - ULTIMO_CHECK_VIVO >= 3600 * 3:
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
    start_bot()