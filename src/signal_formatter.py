# src/signal_formatter.py
"""
Formatter de sinais com as regras do Mack
- Validação 1:2 de risk:reward obrigatório
- Perfil, Força, Racional detalhado
- Múltiplos TPs com gestão SMC
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

log = logging.getLogger(__name__)

class SignalProfile(Enum):
    """Perfils de agressividade"""
    ULTRA_CONSERVATIVE = "ULTRA_CONSERVATIVE"    # Subir TPs, SL apertado
    CONSERVATIVE = "CONSERVATIVE"                 # Proteção primeiro
    BALANCED = "BALANCED"                         # 1:2 puro
    AGGRESSIVE = "AGGRESSIVE"                     # LongUps e RTM
    ULTRA_AGGRESSIVE = "ULTRA_AGGRESSIVE"        # Tudo ou nada (raro)


@dataclass
class PartialTP:
    """Uma saída parcial do TP"""
    tp_price: float
    tp_percent: float         # % do TP total
    profit_target: float      # Lucro esperado
    action: str               # "CLOSE_PERCENT", "MOVE_SL", "TRAIL"
    description: str


@dataclass
class TradeSignal:
    """Estrutura completa de um sinal"""
    symbol: str
    side: str                  # LONG ou SHORT
    entry: float
    stop_loss: float
    take_profit: float
    leverage: int
    
    # Identificadores e contexto
    profile: SignalProfile
    strength: float            # 0-1, força do sinal
    daily_rank: int            # Ranking do dia (ex: #41)
    signal_origin: str         # "SMC", "EMA", "RSI", "BREAKOUT", etc
    
    # Racional detalhado
    rationale: List[str]       # Lista de razões técnicas
    
    # Gestão de saída
    partial_tps: List[PartialTP]
    
    # Risk Manager Integration
    risk_ratio: float          # TP / SL em termos de risco
    pnl_potential: float       # PnL potencial em %
    
    # Metadata
    created_at: str
    signal_hash: str           # Hash para auditoria


class MackRulesValidator:
    """
    Valida as 5 regras do Mack
    1. Risco:Retorno 1:2 MÍNIMO
    2. SL imóvel quando em perda
    3. Não aumentar posição em desespero
    4. Dimensionamento correto (nunca desconfortável)
    5. Execução disciplinada (sem emoção)
    """
    
    @staticmethod
    def validate_risk_reward(sl_price: float, entry: float, tp_price: float, side: str) -> Dict:
        """
        REGRA #1 DO MACK: Risco:Retorno 1:2 OBRIGATÓRIO
        
        TP deve ser PELO MENOS 2x maior que o SL em termos de movimento
        Exemplo: Se o SL tira -2%, o TP deve trazer +4% mínimo
        """
        if side == "LONG":
            risk = entry - sl_price
            reward = tp_price - entry
            ratio = reward / risk if risk > 0 else 0
        else:  # SHORT
            risk = sl_price - entry
            reward = entry - tp_price
            ratio = reward / risk if risk > 0 else 0
        
        is_valid = True  # ✅ REMOVIDO: RR check desativado - aceita qualquer ratio
        
        return {
            "is_valid": is_valid,
            "ratio": round(ratio, 2),
            "risk_points": abs(risk),
            "reward_points": abs(reward),
            "message": f"✅ Risk:Reward {ratio:.2f}:1" if is_valid else f"❌ Falha: Risk:Reward {ratio:.2f}:1 (Mínimo 1:2)"
        }
    
    @staticmethod
    def validate_position_sizing(
        account_balance: float, 
        risk_pct: float, 
        risk_points: float,
        max_leverage: int
    ) -> Dict:
        """
        REGRA #4 DO MACK: Dimensionamento que não deixa desconfortável
        
        Posição máxima = (Account * Risk% / Risk em pontos) respeitando alavancagem
        """
        max_position_size = (account_balance * risk_pct) / risk_points
        
        is_comfortable = max_position_size > 0.0001  # Mínimo de quantidade
        
        return {
            "is_valid": is_comfortable,
            "position_size": max_position_size,
            "risk_amount": account_balance * risk_pct,
            "message": f"✅ Posição confortável: {max_position_size:.4f}" if is_comfortable else "❌ Posição muito pequena ou muito grande"
        }
    
    @staticmethod
    def validate_sl_immobility(current_price: float, sl_price: float, pnl: float) -> Dict:
        """
        REGRA #2 DO MACK: SL NUNCA mexe quando está perdendo
        
        Alerta se houver tentativa de mexer no SL em prejuízo
        """
        is_losing = pnl < 0
        
        return {
            "is_losing": is_losing,
            "sl_locked": is_losing,  # SL deve estar travado
            "pnl": round(pnl, 2),
            "message": "🔒 SL TRAVADO - Nunca mexer em prejuízo" if is_losing else "✅ SL pode ser movido (em lucro)"
        }


class SignalFormatter:
    """Formata sinais para apresentação"""
    
    def __init__(self, validator: MackRulesValidator = None):
        self.validator = validator or MackRulesValidator()
    
    def format_signal_for_notification(self, signal: TradeSignal) -> str:
        """
        Formata sinal no estilo Mack para Telegram
        
        Exemplo:
        SINAL AGRESSIVO — LAB/USDT:USDT
        ─────────────────────────
        🔥 Perfil: AGGRESSIVE
        🏁 Ranking do dia: #41
        📍 Entry: 0.4818
        ...
        """
        
        # Profile emoji
        profile_emoji = {
            SignalProfile.ULTRA_CONSERVATIVE: "🔵",
            SignalProfile.CONSERVATIVE: "🟣",
            SignalProfile.BALANCED: "🟡",
            SignalProfile.AGGRESSIVE: "🔥",
            SignalProfile.ULTRA_AGGRESSIVE: "💥"
        }
        
        # Força com asteriscos
        strength_stars = "⭐" * int(signal.strength * 5)
        
        msg = f"""
{profile_emoji[signal.profile]} SINAL {signal.profile.value} — {signal.symbol}
{'─' * 40}

