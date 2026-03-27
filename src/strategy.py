import pandas as pd
import numpy as np
import datetime
import logging
from collections import deque as python_deque

log = logging.getLogger(__name__)

class TradingStrategy:
    def __init__(self, symbol, notifier):
        self.symbol = symbol
        self.notifier = notifier
        self.data_1m = pd.DataFrame()
        self.data_15m = pd.DataFrame()
        self.candles_1m = python_deque(maxlen=300)
        self.candles_15m = python_deque(maxlen=300)
        self._dirty_1m = False
        self._dirty_15m = False
        
        # --- PARÂMETROS OTIMIZADOS (SNIPER MODE) ---
        self.min_volatilidade_pct = 0.0014  # 0.14%
        self.volume_multiplier = 1.6        # 160% acima da media
        self.ema_1m_trend = 20
        self.ema_15m_period = 200
        self.min_15m_candles = 200
        self.min_adx = 25
        self.rsi_overbought = 75            # Filtro de exaustão
        self.rsi_oversold = 25              # Filtro de exaustão
        
        self.min_pnl_be = 0.007             # 0.7% para mover Stop
        self.distancia_respiro = 0.015      # 1.5% de Trailing
        self.use_regime_filter = True       # Ativado por padrão para segurança
        
        self.invert_signal = False          # Alterar no main.py para SOL/XRP/AVAX
        self.allow_long = True
        self.allow_short = True
        
        # Controle de Posição
        self.is_positioned = False
        self.side = None 
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.be_activated = False 
        self.partial_taken = False 
        self.last_hold_reason = "init"

    # =========================================================
    # UTILITÁRIOS DE CÁLCULO (OTIMIZADOS)
    # =========================================================
    def safe_float(self, val):
        try:
            if val is None or str(val).strip() == "": return 0.0
            return float(val)
        except: return 0.0

    def calculate_indicators(self, df_1m, df_15m):
        """Calcula apenas o necessário para a tomada de decisão atual."""
        results = {}
        
        # M15 Indicators
        ema_200_15 = df_15m['close'].ewm(span=200, adjust=False).mean()
        results['ema_200_15'] = ema_200_15.iloc[-1]
        
        # Regime Filter (EMA 50 vs 200)
        ema_50_15 = df_15m['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        results['regime_gap'] = abs(ema_50_15 - results['ema_200_15']) / df_15m['close'].iloc[-1]

        # M1 Indicators
        results['ema_20_1m'] = df_1m['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        results['rsi_1m'] = self._calc_rsi_single(df_1m).iloc[-1]
        results['adx_1m'] = self._calc_adx_single(df_1m).iloc[-1]
        
        # ATR para volatilidade
        tr = pd.concat([df_1m['high'] - df_1m['low'], 
                        (df_1m['high'] - df_1m['close'].shift()).abs(), 
                        (df_1m['low'] - df_1m['close'].shift()).abs()], axis=1).max(axis=1)
        results['atr_pct'] = tr.rolling(14).mean().iloc[-1] / df_1m['close'].iloc[-1]
        
        return results

    def _calc_rsi_single(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 0.001)
        return 100 - (100 / (1 + rs))

    def _calc_adx_single(self, df, period=14):
        plus_dm = df['high'].diff().clip(lower=0)
        minus_dm = -df['low'].diff().clip(upper=0)
        tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
        return dx.rolling(period).mean().bfill()

    # =========================================================
    # LÓGICA DE SINAL
    # =========================================================
    def check_signal(self, current_time=None, market_sentiment="NEUTRAL"):
        try:
            self._sync_dataframes()
            self.last_hold_reason = "avaliando"
            
            if not self.is_market_safe(current_time):
                self.last_hold_reason = "protecao virada de hora (minuto 00/01/59)"
                return "HOLD", 0
            if len(self.data_1m) < 40 or len(self.data_15m) < self.min_15m_candles:
                self.last_hold_reason = f"dados insuficientes 1m={len(self.data_1m)} 15m={len(self.data_15m)}"
                return "HOLD", 0

            # 1. Preparação de Dados e Indicadores
            ind = self.calculate_indicators(self.data_1m.tail(100), self.data_15m.tail(250))
            
            curr_price = self.data_1m['close'].iloc[-1]
            curr_vol = self.data_1m['volume'].iloc[-1]
            avg_vol = self.data_1m['volume'].tail(20).mean()

            # 2. Filtro de Regime (Evita mercados "mortos")
            if self.use_regime_filter and ind['regime_gap'] < 0.0015:
                self.last_hold_reason = f"regime fraco gap={ind['regime_gap']:.4f} (<0.0015)"
                return "HOLD", 0

            # 3. Lógica de Decisão
            raw_signal = "HOLD"
            dist_sl = 0
            
            pico_vol = curr_vol > (avg_vol * self.volume_multiplier)
            volat_ok = ind['atr_pct'] >= self.min_volatilidade_pct
            tendencia_forte = ind['adx_1m'] >= self.min_adx

            if tendencia_forte and volat_ok and pico_vol:
                # M15 Context
                m15_last = self.data_15m.iloc[-1]
                m15_is_green = m15_last['close'] > m15_last['open']
                m15_is_red = m15_last['close'] < m15_last['open']
                
                # Respiro/Máximas
                max_15m = self.data_1m['high'].iloc[-16:-1].max()
                min_15m = self.data_1m['low'].iloc[-16:-1].min()

                # Condição de COMPRA
                if curr_price > max_15m and curr_price > ind['ema_200_15'] and m15_is_green:
                    if ind['rsi_1m'] < self.rsi_overbought: # Filtro de exaustão
                        raw_signal = "BUY"
                        min_rec = self.data_1m['low'].tail(10).min()
                        dist_sl = max(abs(curr_price - min_rec * 0.999), curr_price * 0.015)

                # Condição de VENDA
                elif curr_price < min_15m and curr_price < ind['ema_200_15'] and m15_is_red:
                    if ind['rsi_1m'] > self.rsi_oversold: # Filtro de exaustão
                        raw_signal = "SELL"
                        max_rec = self.data_1m['high'].tail(10).max()
                        dist_sl = max(abs(max_rec * 1.001 - curr_price), curr_price * 0.015)

            # 4. Filtros de Sentimento e Inversão
            final_signal = raw_signal
            if final_signal == "BUY" and (not self.allow_long or (market_sentiment == "BEARISH" and self.symbol not in ["BTCUSDT", "ETHUSDT"])):
                self.last_hold_reason = f"bloqueado por sentimento/allow_long (sent={market_sentiment})"
                final_signal = "HOLD"
            if final_signal == "SELL" and (not self.allow_short or (market_sentiment == "BULLISH" and self.symbol not in ["BTCUSDT", "ETHUSDT"])):
                self.last_hold_reason = f"bloqueado por sentimento/allow_short (sent={market_sentiment})"
                final_signal = "HOLD"

            if final_signal != "HOLD" and self.invert_signal:
                old = final_signal
                final_signal = "SELL" if old == "BUY" else "BUY"
                log.info(f"🔄 [{self.symbol}] Inversão: {old} -> {final_signal}")

            if final_signal == "HOLD" and self.last_hold_reason == "avaliando":
                motivos = []
                if not tendencia_forte:
                    motivos.append(f"adx={ind['adx_1m']:.1f}<{self.min_adx}")
                if not volat_ok:
                    motivos.append(f"atr%={ind['atr_pct']:.4f}<{self.min_volatilidade_pct}")
                if not pico_vol:
                    motivos.append(f"vol={curr_vol:.2f}<x{self.volume_multiplier} da media({avg_vol:.2f})")
                if len(motivos) == 0:
                    motivos.append("sem rompimento m1/m15 ou RSI de exaustao")
                self.last_hold_reason = " | ".join(motivos)
            elif final_signal != "HOLD":
                self.last_hold_reason = (
                    f"entrada={final_signal} adx={ind['adx_1m']:.1f} "
                    f"atr%={ind['atr_pct']:.4f} vol={curr_vol:.2f}/avg20={avg_vol:.2f}"
                )

            return final_signal, dist_sl

        except Exception as e:
            log.error(f"❌ Erro check_signal ({self.symbol}): {e}")
            return "HOLD", 0

    # =========================================================
    # GESTÃO DE RISCO
    # =========================================================
    def monitor_protection(self, current_price):
        if not self.is_positioned: return None
    
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.side == "BUY" else (self.entry_price - current_price) / self.entry_price
        changed = False
        
        # 1. BREAK-EVEN (Proteção + Taxas da Corretora)
        if not self.be_activated and pnl_pct >= self.min_pnl_be:
            self.be_activated = True
            # Adiciona 0.1% além da entrada para pagar os custos de execução (Maker/Taker)
            offset = 0.001 
            self.sl_price = self.entry_price * (1 + offset if self.side == "BUY" else 1 - offset)
            changed = True
    
        # 2. SAÍDA PARCIAL (Reduz risco em 1.5% de lucro)
        if not self.partial_taken and pnl_pct >= 0.015:
            self.partial_taken = True
            return "PARTIAL_EXIT"
    
        # 3. TRAILING STOP DINÂMICO (Ativa em 2.5% de lucro)
        if pnl_pct >= 0.025:
            if self.side == "BUY":
                novo_sl = current_price * (1 - self.distancia_respiro)
                if novo_sl > self.sl_price:
                    self.sl_price = novo_sl
                    changed = True
            else:
                novo_sl = current_price * (1 + self.distancia_respiro)
                if self.sl_price == 0 or novo_sl < self.sl_price:
                    self.sl_price = novo_sl
                    changed = True
    
        return "UPDATE_SL" if changed else None

    # =========================================================
    # SINCRONIZAÇÃO E DADOS
    # =========================================================
    def is_market_safe(self, current_time=None):
        dt = datetime.datetime.now() if current_time is None else pd.Timestamp(current_time)
        # Evita a "virada" de candle de 1h (alta volatilidade errática)
        return not (dt.minute < 2 or dt.minute > 58)

    def add_new_candle(self, timeframe, candle_data):
        target = self.candles_1m if timeframe == "1m" else self.candles_15m
        if len(target) > 0 and target[-1]['timestamp'] == candle_data['timestamp']:
            target[-1].update(candle_data)
        else:
            target.append(candle_data)
        
        if timeframe == "1m": self._dirty_1m = True
        else: self._dirty_15m = True

    def _sync_dataframes(self):
        if self._dirty_1m:
            self.data_1m = pd.DataFrame(list(self.candles_1m))
            self._dirty_1m = False
        if self._dirty_15m:
            self.data_15m = pd.DataFrame(list(self.candles_15m))
            self._dirty_15m = False
            
    def sync_position(self, side, entry_price, sl_price, tp_price):
        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = self.safe_float(entry_price)
        self.sl_price = self.safe_float(sl_price)
        self.tp_price = self.safe_float(tp_price)
        log.info(f"🔄 [{self.symbol}] Sincronizado: {self.side} @ {self.entry_price}")

    def load_historical_data(self, timeframe, candles):
        target = self.candles_1m if timeframe == "1m" else self.candles_15m
        for candle in candles:
            if len(target) == 0 or target[-1]['timestamp'] != candle['timestamp']:
                target.append(candle)
        self._dirty_1m = (timeframe == "1m")
        self._dirty_15m = (timeframe == "15m")
        self._sync_dataframes()