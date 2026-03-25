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
        self.min_volatilidade_pct = 0.0022  # 0.22%
        self.volume_multiplier = 2.5        # 250% acima da média
        self.ema_1m_trend = 20
        self.ema_15m_period = 200
        self.min_15m_candles = 200
        self.min_adx = 25
        self.atr_multiplier_sl = 1.5
        self.atr_multiplier_tp = 4.0
        self.min_pnl_be = 0.007
        self.distancia_respiro = 0.015
        self.use_regime_filter = False
        self.regime_ema_fast = 50
        self.regime_ema_slow = 200
        self.regime_min_gap = 0.0015
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

    # =========================================================
    # INDICADORES TÉCNICOS
    # =========================================================
    def calculate_atr(self, df, period=14):
        if len(df) <= period: return pd.Series(0.005 * df['close'], index=df.index)
        tr = pd.concat([df['high'] - df['low'], 
                        (df['high'] - df['close'].shift()).abs(), 
                        (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().bfill()

    def calculate_ema(self, df, period):
        return df['close'].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, df, period=14):
        if len(df) < period: return pd.Series(50, index=df.index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 0.001)
        return 100 - (100 / (1 + rs))

    def calculate_adx(self, df, period=14):
        """Mede a força da tendência (ADX > 22 = Tendência Forte)"""
        if len(df) < period * 2: return pd.Series(0, index=df.index)
        plus_dm = df['high'].diff().clip(lower=0)
        minus_dm = -df['low'].diff().clip(upper=0)
        tr = pd.concat([df['high'] - df['low'], (df['high'] - df['close'].shift()).abs(), (df['low'] - df['close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
        return dx.rolling(period).mean().bfill()

    # =========================================================
    # LÓGICA DE SINAL (VERSÃO OTIMIZADA COM INVERSÃO E REGIME)
    # =========================================================
    def check_signal(self, current_time=None, market_sentiment="NEUTRAL"):
        """
        Analisa sinais integrando Filtro de Regime, Direção e Inversão.
        """
        try:
            # 1. Sincronização e Garantia de Atributos
            self._sync_dataframes()
            
            # Recupera parâmetros com valores default de segurança (evita erros de config)
            use_regime = getattr(self, 'use_regime_filter', False)
            allow_long = getattr(self, 'allow_long', True)
            allow_short = getattr(self, 'allow_short', True)
            invert = getattr(self, 'invert_signal', False)
            sig_interval = getattr(self, 'signal_interval', 1)

            # 2. Verificações de Segurança e Warmup
            if not self.is_market_safe(current_time):
                return "HOLD", 0
            
            if len(self.data_1m) < 40 or len(self.data_15m) < self.min_15m_candles:
                return "HOLD", 0

            # 3. Preparação de Dados (Janelas Curtas para Performance)
            data_1m_win = self.data_1m.tail(90)
            data_15m_win = self.data_15m.tail(max(self.ema_15m_period + 30, 230))

            current_price = data_1m_win['close'].iloc[-1]
            current_volume = data_1m_win['volume'].iloc[-1]

            # 4. Filtro de Regime (O que salvou o ETH)
            if use_regime:
                f_per = getattr(self, 'regime_ema_fast', 50)
                s_per = getattr(self, 'regime_ema_slow', 200)
                min_g = getattr(self, 'regime_min_gap', 0.0015)
                
                ema_f = self.calculate_ema(data_15m_win, f_per).iloc[-1]
                ema_s = self.calculate_ema(data_15m_win, s_per).iloc[-1]
                gap = abs(ema_f - ema_s) / current_price if current_price > 0 else 0
                
                if gap < min_g:
                    return "HOLD", 0

            # 5. Indicadores de Rompimento
            avg_vol_20 = data_1m_win['volume'].tail(20).mean()
            adx_1m = self.calculate_adx(data_1m_win, 14).iloc[-1]
            ema_20_1m = self.calculate_ema(data_1m_win, 20).iloc[-1]
            ema_200_15m = self.calculate_ema(data_15m_win, 200).iloc[-1]
            
            # Filtros M15
            m15_last = data_15m_win.iloc[-1]
            m15_is_green = m15_last['close'] > m15_last['open']
            m15_is_red = m15_last['close'] < m15_last['open']

            # 6. Lógica de Decisão Base (Sinal "Cru")
            raw_signal = "HOLD"
            dist_sl = 0
            
            # Condições de Filtro Técnico
            pico_vol = current_volume > (avg_vol_20 * self.volume_multiplier)
            volatilidade_ok = (self.calculate_atr(data_1m_win, 14).iloc[-1] / current_price) >= self.min_volatilidade_pct
            
            if adx_1m >= self.min_adx and volatilidade_ok and pico_vol:
                # Teste de COMPRA (LONG)
                maxima_15m = data_1m_win.iloc[-16:-1]['high'].max()
                if current_price > maxima_15m and current_price > ema_200_15m and m15_is_green:
                    raw_signal = "BUY"
                    min_rec = data_1m_win['low'].tail(8).min()
                    dist_sl = max(abs(current_price - min_rec * 0.9985), current_price * 0.018)

                # Teste de VENDA (SHORT)
                minima_15m = data_1m_win.iloc[-16:-1]['low'].min()
                if current_price < minima_15m and current_price < ema_200_15m and m15_is_red:
                    raw_signal = "SELL"
                    max_rec = data_1m_win['high'].tail(8).max()
                    dist_sl = max(abs(max_rec * 1.0015 - current_price), current_price * 0.018)

            # 7. Aplicação de Direção e Inversão
            final_signal = raw_signal

            if final_signal == "BUY":
                if not allow_long or (market_sentiment == "BEARISH" and self.symbol not in ["BTCUSDT", "ETHUSDT"]):
                    final_signal = "HOLD"
            
            if final_signal == "SELL":
                if not allow_short or (market_sentiment == "BULLISH" and self.symbol not in ["BTCUSDT", "ETHUSDT"]):
                    final_signal = "HOLD"

            # A Mágica da Inversão (SOL, XRP, AVAX)
            if final_signal != "HOLD" and invert:
                old = final_signal
                final_signal = "SELL" if old == "BUY" else "BUY"
                log.info(f"🔄 [{self.symbol}] Inversão aplicada: {old} -> {final_signal}")

            return final_signal, dist_sl

        except Exception as e:
            log.error(f"❌ Erro crítico no check_signal ({self.symbol}): {e}")
            return "HOLD", 0

    # =========================================================
    # GESTÃO DE RISCO (PROTEÇÃO)
    # =========================================================
    def monitor_protection(self, current_price):
        if not self.is_positioned: return None
    
        # Cálculo do PnL em porcentagem (0.01 = 1%)
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.side == "BUY" else (self.entry_price - current_price) / self.entry_price
        changed = False
        
        # 1. BREAK-EVEN RÁPIDO (Proteção de Capital)
        # Se bater 0.7% de lucro, move o Stop para o preço de entrada + taxas.
        if not self.be_activated and pnl_pct >= getattr(self, 'min_pnl_be', 0.007):
            self.be_activated = True
            self.sl_price = self.entry_price * (1.0005 if self.side == "BUY" else 0.9995)
            changed = True
    
        # 2. SAÍDA PARCIAL (Garante o pão)
        # Se bater 1.5% de lucro, fecha metade da posição.
        if not self.partial_taken and pnl_pct >= 0.015:
            self.partial_taken = True
            return "PARTIAL_EXIT"
    
        # 3. TRAILING STOP DINÂMICO (O segredo dos 100% de lucro)
        # Quando a trade passa de 2.5% de lucro, o stop segue o preço a uma distância de 1.5%.
        # Se a moeda subir 10%, seu stop estará travado em 8.5% de lucro!
        if pnl_pct >= 0.025:
            distancia_respiro = getattr(self, 'distancia_respiro', 0.015)
            
            if self.side == "BUY":
                novo_sl = current_price * (1 - distancia_respiro)
                if novo_sl > self.sl_price:
                    self.sl_price = novo_sl
                    changed = True
            else: # SELL (Short)
                novo_sl = current_price * (1 + distancia_respiro)
                if self.sl_price == 0 or novo_sl < self.sl_price:
                    self.sl_price = novo_sl
                    changed = True
    
        return "UPDATE_SL" if changed else None

    def is_market_safe(self, current_time=None):
        if current_time is None:
            dt = datetime.datetime.now()
        else:
            dt = pd.Timestamp(current_time)
        return not (dt.minute < 2 or dt.minute > 58)

    def add_new_candle(self, timeframe, candle_data):
        # Seleciona o deque correto
        target_deque = self.candles_1m if timeframe == "1m" else self.candles_15m
        
        # Verifica se é atualização da mesma vela ou uma nova
        if len(target_deque) > 0 and target_deque[-1]['timestamp'] == candle_data['timestamp']:
            target_deque[-1].update(candle_data)
        else:
            target_deque.append(candle_data)

        if timeframe == "1m":
            self._dirty_1m = True
        else:
            self._dirty_15m = True

    def _sync_dataframes(self):
        if self._dirty_1m:
            self.data_1m = pd.DataFrame(list(self.candles_1m))
            self._dirty_1m = False
        if self._dirty_15m:
            self.data_15m = pd.DataFrame(list(self.candles_15m))
            self._dirty_15m = False
            
    def sync_position(self, side, entry_price, sl_price, tp_price):
        """Sincroniza o estado interno com a realidade da corretora."""
        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = float(entry_price)
        self.sl_price = float(sl_price) if sl_price else 0
        self.tp_price = float(tp_price) if tp_price else 0
        
        # Se já estivermos no lucro no momento do restart, ativa o BE preventivamente
        pnl_at_sync = (self.entry_price - self.sl_price) / self.entry_price if self.side == "BUY" else (self.sl_price - self.entry_price) / self.entry_price
        if abs(pnl_at_sync) < 0.001: # Se o SL está colado no preço de entrada
             self.be_activated = True
             
        log.info(f"🔄 [{self.symbol}] Estado sincronizado: {self.side} @ {self.entry_price}")