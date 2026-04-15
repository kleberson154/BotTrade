"""
Market Sentiment Analyzer
Detecta sentimento do mercado e retorna emotion state para trading decisions
"""

import logging
from typing import Dict, Tuple
from datetime import datetime
import pandas as pd
import numpy as np

log = logging.getLogger(__name__)


class MarketSentimentAnalyzer:
    """
    Análise de Sentimento de Mercado
    
    Sentimentos retornados:
    😨 MEDO (Fear): Mercado em pânico, oportunidade de compra
    🛡️ SEGURANÇA (Security): Mercado estável, baixo risco
    🚀 CONFIANÇA (Confidence): Bull run em progresso
    🎲 ESPECULAÇÃO (Speculation): Pump especulativo, volatilidade alta
    🚨 EUFORIA (Euphoria): Topos formados, venda iminente
    🪙 DISTRIBUIÇÃO (Distribution): Weak hands saindo, volume caindo
    """
    
    def __init__(self):
        self.sentiment_history = []
        self.fear_greed_score = 50  # 0-100 (0=Fear, 100=Greed)
        self.current_sentiment = "NEUTRAL"
        self.last_update = None
    
    def calculate_sentiment(self, 
                           btc_dominance: float,
                           volatility_pct: float,
                           rsi_daily: float,
                           volume_ratio: float,
                           market_phase: str,
                           atr_history: pd.DataFrame = None) -> Dict:
        """
        Calcula sentimento baseado em múltiplos indicadores
        
        Args:
            btc_dominance: % de dominância do BTC (0-100)
            volatility_pct: ATR em % (ex: 0.015 = 1.5%)
            rsi_daily: RSI diário (0-100)
            volume_ratio: Volume atual vs volume médio
            market_phase: Fase detectada (ACCUMULATION, BULL_RUN, DISTRIBUTION, BEAR)
            atr_history: DataFrame com histórico de ATR para calcular volatilidade
        
        Returns:
            Dict com sentiment, emoji, profile, e detalhes
        """
        
        # 1. Calcular componentes de medo/ganância
        fear_score = self._calc_fear_score(btc_dominance, rsi_daily, volatility_pct)
        greed_score = 100 - fear_score
        
        # 2. Score de volume
        volume_score = self._calc_volume_score(volume_ratio)
        
        # 3. Score de volatilidade
        volatility_score = self._calc_volatility_score(volatility_pct, atr_history)
        
        # 4. Score de ciclo de mercado
        cycle_score = self._calc_cycle_score(market_phase, rsi_daily)
        
        # 5. Sentimento final integrado
        sentiment_data = self._determine_sentiment(
            fear_greed=(fear_score, greed_score),
            volume_score=volume_score,
            volatility_score=volatility_score,
            cycle_score=cycle_score,
            btc_dominance=btc_dominance,
            phase=market_phase
        )
        
        self.fear_greed_score = (fear_score + greed_score) / 2  # Para logging
        self.current_sentiment = sentiment_data['emotion']
        self.last_update = datetime.now()
        
        return sentiment_data
    
    def _calc_fear_score(self, btc_dominance: float, rsi: float, volatility: float) -> float:
        """
        Calcula score de medo (0-100)
        Alto = medo, Baixo = ganância
        """
        # Componente 1: Dominância (BTC alta = medo)
        if btc_dominance > 60:
            dom_fear = 80
        elif btc_dominance > 55:
            dom_fear = 60
        elif btc_dominance > 50:
            dom_fear = 40
        elif btc_dominance > 45:
            dom_fear = 30
        elif btc_dominance > 40:
            dom_fear = 20
        else:
            dom_fear = 10  # Muito ganância
        
        # Componente 2: RSI (RSI alto = ganância, RSI baixo = medo)
        rsi_fear = 100 - rsi  # Inversão: RSI 80 = 20 fear, RSI 20 = 80 fear
        
        # Componente 3: Volatilidade (volatilidade extrema = medo)
        if volatility > 0.02:
            vol_fear = 70  # Volatilidade extrema
        elif volatility > 0.015:
            vol_fear = 50
        elif volatility > 0.01:
            vol_fear = 30
        elif volatility > 0.005:
            vol_fear = 20
        else:
            vol_fear = 10  # Muito calma
        
        # Média ponderada
        fear_score = (dom_fear * 0.4 + rsi_fear * 0.35 + vol_fear * 0.25)
        
        return max(0, min(100, fear_score))
    
    def _calc_volume_score(self, volume_ratio: float) -> float:
        """
        Calcula score de volume (0-100)
        High volume = atividade, pode ser fear ou greed
        """
        if volume_ratio > 2.0:
            return 90  # Muito volume
        elif volume_ratio > 1.5:
            return 70
        elif volume_ratio > 1.2:
            return 50
        elif volume_ratio > 0.8:
            return 40
        else:
            return 20  # Muito baixo volume
    
    def _calc_volatility_score(self, volatility_pct: float, atr_history: pd.DataFrame = None) -> float:
        """
        Calcula score de volatilidade (0-100)
        0 = sem volatilidade, 100 = volatilidade extrema
        """
        if volatility_pct > 0.025:
            return 95  # Extrema
        elif volatility_pct > 0.020:
            return 85
        elif volatility_pct > 0.015:
            return 70
        elif volatility_pct > 0.010:
            return 50
        elif volatility_pct > 0.005:
            return 30
        else:
            return 10  # Muito baixa
    
    def _calc_cycle_score(self, market_phase: str, rsi_daily: float) -> float:
        """
        Score de fase do ciclo
        ACCUMULATION = compra (ganância), DISTRIBUTION = venda (medo)
        """
        phase_scores = {
            "ACCUMULATION": 20,      # Medo alto, ótima oportunidade
            "BULL_RUN_EARLY": 35,
            "BULL_RUN_STRONG": 60,   # Ganância média
            "DISTRIBUTION": 75,      # Ganância alta (topos)
            "BEAR": 85,              # Muito medo
        }
        
        return phase_scores.get(market_phase, 50)
    
    def _determine_sentiment(self, fear_greed: Tuple, volume_score: float, 
                            volatility_score: float, cycle_score: float, 
                            btc_dominance: float, phase: str) -> Dict:
        """
        Determina sentimento final combinado
        Retorna um dos 6 sentimentos
        """
        fear_score, greed_score = fear_greed
        
        # Lógica de decisão para cada sentimento
        
        # 😨 MEDO: RSI baixo, volatilidade alta, BTC dominante
        if fear_score > 70 and volatility_score > 60 and btc_dominance > 55:
            sentiment = "FEAR"
            emoji = "😨"
            profile = "CONSERVATIVE"
            recommendation = "Evite trades longas, prepare shorts defensivos"
            leverage_mult = 0.5
            risk_mode = "EXTREME_CAUTION"
        
        # 🛡️ SEGURANÇA: Mercado calmo, volatilidade baixa, RSI neutro
        elif volatility_score < 30 and 40 < fear_score < 60 and phase not in ["BEAR", "DISTRIBUTION"]:
            sentiment = "SECURITY"
            emoji = "🛡️"
            profile = "BALANCED"
            recommendation = "Mercado estável, entradas normais com SL justo"
            leverage_mult = 0.9
            risk_mode = "NEUTRAL"
        
        # 🚀 CONFIANÇA: Bull run em progresso, volume alto, RSI 50-70
        elif 40 < fear_score < 60 and phase == "BULL_RUN_STRONG" and volume_score > 60:
            sentiment = "CONFIDENCE"
            emoji = "🚀"
            profile = "AGGRESSIVE"
            recommendation = "Bull run confirmado, aumente position size"
            leverage_mult = 1.3
            risk_mode = "BULL_CONFIRMED"
        
        # 🎲 ESPECULAÇÃO: Volatilidade muito alta, volume pump, RSI extremo
        elif volatility_score > 80 and volume_score > 75 and (rsi_daily > 75 or rsi_daily < 25):
            sentiment = "SPECULATION"
            emoji = "🎲"
            profile = "VERY_AGGRESSIVE"
            recommendation = "Pump especulativo, entre tight com TP curto"
            leverage_mult = 1.5
            risk_mode = "PUMP_MODE"
        
        # 🚨 EUFORIA: RSI extremo alto (>80), topos formados, volume caindo
        elif fear_score < 30 and phase == "DISTRIBUTION" and volume_score > 70:
            sentiment = "EUPHORIA"
            emoji = "🚨"
            profile = "VERY_CONSERVATIVE"
            recommendation = "ALERTA: Topos! Prepare para queda, tome lucros"
            leverage_mult = 0.4
            risk_mode = "TAKE_PROFITS"
        
        # 🪙 DISTRIBUIÇÃO: Volume caindo, fase distribution, RSI caindo de cima
        elif phase == "DISTRIBUTION" and volume_score < 40 and fear_score > 50:
            sentiment = "DISTRIBUTION"
            emoji = "🪙"
            profile = "CONSERVATIVE"
            recommendation = "Weak hands saindo, prepare para queda"
            leverage_mult = 0.6
            risk_mode = "DISTRIBUTION_PHASE"
        
        # Default
        else:
            sentiment = "NEUTRAL"
            emoji = "⚖️"
            profile = "BALANCED"
            recommendation = "Mercado neutro, estratégia padrão"
            leverage_mult = 1.0
            risk_mode = "NORMAL"
        
        return {
            "emotion": sentiment,
            "emoji": emoji,
            "profile": profile,
            "risk_mode": risk_mode,
            "recommendation": recommendation,
            "leverage_multiplier": leverage_mult,
            "fear_score": round(fear_score, 1),
            "greed_score": round(greed_score, 1),
            "volume_score": round(volume_score, 1),
            "volatility_score": round(volatility_score, 1),
            "cycle_score": round(cycle_score, 1),
            "btc_dominance": round(btc_dominance, 2),
            "market_phase": phase,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_sentiment_message(self, sentiment_data: Dict) -> str:
        """
        Formata mensagem legível do sentimento para Telegram
        """
        msg = (
            f"{sentiment_data['emoji']} *{sentiment_data['emotion']}* | "
            f"{sentiment_data['risk_mode']}\n"
            f"📊 Fear:{sentiment_data['fear_score']:.0f} Greed:{sentiment_data['greed_score']:.0f} "
            f"Vol:{sentiment_data['volatility_score']:.0f} Vol.Traded:{sentiment_data['volume_score']:.0f}\n"
            f"💡 {sentiment_data['recommendation']}\n"
            f"⚡ Profile: {sentiment_data['profile']} | Leverage: {sentiment_data['leverage_multiplier']:.1f}x"
        )
        return msg
