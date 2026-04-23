import pandas as pd
import numpy as np
import datetime
import logging
from collections import deque as python_deque

from src.signal_formatter import TradeSignalBuilder, SignalProfile
from src.mack_compliance import MackCompliance, PositionSizer
from src.fibonacci_manager import FibonacciManager
from src.indicator_scorer import IndicatorScorer
from src.indicators import TechnicalIndicators

log = logging.getLogger(__name__)


def get_leverage_for_symbol(symbol: str) -> int:
    """⚡ Leverage 10x para BTC"""
    return 10  # BTC only configuration

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
        
        # ⚡ LEVERAGE DINÂMICO
        self.base_leverage = get_leverage_for_symbol(symbol)  # 5x ou 10x
        
        # 📊 PARÂMETROS DE ENTRADA (Scalping - Modo Agressivo)
        self.min_15m_candles = 200
        self.min_adx = 1                    # MÍNIMO ABSOLUTO: 1 (praticamente desativado)
        self.rsi_overbought = 70            # Filtro: Rejeita compra se RSI muito alto (exaustão)
        self.rsi_oversold = 30              # Filtro: Rejeita venda se RSI muito baixo (exaustão)
        
<<<<<<< HEAD
        # 🔧 Filtros e controles
        self.use_regime_filter = False      # Desativado por enquanto
        self.invert_signal = False          # Desativado por enquanto
=======
        # Cascata de TPs (não mais TRAILING STOP)
        self.use_regime_filter = False      # ❌ COMPLETAMENTE DESATIVADO: remove regime gap check
        
        self.invert_signal = False          # Alterar no main.py para SOL/XRP/AVAX
        self.allow_long = True
        self.allow_short = True
>>>>>>> parent of b3cd799 (feat: versao estavel de btc com aumento de risco por trade)
        
        # Regime-aware parameters
        self.current_regime = "NORMAL"      # COLD, LATERAL, NORMAL, HOT
        self.regime_params_cold = {
            "min_volatilidade_pct": 0.00001,  # EXTREMAMENTE RELAXADO: 0.001%
            "volume_multiplier": 0.5,        # 50% de média
            "min_adx": 1,                    # MÍNIMO: 1
            "require_volume_peak": False,    # Desativado
        }
        self.regime_params_lateral = {
            "min_volatilidade_pct": 0.00001,  # EXTREMAMENTE RELAXADO: 0.001%
            "volume_multiplier": 0.7,        # 70% de média
            "min_adx": 1,                    # MÍNIMO: 1
            "require_volume_peak": False,    # Desativado
        }
        self.regime_params_normal = {
            "min_volatilidade_pct": 0.00001,  # EXTREMAMENTE RELAXADO: 0.001%
            "volume_multiplier": 0.8,        # 80% de média
            "min_adx": 1,                    # MÍNIMO: 1
            "require_volume_peak": False,    # Desativado
        }
        self.regime_params_hot = {
            "min_volatilidade_pct": 0.00001,  # EXTREMAMENTE RELAXADO: 0.001%
            "volume_multiplier": 1.0,        # 100% de média
            "min_adx": 1,                    # MÍNIMO: 1
            "require_volume_peak": False,    # Desativado
        }
        
        # Controle de Posição
        self.is_positioned = False
        self.side = None 
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.last_hold_reason = "init"
        
        # =========================================================
        # INTEGRAÇÃO MACK - TradeSignalBuilder + Compliance
        # =========================================================
        # TradeSignalBuilder será criado dinamicamente em check_signal()
        # quando houver um sinal válido
        self.compliance = MackCompliance()
        self.position_sizer = PositionSizer()
        self.last_trade_signal = None
        self.account_balance = 100.0  # Será atualizado via main.py
        
<<<<<<< HEAD
=======
        # Risco fixo em 2% (disciplinado conforme Mack)
        self.risk_percent = 0.02  # SEMPRE 2%
        
