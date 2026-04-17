"""
⭐ SISTEMA DE PONTUAÇÃO DE INDICADORES
Calcula score de indicadores técnicos para validar entrada

Indicadores Utilizados:
  1. RSI (acima 80 ou abaixo 20) = 1 ponto
  2. MFI (acima 80 ou abaixo 20) = 1 ponto
  3. ADX (acima de min_adx) = 1 ponto
  4. Volatilidade ATR = 1 ponto
  5. Volume = 1 ponto

Regra: Bate score mínimo → Execute ordem
Telegram: Mostra quais indicadores foram batidos ✅ e quais falharam ❌
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple

from src.indicators import TechnicalIndicators

log = logging.getLogger(__name__)


class IndicatorScorer:
    """
    Calcula pontuação de indicadores técnicos.
    Cada indicador que passa = +1 ponto
    """
    
    def __init__(self, min_score: int = 3, symbol: str = ""):
        """
        Args:
            min_score: Pontuação mínima para executar ordem (ex: 3)
            symbol: Símbolo tradado para logs
        """
        self.min_score = min_score
        self.symbol = symbol
        self.last_indicators = {}  # Armazenar últimas medições
    
    def calculate_score(
        self,
        df: pd.DataFrame,
        min_adx: float = 15,
        min_volatilidade: float = 0.0008,
        volume_multiplier: float = 1.2,
        rsi_period: int = 14,
        mfi_period: int = 14
    ) -> Dict:
        """
        Calcula score total dos indicadores.
        
        Returns:
            {
                "score": 0-5,
                "total_indicators": 5,
                "indicators": {
                    "rsi": {"status": "✅", "value": 75.5},
                    "mfi": {"status": "❌", "value": 45.2},
                    ...
                },
                "triggered": bool,
                "message": str
            }
        """
        
        if len(df) < max(rsi_period, mfi_period) + 10:
            return {
                "score": 0,
                "total_indicators": 5,
                "indicators": {},
                "triggered": False,
                "message": f"Dados insuficientes ({len(df)} < {rsi_period + 10})"
            }
        
        # 📊 Calcular cada indicador
        indicators = {}
        score = 0
        
        # 1️⃣ RSI
        rsi_result = self._check_rsi(df, rsi_period)
        indicators["RSI"] = rsi_result
        if rsi_result["status"] == "✅":
            score += 1
        
        # 2️⃣ MFI
        mfi_result = self._check_mfi(df, mfi_period)
        indicators["MFI"] = mfi_result
        if mfi_result["status"] == "✅":
            score += 1
        
        # 3️⃣ ADX
        adx_result = self._check_adx(df, min_adx)
        indicators["ADX"] = adx_result
        if adx_result["status"] == "✅":
            score += 1
        
        # 4️⃣ Volatilidade (ATR)
        atr_result = self._check_atr(df, min_volatilidade)
        indicators["ATR"] = atr_result
        if atr_result["status"] == "✅":
            score += 1
        
        # 5️⃣ Volume
        volume_result = self._check_volume(df, volume_multiplier)
        indicators["Volume"] = volume_result
        if volume_result["status"] == "✅":
            score += 1
        
        # 📈 Salvar para referência
        self.last_indicators = indicators
        
        # ✅ Verificar se bate score mínimo
        triggered = score >= self.min_score
        
        # 🔔 Mensagem
        message = self._build_message(score, indicators)
        
        return {
            "score": score,
            "total_indicators": 5,
            "min_required": self.min_score,
            "indicators": indicators,
            "triggered": triggered,
            "message": message,
            "stats": {
                "rsi": rsi_result["value"],
                "mfi": mfi_result["value"],
                "adx": adx_result["value"],
                "atr_pct": atr_result["value"],
                "volume_ratio": volume_result["value"],
            }
        }
    
    def _check_rsi(self, df: pd.DataFrame, period: int = 14) -> Dict:
        """Verifica RSI > 80 ou < 20"""
        rsi = self._calc_rsi(df["close"], period).iloc[-1]
        
        triggered = rsi > 80 or rsi < 20
        status = "✅" if triggered else "❌"
        reason = f"RSI={rsi:.1f}"
        
        if rsi > 80:
            reason += " (OVERBOUGHT)"
        elif rsi < 20:
            reason += " (OVERSOLD)"
        
        return {
            "status": status,
            "value": round(rsi, 2),
            "reason": reason,
            "threshold": "80+ ou -20"
        }
    
    def _check_mfi(self, df: pd.DataFrame, period: int = 14) -> Dict:
        """Verifica MFI > 80 ou < 20"""
        mfi = self._calc_mfi(df, period)
        
        triggered = mfi > 80 or mfi < 20
        status = "✅" if triggered else "❌"
        reason = f"MFI={mfi:.1f}"
        
        if mfi > 80:
            reason += " (OVERBOUGHT)"
        elif mfi < 20:
            reason += " (OVERSOLD)"
        
        return {
            "status": status,
            "value": round(mfi, 2),
            "reason": reason,
            "threshold": "80+ ou -20"
        }
    
    def _check_adx(self, df: pd.DataFrame, min_adx: float = 15) -> Dict:
        """Verifica ADX > min_adx (tendência forte)"""
        adx = self._calc_adx(df, 14).iloc[-1]
        
        triggered = adx >= min_adx
        status = "✅" if triggered else "❌"
        
        return {
            "status": status,
            "value": round(adx, 2),
            "reason": f"ADX={adx:.1f}",
            "threshold": f">={min_adx}"
        }
    
    def _check_atr(self, df: pd.DataFrame, min_volatilidade: float = 0.0008) -> Dict:
        """Verifica ATR % > min_volatilidade"""
        atr_pct = self._calc_atr_pct(df)
        
        triggered = atr_pct >= min_volatilidade
        status = "✅" if triggered else "❌"
        
        return {
            "status": status,
            "value": round(atr_pct, 4),
            "reason": f"ATR%={atr_pct*100:.2f}%",
            "threshold": f">={min_volatilidade*100:.2f}%"
        }
    
    def _check_volume(self, df: pd.DataFrame, volume_multiplier: float = 1.2) -> Dict:
        """Verifica Volume > média × multiplier"""
        vol_current = df["volume"].iloc[-1]
        vol_avg = df["volume"].tail(20).mean()
        ratio = vol_current / vol_avg if vol_avg > 0 else 0
        
        triggered = ratio >= volume_multiplier
        status = "✅" if triggered else "❌"
        
        return {
            "status": status,
            "value": round(ratio, 2),
            "reason": f"Vol Ratio={ratio:.2f}x",
            "threshold": f">={volume_multiplier}x"
        }
    
    # ============================================================
    # CÁLCULOS DE INDICADORES (Delegados para TechnicalIndicators)
    # ============================================================
    
    def _calc_rsi(self, prices, period: int = 14) -> pd.Series:
        """Calcula RSI (delega para TechnicalIndicators)"""
        return TechnicalIndicators.calculate_rsi(prices, period)
    
    def _calc_mfi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula MFI (delega para TechnicalIndicators)"""
        return TechnicalIndicators.calculate_mfi(df, period)
    
    def _calc_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calcula ADX (delega para TechnicalIndicators)"""
        return TechnicalIndicators.calculate_adx(df, period)
    
    def _calc_atr_pct(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calcula ATR em % (delega para TechnicalIndicators)"""
        return TechnicalIndicators.calculate_atr_pct(df, period)
    
    # ============================================================
    # FORMATAÇÃO DE MENSAGEM
    # ============================================================
    
    def _build_message(self, score: int, indicators: Dict) -> str:
        """Constrói mensagem formatada dos indicadores"""
        message = f"⭐ SCORE: {score}/5\n\n"
        
        # Indicadores batidos
        message += "✅ BATIDOS:\n"
        for ind_name, ind_data in indicators.items():
            if ind_data["status"] == "✅":
                message += f"  • {ind_name}: {ind_data['reason']}\n"
        
        # Indicadores não batidos
        message += "\n❌ NÃO BATIDOS:\n"
        for ind_name, ind_data in indicators.items():
            if ind_data["status"] == "❌":
                message += f"  • {ind_name}: {ind_data['reason']}\n"
        
        return message
    
    def get_telegram_message(self, direction: str = "BUY") -> str:
        """Formata mensagem para Telegram"""
        if not self.last_indicators:
            return "Nenhum cálculo realizado ainda"
        
        score = sum(1 for ind in self.last_indicators.values() if ind["status"] == "✅")
        
        msg = f"🤖 *{self.symbol} - {direction}*\n"
        msg += f"⭐ Score: {score}/5 (Min: {self.min_score})\n\n"
        
        msg += "✅ *Indicadores OK:*\n"
        for name, data in self.last_indicators.items():
            if data["status"] == "✅":
                msg += f"  • {name}: {data['reason']}\n"
        
        msg += "\n❌ *Indicadores Falhando:*\n"
        for name, data in self.last_indicators.items():
            if data["status"] == "❌":
                msg += f"  • {name}: {data['reason']}\n"
        
        return msg
