"""
Technical Indicators for BotTrade
Baseado em Teoria de Dow (1h timeframe)
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Optional

log = logging.getLogger(__name__)


class DowTheoryAnalyzer:
    """
    Analisador baseado em Teoria de Dow para timeframe de 1h
    
    Princípios Dow:
    1. Mercado desconta tudo
    2. Existem 3 tendências: primária (longo prazo), secundária, menor
    3. Tendências têm 3 fases: acumulação, tendência, distribuição
    4. Confirmação entre ativos (em cripto, confirmação por volume)
    5. Volume confirma a tendência
    6. Tendência persiste até confirmação clara de reversão
    """
    
    def __init__(self, symbol: str = ""):
        self.symbol = symbol
        self.last_higher_high = None
        self.last_higher_low = None
        self.last_lower_high = None
        self.last_lower_low = None
        self.trend_state = "UNDEFINED"  # UPTREND, DOWNTREND, CONSOLIDATION
        self.phase = "UNDEFINED"  # ACCUMULATION, TREND, DISTRIBUTION
        
    def analyze_dow_1h(self, df: pd.DataFrame) -> Dict:
        """
        Análise completa de Teoria de Dow em 1h
        
        Args:
            df: DataFrame com OHLCV (Open, High, Low, Close, Volume)
            
        Returns:
            Dict com:
            - trend: UPTREND, DOWNTREND, CONSOLIDATION
            - phase: ACCUMULATION, TREND, DISTRIBUTION
            - hh_ll_status: Status de Higher High/Lower Low
            - volume_confirmation: Se volume confirma a tendência
            - support: Nível de suporte mais recente
            - resistance: Nível de resistência mais recente
            - strength: Força da tendência (0-100)
            - signal: "BUY", "SELL", "HOLD"
        """
        if len(df) < 20:
            return {
                'trend': 'UNDEFINED',
                'phase': 'UNDEFINED',
                'hh_ll_status': 'INSUFFICIENT_DATA',
                'volume_confirmation': False,
                'support': df['low'].iloc[-1] if len(df) > 0 else 0,
                'resistance': df['high'].iloc[-1] if len(df) > 0 else 0,
                'strength': 0,
                'signal': 'HOLD'
            }
        
        # 1️⃣ Detectar padrão de HH/HL (uptrend) ou LL/LH (downtrend)
        trend, hh_ll_status = self._detect_trend_by_hh_ll(df)
        
        # 2️⃣ Identificar fase do ciclo
        phase = self._identify_phase(df, trend)
        
        # 3️⃣ Confirmar com volume
        volume_confirmation = self._check_volume_confirmation(df, trend)
        
        # 4️⃣ Encontrar support/resistance
        support, resistance = self._find_support_resistance(df, trend)
        
        # 5️⃣ Calcular força da tendência
        strength = self._calculate_trend_strength(df, trend)
        
        # 6️⃣ Gerar sinal
        signal = self._generate_signal(trend, phase, volume_confirmation, strength)
        
        self.trend_state = trend
        self.phase = phase
        
        return {
            'trend': trend,
            'phase': phase,
            'hh_ll_status': hh_ll_status,
            'volume_confirmation': volume_confirmation,
            'support': support,
            'resistance': resistance,
            'strength': strength,
            'signal': signal,
            'analysis': f"Dow Theory 1h: {trend} em {phase}"
        }
    
    def _detect_trend_by_hh_ll(self, df: pd.DataFrame) -> Tuple[str, str]:
        """
        Detecta tendência pelo padrão de Higher High/Lower Low (UPTREND)
        ou Lower High/Lower Low (DOWNTREND)
        
        🔝 UPTREND: HH (Higher High) + HL (Higher Low)
        🔻 DOWNTREND: LH (Lower High) + LL (Lower Low)
        〰️ CONSOLIDATION: Sem padrão claro
        """
        if len(df) < 5:
            return "CONSOLIDATION", "INSUFFICIENT_DATA"
        
        # Últimos 5 máximos e mínimos (últimas 5 velas de 1h = 5h de análise)
        highs = df['high'].tail(5).values
        lows = df['low'].tail(5).values
        
        # Verificar padrão HH/HL (UPTREND)
        hh_count = 0  # Higher Highs
        hl_count = 0  # Higher Lows
        
        for i in range(1, len(highs)):
            if highs[i] > highs[i-1]:
                hh_count += 1
            if lows[i] > lows[i-1]:
                hl_count += 1
        
        # Verificar padrão LL/LH (DOWNTREND)
        ll_count = 0  # Lower Lows
        lh_count = 0  # Lower Highs
        
        for i in range(1, len(highs)):
            if lows[i] < lows[i-1]:
                ll_count += 1
            if highs[i] < highs[i-1]:
                lh_count += 1
        
        # Classificação
        if hh_count >= 2 and hl_count >= 2:
            status = f"HH({hh_count})/HL({hl_count})"
            return "UPTREND", status
        elif ll_count >= 2 and lh_count >= 2:
            status = f"LL({ll_count})/LH({lh_count})"
            return "DOWNTREND", status
        else:
            status = f"HH({hh_count})/HL({hl_count})/LL({ll_count})/LH({lh_count})"
            return "CONSOLIDATION", status
    
    def _identify_phase(self, df: pd.DataFrame, trend: str) -> str:
        """
        Identifica a fase da tendência (Accumulation, Trend, Distribution)
        usando análise de volume e preço
        
        Fases Dow:
        1. ACCUMULATION: Compradores inteligentes acumulando, volume baixo/médio
        2. TREND: Movimento claro, volume crescente confirmando
        3. DISTRIBUTION: Topo, volume altíssimo, distribuidores saindo
        """
        if len(df) < 14:
            return "UNDEFINED"
        
        # Analisar últimas 14 velas (2 semanas em 1h)
        recent = df.tail(14)
        
        # Calcular volatilidade média
        close_range = recent['close'].max() - recent['close'].min()
        close_avg = recent['close'].mean()
        volatility = (close_range / close_avg) * 100 if close_avg > 0 else 0
        
        # Calcular volume médio e atual
        vol_avg = recent['volume'].mean()
        vol_current = recent['volume'].iloc[-1]
        vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0
        
        # Análise de distribuição de preço
        highs = recent['high'].values
        lows = recent['low'].values
        closes = recent['close'].values
        
        # Em TREND: preço move decididamente, alguns closes fortes
        strong_closes = sum(1 for i in range(len(closes)-1) if abs(closes[i] - closes[i-1]) > (close_range / 14))
        
        if trend == "UPTREND":
            # Em ACCUMULATION uptrend: baixa volatilidade, volume médio
            if volatility < 1.5 and vol_ratio < 1.2:
                return "ACCUMULATION"
            # Em DISTRIBUTION uptrend: alta volatilidade, volume altíssimo (topo)
            elif volatility > 2.5 and vol_ratio > 2.0:
                return "DISTRIBUTION"
            # Em TREND: movimento claro
            else:
                return "TREND"
        
        elif trend == "DOWNTREND":
            # Em ACCUMULATION downtrend: preço estabilizando no fundo
            if volatility < 1.5 and vol_ratio < 1.2:
                return "ACCUMULATION"
            # Em DISTRIBUTION downtrend: queda acelerada com volume
            elif volatility > 2.5 and vol_ratio > 2.0:
                return "DISTRIBUTION"
            else:
                return "TREND"
        
        return "CONSOLIDATION"
    
    def _check_volume_confirmation(self, df: pd.DataFrame, trend: str) -> bool:
        """
        Verifica se volume confirma a tendência (princípio Dow #5)
        
        ✅ Confirmação: Em UPTREND, volume cresce nos dias de alta e diminui nos de queda
        ❌ Sem confirmação: Volume não acompanha o movimento
        """
        if len(df) < 5:
            return False
        
        recent = df.tail(5)
        
        # Calcular mudança de preço vs volume
        price_changes = recent['close'].diff()
        volumes = recent['volume']
        
        # Correlação simples: volume alto quando preço sobe (uptrend)?
        confirmation_count = 0
        for i in range(1, len(price_changes)):
            if trend == "UPTREND":
                # Em uptrend: quando preço sobe, volume deve ser alto
                if price_changes.iloc[i] > 0 and volumes.iloc[i] > volumes.mean():
                    confirmation_count += 1
            elif trend == "DOWNTREND":
                # Em downtrend: quando preço cai, volume deve ser alto
                if price_changes.iloc[i] < 0 and volumes.iloc[i] > volumes.mean():
                    confirmation_count += 1
        
        # Precisa de pelo menos 60% de confirmação
        return confirmation_count >= (len(price_changes) * 0.6)
    
    def _find_support_resistance(self, df: pd.DataFrame, trend: str) -> Tuple[float, float]:
        """
        Encontra suporte e resistência baseado em Dow (pivôs de preço)
        
        UPTREND: Last Higher Low = suporte, Last Higher High = resistência
        DOWNTREND: Last Lower High = resistência, Last Lower Low = suporte
        """
        if len(df) < 10:
            recent_low = df['low'].min()
            recent_high = df['high'].max()
            return recent_low, recent_high
        
        recent = df.tail(10)
        
        if trend == "UPTREND":
            # Suporte: último mínimo local (Higher Low mais recente)
            support = recent['low'].min()
            # Resistência: último máximo local (Higher High mais recente)
            resistance = recent['high'].max()
        elif trend == "DOWNTREND":
            # Resistência: último máximo local
            resistance = recent['high'].max()
            # Suporte: último mínimo local
            support = recent['low'].min()
        else:  # CONSOLIDATION
            support = recent['low'].min()
            resistance = recent['high'].max()
        
        return support, resistance
    
    def _calculate_trend_strength(self, df: pd.DataFrame, trend: str) -> float:
        """
        Calcula força da tendência (0-100)
        
        Fatores:
        - ADX-like: força do movimento direcional
        - Duração da tendência
        - Confirmação de volume
        """
        if len(df) < 5:
            return 0.0
        
        recent = df.tail(20)
        
        # Fator 1: Directional Movement Strength
        ups = sum(1 for i in range(1, len(recent)) if recent['close'].iloc[i] > recent['close'].iloc[i-1])
        downs = len(recent) - ups - 1
        
        if trend == "UPTREND":
            directional_strength = (ups / len(recent)) * 100 if len(recent) > 0 else 0
        elif trend == "DOWNTREND":
            directional_strength = (downs / len(recent)) * 100 if len(recent) > 0 else 0
        else:
            directional_strength = 50.0
        
        # Fator 2: Volume confirmation (0-40 pontos)
        avg_vol = recent['volume'].mean()
        current_vol = recent['volume'].iloc[-1]
        vol_strength = min((current_vol / avg_vol) * 20, 40) if avg_vol > 0 else 0
        
        # Fator 3: Price momentum (0-30 pontos)
        price_range = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0]
        momentum_strength = min(abs(price_range) * 100, 30)
        
        total_strength = directional_strength * 0.3 + vol_strength + momentum_strength
        
        return min(total_strength, 100.0)
    
    def _generate_signal(self, trend: str, phase: str, vol_confirm: bool, strength: float) -> str:
        """
        Gera sinal de trading baseado em Dow Theory
        
        BUY:
        - UPTREND confirmado com volume
        - Entrando em ACCUMULATION (formando base)
        
        SELL:
        - DOWNTREND confirmado com volume
        - Em DISTRIBUTION (topos)
        
        HOLD:
        - CONSOLIDATION
        - Sem confirmação de volume
        """
        
        if trend == "UPTREND":
            if vol_confirm and strength > 60:
                if phase in ["TREND", "ACCUMULATION"]:
                    return "BUY"
            return "HOLD"
        
        elif trend == "DOWNTREND":
            if vol_confirm and strength > 60:
                if phase in ["TREND", "DISTRIBUTION"]:
                    return "SELL"
            return "HOLD"
        
        else:  # CONSOLIDATION
            return "HOLD"


class SMA20Analyzer:
    """
    Analisador de SMA 20 com confluência para Dow Theory
    
    Estratégia:
    - SMA 20 define a tendência intermediária
    - Preço acima SMA 20 = ambiente de ALTA
    - Preço abaixo SMA 20 = ambiente de BAIXA
    - Ângulo da SMA = força da tendência
    
    Confluência com Dow Theory:
    ✅ BUY forte: Dow BUY + Preço acima SMA 20 + SMA ascendente
    ✅ SELL forte: Dow SELL + Preço abaixo SMA 20 + SMA descendente
    ⚠️ Divergência: Dow BUY mas Preço abaixo SMA 20 = HOLD (esperar confirmação)
    """
    
    def __init__(self, symbol: str = ""):
        self.symbol = symbol
        self.sma_20 = None
        self.price_position = "UNDEFINED"  # ABOVE, BELOW
        self.sma_slope = 0.0  # Inclinação (radianos)
        self.sma_momentum = "UNDEFINED"  # RISING, FALLING, NEUTRAL
    
    def analyze_sma20_confluence(self, df: pd.DataFrame, dow_signal: str) -> Dict:
        """
        Análise de SMA 20 com confluência ao sinal Dow Theory
        
        Args:
            df: DataFrame com OHLCV
            dow_signal: Sinal do Dow Theory ("BUY", "SELL", "HOLD")
            
        Returns:
            Dict com:
            - sma_20: Valor da SMA 20
            - price_position: ABOVE ou BELOW (em relação a SMA)
            - sma_slope: Ângulo de inclinação da SMA
            - sma_momentum: RISING, FALLING, NEUTRAL
            - confluence: "STRONG", "WEAK", "DIVERGENCE", "NO_SIGNAL"
            - confluent_signal: Sinal final após validação
        """
        if len(df) < 20:
            return {
                'sma_20': None,
                'price_position': 'INSUFFICIENT_DATA',
                'sma_slope': 0.0,
                'sma_momentum': 'INSUFFICIENT_DATA',
                'confluence': 'INSUFFICIENT_DATA',
                'confluent_signal': 'HOLD'
            }
        
        # 1️⃣ Calcular SMA 20
        sma_20_series = df['close'].rolling(window=20).mean()
        sma_20_value = sma_20_series.iloc[-1]
        current_price = df['close'].iloc[-1]
        
        # 2️⃣ Determinar posição do preço
        price_position = "ABOVE" if current_price > sma_20_value else "BELOW"
        
        # 3️⃣ Calcular slope da SMA (inclinação nos últimos 5 períodos)
        sma_20_last5 = sma_20_series.tail(5).values
        sma_slope = self._calculate_slope(sma_20_last5)
        
        # 4️⃣ Determinar momentum da SMA
        sma_momentum = self._determine_sma_momentum(sma_slope)
        
        # 5️⃣ Verificar confluência com Dow
        confluence, confluent_signal = self._check_confluence(
            dow_signal=dow_signal,
            price_position=price_position,
            sma_momentum=sma_momentum
        )
        
        self.sma_20 = sma_20_value
        self.price_position = price_position
        self.sma_slope = sma_slope
        self.sma_momentum = sma_momentum
        
        return {
            'sma_20': sma_20_value,
            'price_position': price_position,
            'price_vs_sma': f"{((current_price - sma_20_value) / sma_20_value * 100):.2f}%",
            'sma_slope': sma_slope,
            'sma_momentum': sma_momentum,
            'confluence': confluence,
            'confluent_signal': confluent_signal,
            'analysis': f"SMA20: {price_position} | Dow: {dow_signal} | Confluência: {confluence}"
        }
    
    def _calculate_slope(self, values: np.ndarray) -> float:
        """
        Calcula a inclinação (slope) usando regressão linear simples
        
        Retorna:
            slope (radianos): Positivo = ascendente, Negativo = descendente
        """
        if len(values) < 2:
            return 0.0
        
        x = np.arange(len(values))
        y = values
        
        # Regressão linear: y = mx + b
        coefficients = np.polyfit(x, y, 1)
        slope = coefficients[0]
        
        # Normalizar entre -1 e 1 para interpretação
        normalized_slope = np.arctan(slope)
        
        return float(normalized_slope)
    
    def _determine_sma_momentum(self, slope: float) -> str:
        """
        Classifica o momentum da SMA baseado no slope
        
        RISING: SMA subindo (slope > 0.01)
        FALLING: SMA caindo (slope < -0.01)
        NEUTRAL: SMA lateral (|slope| <= 0.01)
        """
        threshold = 0.01
        
        if slope > threshold:
            return "RISING"
        elif slope < -threshold:
            return "FALLING"
        else:
            return "NEUTRAL"
    
    def _check_confluence(self, dow_signal: str, price_position: str, sma_momentum: str) -> Tuple[str, str]:
        """
        Verifica confluência entre Dow Theory e SMA 20
        
        ✅ STRONG: Dow + SMA alignment perfeito
        ⚠️ WEAK: Dow + SMA parcialmente alinhados
        🔄 DIVERGENCE: Dow + SMA desalinhados
        ❌ NO_SIGNAL: Dow HOLD
        
        Returns:
            (confluence_type, confluent_signal)
        """
        
        if dow_signal == "HOLD":
            return "NO_SIGNAL", "HOLD"
        
        # ✅ STRONG CONFLUENCE: BUY
        if (dow_signal == "BUY" and 
            price_position == "ABOVE" and 
            sma_momentum == "RISING"):
            return "STRONG", "BUY"
        
        # ✅ STRONG CONFLUENCE: SELL
        elif (dow_signal == "SELL" and 
              price_position == "BELOW" and 
              sma_momentum == "FALLING"):
            return "STRONG", "SELL"
        
        # ⚠️ WEAK CONFLUENCE: BUY (sem momentum confirmar)
        elif (dow_signal == "BUY" and price_position == "ABOVE"):
            return "WEAK", "BUY"
        
        # ⚠️ WEAK CONFLUENCE: SELL (sem momentum confirmar)
        elif (dow_signal == "SELL" and price_position == "BELOW"):
            return "WEAK", "SELL"
        
        # 🔄 DIVERGENCE: Dow BUY mas preço abaixo SMA
        elif dow_signal == "BUY" and price_position == "BELOW":
            return "DIVERGENCE", "HOLD"
        
        # 🔄 DIVERGENCE: Dow SELL mas preço acima SMA
        elif dow_signal == "SELL" and price_position == "ABOVE":
            return "DIVERGENCE", "HOLD"
        
        return "NO_SIGNAL", "HOLD"
    
    @staticmethod
    def calculate_sma20_series(df: pd.DataFrame) -> pd.Series:
        """
        Retorna série completa de SMA 20 para análise ou plotting
        """
        return df['close'].rolling(window=20).mean()


class ConfluenceSignalValidator:
    """
    Valida sinal final integrando Dow Theory + SMA 20
    
    Scoring:
    - Dow Theory: até 60 pontos
    - SMA 20: até 40 pontos
    - Total: 0-100 (confiabilidade)
    """
    
    def __init__(self):
        self.dow_analyzer = DowTheoryAnalyzer()
        self.sma_analyzer = SMA20Analyzer()
    
    def validate_signal(self, df: pd.DataFrame) -> Dict:
        """
        Valida sinal completo com ambos os indicadores
        
        Returns:
            Dict com sinal final e confiança (0-100)
        """
        if len(df) < 20:
            return {
                'signal': 'HOLD',
                'confidence': 0,
                'reasoning': 'Dados insuficientes',
                'dow_result': None,
                'sma_result': None
            }
        
        # Análise Dow
        dow_result = self.dow_analyzer.analyze_dow_1h(df)
        dow_signal = dow_result['signal']
        dow_strength = dow_result['strength']
        
        # Análise SMA 20 com confluência
        sma_result = self.sma_analyzer.analyze_sma20_confluence(df, dow_signal)
        confluent_signal = sma_result['confluent_signal']
        confluence_type = sma_result['confluence']
        
        # Calcular confiança
        confidence = self._calculate_confidence(dow_strength, confluence_type)
        
        # Gerar reasoning
        reasoning = self._generate_reasoning(dow_result, sma_result, confidence)
        
        return {
            'signal': confluent_signal,
            'confidence': confidence,
            'reasoning': reasoning,
            'dow_result': dow_result,
            'sma_result': sma_result,
            'final_analysis': f"Signal: {confluent_signal} | Confiança: {confidence}% | {confluence_type}"
        }
    
    def _calculate_confidence(self, dow_strength: float, confluence_type: str) -> float:
        """
        Calcula confiança do sinal (0-100)
        """
        base_confidence = dow_strength  # 0-100 do Dow
        
        if confluence_type == "STRONG":
            confidence = base_confidence * 0.95  # 95% da força Dow
        elif confluence_type == "WEAK":
            confidence = base_confidence * 0.70  # 70% da força Dow
        elif confluence_type == "DIVERGENCE":
            confidence = base_confidence * 0.30  # 30% (não confiar muito)
        else:  # NO_SIGNAL
            confidence = 0
        
        return min(confidence, 100.0)
    
    def _generate_reasoning(self, dow_result: Dict, sma_result: Dict, confidence: float) -> str:
        """
        Gera explicação textual do sinal
        """
        parts = [
            f"🎯 Dow: {dow_result['trend']} ({dow_result['phase']}) - {dow_result['signal']}",
            f"📊 SMA: {sma_result['price_position']} - {sma_result['sma_momentum']}",
            f"🔗 Confluência: {sma_result['confluence']}",
            f"💪 Confiança: {confidence:.0f}%"
        ]
        return " | ".join(parts)


class VolumeAnalyzer:
    """
    Analisador de Volume com Divergência Preço/Volume
    
    Teoria: Volume é a energia do mercado
    - Volume + Preço em alta = força genuine
    - Preço em alta + Volume em baixa = divergência bearish (topo iminente)
    - Nova máxima sem volume = fraqueza técnica (revisão iminente)
    - Divergência volume/preço = mudança iminente
    
    Fonte: https://www.youtube.com/watch?v=QfjOgF2_NEw (Volume analysis)
    """
    
    def __init__(self, symbol: str = ""):
        self.symbol = symbol
        self.volume_trend = "UNDEFINED"  # INCREASING, DECREASING, NEUTRAL
        self.price_volume_agreement = True  # Preço e volume concordam?
        self.divergence_type = None  # BULLISH, BEARISH, NONE
        self.new_high_unconfirmed = False  # Novo máximo sem volume
    
    def analyze_volume_divergence(self, df: pd.DataFrame, dow_signal: str) -> Dict:
        """
        Análise completa de Volume com divergência Preço/Volume
        
        Args:
            df: DataFrame com OHLCV
            dow_signal: Sinal do Dow Theory ("BUY", "SELL", "HOLD")
            
        Returns:
            Dict com:
            - volume_trend: Tendência de volume (INCREASING, DECREASING)
            - volume_avg: Volume médio (últimas 20 velas)
            - volume_current: Volume atual
            - volume_ratio: Ratio volume_atual / volume_médio
            - price_volume_agreement: Estão em concordância?
            - divergence_type: BULLISH, BEARISH, NONE
            - new_high_unconfirmed: Novo máximo sem volume?
            - volume_strength: Força do volume (0-100)
            - signal_validation: SE é válido baseado em volume
            - warning: Aviso se há divergência perigosa
        """
        if len(df) < 20:
            return {
                'volume_trend': 'INSUFFICIENT_DATA',
                'volume_avg': None,
                'volume_current': None,
                'volume_ratio': 0,
                'price_volume_agreement': False,
                'divergence_type': 'NONE',
                'new_high_unconfirmed': False,
                'volume_strength': 0,
                'signal_validation': False,
                'warning': 'Dados insuficientes'
            }
        
        # 1️⃣ Calcular volume trend
        recent_20 = df.tail(20)
        volume_avg = recent_20['volume'].mean()
        volume_current = df['volume'].iloc[-1]
        volume_ratio = volume_current / volume_avg if volume_avg > 0 else 1.0
        
        volume_trend = self._determine_volume_trend(recent_20, volume_ratio)
        
        # 2️⃣ Detectar tendência de preço
        price_trend = self._determine_price_trend(recent_20)
        
        # 3️⃣ Verificar concordância preço/volume
        price_volume_agreement = self._check_price_volume_agreement(
            price_trend=price_trend,
            volume_trend=volume_trend
        )
        
        # 4️⃣ Detectar divergências
        divergence_type, divergence_details = self._detect_divergences(
            df, price_trend, volume_trend, price_volume_agreement
        )
        
        # 5️⃣ Verificar novo máximo sem confirmação
        new_high_unconfirmed = self._check_new_high_unconfirmed(df)
        
        # 6️⃣ Calcular força do volume
        volume_strength = self._calculate_volume_strength(
            volume_ratio, price_volume_agreement, divergence_type
        )
        
        # 7️⃣ Validar sinal baseado em volume
        signal_validation, validation_reason = self._validate_signal_by_volume(
            dow_signal, price_volume_agreement, divergence_type,
            new_high_unconfirmed, volume_strength
        )
        
        # 8️⃣ Gerar aviso se necessário
        warning = self._generate_volume_warning(
            divergence_type, new_high_unconfirmed, price_volume_agreement
        )
        
        self.volume_trend = volume_trend
        self.price_volume_agreement = price_volume_agreement
        self.divergence_type = divergence_type
        self.new_high_unconfirmed = new_high_unconfirmed
        
        return {
            'volume_trend': volume_trend,
            'volume_avg': volume_avg,
            'volume_current': volume_current,
            'volume_ratio': volume_ratio,
            'price_trend': price_trend,
            'price_volume_agreement': price_volume_agreement,
            'divergence_type': divergence_type,
            'divergence_details': divergence_details,
            'new_high_unconfirmed': new_high_unconfirmed,
            'volume_strength': volume_strength,
            'signal_validation': signal_validation,
            'validation_reason': validation_reason,
            'warning': warning,
            'analysis': f"Volume: {volume_trend} | Acordo: {'✅' if price_volume_agreement else '❌'} | Divergência: {divergence_type}"
        }
    
    def _determine_volume_trend(self, df: pd.DataFrame, ratio: float) -> str:
        """
        Determina se volume está aumentando, diminuindo ou neutro
        """
        # Calcular slope de volume (últimos 5 períodos)
        vol_last5 = df['volume'].tail(5).values
        
        if len(vol_last5) < 2:
            return "NEUTRAL"
        
        # Comparar começo vs fim
        vol_start = vol_last5[0]
        vol_end = vol_last5[-1]
        vol_change = (vol_end - vol_start) / vol_start if vol_start > 0 else 0
        
        # Também considerar o ratio
        threshold_high = 1.3
        threshold_low = 0.7
        
        if ratio > threshold_high or vol_change > 0.2:
            return "INCREASING"
        elif ratio < threshold_low or vol_change < -0.2:
            return "DECREASING"
        else:
            return "NEUTRAL"
    
    def _determine_price_trend(self, df: pd.DataFrame) -> str:
        """
        Determina se preço está subindo ou descendo nos últimos 5 períodos
        """
        close_last5 = df['close'].tail(5).values
        
        if len(close_last5) < 2:
            return "NEUTRAL"
        
        ups = sum(1 for i in range(1, len(close_last5)) if close_last5[i] > close_last5[i-1])
        downs = len(close_last5) - ups - 1
        
        if ups > downs:
            return "UP"
        elif downs > ups:
            return "DOWN"
        else:
            return "NEUTRAL"
    
    def _check_price_volume_agreement(self, price_trend: str, volume_trend: str) -> bool:
        """
        Verifica se preço e volume estão em concordância
        
        ✅ Concordância:
        - Preço UP + Volume INCREASING
        - Preço DOWN + Volume INCREASING (volume confirma movimento)
        - Qualquer tendência com volume NEUTRAL
        
        ❌ Discordância:
        - Preço UP + Volume DECREASING (divergência bearish!)
        - Preço DOWN + Volume DECREASING (fraqueza)
        """
        if volume_trend == "NEUTRAL":
            return True  # Neutro é aceitável
        
        if price_trend == "UP" and volume_trend == "INCREASING":
            return True  # Força genuína
        
        if price_trend == "DOWN" and volume_trend == "INCREASING":
            return True  # Volume confirma movimento
        
        # Se preço sobe mas volume cai = bearish divergence
        if price_trend == "UP" and volume_trend == "DECREASING":
            return False
        
        # Se preço cai mas volume cai = fraqueza
        if price_trend == "DOWN" and volume_trend == "DECREASING":
            return False
        
        return True
    
    def _detect_divergences(self, df: pd.DataFrame, price_trend: str, 
                           volume_trend: str, agreement: bool) -> Tuple[str, str]:
        """
        Detecta divergências específicas entre preço e volume
        
        DIVERGÊNCIA BEARISH:
        1. Preço em alta mas volume em baixa (topo iminente)
        2. Novos máximos sem confirmação de volume
        
        DIVERGÊNCIA BULLISH:
        - Menos comum, mas volume alto com preço caindo pode indicar fundo
        """
        divergence_details = ""
        
        # Caso 1: Preço UP + Volume DOWN = BEARISH
        if price_trend == "UP" and volume_trend == "DECREASING":
            return "BEARISH", "Preço em alta mas volume em queda = divergência bearish (topo iminente)"
        
        # Caso 2: Preço DOWN + Volume UP = pode ser fundo
        if price_trend == "DOWN" and volume_trend == "INCREASING":
            return "BULLISH", "Preço em queda com volume crescente = acumulação (fundo iminente)"
        
        # Caso 3: Concordância perfeita
        if agreement and price_trend != "NEUTRAL":
            if price_trend == "UP" and volume_trend == "INCREASING":
                return "BULLISH", "Preço e volume em concordância na alta = força genuína"
            elif price_trend == "DOWN" and volume_trend == "NEUTRAL":
                return "BEARISH", "Preço caindo com volume baixo = fraqueza"
        
        return "NONE", "Sem divergência significativa"
    
    def _check_new_high_unconfirmed(self, df: pd.DataFrame) -> bool:
        """
        Verifica se há novo máximo no preço mas SEM confirmação de volume
        
        Sinal de topo iminente (muito importante!)
        """
        if len(df) < 10:
            return False
        
        recent = df.tail(10)
        current_high = df['high'].iloc[-1]
        previous_high = df['high'].iloc[-2:-1].max()
        
        current_vol = df['volume'].iloc[-1]
        vol_avg_prev = df['volume'].iloc[-10:-1].mean()
        
        # É novo máximo?
        is_new_high = current_high > previous_high
        
        # Volume confirma?
        volume_confirms = current_vol > vol_avg_prev * 1.2  # Deve estar 20% acima da média
        
        # Novo máximo SEM volume = problema!
        if is_new_high and not volume_confirms:
            return True
        
        return False
    
    def _calculate_volume_strength(self, volume_ratio: float, 
                                  agreement: bool, divergence_type: str) -> float:
        """
        Calcula força do volume (0-100)
        
        Fatores:
        - Volume ratio: Quanto volume está acima/abaixo da média
        - Concordância: Se está alinhado com preço
        - Tipo de divergência: Se é bullish ou bearish
        """
        base_strength = 50.0  # Baseline
        
        # Fator 1: Volume ratio (0-40 pontos)
        if volume_ratio > 1.5:
            volume_factor = 40
        elif volume_ratio > 1.2:
            volume_factor = 25
        elif volume_ratio > 0.8:
            volume_factor = 0
        else:
            volume_factor = -20  # Volume baixo reduz confiança
        
        # Fator 2: Concordância (0-30 pontos)
        agreement_factor = 30 if agreement else -30
        
        # Fator 3: Tipo de divergência (-20 pontos se bearish)
        divergence_factor = -20 if divergence_type == "BEARISH" else (10 if divergence_type == "BULLISH" else 0)
        
        total_strength = base_strength + volume_factor + agreement_factor + divergence_factor
        
        return max(0, min(total_strength, 100.0))
    
    def _validate_signal_by_volume(self, dow_signal: str, agreement: bool, 
                                   divergence_type: str, new_high_unconfirmed: bool,
                                   volume_strength: float) -> Tuple[bool, str]:
        """
        Valida se o sinal Dow é válido baseado em análise de volume
        
        ✅ Válido: Preço/volume em concordância + sem divergências perigosas
        ❌ Inválido: Divergência bearish + novo máximo sem volume
        """
        
        if dow_signal == "HOLD":
            return True, "HOLD (sem sinal para validar)"
        
        # 🚨 RED FLAGS
        if new_high_unconfirmed:
            return False, "ALERTA: Novo máximo SEM confirmação de volume = FRAQUEZA TÉCNICA"
        
        if divergence_type == "BEARISH" and dow_signal == "BUY":
            return False, "CONFLITO: Dow BUY mas divergência BEARISH volume = topo iminente"
        
        if not agreement and volume_strength < 40:
            return False, f"Preço/volume desalinhados + volume fraco ({volume_strength:.0f}) = sinal duvidoso"
        
        # ✅ VALIDAÇÃO POSITIVA
        if divergence_type == "BULLISH" and dow_signal == "BUY":
            return True, "FORTE: Dow BUY + divergência BULLISH + volume confirma"
        
        if agreement and volume_strength > 60:
            return True, f"VÁLIDO: Preço/volume concordam + força {volume_strength:.0f}%"
        
        # Neutro
        return True, "VALIDAÇÃO OK (sem sinais de alerta)"
    
    def _generate_volume_warning(self, divergence_type: str, new_high_unconfirmed: bool,
                                 agreement: bool) -> Optional[str]:
        """
        Gera aviso se há sinais de perigo
        """
        warnings = []
        
        if new_high_unconfirmed:
            warnings.append("⚠️ NOVO MÁXIMO SEM VOLUME: Topo iminente, esperar confirmação")
        
        if divergence_type == "BEARISH":
            warnings.append("⚠️ DIVERGÊNCIA BEARISH: Preço alto + volume baixo = reversão iminente")
        
        if not agreement and divergence_type != "NONE":
            warnings.append("⚠️ DESALINHAMENTO: Preço e volume em discordância = fraqueza técnica")
        
        return " | ".join(warnings) if warnings else None
    
    def detect_advanced_volume_patterns(self, df: pd.DataFrame, dow_result: Dict = None) -> Dict:
        """
        Detecta 6 padrões avançados de volume
        
        1. Linha de Tendência Alta sendo perdida com volume = BEARISH
        2. Rompimento de máxima sem volume = BEARISH
        3. Volume em expansão numa lateralização pós-alta = BEARISH
        4. Forte volume em baixa movimentação após queda = BULLISH (acumulação)
        5. Volume recorde num fundo = BULLISH (chão encontrado)
        6. Volatilidade caindo + volume concentrado = BEARISH (desinteresse)
        
        Fonte: Análise avançada de volume
        """
        if len(df) < 30:
            return {
                'patterns': [],
                'pattern_signal': 'HOLD',
                'pattern_confidence': 0,
                'details': 'Dados insuficientes'
            }
        
        patterns = []
        signal = 'HOLD'
        confidence = 0
        
        # Padrão 1: Linha de Tendência Alta sendo perdida com volume
        pattern1 = self._detect_trendline_breakdown_high_volume(df)
        if pattern1['detected']:
            patterns.append(pattern1)
            signal = 'SELL'
            confidence = max(confidence, 75)
        
        # Padrão 2: Rompimento de máxima sem volume
        pattern2 = self._detect_breakout_no_volume(df)
        if pattern2['detected']:
            patterns.append(pattern2)
            signal = 'SELL'
            confidence = max(confidence, 70)
        
        # Padrão 3: Volume em expansão numa lateralização pós-alta
        pattern3 = self._detect_expansion_after_rally(df)
        if pattern3['detected']:
            patterns.append(pattern3)
            signal = 'SELL'
            confidence = max(confidence, 65)
        
        # Padrão 4: Forte volume em baixa movimentação = acumulação
        pattern4 = self._detect_accumulation_after_decline(df)
        if pattern4['detected']:
            patterns.append(pattern4)
            if signal == 'HOLD':
                signal = 'BUY'
            confidence = max(confidence, 70)
        
        # Padrão 5: Volume recorde num fundo
        pattern5 = self._detect_volume_climax_at_bottom(df)
        if pattern5['detected']:
            patterns.append(pattern5)
            if signal == 'HOLD':
                signal = 'BUY'
            confidence = max(confidence, 80)
        
        # Padrão 6: Volatilidade baixa + volume concentrado
        pattern6 = self._detect_low_volatility_concentrated_volume(df)
        if pattern6['detected']:
            patterns.append(pattern6)
            signal = 'SELL'
            confidence = max(confidence, 60)
        
        return {
            'patterns': patterns,
            'pattern_signal': signal,
            'pattern_confidence': confidence,
            'count': len(patterns),
            'summary': f"{len(patterns)} padrões detectados | Sinal: {signal} ({confidence:.0f}%)"
        }
    
    def _detect_trendline_breakdown_high_volume(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Linha de Tendência Alta sendo perdida com volume
        
        = Preço rompe suporte com volume alto = BEARISH
        """
        if len(df) < 20:
            return {'detected': False}
        
        recent = df.tail(20)
        
        # Calcular suporte (mínimo dos últimos 20)
        support = recent['low'].min()
        support_idx = recent['low'].idxmin()
        
        # Verificar se preço está acima do suporte
        current_price = df['close'].iloc[-1]
        previous_price = df['close'].iloc[-2]
        
        # Se cruzou suporte para baixo
        crossed_support = previous_price > support and current_price < support
        
        # Volume confirmando
        current_vol = df['volume'].iloc[-1]
        avg_vol = recent['volume'].mean()
        vol_confirms = current_vol > avg_vol * 1.3
        
        if crossed_support and vol_confirms:
            return {
                'detected': True,
                'pattern': 'Trendline Breakdown com Volume',
                'description': f'Suporte {support:.2f} quebrado com volume {current_vol:.0f}',
                'severity': 'HIGH',
                'signal': 'SELL'
            }
        
        return {'detected': False}
    
    def _detect_breakout_no_volume(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Rompimento de máxima sem volume
        
        = Novo máximo mas volume baixo = BEARISH (falso rompimento)
        """
        if len(df) < 20:
            return {'detected': False}
        
        recent = df.tail(20)
        
        # Verificar novo máximo
        current_high = df['high'].iloc[-1]
        recent_max = recent['high'].iloc[:-1].max()
        is_new_high = current_high > recent_max
        
        # Verificar volume baixo
        current_vol = df['volume'].iloc[-1]
        avg_vol = recent['volume'].mean()
        vol_low = current_vol < avg_vol * 0.9
        
        if is_new_high and vol_low:
            return {
                'detected': True,
                'pattern': 'Breakout sem Volume',
                'description': f'Nova máxima {current_high:.2f} sem volume (vol: {current_vol:.0f} < {avg_vol:.0f})',
                'severity': 'HIGH',
                'signal': 'SELL'
            }
        
        return {'detected': False}
    
    def _detect_expansion_after_rally(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Volume em expansão numa lateralização vinda de uma forte alta
        
        = Preço subiu bastante, agora está lateral, mas volume aumenta = BEARISH (distribuição)
        """
        if len(df) < 30:
            return {'detected': False}
        
        recent_30 = df.tail(30)
        recent_10 = df.tail(10)
        
        # Checar se foi uptrend
        price_start = recent_30['close'].iloc[0]
        price_now = recent_30['close'].iloc[-1]
        uptrend = price_now > price_start * 1.05  # Subiu 5%+
        
        # Checar se está lateral agora
        price_range = recent_10['high'].max() - recent_10['low'].min()
        avg_price = recent_10['close'].mean()
        range_pct = (price_range / avg_price) * 100
        is_lateral = range_pct < 2.0  # Range < 2%
        
        # Checar volume em expansão
        vol_start = recent_30['volume'].iloc[0:5].mean()
        vol_now = recent_10['volume'].mean()
        vol_expanding = vol_now > vol_start * 1.3
        
        if uptrend and is_lateral and vol_expanding:
            return {
                'detected': True,
                'pattern': 'Volume Expansão em Lateralização',
                'description': f'Forte alta seguida de lateral, volume crescendo = distribuição',
                'severity': 'MEDIUM',
                'signal': 'SELL'
            }
        
        return {'detected': False}
    
    def _detect_accumulation_after_decline(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Depois de uma queda, forte volume em baixa movimentação = acumulação
        
        = Volume alto durante consolidação após queda = BULLISH (acumulação inteligente)
        """
        if len(df) < 30:
            return {'detected': False}
        
        recent_30 = df.tail(30)
        recent_10 = df.tail(10)
        
        # Checar se foi downtrend
        price_start = recent_30['close'].iloc[0]
        price_min = recent_30['close'].min()
        downtrend = price_start > price_min * 1.05  # Caiu 5%+
        
        # Checar se está estável agora (baixa movimentação)
        price_range = recent_10['high'].max() - recent_10['low'].min()
        avg_price = recent_10['close'].mean()
        range_pct = (price_range / avg_price) * 100
        low_volatility = range_pct < 1.5  # Movimento <1.5%
        
        # Checar volume forte
        vol_avg_total = recent_30['volume'].mean()
        vol_now = recent_10['volume'].mean()
        vol_strong = vol_now > vol_avg_total * 1.2
        
        if downtrend and low_volatility and vol_strong:
            return {
                'detected': True,
                'pattern': 'Acumulação Pós-Queda',
                'description': f'Queda seguida de consolidação com volume forte = compradores acumulando',
                'severity': 'MEDIUM',
                'signal': 'BUY'
            }
        
        return {'detected': False}
    
    def _detect_volume_climax_at_bottom(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Volume recorde num fundo
        
        = Volume muito alto combinado com preço próximo ao mínimo recente = BULLISH (chão encontrado)
        """
        if len(df) < 30:
            return {'detected': False}
        
        recent_30 = df.tail(30)
        
        # Verificar se está perto do mínimo
        current_price = df['close'].iloc[-1]
        min_30 = recent_30['low'].min()
        max_30 = recent_30['high'].max()
        price_range = max_30 - min_30
        distance_from_min = current_price - min_30
        pct_from_min = (distance_from_min / price_range) * 100 if price_range > 0 else 0
        
        near_bottom = pct_from_min < 10  # Preço está nos 10% inferiores do range
        
        # Verificar se volume é recorde
        current_vol = df['volume'].iloc[-1]
        vol_avg = recent_30['volume'].mean()
        vol_max = recent_30['volume'].max()
        is_volume_climax = current_vol > vol_max * 0.9  # Volume acima de 90% do máximo
        
        if near_bottom and is_volume_climax:
            return {
                'detected': True,
                'pattern': 'Volume Climax no Fundo',
                'description': f'Preço no fundo + volume recorde = chão encontrado, reversão esperada',
                'severity': 'HIGH',
                'signal': 'BUY'
            }
        
        return {'detected': False}
    
    def _detect_low_volatility_concentrated_volume(self, df: pd.DataFrame) -> Dict:
        """
        Detecta: Volatilidade caindo + volume concentrado = desinteresse
        
        = ATR/volatilidade muito baixa + volume baixo = inatividade = BEARISH (antes de movimento)
        """
        if len(df) < 30:
            return {'detected': False}
        
        recent_30 = df.tail(30)
        recent_10 = df.tail(10)
        
        # Calcular ATR simples (high - low)
        atr_recent = (recent_30['high'] - recent_30['low']).mean()
        atr_last10 = (recent_10['high'] - recent_10['low']).mean()
        atr_declining = atr_last10 < atr_recent * 0.7  # ATR caiu 30%
        
        # Volatilidade muito baixa
        vol_pct = (atr_last10 / df['close'].iloc[-1]) * 100
        vol_very_low = vol_pct < 0.5  # ATR < 0.5%
        
        # Volume concentrado (baixo)
        vol_current = df['volume'].iloc[-1]
        vol_avg = recent_30['volume'].mean()
        vol_concentrated = vol_current < vol_avg * 0.8
        
        if atr_declining and vol_very_low and vol_concentrated:
            return {
                'detected': True,
                'pattern': 'Volatilidade Baixa + Volume Concentrado',
                'description': f'Volatilidade em mínimos + volume em baixa = desinteresse, movimento vindo',
                'severity': 'LOW',
                'signal': 'HOLD'
            }
        
        return {'detected': False}


class FinalSignalValidator:
    """
    Validador Final: Integra TODOS os 3 indicadores
    
    1. Dow Theory (tendência primária)
    2. SMA 20 (confirmação intermediária)
    3. Volume (validação de força)
    
    Retorna sinal final com confiança total
    """
    
    def __init__(self):
        self.dow_analyzer = DowTheoryAnalyzer()
        self.sma_analyzer = SMA20Analyzer()
        self.volume_analyzer = VolumeAnalyzer()
    
    def validate_complete(self, df: pd.DataFrame) -> Dict:
        """
        Análise completa com todos os 3 indicadores + padrões avançados de volume
        
        Returns:
            Dict com:
            - signal: BUY, SELL, HOLD
            - confidence: 0-100% (confiabilidade total)
            - is_strong: Boolean (confiança > 70)
            - details: Dict com análise detalhada de cada indicador
            - patterns: Padrões de volume detectados
            - warnings: Array de avisos
            - reasoning: Explicação textual
        """
        if len(df) < 20:
            return {
                'signal': 'HOLD',
                'confidence': 0,
                'is_strong': False,
                'details': {},
                'patterns': [],
                'warnings': ['Dados insuficientes'],
                'reasoning': 'Menos de 20 velas (20 horas)',
                'analysis': 'HOLD'
            }
        
        # 1️⃣ ANÁLISE DOW THEORY
        dow_result = self.dow_analyzer.analyze_dow_1h(df)
        dow_signal = dow_result['signal']
        dow_strength = dow_result['strength']
        dow_trend = dow_result['trend']
        
        # 2️⃣ ANÁLISE SMA 20
        sma_result = self.sma_analyzer.analyze_sma20_confluence(df, dow_signal)
        sma_signal = sma_result['confluent_signal']
        sma_confluence = sma_result['confluence']
        
        # 3️⃣ ANÁLISE VOLUME BÁSICO
        volume_result = self.volume_analyzer.analyze_volume_divergence(df, dow_signal)
        volume_valid = volume_result['signal_validation']
        volume_strength = volume_result['volume_strength']
        
        # 4️⃣ ANÁLISE VOLUME AVANÇADO (6 padrões)
        volume_patterns = self.volume_analyzer.detect_advanced_volume_patterns(df, dow_result)
        
        # 5️⃣ INTEGRAÇÃO DOS 3 INDICADORES + PADRÕES
        final_signal = self._integrate_signals_with_patterns(
            dow_signal, sma_signal, volume_result['divergence_type'],
            volume_patterns['pattern_signal']
        )
        final_confidence = self._calculate_final_confidence_advanced(
            dow_strength, sma_confluence, volume_strength, 
            volume_valid, volume_patterns['pattern_confidence']
        )
        
        # 6️⃣ AVISOS
        warnings = self._compile_warnings_advanced(
            dow_result, sma_result, volume_result, volume_patterns
        )
        
        # 7️⃣ REASONING
        reasoning = self._generate_final_reasoning_advanced(
            dow_result, sma_result, volume_result, volume_patterns,
            final_signal, final_confidence
        )
        
        is_strong = final_confidence >= 70
        
        return {
            'signal': final_signal,
            'confidence': final_confidence,
            'is_strong': is_strong,
            'details': {
                'dow': dow_result,
                'sma': sma_result,
                'volume': volume_result,
                'patterns': volume_patterns
            },
            'patterns': volume_patterns.get('patterns', []),
            'warnings': warnings,
            'reasoning': reasoning,
            'analysis': f"Signal: {final_signal} | Confiança: {final_confidence:.0f}% | {'🟢 STRONG' if is_strong else '🟡 WEAK'}"
        }
    
    def _integrate_signals_with_patterns(self, dow_signal: str, sma_signal: str, 
                                        vol_divergence: str, pattern_signal: str) -> str:
        """
        Integra sinais dos 4 componentes (Dow, SMA, Volume, Padrões)
        
        Regra: Maioria simples determina sinal final
        """
        signals = [dow_signal, sma_signal, pattern_signal]
        
        # Contar sinais de cada tipo
        buy_count = signals.count("BUY")
        sell_count = signals.count("SELL")
        hold_count = signals.count("HOLD")
        
        # Maioria?
        if buy_count >= 2:
            return "BUY"
        elif sell_count >= 2:
            return "SELL"
        
        # Sem maioria clara
        return "HOLD"
    
    def _calculate_final_confidence_advanced(self, dow_strength: float, sma_confluence: str,
                                            volume_strength: float, volume_valid: bool,
                                            pattern_confidence: float) -> float:
        """
        Calcula confiança final com padrões avançados de volume
        
        Weighted scoring:
        - Dow: 35% (tendência primária)
        - SMA: 30% (confirmação)
        - Volume Básico: 20% (validação)
        - Padrões: 15% (padrões avançados)
        """
        # Dow: 0-100 → 35%
        dow_component = dow_strength * 0.35
        
        # SMA: STRONG=100, WEAK=65, etc → 30%
        sma_scores = {
            "STRONG": 100,
            "WEAK": 65,
            "DIVERGENCE": 25,
            "NO_SIGNAL": 0
        }
        sma_score = sma_scores.get(sma_confluence, 50)
        sma_component = sma_score * 0.30
        
        # Volume: 0-100 → 20%
        volume_score = volume_strength if volume_valid else volume_strength * 0.6
        volume_component = volume_score * 0.20
        
        # Padrões: 0-100 → 15%
        pattern_component = pattern_confidence * 0.15
        
        total_confidence = dow_component + sma_component + volume_component + pattern_component
        
        return min(total_confidence, 100.0)
    
    def _compile_warnings_advanced(self, dow_result: Dict, sma_result: Dict,
                                   volume_result: Dict, pattern_result: Dict) -> list:
        """
        Compila avisos de todos os indicadores incluindo padrões
        """
        warnings = []
        
        # Avisos Dow
        if dow_result['trend'] == "CONSOLIDATION":
            warnings.append("Dow: Mercado em consolidação")
        
        # Avisos SMA
        if sma_result['confluence'] == "DIVERGENCE":
            warnings.append("SMA: Divergência entre Dow e SMA 20")
        
        # Avisos Volume
        if volume_result['warning']:
            warnings.append(f"Volume: {volume_result['warning']}")
        
        # Avisos Padrões
        if pattern_result['patterns']:
            for pattern in pattern_result['patterns']:
                warnings.append(f"Padrão: {pattern['pattern']} - {pattern['description']}")
        
        return warnings
    
    def _generate_final_reasoning_advanced(self, dow_result: Dict, sma_result: Dict,
                                          volume_result: Dict, pattern_result: Dict,
                                          final_signal: str, final_confidence: float) -> str:
        """
        Gera reasoning detalhado incluindo padrões
        """
        parts = []
        
        # Dow
        parts.append(
            f"🎯 Dow: {dow_result['trend']} → {dow_result['signal']} ({dow_result['strength']:.0f}%)"
        )
        
        # SMA
        parts.append(
            f"📊 SMA: {sma_result['price_position']} ({sma_result['sma_momentum']}) → {sma_result['confluent_signal']}"
        )
        
        # Volume
        parts.append(
            f"📈 Volume: {volume_result['volume_trend']} - {volume_result['divergence_type']} ({volume_result['volume_strength']:.0f}%)"
        )
        
        # Padrões
        if pattern_result['patterns']:
            pattern_names = [p['pattern'] for p in pattern_result['patterns']]
            parts.append(f"🔍 Padrões: {', '.join(pattern_names)}")
        
        # Sinal Final
        strength_emoji = "🟢 FORTE" if final_confidence >= 70 else "🟡 FRACO" if final_confidence >= 40 else "🔴 MUITO FRACO"
        parts.append(
            f"🎯 FINAL: {final_signal} | {final_confidence:.0f}% | {strength_emoji}"
        )
        
        return " | ".join(parts)


class CHoCHAnalyzer:
    """
    CHoCH = Change of Character (Mudança de Caráter)
    
    Detecta quando a tendência MUDA de padrão:
    - UPTREND: Espera HH (Higher High) + HL (Higher Low)
    - DOWNTREND: Espera LL (Lower Low) + LH (Lower High)
    
    CHoCH OCORRE quando:
    - Em UPTREND: quebra do padrão HL (novo lower low)
    - Em DOWNTREND: quebra do padrão LH (novo higher high)
    
    Sinal: FORTE reversão iminente ou pelo menos pullback
    
    Fonte: Smart Money Concepts
    """
    
    def __init__(self):
        self.last_hh = None
        self.last_hl = None
        self.last_ll = None
        self.last_lh = None
    
    def analyze_choch(self, df: pd.DataFrame, current_trend: str) -> Dict:
        """
        Detecta CHoCH baseado na tendência atual
        
        Args:
            df: DataFrame com OHLCV
            current_trend: Tendência atual (UPTREND, DOWNTREND, CONSOLIDATION)
            
        Returns:
            Dict com:
            - choch_detected: bool - Se houve mudança de caráter
            - choch_type: "UPTREND_CHoCH" ou "DOWNTREND_CHoCH"
            - severity: "HIGH" = reversão iminente
            - signal: "SELL" (se UPTREND CHoCH) ou "BUY" (se DOWNTREND CHoCH)
            - details: Descrição do CHoCH
            - level: Nível exato onde ocorreu o CHoCH
        """
        if len(df) < 10:
            return {
                'choch_detected': False,
                'choch_type': None,
                'severity': 'LOW',
                'signal': 'HOLD',
                'details': 'Dados insuficientes',
                'level': None
            }
        
        recent = df.tail(10)
        highs = recent['high'].values
        lows = recent['low'].values
        
        if current_trend == "UPTREND":
            # Procurar último HL (Higher Low)
            last_hl_idx = self._find_last_higher_low(lows)
            
            if last_hl_idx >= 0:
                last_hl_value = lows[last_hl_idx]
                current_low = lows[-1]
                
                # CHoCH = novo low abaixo do último HL
                if current_low < last_hl_value:
                    return {
                        'choch_detected': True,
                        'choch_type': 'UPTREND_CHoCH',
                        'severity': 'HIGH',
                        'signal': 'SELL',
                        'details': f'CHoCH em uptrend: último HL em {last_hl_value:.2f}, novo low em {current_low:.2f} = reversão iminente',
                        'level': current_low,
                        'breakpoint': last_hl_value,
                        'choch_strength': ((last_hl_value - current_low) / last_hl_value) * 100
                    }
        
        elif current_trend == "DOWNTREND":
            # Procurar último LH (Lower High)
            last_lh_idx = self._find_last_lower_high(highs)
            
            if last_lh_idx >= 0:
                last_lh_value = highs[last_lh_idx]
                current_high = highs[-1]
                
                # CHoCH = novo high acima do último LH
                if current_high > last_lh_value:
                    return {
                        'choch_detected': True,
                        'choch_type': 'DOWNTREND_CHoCH',
                        'severity': 'HIGH',
                        'signal': 'BUY',
                        'details': f'CHoCH em downtrend: último LH em {last_lh_value:.2f}, novo high em {current_high:.2f} = reversão iminente',
                        'level': current_high,
                        'breakpoint': last_lh_value,
                        'choch_strength': ((current_high - last_lh_value) / last_lh_value) * 100
                    }
        
        return {
            'choch_detected': False,
            'choch_type': None,
            'severity': 'LOW',
            'signal': 'HOLD',
            'details': 'Sem mudança de caráter detectada',
            'level': None
        }
    
    @staticmethod
    def _find_last_higher_low(lows: np.ndarray) -> int:
        """Encontra índice do último Higher Low"""
        for i in range(len(lows) - 1, 0, -1):
            if lows[i] > lows[i - 1]:
                return i
        return -1
    
    @staticmethod
    def _find_last_lower_high(highs: np.ndarray) -> int:
        """Encontra índice do último Lower High"""
        for i in range(len(highs) - 1, 0, -1):
            if highs[i] < highs[i - 1]:
                return i
        return -1


class POIAnalyzer:
    """
    POI = Point of Interest (Ponto de Interesse)
    
    Identifica níveis onde há LIQUIDEZ acumulada:
    - TOPOS = POI BEARISH (Stop loss de compradores)
    - FUNDOS = POI BULLISH (Stop loss de vendedores)
    
    Estratégia:
    1. Identificar últimos 5 topos/fundos significativos
    2. Marcar como POI
    3. Quando preço aproxima: preparar para "limpeza" (break com volume)
    
    Limpeza de POI = smart money pegando os stops + reversão
    """
    
    def __init__(self, symbol: str = ""):
        self.symbol = symbol
        self.bearish_pois = []  # Topos (resistências)
        self.bullish_pois = []  # Fundos (suportes)
    
    def analyze_poi(self, df: pd.DataFrame, lookback: int = 50) -> Dict:
        """
        Identifica Points of Interest (topos e fundos significativos)
        
        Args:
            df: DataFrame com OHLCV
            lookback: Quantas velas voltar para procurar
            
        Returns:
            Dict com:
            - bearish_pois: List de topos (POI de venda)
            - bullish_pois: List de fundos (POI de compra)
            - nearest_poi: POI mais próximo atualmente
            - distance_to_poi: Distância em %
            - poi_signal: "APPROACH_POI" ou "AWAY"
        """
        if len(df) < lookback:
            lookback = len(df)
        
        recent = df.tail(lookback)
        current_price = df['close'].iloc[-1]
        
        # 1️⃣ Encontrar topos locais (máximos)
        bearish_pois = self._find_swing_highs(recent, min_lookback=5)
        
        # 2️⃣ Encontrar fundos locais (mínimos)
        bullish_pois = self._find_swing_lows(recent, min_lookback=5)
        
        # 3️⃣ Encontrar POI mais próximo
        nearest_poi, distance_pct, poi_type = self._find_nearest_poi(
            current_price, bearish_pois, bullish_pois
        )
        
        # 4️⃣ Sinal se está aproximando de POI
        poi_signal = "APPROACH_POI" if distance_pct < 1.5 else "AWAY"
        
        self.bearish_pois = bearish_pois
        self.bullish_pois = bullish_pois
        
        return {
            'bearish_pois': bearish_pois,  # Topos - liquidez de venda
            'bullish_pois': bullish_pois,  # Fundos - liquidez de compra
            'nearest_poi': nearest_poi,
            'nearest_poi_type': poi_type,  # "BULLISH" ou "BEARISH"
            'distance_to_nearest_pct': distance_pct,
            'poi_signal': poi_signal,
            'details': f"Topos: {len(bearish_pois)} | Fundos: {len(bullish_pois)} | Próximo: {poi_type} em {nearest_poi:.2f} ({distance_pct:.2f}% de distância)"
        }
    
    @staticmethod
    def _find_swing_highs(df: pd.DataFrame, min_lookback: int = 3) -> list:
        """
        Encontra máximos locais (topos significativos)
        """
        highs = df['high'].values
        swing_highs = []
        
        for i in range(min_lookback, len(highs) - min_lookback):
            # Máximo local: maior que vizinhos
            if highs[i] > highs[i - min_lookback:i].max() and highs[i] > highs[i + 1:i + min_lookback + 1].max():
                swing_highs.append({
                    'level': highs[i],
                    'index': i,
                    'bars_ago': len(highs) - i - 1
                })
        
        # Retornar os 5 mais recentes
        return sorted(swing_highs, key=lambda x: x['bars_ago'])[-5:]
    
    @staticmethod
    def _find_swing_lows(df: pd.DataFrame, min_lookback: int = 3) -> list:
        """
        Encontra mínimos locais (fundos significativos)
        """
        lows = df['low'].values
        swing_lows = []
        
        for i in range(min_lookback, len(lows) - min_lookback):
            # Mínimo local: menor que vizinhos
            if lows[i] < lows[i - min_lookback:i].min() and lows[i] < lows[i + 1:i + min_lookback + 1].min():
                swing_lows.append({
                    'level': lows[i],
                    'index': i,
                    'bars_ago': len(lows) - i - 1
                })
        
        # Retornar os 5 mais recentes
        return sorted(swing_lows, key=lambda x: x['bars_ago'])[-5:]
    
    @staticmethod
    def _find_nearest_poi(current_price: float, bearish_pois: list, bullish_pois: list) -> Tuple:
        """
        Encontra POI mais próximo (superior ou inferior)
        """
        nearest_distance = float('inf')
        nearest_poi = current_price
        poi_type = "NONE"
        
        # Checar topos (acima do preço)
        for poi in bearish_pois:
            distance = abs(poi['level'] - current_price)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_poi = poi['level']
                poi_type = "BEARISH"
        
        # Checar fundos (abaixo do preço)
        for poi in bullish_pois:
            distance = abs(poi['level'] - current_price)
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_poi = poi['level']
                poi_type = "BULLISH"
        
        # Converter para %
        distance_pct = (nearest_distance / current_price) * 100 if current_price > 0 else 0
        
        return nearest_poi, distance_pct, poi_type


class FVGAnalyzer:
    """
    FVG = Fair Value Gap (Lacuna de Valor Justo / Imbalance)
    
    Lacunas deixadas quando o preço SALTA rapidamente
    = Desequilíbrio que SEMPRE será preenchido
    
    Tipos:
    1. BULLISH FVG: Gap para cima = preço vai voltar para preencher
    2. BEARISH FVG: Gap para baixo = preço vai voltar para preencher
    
    Estratégia:
    - FVG criado = target futuro para o preço (pullback)
    - Se FVG em trend bullish = usar como suporte
    - Se FVG em trend bearish = usar como resistência
    
    Fonte: Smart Money Concepts (Order Blocks + FVG)
    """
    
    def __init__(self):
        self.active_fvgs = []
    
    def analyze_fvg(self, df: pd.DataFrame) -> Dict:
        """
        Detecta Fair Value Gaps (imbalances)
        
        Args:
            df: DataFrame com OHLCV
            
        Returns:
            Dict com:
            - fvgs: List de FVGs ativos
            - nearest_fvg: FVG mais próximo
            - distance_to_fvg: Distância para preencher (em %)
            - fvg_signal: "CONVERGING" (aproximando) ou "DIVERGING" (afastando)
        """
        if len(df) < 3:
            return {
                'fvgs': [],
                'nearest_fvg': None,
                'distance_to_fvg_pct': 0,
                'fvg_signal': 'HOLD',
                'details': 'Dados insuficientes'
            }
        
        # Detectar FVGs nas últimas 20 velas
        recent = df.tail(20)
        current_price = df['close'].iloc[-1]
        fvgs = self._detect_fvgs(recent)
        
        # Encontrar FVG mais próximo
        nearest_fvg, distance_pct = self._find_nearest_fvg(current_price, fvgs)
        
        # Determinar sinal
        fvg_signal = "CONVERGING" if distance_pct > 0 and distance_pct < 2.5 else "DIVERGING"
        
        self.active_fvgs = fvgs
        
        return {
            'fvgs': fvgs,
            'nearest_fvg': nearest_fvg,
            'distance_to_fvg_pct': distance_pct,
            'fvg_signal': fvg_signal,
            'details': f"{len(fvgs)} FVGs detectados | Próximo: {distance_pct:.2f}% de distância"
        }
    
    @staticmethod
    def _detect_fvgs(df: pd.DataFrame) -> list:
        """
        Detecta Fair Value Gaps (gaps não preenchidos)
        
        BULLISH FVG:
        - Candle 1: fecha em X
        - Candle 2: abre ACIMA de X (deixa gap)
        - Candle 3: fecha ACIMA do gap
        
        BEARISH FVG:
        - Candle 1: fecha em X
        - Candle 2: abre ABAIXO de X (deixa gap)
        - Candle 3: fecha ABAIXO do gap
        """
        fvgs = []
        
        for i in range(len(df) - 2):
            candle1_close = df['close'].iloc[i]
            candle2_open = df['open'].iloc[i + 1]
            candle2_close = df['close'].iloc[i + 1]
            candle3_close = df['close'].iloc[i + 2]
            
            # BULLISH FVG (gap para cima)
            if candle2_open > candle1_close and candle2_close > candle1_close and candle3_close > candle2_open:
                fvg_top = candle1_close
                fvg_bottom = candle2_open
                
                fvgs.append({
                    'type': 'BULLISH',
                    'top': fvg_top,
                    'bottom': fvg_bottom,
                    'midpoint': (fvg_top + fvg_bottom) / 2,
                    'size_pct': ((fvg_bottom - fvg_top) / fvg_top) * 100,
                    'bars_ago': len(df) - i - 3
                })
            
            # BEARISH FVG (gap para baixo)
            elif candle2_open < candle1_close and candle2_close < candle1_close and candle3_close < candle2_open:
                fvg_top = candle2_open
                fvg_bottom = candle1_close
                
                fvgs.append({
                    'type': 'BEARISH',
                    'top': fvg_top,
                    'bottom': fvg_bottom,
                    'midpoint': (fvg_top + fvg_bottom) / 2,
                    'size_pct': ((fvg_bottom - fvg_top) / fvg_top) * 100,
                    'bars_ago': len(df) - i - 3
                })
        
        # Retornar os 5 mais recentes
        return sorted(fvgs, key=lambda x: x['bars_ago'])[-5:]
    
    @staticmethod
    def _find_nearest_fvg(current_price: float, fvgs: list) -> Tuple:
        """
        Encontra FVG mais próximo (que precisa ser preenchido)
        """
        if not fvgs:
            return None, 0
        
        nearest_fvg = None
        nearest_distance = float('inf')
        
        for fvg in fvgs:
            # Distância até o meio do FVG
            distance = abs(fvg['midpoint'] - current_price)
            
            if distance < nearest_distance:
                nearest_distance = distance
                nearest_fvg = fvg
        
        if nearest_fvg:
            distance_pct = (nearest_distance / current_price) * 100
            return nearest_fvg, distance_pct
        
        return None, 0


class LiquidityCaptureAnalyzer:
    """
    Analisador de Captura de Liquidez com Suporte/Resistência
    
    Conceito: Smart Money coloca liquidez em suportes/resistências
    = Stops acumulados desses preços
    
    Padrão típico:
    1. Preço forma suporte (POI BULLISH)
    2. Quebra com volume (LIMPEZA de stops)
    3. Volta para preencher gap/POI (FVG preenchido)
    4. Sai com força (seguindo smart money)
    
    Fonte: Smart Money Concepts - Liquidity Run e Liquidity Sweep
    """
    
    def __init__(self):
        self.choch_analyzer = CHoCHAnalyzer()
        self.poi_analyzer = POIAnalyzer()
        self.fvg_analyzer = FVGAnalyzer()
    
    def analyze_liquidity_capture(self, df: pd.DataFrame, dow_result: Dict, 
                                  support: float, resistance: float) -> Dict:
        """
        Análise completa de captura de liquidez
        
        Args:
            df: DataFrame com OHLCV
            dow_result: Resultado do Dow Theory
            support: Nível de suporte
            resistance: Nível de resistência
            
        Returns:
            Dict com:
            - choch_analysis: Análise de CHoCH
            - poi_analysis: Pontos de interesse (suportes/resistências)
            - fvg_analysis: Fair Value Gaps (imbalances)
            - liquidity_scenario: Cenário de liquidez (BULLISH, BEARISH, NEUTRAL)
            - capture_signal: Sinal de captura de liquidez
        """
        if len(df) < 20:
            return {
                'choch_analysis': None,
                'poi_analysis': None,
                'fvg_analysis': None,
                'liquidity_scenario': 'INSUFFICIENT_DATA',
                'capture_signal': 'HOLD',
                'details': 'Dados insuficientes'
            }
        
        # 1️⃣ Analisar CHoCH (mudança de caráter)
        choch_result = self.choch_analyzer.analyze_choch(df, dow_result['trend'])
        
        # 2️⃣ Analisar POI (pontos de interesse)
        poi_result = self.poi_analyzer.analyze_poi(df)
        
        # 3️⃣ Analisar FVG (lacunas de valor)
        fvg_result = self.fvg_analyzer.analyze_fvg(df)
        
        # 4️⃣ Determinar cenário de liquidez
        liquidity_scenario = self._determine_liquidity_scenario(
            choch_result, poi_result, fvg_result, dow_result
        )
        
        # 5️⃣ Gerar sinal de captura
        capture_signal = self._generate_capture_signal(
            choch_result, poi_result, fvg_result, liquidity_scenario, support, resistance
        )
        
        return {
            'choch_analysis': choch_result,
            'poi_analysis': poi_result,
            'fvg_analysis': fvg_result,
            'liquidity_scenario': liquidity_scenario,
            'capture_signal': capture_signal,
            'support_level': support,
            'resistance_level': resistance,
            'analysis': f"Liquidez: {liquidity_scenario} | CHoCH: {'✅' if choch_result['choch_detected'] else '❌'} | POI: {poi_result['poi_signal']} | FVG: {fvg_result['fvg_signal']}"
        }
    
    def _determine_liquidity_scenario(self, choch_result: Dict, poi_result: Dict,
                                     fvg_result: Dict, dow_result: Dict) -> str:
        """
        Determina o cenário de liquidez baseado em todos os indicadores
        
        BULLISH:
        - DOWNTREND CHoCH (quebra de resistência)
        - Próximo de fundos (POI BULLISH)
        - FVG bullish acima
        
        BEARISH:
        - UPTREND CHoCH (quebra de suporte)
        - Próximo de topos (POI BEARISH)
        - FVG bearish abaixo
        """
        
        # CHoCH detectado?
        if choch_result['choch_detected']:
            if choch_result['choch_type'] == 'DOWNTREND_CHoCH':
                # Quebra de resistência = BULLISH
                return 'BULLISH_LIQUIDITY_SWEEP'
            elif choch_result['choch_type'] == 'UPTREND_CHoCH':
                # Quebra de suporte = BEARISH
                return 'BEARISH_LIQUIDITY_SWEEP'
        
        # POI próximo?
        if poi_result['poi_signal'] == 'APPROACH_POI':
            if poi_result['nearest_poi_type'] == 'BULLISH':
                return 'APPROACHING_BULLISH_POI'
            elif poi_result['nearest_poi_type'] == 'BEARISH':
                return 'APPROACHING_BEARISH_POI'
        
        # FVG convergindo?
        if fvg_result['fvg_signal'] == 'CONVERGING':
            nearest_fvg = fvg_result['nearest_fvg']
            if nearest_fvg:
                if nearest_fvg['type'] == 'BULLISH':
                    return 'CONVERGING_TO_BULLISH_FVG'
                else:
                    return 'CONVERGING_TO_BEARISH_FVG'
        
        # Padrão com Dow
        if dow_result['trend'] == 'UPTREND':
            return 'BULLISH_ENVIRONMENT'
        elif dow_result['trend'] == 'DOWNTREND':
            return 'BEARISH_ENVIRONMENT'
        
        return 'NEUTRAL'
    
    def _generate_capture_signal(self, choch_result: Dict, poi_result: Dict,
                                fvg_result: Dict, scenario: str,
                                support: float, resistance: float) -> str:
        """
        Gera sinal final de captura de liquidez
        
        Lógica:
        - Se CHoCH + próximo de POI = sinal FORTE de captura
        - Se FVG convergindo + POI próximo = preparação para captura
        - Cenário bullish + suporte sendo testado = BUY
        - Cenário bearish + resistência sendo testada = SELL
        """
        current_price = poi_result['nearest_poi'] if poi_result['nearest_poi'] else support
        
        # Sinal FORTE: CHoCH + POI
        if choch_result['choch_detected'] and poi_result['poi_signal'] == 'APPROACH_POI':
            if 'BULLISH' in scenario:
                return 'BUY_LIQUIDITY_SWEEP'
            elif 'BEARISH' in scenario:
                return 'SELL_LIQUIDITY_SWEEP'
        
        # Sinal MÉDIO: Aproximando POI
        if poi_result['poi_signal'] == 'APPROACH_POI':
            if poi_result['nearest_poi_type'] == 'BULLISH':
                return 'PREPARE_BUY'  # Prepara para entrada em suporte
            else:
                return 'PREPARE_SELL'  # Prepara para entrada em resistência
        
        # Sinal MÉDIO: FVG convergindo
        if fvg_result['fvg_signal'] == 'CONVERGING':
            nearest_fvg = fvg_result['nearest_fvg']
            if nearest_fvg and nearest_fvg['type'] == 'BULLISH':
                return 'FVG_FILL_BULLISH'
            elif nearest_fvg and nearest_fvg['type'] == 'BEARISH':
                return 'FVG_FILL_BEARISH'
        
        return 'HOLD'


class EnhancedSignalValidator:
    """
    SISTEMA FINAL COMPLETO: 6 Indicadores Integrados
    
    Componentes:
    1. Dow Theory (35%) - Tendência primária
    2. SMA 20 (30%) - Confirmação intermediária
    3. Volume (20%) - Força + Divergência
    4. CHoCH + POI + FVG (15%) - Smart Money Concepts
    
    Retorna sinal final com confiança integrada
    """
    
    def __init__(self):
        self.dow_analyzer = DowTheoryAnalyzer()
        self.sma_analyzer = SMA20Analyzer()
        self.volume_analyzer = VolumeAnalyzer()
        self.patterns_analyzer = VolumeAnalyzer()  # Usa padrões avançados
        self.confluence_validator = ConfluenceSignalValidator()
        self.liquidity_analyzer = LiquidityCaptureAnalyzer()
        self.final_validator = FinalSignalValidator()
    
    def validate_complete_enhanced(self, df: pd.DataFrame) -> Dict:
        """
        Validação completa com todos os 6 componentes + Smart Money
        
        Returns:
            Dict com:
            - signal: BUY, SELL, HOLD
            - confidence: 0-100%
            - is_strong: boolean
            - component_scores: Scores de cada indicador
            - smart_money_signal: Sinal de captura de liquidez
            - final_reasoning: Explicação detalhada
        """
        if len(df) < 20:
            return {
                'signal': 'HOLD',
                'confidence': 0,
                'is_strong': False,
                'details': 'Dados insuficientes',
                'message': 'Aguardando mais dados (mín. 20 velas)'
            }
        
        # 1️⃣ Análise Dow Theory (35%)
        dow_result = self.dow_analyzer.analyze_dow_1h(df)
        dow_score = (dow_result['strength'] / 100) * 35
        
        # 2️⃣ Análise SMA 20 (30%)
        sma_result = self.sma_analyzer.analyze_sma20_confluence(df, dow_result['signal'])
        sma_base_score = (dow_result['strength'] / 100) * 30
        if sma_result['confluence'] == 'STRONG':
            sma_score = sma_base_score * 1.0
        elif sma_result['confluence'] == 'WEAK':
            sma_score = sma_base_score * 0.7
        elif sma_result['confluence'] == 'DIVERGENCE':
            sma_score = sma_base_score * 0.3
        else:  # NO_SIGNAL
            sma_score = 0
        
        # 3️⃣ Análise Volume (20%)
        volume_result = self.volume_analyzer.analyze_volume_divergence(df, dow_result['signal'])
        volume_score = (volume_result['volume_strength'] / 100) * 20
        
        # 4️⃣ Padrões Avançados de Volume (já incluído em patterns)
        patterns_result = self.patterns_analyzer.detect_advanced_volume_patterns(df)
        pattern_score = (patterns_result['pattern_confidence'] / 100) * 15  # Ajustado
        
        # 5️⃣ Smart Money - Captura de Liquidez (15%)
        liquidity_result = self.liquidity_analyzer.analyze_liquidity_capture(
            df, dow_result, dow_result['support'], dow_result['resistance']
        )
        
        # Score Smart Money baseado em CHoCH + POI + FVG
        smart_money_score = self._calculate_smart_money_score(liquidity_result)
        smart_money_score = (smart_money_score / 100) * 15
        
        # 6️⃣ Calcular score final (total 100)
        total_score = dow_score + sma_score + volume_score + pattern_score + smart_money_score
        
        # Determinar sinal final
        final_signal = self._determine_enhanced_signal(
            dow_result, sma_result, volume_result, patterns_result, liquidity_result
        )
        
        # Calcular força
        is_strong = total_score >= 70 and final_signal != 'HOLD'
        
        # Gerar reasoning
        reasoning = self._generate_enhanced_reasoning(
            dow_result, sma_result, volume_result, patterns_result, 
            liquidity_result, total_score, final_signal
        )
        
        # Gerar avisos
        warnings = self._compile_enhanced_warnings(
            dow_result, sma_result, volume_result, patterns_result, liquidity_result
        )
        
        return {
            'signal': final_signal,
            'confidence': min(total_score, 100.0),
            'is_strong': is_strong,
            'component_scores': {
                'dow': dow_score,
                'sma20': sma_score,
                'volume': volume_score,
                'patterns': pattern_score,
                'smart_money': smart_money_score,
                'total': min(total_score, 100.0)
            },
            'dow_result': dow_result,
            'sma_result': sma_result,
            'volume_result': volume_result,
            'patterns_result': patterns_result,
            'liquidity_result': liquidity_result,
            'smart_money_signal': liquidity_result['capture_signal'],
            'reasoning': reasoning,
            'warnings': warnings,
            'analysis': f"Signal: {final_signal} | Confidence: {total_score:.0f}% | SmartMoney: {liquidity_result['capture_signal']}"
        }
    
    def _calculate_smart_money_score(self, liquidity_result: Dict) -> float:
        """
        Calcula score de Smart Money (0-100) baseado em CHoCH + POI + FVG
        """
        score = 50.0  # Baseline
        
        # CHoCH detectado = +30
        if liquidity_result['choch_analysis']['choch_detected']:
            score += 30
        
        # POI próximo = +20
        if liquidity_result['poi_analysis']['poi_signal'] == 'APPROACH_POI':
            score += 20
        
        # FVG convergindo = +15
        if liquidity_result['fvg_analysis']['fvg_signal'] == 'CONVERGING':
            score += 15
        
        # Cenário alinhado = +10
        if 'BULLISH' in liquidity_result['liquidity_scenario'] or 'BEARISH' in liquidity_result['liquidity_scenario']:
            if 'SWEEP' in liquidity_result['capture_signal']:
                score += 10
        
        return min(score, 100.0)
    
    def _determine_enhanced_signal(self, dow_result: Dict, sma_result: Dict,
                                  volume_result: Dict, patterns_result: Dict,
                                  liquidity_result: Dict) -> str:
        """
        Determina sinal final considerando TODOS os 6 componentes
        
        Lógica:
        - BUY: Dow BUY + SMA alinhada + Volume confirma + Smart Money bullish
        - SELL: Dow SELL + SMA alinhada + Volume confirma + Smart Money bearish
        - HOLD: Conflitos ou sem confluência
        """
        
        dow_signal = dow_result['signal']
        sma_signal = sma_result['confluent_signal']
        vol_agrees = volume_result['price_volume_agreement']
        smart_money_signal = liquidity_result['capture_signal']
        
        # 🔴 RED FLAGS (VETO)
        if volume_result['new_high_unconfirmed']:
            return 'HOLD'  # Novo máximo sem volume = FRAQUEZA
        
        if volume_result['divergence_type'] == 'BEARISH' and dow_signal == 'BUY':
            return 'HOLD'  # Conflito: Dow BUY mas volume divergência bearish
        
        if not vol_agrees and volume_result['volume_strength'] < 40:
            return 'HOLD'  # Preço/volume desalinhados + volume fraco
        
        # ✅ BUY SIGNAL
        if (dow_signal == 'BUY' and 
            sma_signal == 'BUY' and 
            vol_agrees and
            volume_result['divergence_type'] in ['BULLISH', 'NONE']):
            
            # Smart Money confirma?
            if 'BUY' in smart_money_signal or smart_money_signal == 'HOLD':
                return 'BUY'
        
        # ✅ SELL SIGNAL
        if (dow_signal == 'SELL' and 
            sma_signal == 'SELL' and 
            vol_agrees and
            volume_result['divergence_type'] in ['BEARISH', 'NONE']):
            
            # Smart Money confirma?
            if 'SELL' in smart_money_signal or smart_money_signal == 'HOLD':
                return 'SELL'
        
        # ⚠️ SMA + Smart Money podem vencer Dow se confirmarem
        if sma_result['confluence'] == 'STRONG' and sma_signal != 'HOLD':
            if 'SWEEP' in smart_money_signal:
                return sma_signal
        
        return 'HOLD'
    
    def _generate_enhanced_reasoning(self, dow_result: Dict, sma_result: Dict,
                                    volume_result: Dict, patterns_result: Dict,
                                    liquidity_result: Dict, total_score: float,
                                    final_signal: str) -> str:
        """
        Gera reasoning detalhado com todos os 6 componentes
        """
        parts = []
        
        # Scores
        parts.append(f"📊 Scores Ponderados:")
        parts.append(f"   Dow: {dow_result['strength']:.0f}% | SMA: {sma_result['confluence']} | Vol: {volume_result['volume_strength']:.0f}%")
        
        # Tendência
        parts.append(f"\n🎯 Tendência (Dow): {dow_result['trend']} - Fase: {dow_result['phase']}")
        parts.append(f"   Força: {dow_result['strength']:.0f}% | Volume Confirmação: {'✅' if dow_result['volume_confirmation'] else '❌'}")
        
        # SMA
        parts.append(f"\n📈 SMA 20: {sma_result['price_position']} ({sma_result['sma_momentum']})")
        parts.append(f"   Confluência: {sma_result['confluence']} → Sinal: {sma_result['confluent_signal']}")
        
        # Volume
        parts.append(f"\n📊 Volume: {volume_result['volume_trend']} | Acordo P/V: {'✅' if volume_result['price_volume_agreement'] else '❌'}")
        parts.append(f"   Divergência: {volume_result['divergence_type']} | Força: {volume_result['volume_strength']:.0f}%")
        
        # Padrões
        if patterns_result['patterns']:
            parts.append(f"\n🔍 Padrões: {patterns_result['count']} detectados")
            for p in patterns_result['patterns'][:3]:  # Top 3
                parts.append(f"   • {p['pattern']}")
        
        # Smart Money
        parts.append(f"\n💧 Smart Money: {liquidity_result['capture_signal']}")
        parts.append(f"   CHoCH: {'✅' if liquidity_result['choch_analysis']['choch_detected'] else '❌'} | POI: {liquidity_result['poi_analysis']['poi_signal']} | FVG: {liquidity_result['fvg_analysis']['fvg_signal']}")
        
        # Resultado
        strength = "🟢 FORTE" if total_score >= 70 else "🟡 FRACO" if total_score >= 40 else "🔴 MUITO FRACO"
        parts.append(f"\n🎯 FINAL: {final_signal} | {total_score:.0f}% | {strength}")
        
        return "\n".join(parts)
    
    def _compile_enhanced_warnings(self, dow_result: Dict, sma_result: Dict,
                                  volume_result: Dict, patterns_result: Dict,
                                  liquidity_result: Dict) -> list:
        """
        Compila avisos de todos os 6 componentes
        """
        warnings = []
        
        # Avisos Dow
        if dow_result['trend'] == 'CONSOLIDATION':
            warnings.append("🟡 Dow: Mercado em consolidação (sem tendência clara)")
        
        # Avisos SMA
        if sma_result['confluence'] == 'DIVERGENCE':
            warnings.append("🟡 SMA: Divergência entre Dow e SMA 20 (fraco sinal)")
        
        # Avisos Volume
        if volume_result['new_high_unconfirmed']:
            warnings.append("🔴 Volume: NOVO MÁXIMO SEM CONFIRMAÇÃO = topo iminente")
        if volume_result['divergence_type'] == 'BEARISH':
            warnings.append("🟡 Volume: Divergência Bearish detectada (reversão iminente)")
        
        # Avisos Padrões
        if patterns_result['patterns']:
            for p in patterns_result['patterns']:
                if p['severity'] == 'HIGH':
                    warnings.append(f"🔴 Padrão: {p['pattern']} - {p['description']}")
        
        # Avisos Smart Money
        if liquidity_result['choch_analysis']['choch_detected']:
            choch = liquidity_result['choch_analysis']
            warnings.append(f"🟢 CHoCH: {choch['choch_type']} detectado (força: {choch['choch_strength']:.2f}%)")
        
        if liquidity_result['poi_analysis']['poi_signal'] == 'APPROACH_POI':
            poi = liquidity_result['poi_analysis']
            warnings.append(f"🟡 POI: Aproximando de {poi['nearest_poi_type']} POI em {poi['nearest_poi']:.2f}")
        
        return warnings