>>>>>>> parent of b3cd799 (feat: versao estavel de btc com aumento de risco por trade)
        # =========================================================
        # FIBONACCI MANAGER (Estratégias 1, 2, 3)
        # =========================================================
        self.fib_manager = FibonacciManager(atr_pct=0.005)
        self.fibo_confidence = 0.0  # Armazenar confidence para logs
        self.fibo_targets = {}  # Armazenar targets calculados
        
        # =========================================================
        # ⭐ SISTEMA DE PONTUAÇÃO DE INDICADORES
        # =========================================================
        self.indicator_scorer = IndicatorScorer(min_score=3, symbol=symbol)
        self.last_score_result = None  # Último resultado de score

    # =========================================================
    # UTILITÁRIOS DE CÁLCULO (OTIMIZADOS)
    # =========================================================
    def safe_float(self, val):
        try:
            if val is None or str(val).strip() == "": return 0.0
            return float(val)
        except: return 0.0

    def _log_trade_decision(self, status, signal, reason_details, indicators_dict=None):
        """
        Centraliza o logging estruturado de decisões de trade.
        
        Args:
            status: "ACEITADO" ou "REJEITADO"
            signal: "BUY", "SELL", "HOLD"
            reason_details: dict com detalhes da rejeição/aceitação
            indicators_dict: dict com valores de indicadores
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Construir mensagem estruturada
        if status == "ACEITADO":
            emoji = "✅"
            log_level = log.info
        else:
            emoji = "🚫"
            log_level = log.warning
        
        # Linha principal
        main_msg = f"{emoji} [{self.symbol}] {status}: {signal}"
        log_level(main_msg)
        
        # Detalhes estruturados
        reason_msg = f"   Motivo: {reason_details.get('reason', 'N/A')}"
        log_level(reason_msg)
        
        if reason_details.get('details'):
            detail_msg = f"   Detalhes: {reason_details['details']}"
            log_level(detail_msg)
        
        # Indicadores (se fornecido)
        if indicators_dict:
            ind_msg = (
                f"   Indicadores: "
                f"ADX={indicators_dict.get('adx', 0):.1f} | "
                f"RSI={indicators_dict.get('rsi', 0):.1f} | "
                f"ATR%={indicators_dict.get('atr_pct', 0):.4f} | "
                f"Vol={indicators_dict.get('vol', 0):.2f}"
            )
            log_level(ind_msg)

    def detect_market_regime(self, df_1m):
        """Detecta regime de mercado baseado em ATR e ADX."""
        if len(df_1m) < 30:
            return "NORMAL"
        
        recent = df_1m.tail(30)
        atr_pct = TechnicalIndicators.calculate_atr_pct(recent)
        adx = TechnicalIndicators.calculate_adx(df_1m).iloc[-1]
        
        # 🔥 HOT: ATR MUITO alto (volatilidade extrema >0.008 = 0.8%)
        if atr_pct >= 0.0080:
            return "HOT"
        # 🔥 HOT: ATR alto (0.003 a 0.008 = 0.3% a 0.8%)
        elif atr_pct >= 0.0030:
            return "HOT"
        # 🧊 COLD: ATR muito baixo
        elif atr_pct < 0.0010 and adx < 20:
            return "COLD"
        # 〰️ LATERAL: ADX muito baixo (sem tendência)
        elif adx < 15 and atr_pct < 0.0018:
            return "LATERAL"
        # ✅ NORMAL: tudo dentro da normalidade
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
        results['rsi_1m'] = TechnicalIndicators.calculate_rsi(df_1m['close']).iloc[-1]
        results['adx_1m'] = TechnicalIndicators.calculate_adx(df_1m).iloc[-1]
        
        # ATR para volatilidade
        results['atr_pct'] = TechnicalIndicators.calculate_atr_pct(df_1m)
        
        # Volume Divergence
        if len(df_1m) >= 5:
            vol_recent = df_1m['volume'].iloc[-1]
            vol_avg5 = df_1m['volume'].iloc[-5:-1].mean()
            vol_momentum = vol_recent / vol_avg5 if vol_avg5 > 0 else 1.0
            results['volume_divergence_ok'] = vol_momentum > 0.40  # Mínimo 40% de momentum
            results['volume_momentum'] = vol_momentum
        else:
            results['volume_divergence_ok'] = True
            results['volume_momentum'] = 1.0
        
        return results

    # =========================================================
    # LÓGICA DE SINAL
    # =========================================================
    def check_signal(self, current_time=None, market_sentiment="NEUTRAL"):
        try:
            self._sync_dataframes()
            self.last_hold_reason = "avaliando"
            
            # ====== REJEIÇÃO 1: PROTEÇÃO DE HORÁRIO ======
            if not self.is_market_safe(current_time):
                self.last_hold_reason = "protecao virada de hora (minuto 00/01/59)"
                self._log_trade_decision(
                    "REJEITADO", "HOLD",
                    {
                        "reason": "Proteção de virada de hora (volatilidade errática)",
                        "details": f"Horário atual em minuto 00/01/59 não permitido"
                    }
                )
                return "HOLD", 0
            
            # ====== REJEIÇÃO 2: DADOS INSUFICIENTES ======
            if len(self.data_1m) < 40 or len(self.data_15m) < self.min_15m_candles:
                self.last_hold_reason = f"dados insuficientes 1m={len(self.data_1m)} 15m={len(self.data_15m)}"
                self._log_trade_decision(
                    "REJEITADO", "HOLD",
                    {
                        "reason": "Dados insuficientes para análise",
                        "details": f"Candles disponíveis: 1m={len(self.data_1m)}/40 | 15m={len(self.data_15m)}/{self.min_15m_candles}"
                    }
                )
                return "HOLD", 0

            # 1. Preparação de Dados e Indicadores
            ind = self.calculate_indicators(self.data_1m.tail(100), self.data_15m.tail(250))
            
            curr_price = self.data_1m['close'].iloc[-1]
            curr_vol = self.data_1m['volume'].iloc[-1]
            avg_vol = self.data_1m['volume'].tail(20).mean()

            # ====== REJEIÇÃO 3: REGIME FRACO ======
            if self.use_regime_filter and ind['regime_gap'] < 0.010:  # AUMENTADO: 0.010 (era 0.0015 - muito rigoroso)
                self.last_hold_reason = f"regime fraco gap={ind['regime_gap']:.4f} (<0.010)"
                self._log_trade_decision(
                    "REJEITADO", "HOLD",
                    {
                        "reason": "Regime fraco - Mercado sem tendência clara",
                        "details": f"Regime gap: {ind['regime_gap']:.4f} < 0.010 | Regime: {ind['market_regime']}"
                    },
                    {
                        "adx": ind['adx_1m'],
                        "rsi": ind['rsi_1m'],
                        "atr_pct": ind['atr_pct'],
                        "vol": curr_vol
                    }
                )
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
            volume_confirmado = True  # DESATIVADO: sem restrição de volume
            
            # Modo SIGNAL-FIRST para regimes frios: relaxa volume se há sinal técnico
            if not self.require_volume_peak and tendencia_forte and ind['atr_pct'] >= 0.0005:
                pico_vol = True

            # Condição de COMPRA - SIMPLIFICADA: apenas RSI check
            if ind['rsi_1m'] < self.rsi_overbought:  # Apenas verifica RSI não está em exaustão
                raw_signal = "BUY"
                min_rec = self.data_1m['low'].tail(10).min()
                dist_sl = max(abs(curr_price - min_rec * 0.999), curr_price * 0.015)

            # Condição de VENDA - SIMPLIFICADA: apenas RSI check
            elif ind['rsi_1m'] > self.rsi_oversold:  # Apenas verifica RSI não está em exaustão
                raw_signal = "SELL"
                max_rec = self.data_1m['high'].tail(10).max()
                dist_sl = max(abs(max_rec * 1.001 - curr_price), curr_price * 0.015)

            # 4. Filtros de Sentimento e Inversão
            final_signal = raw_signal

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
                if len(motivos) == 0:
                    motivos.append("sem sinal técnico claro (ADX baixo, RSI neutro)")
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
                # Calcular SL e TP1 base com RR 1:2 mínimo
                tp1_distance = dist_sl * 2  # TP1 é 2x a distância do SL (garante RR 1:2)
                
                if final_signal == "BUY":
                    tp1_price = curr_price + tp1_distance
                    sl_price = curr_price - dist_sl
                else:  # SELL
                    tp1_price = curr_price - tp1_distance
                    sl_price = curr_price + dist_sl
                
                # Validar regra 1: Risk:Reward 1:2 mínimo
                validate_result = self.compliance.validate_rr_ratio(
                    entry=curr_price,
                    sl=sl_price,
                    tp=tp1_price,
                    side="LONG" if final_signal == "BUY" else "SHORT",
                    symbol=self.symbol
                )
                
                if not validate_result['valid']:
                    # ====== REJEIÇÃO 9: RR VIOLADA ======
                    self._log_trade_decision(
                        "REJEITADO", final_signal,
                        {
                            "reason": "Razão Risk:Reward insuficiente (Mack Rule #1)",
                            "details": f"RR encontrada: {validate_result['ratio']}:1 | Mínimo exigido: 1:2"
                        },
                        {
                            "adx": ind['adx_1m'],
                            "rsi": ind['rsi_1m'],
                            "atr_pct": ind['atr_pct'],
                            "vol": curr_vol
                        }
                    )
                    final_signal = "HOLD"
                    self.last_hold_reason = f"RR violada: {validate_result['ratio']}:1 < 1:2"
                else:
                    # ⭐ VALIDAÇÃO 2: SCORE DE INDICADORES
                    score_result = self.indicator_scorer.calculate_score(
                        df=self.data_1m.tail(100),
                        min_adx=self.min_adx,
                        min_volatilidade=self.min_volatilidade_pct,
                        volume_multiplier=self.volume_multiplier
                    )
                    
                    self.last_score_result = score_result
                    
                    try:
                        # 3. Calcular quantidade com risco máximo 2% (DISCIPLINADO)
                        qty = self.position_sizer.calculate_qty(
                            account_balance=self.account_balance,
                            entry_price=curr_price,
                            sl_price=sl_price,
                            risk_percent=0.02,  # FIXO EM 2% SEMPRE
                            side="LONG" if final_signal == "BUY" else "SHORT"
                        )
                        
                        # 4. Criar TradeSignal com TP único
                        signal = (TradeSignalBuilder(self.symbol, final_signal, curr_price)
                            .with_stops(sl_price, tp1_price)
                            .with_leverage(10)
                            .with_profile(SignalProfile.BALANCED)
                            .build())
                        
                        self.last_trade_signal = signal
                        self.tp_price = tp1_price
                        
                        # 5. Fibonacci boost (se aplicável)
                        max_15m = self.data_1m['high'].iloc[-16:-1].max()
                        min_15m = self.data_1m['low'].iloc[-16:-1].min()
                        
                        fibo_confidence = self.fib_manager.get_fibo_confidence_boost(
                            curr_price, curr_price, max_15m, min_15m, final_signal
                        )
                        
                        self.fibo_confidence = fibo_confidence['confidence_boost']
                        self.fibo_targets = self.fib_manager.calculate_targets_fibo(
                            curr_price, final_signal, max_15m, min_15m, 
                            atr=ind['atr_pct'] * curr_price  # Converter percentual para absoluto
                        )
                        
                        # ✅ ====== TRADE ACEITO ======
                        self._log_trade_decision(
                            "ACEITADO", final_signal,
                            {
                                "reason": "Todos os critérios validados com sucesso",
                                "details": (
                                    f"Entry: ${curr_price:.8f} | "
                                    f"SL: ${sl_price:.8f} | "
                                    f"TP: ${tp1_price:.8f} | "
                                    f"Qty: {qty:.4f} | "
                                    f"RR: {validate_result['ratio']}:1 | "
                                    f"Score: {score_result['score']}/{score_result['total_indicators']} | "
                                    f"Regime: {self.current_regime} | "
                                    f"Fibo: {fibo_confidence['nearest_level']} (+{fibo_confidence['confidence_boost']:+.2f}%)"
                                )
                            },
                            {
                                "adx": ind['adx_1m'],
                                "rsi": ind['rsi_1m'],
                                "atr_pct": ind['atr_pct'],
                                "vol": curr_vol
                            }
                        )
                    
                    except Exception as e:
                        # ====== REJEIÇÃO 12: ERRO NO SETUP ======
                        self._log_trade_decision(
                            "REJEITADO", final_signal,
                            {
                                "reason": f"Erro ao configurar posição",
                                "details": f"Erro: {str(e)[:100]}"
                            },
                            {
                                "adx": ind['adx_1m'],
                                "rsi": ind['rsi_1m'],
                                "atr_pct": ind['atr_pct'],
                                "vol": curr_vol
                            }
                        )
                        log.error(f"❌ Erro ao criar TradeSignal ({self.symbol}): {e}")
                        final_signal = "HOLD"
                        self.last_hold_reason = f"Erro no setup: {str(e)[:50]}"

            return final_signal, dist_sl

        except Exception as e:
            log.error(f"❌ Erro check_signal ({self.symbol}): {e}")
            return "HOLD", 0

    # =========================================================
    # GESTÃO DE RISCO - CASCATA DE TPS
    # =========================================================
<<<<<<< HEAD
=======
    def check_cascade_tp(self, current_price):
        """
        Monitora cascata de TPs e retorna ação se algum foi atingido.
        
        Retorna: {
            "action": "CLOSE_PARTIAL" | "COMPLETE",
            "tp_hit": 1/2/3,
            "close_percent": quantidade a fechar,
            "new_sl": novo stop loss
        } ou None se nada foi atingido
        """
        
        if not self.is_positioned or self.tp_cascade is None:
            return None
        
        result = self.tp_cascade.check_cascade_hit(current_price)
        
        if result and result.get("action") == "CLOSE_PARTIAL":
            # Atualizar SL conforme cascata determina
            self.sl_price = result["new_sl"]
            
            log.info(
                f"✅ [{self.symbol}] Cascata recomenda: TP{result['tp_hit']} hit\n"
                f"  Fechar: {result['close_percent']}%\n"
                f"  Novo SL: {self.sl_price:.8f}"
            )
            
            return result
        
        return None

>>>>>>> parent of b3cd799 (feat: versao estavel de btc com aumento de risco por trade)
    # =========================================================
    # SINCRONIZAÇÃO E DADOS
    # =========================================================
    def is_market_safe(self, current_time=None):
        dt = datetime.datetime.now() if current_time is None else pd.Timestamp(current_time)
        # Evita apenas o minuto 00 (virada de hora com alta volatilidade)
        return not (dt.minute == 0)  # RELAXADO: apenas bloqueia minuto 0 (era 0,1 e 59)

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
        """
        Sincroniza posição aberta com a estratégia.
        """
        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = self.safe_float(entry_price)
        self.sl_price = self.safe_float(sl_price)
        self.tp_price = self.safe_float(tp_price)
        
        log.info(
            f"🔄 [{self.symbol}] Sincronizado: {self.side} @ {self.entry_price}\n"
            f"  SL: {self.sl_price:.8f}\n"
            f"  TP: {self.tp_price:.8f}"
        )

    def load_historical_data(self, timeframe, candles):
        target = self.candles_1m if timeframe == "1m" else self.candles_15m
        for candle in candles:
            if len(target) == 0 or target[-1]['timestamp'] != candle['timestamp']:
                target.append(candle)
        self._dirty_1m = (timeframe == "1m")
        self._dirty_15m = (timeframe == "15m")
        self._sync_dataframes()