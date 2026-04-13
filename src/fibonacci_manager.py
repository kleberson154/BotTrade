"""
Fibonacci Target Manager
Implementa as 3 estratégias de Fibonacci:
1. Targets precisos em níveis de Fibonacci
2. Confirmação leve com boost de confiança
3. Proteção de SL em suportes/resistências de Fibonacci
"""
import numpy as np
from typing import Dict, Tuple, Optional

class FibonacciManager:
    """
    Calcula e gerencia níveis de Fibonacci para posicionamento inteligente de TP/SL
    Usa teoria de ondas de Elliot e retração de ouro (1.618)
    """
    
    # Níveis clássicos de Fibonacci
    FIBONACCI_LEVELS = {
        '23.6%': 0.236,
        '38.2%': 0.382,
        '50.0%': 0.500,
        '61.8%': 0.618,
        '78.6%': 0.786,
        '100%':  1.000,
        '127%':  1.272,
        '161.8%': 1.618,
    }
    
    # Níveis primários para decisões (os mais importantes)
    PRIMARY_LEVELS = [0.382, 0.618, 1.000, 1.618]
    
    def __init__(self, atr_pct: float = 0.005):
        """
        Args:
            atr_pct: Volatilidade esperada (ATR em %)
        """
        self.atr_pct = atr_pct
    
    # =========================================================
    # ESTRATÉGIA 1: Fibonacci para TARGETS (Exit Management)
    # =========================================================
    
    def calculate_targets_fibo(
        self, 
        entry_price: float, 
        direction: str,
        swing_high: float,
        swing_low: float,
        atr: float
    ) -> Dict[str, float]:
        """
        Calcula 4 níveis de TP baseados em Fibonacci retraction.
        
        ESTRATÉGIA 1:
        - TP1 (38.2%) → Lucro rápido, saída parcial
        - TP2 (50.0%) → Ponto de equilíbrio psicológico
        - TP3 (61.8%) → Alvo principal (razão dourada)
        - TP4 (100%) → Movimento completo
        
        Args:
            entry_price: Preço de entrada
            direction: "BUY" ou "SELL"
            swing_high: Máxima do swing (para SHORT)
            swing_low: Mínima do swing (para LONG)
            atr: ATR em valor absoluto
            
        Returns:
            Dict com TP1, TP2, TP3, TP4, e também SL sugerido
        """
        
        if direction == "BUY":
            # LONG: swing_low é a base, entry_price é o início
            swing_range = entry_price - swing_low
            
            tp1 = entry_price + (swing_range * 0.382)
            tp2 = entry_price + (swing_range * 0.500)
            tp3 = entry_price + (swing_range * 0.618)  # Nível dourado
            tp4 = entry_price + (swing_range * 1.000)
            
            # SL protetor em Fibonacci (Strategy 3)
            sl = swing_low - (atr * 0.5)  # Ligeiramente abaixo do swing
            
        else:  # SHORT
            # SHORT: swing_high é a base
            swing_range = swing_high - entry_price
            
            tp1 = entry_price - (swing_range * 0.382)
            tp2 = entry_price - (swing_range * 0.500)
            tp3 = entry_price - (swing_range * 0.618)  # Nível dourado
            tp4 = entry_price - (swing_range * 1.000)
            
            sl = swing_high + (atr * 0.5)
        
        return {
            'tp1': tp1,
            'tp2': tp2,
            'tp3': tp3,  # ← Principal (Golden Ratio)
            'tp4': tp4,
            'sl': sl,
            'swing_range': swing_range,
            'levels': {
                '38.2% (TP1)': tp1,
                '50.0% (TP2)': tp2,
                '61.8% (TP3 - Golden)': tp3,
                '100% (TP4)': tp4,
            }
        }
    
    # =========================================================
    # ESTRATÉGIA 2: Fibonacci para Confirmação LEVE
    # =========================================================
    
    def get_fibo_confidence_boost(
        self,
        current_price: float,
        entry_price: float,
        swing_high: float,
        swing_low: float,
        direction: str,
        tolerance_pct: float = 0.003  # 0.3% de tolerância
    ) -> Dict[str, any]:
        """
        Calcula confiança baseada em proximidade a níveis de Fibonacci.
        
        ESTRATÉGIA 2:
        - Se preço está em nível Fibo: confidence += 0.15 (boost leverage)
        - Se preço longe: confidence -= 0.05 (reduz leverage)
        - Trade ainda é válida, mas ajusta agressividade
        
        Args:
            current_price: Preço atual
            entry_price: Preço de entrada
            swing_high/low: Swing para calcular range
            direction: "BUY" ou "SELL"
            tolerance_pct: Tolerância para considerar "em nível"
            
        Returns:
            {
                'in_level': bool,
                'nearest_level': str,
                'confidence_boost': float (-0.05 a +0.15),
                'leverage_multiplier': float (0.85 a 1.15)
            }
        """
        
        # Calcula range
        if direction == "BUY":
            swing_range = entry_price - swing_low
        else:
            swing_range = swing_high - entry_price
        
        # Calcula distância como % do swing
        if direction == "BUY":
            movement_from_entry = current_price - entry_price
            movement_pct = movement_from_entry / swing_range if swing_range > 0 else 0
        else:
            movement_from_entry = entry_price - current_price
            movement_pct = movement_from_entry / swing_range if swing_range > 0 else 0
        
        tolerance = tolerance_pct
        
        # Verifica se está perto de algum nível
        in_level = False
        nearest_level = "Fora dos níveis"
        confidence_boost = -0.05  # Default: menos confiança
        
        for level_name, level_value in [('38.2%', 0.382), ('50.0%', 0.500), 
                                        ('61.8%', 0.618), ('100%', 1.000), 
                                        ('127%', 1.272), ('161.8%', 1.618)]:
            if abs(movement_pct - level_value) < tolerance:
                in_level = True
                nearest_level = level_name
                
                # Golden ratio (61.8%) e 100% têm mais confiança
                if level_value in [0.618, 1.000]:
                    confidence_boost = +0.15  # Boost significativo
                else:
                    confidence_boost = +0.10
                break
        
        # Calcula multiplicador de leverage
        leverage_multiplier = 1.0 + confidence_boost
        leverage_multiplier = max(0.85, min(1.15, leverage_multiplier))  # Clamp 0.85-1.15
        
        return {
            'in_level': in_level,
            'nearest_level': nearest_level,
            'confidence_boost': confidence_boost,
            'leverage_multiplier': leverage_multiplier,
            'movement_pct': movement_pct,
            'movement_from_entry': movement_from_entry
        }
    
    # =========================================================
    # ESTRATÉGIA 3: Fibonacci para Proteção de SL
    # =========================================================
    
    def calculate_fibo_sl(
        self,
        entry_price: float,
        direction: str,
        swing_high: float,
        swing_low: float,
        atr: float,
        atr_multiplier: float = 1.0
    ) -> Dict[str, float]:
        """
        Posiciona SL em nível de Fibonacci para melhor proteção.
        
        ESTRATÉGIA 3:
        - Para LONG: SL logo abaixo do swing_low
        - Para SHORT: SL logo acima do swing_high
        - Reduz whipsaws posicionando em suportes matemáticos
        - Usa ATR como margem de segurança
        
        Args:
            entry_price: Preço de entrada
            direction: "BUY" ou "SELL"
            swing_high/low: Suporte/resistência de Fibonacci
            atr: ATR em valor absoluto
            atr_multiplier: Multiplicador de ATR para margem extra
            
        Returns:
            {
                'sl': float,
                'risk_distance': float,
                'risk_pct': float,
                'protection_level': str (descrição do nível)
            }
        """
        
        if direction == "BUY":
            # SL em Fibonacci abaixo do swing
            margin = atr * atr_multiplier
            sl = swing_low - margin
            risk_distance = entry_price - sl
            
            protection_level = f"Abaixo do swing_low ({swing_low:.2f}) com margem ATR ({margin:.2f})"
            
        else:  # SHORT
            # SL em Fibonacci acima do swing
            margin = atr * atr_multiplier
            sl = swing_high + margin
            risk_distance = sl - entry_price
            
            protection_level = f"Acima do swing_high ({swing_high:.2f}) com margem ATR ({margin:.2f})"
        
        risk_pct = (risk_distance / entry_price) * 100 if entry_price > 0 else 0
        
        return {
            'sl': sl,
            'risk_distance': risk_distance,
            'risk_pct': risk_pct,
            'protection_level': protection_level,
            'margin_used': atr * atr_multiplier
        }
    
    # =========================================================
    # UTILIDADES
    # =========================================================
    
    def get_fibo_summary(
        self,
        entry_price: float,
        direction: str,
        swing_high: float,
        swing_low: float,
        atr: float,
        current_price: Optional[float] = None
    ) -> str:
        """Retorna resumo de Fibonacci em formato legível"""
        
        targets = self.calculate_targets_fibo(entry_price, direction, swing_high, swing_low, atr)
        sl_info = self.calculate_fibo_sl(entry_price, direction, swing_high, swing_low, atr)
        
        summary = f"""
🎯 FIBONACCI TARGETS ({direction}):
  Entry: {entry_price:.2f}
  TP1 (38.2%):  {targets['tp1']:.2f}  [Quick profit]
  TP2 (50.0%):  {targets['tp2']:.2f}  [Balance point]
  TP3 (61.8%):  {targets['tp3']:.2f}  [🏆 Golden Ratio - PRIMARY]
  TP4 (100%):   {targets['tp4']:.2f}  [Full move]
  SL:           {targets['sl']:.2f}  [Protected]
  
Risk/Reward Ratio:
  Risk: {sl_info['risk_pct']:.2f}%
"""
        
        if current_price:
            confidence = self.get_fibo_confidence_boost(
                current_price, entry_price, swing_high, swing_low, direction
            )
            summary += f"""
Current Position: {current_price:.2f}
  Level: {confidence['nearest_level']}
  Confidence Boost: {confidence['confidence_boost']:+.2f}
  Leverage Multiplier: {confidence['leverage_multiplier']:.2f}x
"""
        
        return summary
    
    def detect_fibo_breakdown(
        self,
        prices: list,
        direction: str,
        atr: float
    ) -> Dict[str, any]:
        """
        Detecta se há breakout em nível de Fibonacci.
        Útil para confirmar que breakout é real (em nível matemático).
        """
        
        if len(prices) < 5:
            return {'is_breakdown': False, 'confidence': 0}
        
        # Usa os últimos preços para calcular fibo
        high = max(prices[-20:]) if len(prices) >= 20 else max(prices)
        low = min(prices[-20:]) if len(prices) >= 20 else min(prices)
        current = prices[-1]
        
        if high == low:
            return {'is_breakdown': False, 'confidence': 0}
        
        movement_pct = (current - low) / (high - low) if direction == "BUY" else (high - current) / (high - low)
        
        # Verifica proximidade a nível de Fibonacci
        tolerance = 0.05  # 5% de tolerância
        
        for level_value in self.PRIMARY_LEVELS:
            if abs(movement_pct - level_value) < tolerance:
                return {
                    'is_breakdown': True,
                    'fibo_level': f"{level_value*100:.1f}%",
                    'confidence': 0.8,
                    'reason': f"Breakout em nível Fibonacci {level_value*100:.1f}%"
                }
        
        return {'is_breakdown': False, 'confidence': 0}


# =========================================================
# EXEMPLO DE USO
# =========================================================
if __name__ == "__main__":
    fib = FibonacciManager(atr_pct=0.005)
    
    # Exemplo LONG
    entry = 45000
    swing_low = 44000
    atr = 200
    
    targets = fib.calculate_targets_fibo(entry, "BUY", 46000, swing_low, atr)
    print(fib.get_fibo_summary(entry, "BUY", 46000, swing_low, atr, current_price=45100))
    
    # Testar confidence boost
    confidence = fib.get_fibo_confidence_boost(45382, entry, 46000, swing_low, "BUY")
    print(f"\n✅ Confidence: {confidence['confidence_boost']:+.2f}, Leverage: {confidence['leverage_multiplier']:.2f}x")