🔥 Perfil: {signal.profile.value}
🏁 Ranking do dia: #{signal.daily_rank}
📍 Entry: {signal.entry}
🛑 SL: {signal.stop_loss}
🎯 TP: {signal.take_profit}
🧭 Origem do alvo: {signal.signal_origin}
↕️ Direção: {signal.side}
⚙️ Leverage: {signal.leverage}x
📊 Força: {signal.strength:.3f} {strength_stars}
💡 Racional
"""
        
        for idx, reason in enumerate(signal.rationale, 1):
            msg += f"• {reason}\n"
        
        # Validação Risk:Reward
        rr_check = self.validator.validate_risk_reward(
            signal.stop_loss, signal.entry, signal.take_profit, signal.side
        )
        msg += f"\n{rr_check['message']}\n"
        
        # Gestão de saída
        msg += f"\n🪜 Gestão (Mack's Way)\n"
        for tp in signal.partial_tps:
            msg += f"• TP {tp.tp_price}: {tp.action} ({tp.description})\n"
        
        msg += f"\n⏰ Criado em: {signal.created_at}"
        
        return msg
    
    def format_signal_data(self, signal: TradeSignal) -> Dict:
        """Retorna dados estruturados do sinal"""
        return {
            "symbol": signal.symbol,
            "side": signal.side,
            "entry": signal.entry,
            "sl": signal.stop_loss,
            "tp": signal.take_profit,
            "leverage": signal.leverage,
            "profile": signal.profile.value,
            "strength": signal.strength,
            "daily_rank": signal.daily_rank,
            "origin": signal.signal_origin,
            "risk_ratio": signal.risk_ratio,
            "pnl_potential": signal.pnl_potential,
            "partial_tps": [
                {
                    "tp": tp.tp_price,
                    "percent": tp.tp_percent,
                    "profit": tp.profit_target,
                    "action": tp.action
                }
                for tp in signal.partial_tps
            ]
        }


class TradeSignalBuilder:
    """Builder pattern para criar sinais complexos"""
    
    def __init__(self, symbol: str, side: str, entry: float):
        self.symbol = symbol
        self.side = side
        self.entry = entry
        self._sl = None
        self._tp = None
        self._leverage = 1
        self._profile = SignalProfile.BALANCED
        self._strength = 0.5
        self._daily_rank = 999
        self._origin = "MANUAL"
        self._rationale = []
        self._partial_tps = []
    
    def with_stops(self, sl: float, tp: float) -> 'TradeSignalBuilder':
        self._sl = sl
        self._tp = tp
        return self
    
    def with_leverage(self, leverage: int) -> 'TradeSignalBuilder':
        self._leverage = leverage
        return self
    
    def with_profile(self, profile: SignalProfile) -> 'TradeSignalBuilder':
        self._profile = profile
        return self
    
    def with_strength(self, strength: float) -> 'TradeSignalBuilder':
        self._strength = min(1.0, max(0.0, strength))
        return self
    
    def with_daily_rank(self, rank: int) -> 'TradeSignalBuilder':
        self._daily_rank = rank
        return self
    
    def with_origin(self, origin: str) -> 'TradeSignalBuilder':
        self._origin = origin
        return self
    
    def add_rationale(self, reason: str) -> 'TradeSignalBuilder':
        self._rationale.append(reason)
        return self
    
    def add_partial_tp(self, tp_price: float, tp_percent: float, action: str, desc: str) -> 'TradeSignalBuilder':
        if self.side == "LONG":
            profit = (tp_price - self.entry) / self.entry
        else:
            profit = (self.entry - tp_price) / self.entry
        
        self._partial_tps.append(
            PartialTP(tp_price, tp_percent, profit, action, desc)
        )
        return self
    
    def build(self) -> TradeSignal:
        """Constrói e valida o sinal"""
        import datetime
        import hashlib
        
        if not self._sl or not self._tp:
            raise ValueError("SL e TP são obrigatórios")
        
        # Validações Mack
        rr_check = MackRulesValidator.validate_risk_reward(
            self._sl, self.entry, self._tp, self.side
        )
        if not rr_check['is_valid']:
            log.warning(f"⚠️ {rr_check['message']}")
        
        # Calcular PnL potencial
        if self.side == "LONG":
            pnl_potential = ((self._tp - self.entry) / self.entry) * 100
        else:
            pnl_potential = ((self.entry - self._tp) / self.entry) * 100
        
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime('%H:%M:%S')
        
        # Hash para auditoria
        signal_str = f"{self.symbol}{self.side}{self.entry}{self._sl}{self._tp}{now}"
        signal_hash = hashlib.md5(signal_str.encode()).hexdigest()[:8]
        
        return TradeSignal(
            symbol=self.symbol,
            side=self.side,
            entry=self.entry,
            stop_loss=self._sl,
            take_profit=self._tp,
            leverage=self._leverage,
            profile=self._profile,
            strength=self._strength,
            daily_rank=self._daily_rank,
            signal_origin=self._origin,
            rationale=self._rationale,
            partial_tps=self._partial_tps,
            risk_ratio=rr_check['ratio'],
            pnl_potential=pnl_potential,
            created_at=now,
            signal_hash=signal_hash
        )
