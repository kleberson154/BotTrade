"""
SISTEMA DE PONTUACAO DE INDICADORES (SIMPLIFICADO)

Indicadores Utilizados:
  1. Liquidez (CHOCH, POI, FVG) = APENAS 1 PONTO (escolher UM deles)
  2. Volume = 1 ponto

Total maximo: 2 pontos

REGRA IMPORTANTE:
- CHOCH, POI, FVG sao indicadores de liquidez
- Apenas UM deles deve ser acionado
- Se multiplos acionados, escolher o de maior confianca
"""

import logging
import pandas as pd
from typing import Dict, Optional

log = logging.getLogger(__name__)


class IndicatorScorer:
    """Calcula pontuacao de indicadores com apenas liquidez + volume."""
    
    def __init__(self, min_score: int = 1, symbol: str = ""):
        self.min_score = min_score
        self.symbol = symbol
        self.last_indicators = {}
    
    def calculate_score(
        self,
        df: pd.DataFrame,
        choch_result: Optional[Dict] = None,
        poi_result: Optional[Dict] = None,
        fvg_result: Optional[Dict] = None,
        min_volume_multiplier: float = 1.2
    ) -> Dict:
        """Calcula score total dos indicadores."""
        
        if len(df) < 20:
            return {
                "score": 0,
                "total_indicators": 2,
                "indicators": {},
                "triggered": False,
                "message": f"Dados insuficientes ({len(df)} < 20)",
                "confidence": 0
            }
        
        indicators = {}
        score = 0
        triggered_indicators = []
        
        # LIQUIDEZ: CHOCH, POI, FVG (APENAS 1 PONTO, escolher o melhor)
        liquidity_result = self._check_liquidity(choch_result, poi_result, fvg_result)
        indicators["Liquidez"] = liquidity_result
        
        if liquidity_result["status"] == "OK":
            score += 1
            triggered_indicators.append(f"Liquidez ({liquidity_result['type']})")
        
        # VOLUME
        volume_result = self._check_volume(df, min_volume_multiplier)
        indicators["Volume"] = volume_result
        if volume_result["status"] == "OK":
            score += 1
            triggered_indicators.append("Volume")
        
        # RESULTADO FINAL
        triggered = score >= self.min_score
        confidence = (score / 2) * 100
        
        message = self._build_message(
            score, self.min_score, triggered_indicators, indicators
        )
        
        self.last_indicators = indicators
        
        return {
            "score": score,
            "total_indicators": 2,
            "min_score": self.min_score,
            "indicators": indicators,
            "triggered_indicators": triggered_indicators,
            "triggered": triggered,
            "confidence": confidence,
            "message": message,
            "emoji": "OK" if triggered else "WAIT"
        }
    
    @staticmethod
    def _check_liquidity(choch_result: Optional[Dict], 
                        poi_result: Optional[Dict],
                        fvg_result: Optional[Dict]) -> Dict:
        """Verifica APENAS UM dos 3 indicadores de liquidez (prioridade)."""
        
        # Prioridade 1: CHOCH
        if choch_result and choch_result.get('choch_detected'):
            return {
                'status': 'OK',
                'type': 'CHOCH',
                'value': choch_result.get('severity', 'MEDIUM'),
                'signal': choch_result.get('signal', 'HOLD'),
                'details': choch_result.get('details', ''),
                'confidence': 85
            }
        
        # Prioridade 2: POI
        if poi_result and poi_result.get('poi_signal') == 'APPROACH_POI':
            nearest = poi_result.get('nearest_poi', 0)
            poi_type = poi_result.get('nearest_poi_type', 'UNKNOWN')
            return {
                'status': 'OK',
                'type': 'POI',
                'value': poi_type,
                'nearest_poi': nearest,
                'details': poi_result.get('details', ''),
                'confidence': 70
            }
        
        # Prioridade 3: FVG
        if fvg_result and fvg_result.get('fvg_signal') == 'CONVERGING':
            return {
                'status': 'OK',
                'type': 'FVG',
                'value': fvg_result.get('nearest_fvg'),
                'distance_pct': fvg_result.get('distance_to_fvg_pct', 0),
                'details': fvg_result.get('details', ''),
                'confidence': 60
            }
        
        # Nenhum acionado
        return {
            'status': 'FAIL',
            'type': 'NONE',
            'value': None,
            'details': 'Nenhum indicador de liquidez acionado',
            'confidence': 0
        }
    
    @staticmethod
    def _check_volume(df: pd.DataFrame, min_multiplier: float = 1.2) -> Dict:
        """Verifica se volume esta elevado"""
        
        if len(df) < 20:
            return {'status': 'FAIL', 'value': None}
        
        avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        if volume_ratio > min_multiplier:
            return {
                'status': 'OK',
                'value': volume_ratio,
                'current': int(current_volume),
                'average': int(avg_volume)
            }
        
        return {'status': 'FAIL', 'value': volume_ratio}
    
    @staticmethod
    def _build_message(score: int, min_score: int, 
                      triggered: list, indicators: Dict) -> str:
        """Constroi mensagem resumida"""
        
        if score >= min_score:
            indicators_str = " + ".join(triggered)
            return f"[{score}/2] SINAL VALIDO: {indicators_str}"
        else:
            indicators_str = " + ".join(triggered) if triggered else "Nenhum"
            return f"[{score}/2] Aguardando (min: {min_score}). Acionados: {indicators_str}"
    
    def get_telegram_message(self, direction: str = "BUY") -> str:
        """Formata mensagem para Telegram"""
        if not self.last_indicators:
            return "Nenhum calculo realizado ainda"
        
        score = sum(1 for ind in self.last_indicators.values() if ind.get("status") == "OK")
        
        msg = f"Bot {self.symbol} - {direction}\n"
        msg += f"Score: {score}/2 (Min: {self.min_score})\n\n"
        
        msg += "OK:\n"
        for name, data in self.last_indicators.items():
            if data.get("status") == "OK":
                msg += f"  - {name}: {data.get('value')}\n"
        
        msg += "\nFAIL:\n"
        for name, data in self.last_indicators.items():
            if data.get("status") == "FAIL":
                msg += f"  - {name}: {data.get('value')}\n"
        
        return msg
