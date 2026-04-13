import pandas as pd
import numpy as np
import datetime
import logging
from collections import deque as python_deque

from src.signal_formatter import TradeSignalBuilder, SignalProfile
from src.mack_compliance import MackCompliance, PositionSizer
from src.multi_tp_manager import SMCTPManager

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
        self.rsi_overbought = 70            # Filtro: Rejeita compra se RSI muito alto (exaustão)
        self.rsi_oversold = 30              # Filtro: Rejeita venda se RSI muito baixo (exaustão)
        
        self.min_pnl_be = 0.007             # 0.7% para mover Stop
        self.distancia_respiro = 0.015      # 1.5% de Trailing
        self.use_regime_filter = True       # Ativado por padrão para segurança
        
        self.invert_signal = False          # Alterar no main.py para SOL/XRP/AVAX
        self.allow_long = True
        self.allow_short = True
        
        # Regime-aware parameters
        self.current_regime = "NORMAL"      # COLD, LATERAL, NORMAL, HOT
        self.regime_params_cold = {
            "min_volatilidade_pct": 0.0005,  # 0.05% - RELAXED: volatilidade opcional
            "volume_multiplier": 1.0,        # sem requisito volume (entra com sinal)
            "min_adx": 20,                   # AUMENTADO: tendência REAL (não lateral)
            "atr_multiplier_sl": 1.5,        # SL mais apertado
            "leverage": 5.0,                 # alavancagem reduzida
            "require_volume_peak": True,     # ✅ ATIVADO: requer volume mesmo em COLD
        }
        self.regime_params_lateral = {
            "min_volatilidade_pct": 0.0008,  # 0.08% - RELAXED: volatilidade low-bar
            "volume_multiplier": 1.2,        # 120% - requisito relaxado
            "min_adx": 18,                   # AUMENTADO: requer tendência mais forte
            "atr_multiplier_sl": 1.3,
            "leverage": 3.0,                 # alavancagem baixa
            "require_volume_peak": True,     # ✅ ATIVADO: requer volume em LATERAL
        }
        self.regime_params_normal = {
            "min_volatilidade_pct": 0.0012,  # ligeiramente relaxado (era 0.0014)
            "volume_multiplier": 1.4,        # um pouco menos rígido (era 1.6)
            "min_adx": 25,                   # AUMENTADO para 25: filtra mercados laterais
            "atr_multiplier_sl": 1.8,
            "leverage": 10.0,
            "require_volume_peak": True,     # ✅ Mantém requisito rigoroso
        }
        self.regime_params_hot = {
            "min_volatilidade_pct": 0.0018,  # Relaxado: agora é base para HOT
            "volume_multiplier": 2.0,        # Relaxado: x2.0 em vez de 2.2
            "min_adx": 25,                   # AUMENTADO para 25: requer tendência clara
            "atr_multiplier_sl": 2.0,
            "leverage": 15.0,
            "require_volume_peak": True,     # Mantém volume requirement
        }
        
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
        # INTEGRAÇÃO MACK - TradeSignalBuilder + Compliance
        # =========================================================
        # TradeSignalBuilder será criado dinamicamente em check_signal()
        # quando houver um sinal válido
        self.compliance = MackCompliance()
        self.position_sizer = PositionSizer()
        self.last_trade_signal = None
        self.account_balance = 1000.0
        self.tp_manager = None

    # =========================================================
    # UTILITÁRIOS DE CÁLCULO (OTIMIZADOS)
    # =========================================================
    def safe_float(self, val):
        try:
            if val is None or str(val).strip() == "": return 0.0
            return float(val)
        except: return 0.0

    def detect_market_regime(self, df_1m):
        """Detecta regime de mercado baseado em ATR e ADX."""
        if len(df_1m) < 30:
            return "NORMAL"
        
        recent = df_1m.tail(30)
        tr = pd.concat([recent['high'] - recent['low'],
                        (recent['high'] - recent['close'].shift()).abs(),
                        (recent['low'] - recent['close'].shift()).abs()], axis=1).max(axis=1)
        atr_pct = tr.rolling(14).mean().iloc[-1] / recent['close'].iloc[-1]
        adx = self._calc_adx_single(df_1m).iloc[-1]
        
        # COLD: ATR muito baixo
        if atr_pct < 0.0010 and adx < 20:
            return "COLD"
        # LATERAL: ADX muito baixo (sem tendência)
        elif adx < 15 and atr_pct < 0.0018:
            return "LATERAL"
        # HOT: ATR muito alto (volatilidade reconhecida) - sem requisito ADX
        elif atr_pct >= 0.0018:
            return "HOT"
        # NORMAL: tudo dentro da normalidade
        else:
            return "NORMAL"
    
    def apply_regime_params(self):
        """Aplica parâmetros baseados no regime detectado."""
        params = {
            "COLD": self.regime_params_cold,
            "LATERAL": self.regime_params_lateral,
            "NORMAL": self.regime_params_normal,
            "HOT": self.regime_params_hot,
        }.get(self.current_regime, self.regime_params_normal)
        
        self.min_volatilidade_pct = params["min_volatilidade_pct"]
        self.volume_multiplier = params["volume_multiplier"]
        self.min_adx = params["min_adx"]
        self.require_volume_peak = params.get("require_volume_peak", True)  # Novo: controla se volume é obrigatório

    def calculate_indicators(self, df_1m, df_15m):
        """Calcula apenas o necessário para a tomada de decisão atual."""
        results = {}
        
        # Detecta regime e aplica parâmetros
        self.current_regime = self.detect_market_regime(df_1m)
        self.apply_regime_params()
        
        # M15 Indicators
        ema_200_15 = df_15m['close'].ewm(span=200, adjust=False).mean()
        results['ema_200_15'] = ema_200_15.iloc[-1]
        
        # Regime Filter (EMA 50 vs 200)
        ema_50_15 = df_15m['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        results['regime_gap'] = abs(ema_50_15 - results['ema_200_15']) / df_15m['close'].iloc[-1]
        results['market_regime'] = self.current_regime

        # M1 Indicators
        results['ema_20_1m'] = df_1m['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        results['rsi_1m'] = self._calc_rsi_single(df_1m).iloc[-1]
        results['adx_1m'] = self._calc_adx_single(df_1m).iloc[-1]
        
        # ATR para volatilidade
        tr = pd.concat([df_1m['high'] - df_1m['low'], 
                        (df_1m['high'] - df_1m['close'].shift()).abs(), 
                        (df_1m['low'] - df_1m['close'].shift()).abs()], axis=1).max(axis=1)
        results['atr_pct'] = tr.rolling(14).mean().iloc[-1] / df_1m['close'].iloc[-1]
        
        # Volume Divergence: Confirma se volume está apoiando a direção do preço
        # Retorna True se volume está CRESCENDO na última vela (suporta movimento de preço)
        if len(df_1m) >= 5:
            vol_recent = df_1m['volume'].iloc[-1]
            vol_avg5 = df_1m['volume'].iloc[-5:-1].mean()
            vol_trend = vol_recent > vol_avg5  # True se volume increasing
            
            # Calcula também o momentum de volume (aceleração)
            vol_momentum = vol_recent / vol_avg5 if vol_avg5 > 0 else 1.0
            
            results['volume_divergence_ok'] = vol_trend and vol_momentum > 0.95
            results['volume_momentum'] = vol_momentum
        else:
            results['volume_divergence_ok'] = True  # Se dados insuficientes, permite
            results['volume_momentum'] = 1.0
        
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

            # 3. Lógica de Decisão (Regime-Aware)
            raw_signal = "HOLD"
            dist_sl = 0
            
            # ⚡ Ajustes Dinâmicos por Ciclos de Mercado (RSI como proxy)
            rsi = ind['rsi_1m']
            cycle_mult_adx = 1.0
            cycle_mult_vol = 1.0
            
            if rsi > 65:  # Fase quente/overbought - menos volume, mais rigor técnico
                cycle_mult_adx = 1.15    # Exigir ADX mais alto (reduz false signals em picos)
                cycle_mult_vol = 0.9     # Menos exigente com volume (momentum está claro)
            elif rsi < 35:  # Fase fria/oversold - mais volume, menos rigor técnico
                cycle_mult_adx = 0.85    # Mais relaxo com ADX (aproveitando reversão)
                cycle_mult_vol = 1.1     # Mais exigente com volume (validação mais forte)
            
            adjusted_min_adx = self.min_adx * cycle_mult_adx
            adjusted_volume_multiplier = self.volume_multiplier * cycle_mult_vol
            
            pico_vol = curr_vol > (avg_vol * adjusted_volume_multiplier)
            volat_ok = ind['atr_pct'] >= self.min_volatilidade_pct
            tendencia_forte = ind['adx_1m'] >= adjusted_min_adx
            volume_confirmado = ind.get('volume_divergence_ok', True)  # Volume não deve estar em queda extrema
            
            # 🔥 MODO SIGNAL-FIRST para regimes frios: relaxa volume se há sinal técnico
            if not self.require_volume_peak and tendencia_forte and ind['atr_pct'] >= 0.0005:
                # Em COLD/LATERAL: volume não é obrigatório, permite entrada por rompimento puro
                pico_vol = True

            if tendencia_forte and volat_ok and pico_vol and volume_confirmado:
                # M15 Context
                m15_last = self.data_15m.iloc[-1]
                m15_is_green = m15_last['close'] > m15_last['open']
                m15_is_red = m15_last['close'] < m15_last['open']
                
                # Respiro/Máximas
                max_15m = self.data_1m['high'].iloc[-16:-1].max()
                min_15m = self.data_1m['low'].iloc[-16:-1].min()
                
                # Clean Breakout Filter: Valida se o breakout é sólido ou apenas um rebote
                is_clean_breakout_up = False
                is_clean_breakout_down = False
                
                if curr_price > max_15m:
                    # Verificar se o movimento para cima é sólido:
                    # 1. Preço está claramente acima (não na borda)
                    # 2. O movimento foi com volume crescente
                    # 3. A vela anterior também estava tentando sair
                    breakout_margin = (curr_price - max_15m) / max_15m
                    prev_price = self.data_1m['close'].iloc[-2] if len(self.data_1m) >= 2 else max_15m
                    is_clean_breakout_up = (
                        breakout_margin > 0.0001 and  # Mínimo 0.01% acima
                        volume_confirmado and  # Volume deve estar alto
                        prev_price > max_15m * 0.995  # Vela anterior também acima
                    )
                
                if curr_price < min_15m:
                    # Verificar se o movimento para baixo é sólido
                    breakout_margin = (min_15m - curr_price) / min_15m
                    prev_price = self.data_1m['close'].iloc[-2] if len(self.data_1m) >= 2 else min_15m
                    is_clean_breakout_down = (
                        breakout_margin > 0.0001 and  # Mínimo 0.01% abaixo
                        volume_confirmado and  # Volume deve estar alto
                        prev_price < min_15m * 1.005  # Vela anterior também abaixo
                    )

                # Condição de COMPRA
                if is_clean_breakout_up and curr_price > ind['ema_200_15'] and m15_is_green:
                    if ind['rsi_1m'] < self.rsi_overbought: # Filtro de exaustão
                        raw_signal = "BUY"
                        min_rec = self.data_1m['low'].tail(10).min()
                        dist_sl = max(abs(curr_price - min_rec * 0.999), curr_price * 0.015)

                # Condição de VENDA
                elif is_clean_breakout_down and curr_price < ind['ema_200_15'] and m15_is_red:
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
                    motivos.append(f"adx={ind['adx_1m']:.1f}<{adjusted_min_adx:.1f}(base={self.min_adx:.1f}x{cycle_mult_adx:.2f})")
                if not volat_ok:
                    motivos.append(f"atr%={ind['atr_pct']:.4f}<{self.min_volatilidade_pct}")
                if not pico_vol:
                    motivos.append(f"vol={curr_vol:.2f}<x{adjusted_volume_multiplier:.2f}(base={self.volume_multiplier:.2f}x{cycle_mult_vol:.2f})*avg({avg_vol:.2f})")
                if not volume_confirmado:
                    vol_momentum = ind.get('volume_momentum', 1.0)
                    motivos.append(f"vol_divergence (momentum={vol_momentum:.2f})")
                if len(motivos) == 0:
                    motivos.append("sem clean breakout ou RSI exaustao")
                self.last_hold_reason = " | ".join(motivos)
            elif final_signal != "HOLD":
                self.last_hold_reason = (
                    f"entrada={final_signal} adx={ind['adx_1m']:.1f} "
                    f"atr%={ind['atr_pct']:.4f} vol={curr_vol:.2f}/avg20={avg_vol:.2f}"
                )

            # =========================================================
            # 🆕 INTEGRAÇÃO MACK: Validação RR 1:2 Antes de Retornar
            # =========================================================
            if final_signal in ["BUY", "SELL"]:
                # Calcular TP com base na distância SL (RR 1:2 mínimo)
                tp_distance = dist_sl * 2  # TP é 2x a distância do SL
                
                if final_signal == "BUY":
                    tp_price = curr_price + tp_distance
                    sl_price = curr_price - dist_sl
                else:  # SELL
                    tp_price = curr_price - tp_distance
                    sl_price = curr_price + dist_sl
                
                # Validar regra 1: Risk:Reward 1:2 mínimo
                validate_result = self.compliance.validate_rr_ratio(
                    entry=curr_price,
                    sl=sl_price,
                    tp=tp_price,
                    side="LONG" if final_signal == "BUY" else "SHORT",
                    symbol=self.symbol
                )
                
                if not validate_result['valid']:
                    # RR violada, rejeitar sinal
                    log.warning(
                        f"🚫 [{self.symbol}] Sinal {final_signal} REJEITADO: "
                        f"RR {validate_result['ratio']}:1 < 1:2 (Mack Rule #1)"
                    )
                    final_signal = "HOLD"
                    self.last_hold_reason = f"RR violada: {validate_result['ratio']}:1 < 1:2"
                else:
                    # RR aprovada, criar TradeSignal
                    try:
                        signal = (TradeSignalBuilder(self.symbol, final_signal, curr_price)
                            .with_stops(sl_price, tp_price)
                            .with_leverage(10)
                            .with_profile(SignalProfile.BALANCED)
                            .build())
                        
                        self.last_trade_signal = signal
                        log.info(
                            f"✅ [{self.symbol}] TradeSignal criado: {final_signal} @ {curr_price:.8f} "
                            f"| RR: {validate_result['ratio']}:1 | SL: {sl_price:.8f} | TP: {tp_price:.8f}"
                        )
                    except Exception as e:
                        log.error(f"❌ Erro ao criar TradeSignal ({self.symbol}): {e}")

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