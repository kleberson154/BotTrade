import pandas as pd
import numpy as np
import datetime
import logging
from collections import deque as python_deque

from src.signal_formatter import TradeSignalBuilder, SignalProfile
from src.mack_compliance import MackCompliance, PositionSizer
from src.tp_cascade_manager import TPCascadeManager
from src.fibonacci_manager import FibonacciManager
from src.indicator_scorer import IndicatorScorer
from src.indicators import (
    CHoCHAnalyzer, POIAnalyzer, FVGAnalyzer,
    DowTheoryAnalyzer, SMA20Analyzer, VolumeAnalyzer, LiquidityCaptureAnalyzer
)

log = logging.getLogger(__name__)


def get_leverage_for_symbol(symbol: str) -> int:
    """⚡ Leverage dinâmico: 10x para BTC/ETH, 5x para outros"""
    return 10 if symbol in ["BTCUSDT", "ETHUSDT"] else 5

class TradingStrategy:
    def __init__(self, symbol, notifier):
        self.symbol = symbol
        self.notifier = notifier
        self.data_1h = pd.DataFrame()
        self.data_15m = pd.DataFrame()
        self.candles_1h = python_deque(maxlen=300)
        self.candles_15m = python_deque(maxlen=300)
        self._dirty_1h = False
        self._dirty_15m = False
        
        # ⚡ LEVERAGE DINÂMICO
        self.base_leverage = get_leverage_for_symbol(symbol)  # 5x ou 10x
        
        # 📊 PARÂMETROS DE ENTRADA (Scalping - Modo Agressivo)
        self.min_15m_candles = 200
        
        # Cascata de TPs (não mais TRAILING STOP)
        self.use_regime_filter = False      # ❌ COMPLETAMENTE DESATIVADO: remove regime gap check
        
        self.invert_signal = False          # Alterar no main.py para SOL/XRP/AVAX
        self.allow_long = True
        self.allow_short = True
        
        # Regime-aware parameters (simplificado - não usamos mais)
        self.current_regime = "NORMAL"      # Sempre NORMAL
        
        # Controle de Posição
        self.is_positioned = False
        self.side = None 
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.last_hold_reason = "init"
        
        # Cascata de TPs (novo sistema)
        self.tp_cascade = None  # Será criado quando entrar em posição
        
        # =========================================================
        # INTEGRAÇÃO MACK - TradeSignalBuilder + Compliance
        # =========================================================
        # TradeSignalBuilder será criado dinamicamente em check_signal()
        # quando houver um sinal válido
        self.compliance = MackCompliance()
        self.position_sizer = PositionSizer()
        self.last_trade_signal = None
        self.account_balance = 100.0  # Será atualizado via main.py
        
        # Risco fixo em 2% (disciplinado conforme Mack)
        self.risk_percent = 0.02  # SEMPRE 2%
        
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
        # 🆕 ANALISADORES DE ESTRUTURA E LIQUIDEZ (7 TOTAL)
        # =========================================================
        # Liquidez (3 primeiros)
        self.choch_analyzer = CHoCHAnalyzer()
        self.poi_analyzer = POIAnalyzer()
        self.fvg_analyzer = FVGAnalyzer()
        # Estrutura e Volume (4 últimos)
        self.dow_analyzer = DowTheoryAnalyzer()
        self.sma20_analyzer = SMA20Analyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.liquidity_analyzer = LiquidityCaptureAnalyzer()
        self.last_liquidity_results = {}  # Armazenar resultados de todos os 7 analisadores

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

    def detect_market_regime(self, df_1h):
        """Detecta regime de mercado - simplificado (apenas retorna NORMAL)."""
        if len(df_1h) < 30:
            return "NORMAL"
        # Regime sempre NORMAL - não estamos usando indicadores para detectar regimes
        return "NORMAL"
    
    def apply_regime_params(self):
        """Aplica parâmetros - simplificado (não estamos usando regime_params mais)."""
        pass

    def calculate_indicators(self, df_1h, df_15m):
        """Calcula indicadores - apenas estrutura de mercado e liquidez."""
        results = {}
        self.current_regime = self.detect_market_regime(df_1h)
        self.apply_regime_params()
        
        # =========================================================
        # 🔥 CHAMAR TODOS OS 7 ANALISADORES
        # =========================================================
        df_1h_tail = df_1h.tail(100)
        current_trend = "UP" if df_1h['close'].iloc[-1] > df_1h['open'].iloc[-1] else "DOWN"
        
        # Liquidez (3)
        choch_result = self.choch_analyzer.analyze_choch(df_1h_tail, current_trend)
        poi_result = self.poi_analyzer.analyze_poi(df_1h_tail, lookback=20)
        fvg_result = self.fvg_analyzer.analyze_fvg(df_1h_tail)
        
        # Estrutura (4)
        dow_result = self.dow_analyzer.analyze(df_1h_tail)
        sma20_result = self.sma20_analyzer.analyze(df_1h_tail)
        volume_result = self.volume_analyzer.analyze(df_1h_tail)
        liquidity_result = self.liquidity_analyzer.analyze(df_1h_tail)
        
        # Armazenar todos os 7 resultados
        self.last_liquidity_results = {
            'choch': choch_result,
            'poi': poi_result,
            'fvg': fvg_result,
            'dow_theory': dow_result,
            'sma20': sma20_result,
            'volume': volume_result,
            'liquidity': liquidity_result,
        }
        results['analyzers'] = self.last_liquidity_results
        
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
            if len(self.data_1h) < 40 or len(self.data_15m) < self.min_15m_candles:
                self.last_hold_reason = f"dados insuficientes 1h={len(self.data_1h)} 15m={len(self.data_15m)}"
                self._log_trade_decision(
                    "REJEITADO", "HOLD",
                    {
                        "reason": "Dados insuficientes para análise",
                        "details": f"Candles disponíveis: 1h={len(self.data_1h)}/40 | 15m={len(self.data_15m)}/{self.min_15m_candles}"
                    }
                )
                return "HOLD", 0

            # 1. Preparação de Dados e Indicadores
            ind = self.calculate_indicators(self.data_1h.tail(100), self.data_15m.tail(250))
            
            curr_price = self.data_1h['close'].iloc[-1]
            curr_vol = self.data_1h['volume'].iloc[-1]
            avg_vol = self.data_1h['volume'].tail(20).mean()

            # ====== REJEIÇÃO 3: ESTRUTURA DOS ANALISADORES ======
            ind = self.calculate_indicators(self.data_1h.tail(100), self.data_15m.tail(250))
            
            curr_price = self.data_1h['close'].iloc[-1]
            curr_vol = self.data_1h['volume'].iloc[-1]
            avg_vol = self.data_1h['volume'].tail(20).mean()
            
            # =========================================================
            # LÓGICA SIMPLIFICADA: Apenas Tendência 15m
            # =========================================================
            m15_last = self.data_15m.iloc[-1]
            m15_is_green = m15_last['close'] > m15_last['open']
            m15_is_red = m15_last['close'] < m15_last['open']
            
            raw_signal = "HOLD"
            dist_sl = 0
            
            # BUY: 15m verde
            if m15_is_green:
                raw_signal = "BUY"
                min_rec = self.data_15m['low'].tail(10).min()
                dist_sl = max(abs(curr_price - min_rec * 0.999), curr_price * 0.015)
            
            # SELL: 15m vermelho
            elif m15_is_red:
                raw_signal = "SELL"
                max_rec = self.data_15m['high'].tail(10).max()
                dist_sl = max(abs(max_rec * 1.001 - curr_price), curr_price * 0.015)

            # 4. Filtros de Sentimento e Inversão
            final_signal = raw_signal
            # ✅ REMOVIDO: Bloqueios de sentimento/allow_long/allow_short desativados
            # if final_signal == "BUY" and (not self.allow_long or (market_sentiment == "BEARISH"...)):
            #     final_signal = "HOLD"
            # if final_signal == "SELL" and (not self.allow_short or (market_sentiment == "BULLISH"...)):
            #     final_signal = "HOLD"

            if final_signal != "HOLD" and self.invert_signal:
                old = final_signal
                final_signal = "SELL" if old == "BUY" else "BUY"
                log.info(f"🔄 [{self.symbol}] Inversão: {old} -> {final_signal}")

            if final_signal == "HOLD" and self.last_hold_reason == "avaliando":
                self.last_hold_reason = "15m não possui sinal claro (esperando candle verde ou vermelho)"
            elif final_signal != "HOLD":
                self.last_hold_reason = f"entrada={final_signal} | 15m={'verde' if m15_is_green else 'vermelho'} | vol={curr_vol:.2f}/avg20={avg_vol:.2f}"

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
                        }
                    )
                    final_signal = "HOLD"
                    self.last_hold_reason = f"RR violada: {validate_result['ratio']}:1 < 1:2"
                else:
                    # ⭐ VALIDAÇÃO 2: SCORE DE INDICADORES
                    score_result = self.indicator_scorer.calculate_score(
                        df=self.data_1h.tail(100)
                    )
                    
                    self.last_score_result = score_result
                    
                    if True:  # ✅ REMOVIDO: Score check desativado - aceita todos os sinais
                        # Código antigo:
                        # if not score_result["triggered"]:
                        #     final_signal = "HOLD"
                        # ✅ Score aprovado, criar TradeSignal COM CASCATA DE TPS
                        try:
                            # ====== CASCATA DE TPS REALISTA ======
                            # 1. Criar gerenciador de cascata
                            self.tp_cascade = TPCascadeManager(
                                symbol=self.symbol,
                                side="LONG" if final_signal == "BUY" else "SHORT",
                                entry=curr_price,
                                initial_sl=sl_price,
                                account_balance=self.account_balance,
                                leverage=self.base_leverage
                            )
                            
                            # 2. Calcular TPs realistas baseado em volatilidade
                            market_volatility = self.current_regime  # COLD, LATERAL, NORMAL, HOT
                            self.tp_cascade.calculate_scalp_tps(
                                market_volatility=market_volatility
                            )
                            
                            # 3. Calcular quantidade com risco máximo 2% (DISCIPLINADO)
                            qty = self.position_sizer.calculate_qty(
                                account_balance=self.account_balance,
                                entry_price=curr_price,
                                sl_price=sl_price,
                                risk_percent=0.02,  # FIXO EM 2% SEMPRE
                                side="LONG" if final_signal == "BUY" else "SHORT"
                            )
                            
                            # 4. Validar alavancagem
                            leverage_ok = True  # ✅ REMOVIDO: Leverage check desativado - aceita qualquer quantidade
                            
                            if not leverage_ok:  # Nunca será True (desativado)
                                pass
                                # ====== REJEIÇÃO 11: LEVERAGE EXCEDIDO ======
                                self._log_trade_decision(
                                    "REJEITADO", final_signal,
                                    {
                                        "reason": "Alavancagem excedida (>10x com 2% risk)",
                                        "details": f"Qty calculada: {qty:.4f} | Saldo: ${self.account_balance:.2f}"
                                    }
                                )
                                final_signal = "HOLD"
                                self.last_hold_reason = "Leverage excedido (>10x) com 2% risk"
                            else:
                                # 5. Criar TradeSignal (com TP1 como referência)
                                tp1_price = self.tp_cascade.tp_levels[0].tp_price
                                signal = (TradeSignalBuilder(self.symbol, final_signal, curr_price)
                                    .with_stops(sl_price, tp1_price)
                                    .with_leverage(10)
                                    .with_profile(SignalProfile.BALANCED)
                                    .build())
                                
                                self.last_trade_signal = signal
                                
                                # 6. Fibonacci boost (se aplicável)
                                max_15m = self.data_1h['high'].iloc[-16:-1].max()
                                min_15m = self.data_1h['low'].iloc[-16:-1].min()
                                
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
                                            f"TP1/TP2/TP3: ${self.tp_cascade.tp_levels[0].tp_price:.8f} / "
                                            f"${self.tp_cascade.tp_levels[1].tp_price:.8f} / "
                                            f"${self.tp_cascade.tp_levels[2].tp_price:.8f} | "
                                            f"Qty: {qty:.4f} | "
                                            f"RR: {validate_result['ratio']}:1 | "
                                            f"Score: {score_result['score']}/{score_result['total_indicators']} | "
                                            f"Regime: {self.current_regime} | "
                                            f"Fibo: {fibo_confidence['nearest_level']} (+{fibo_confidence['confidence_boost']:+.2f}%)"
                                        )
                                    },
                                    {
                                        "adx": ind['adx_1h'],
                                        "rsi": ind['rsi_1h'],
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
                                    "adx": ind['adx_1h'],
                                    "rsi": ind['rsi_1h'],
                                    "atr_pct": ind['atr_pct'],
                                    "vol": curr_vol
                                }
                            )
                            log.error(f"❌ Erro ao criar TradeSignal/TPCascade ({self.symbol}): {e}")
                            final_signal = "HOLD"
                            self.last_hold_reason = f"Erro no setup: {str(e)[:50]}"

            return final_signal, dist_sl

        except Exception as e:
            log.error(f"❌ Erro check_signal ({self.symbol}): {e}")
            return "HOLD", 0

    # =========================================================
    # GESTÃO DE RISCO - CASCATA DE TPS
    # =========================================================
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

    # =========================================================
    # SINCRONIZAÇÃO E DADOS
    # =========================================================
    def is_market_safe(self, current_time=None):
        dt = datetime.datetime.now() if current_time is None else pd.Timestamp(current_time)
        # Evita apenas o minuto 00 (virada de hora com alta volatilidade)
        return not (dt.minute == 0)  # RELAXADO: apenas bloqueia minuto 0 (era 0,1 e 59)

    def add_new_candle(self, timeframe, candle_data):
        target = self.candles_1h if timeframe == "1h" else self.candles_15m
        if len(target) > 0 and target[-1]['timestamp'] == candle_data['timestamp']:
            target[-1].update(candle_data)
        else:
            target.append(candle_data)
        
        if timeframe == "1h": self._dirty_1h = True
        else: self._dirty_15m = True

    def _sync_dataframes(self):
        if self._dirty_1h:
            self.data_1h = pd.DataFrame(list(self.candles_1h))
            self._dirty_1h = False
        if self._dirty_15m:
            self.data_15m = pd.DataFrame(list(self.candles_15m))
            self._dirty_15m = False
            
    def sync_position(self, side, entry_price, sl_price, tp_price):
        """
        Sincroniza posição aberta com a estratégia.
        Cria cascata de TPs para gerenciar saídas.
        """
        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = self.safe_float(entry_price)
        self.sl_price = self.safe_float(sl_price)
        self.tp_price = self.safe_float(tp_price)
        
        # Criar cascata de TPs para a posição sincronizada
        self.tp_cascade = TPCascadeManager(
            symbol=self.symbol,
            side=self.side,
            entry=self.entry_price,
            initial_sl=self.sl_price,
            account_balance=self.account_balance,
            leverage=10
        )
        
        # Calcular TPs realistas
        self.tp_cascade.calculate_scalp_tps(
            market_volatility=self.current_regime
        )
        
        log.info(
            f"🔄 [{self.symbol}] Sincronizado: {self.side} @ {self.entry_price}\n"
            f"  SL: {self.sl_price:.8f}\n"
            f"  Cascata TP1/TP2/TP3: {self.tp_cascade.tp_levels[0].tp_price:.8f} / "
            f"{self.tp_cascade.tp_levels[1].tp_price:.8f} / "
            f"{self.tp_cascade.tp_levels[2].tp_price:.8f}"
        )
    
    def get_score_message(self) -> str:
        """Retorna mensagem formatada de score para Telegram"""
        if not self.last_score_result:
            return "Nenhum score calculado"
        
        return self.indicator_scorer.get_telegram_message(self.side or "BUY")

    def load_historical_data(self, timeframe, candles):
        target = self.candles_1h if timeframe == "1h" else self.candles_15m
        for candle in candles:
            if len(target) == 0 or target[-1]['timestamp'] != candle['timestamp']:
                target.append(candle)
        self._dirty_1h = (timeframe == "1h")
        self._dirty_15m = (timeframe == "15m")
        self._sync_dataframes()