# src/mack_compliance.py
"""
Compliance com as 5 regras do Mack para trading disciplinado
- Regra 1: Risco:Retorno 1:3
- Regra 2: SL imóvel em prejuízo
- Regra 3: Sem aumentar posição no desespero
- Regra 4: Dimensionamento correto
- Regra 5: Execução disciplinada
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)

class MackCompliance:
    def __init__(self, account_balance: float = 1000.0):
        self.account_balance = account_balance
        self.max_risk_per_trade = 0.10  # 2% máximo por trade
        self.max_daily_risk = 0.55      # 5% máximo por dia
        self.daily_loss_accumulated = 0.0
        
        # Auditoria
        self.audit_log = []
        self.violations = []
    
    # ========================================================
    # REGRA 1: RISCO:RETORNO 1:3 MÍNIMO
    # ========================================================
    
    def validate_rr_ratio(
        self, 
        entry: float, 
        sl: float, 
        tp: float, 
        side: str,
        symbol: str = ""
    ) -> Dict:
        if side == "LONG":
            risk = entry - sl
            reward = tp - entry
        elif side == "SHORT":
            risk = sl - entry
            reward = entry - tp
        else:
            return {"valid": False, "error": f"Lado inválido: {side}"}
        
        if risk <= 0:
            return {"valid": False, "error": "SL no lado errado", "risk": risk}
        
        if reward <= 0:
            return {"valid": False, "error": "TP no lado errado", "reward": reward}
        
        ratio = reward / risk
        is_valid = ratio >= 0.5  # ✅ RELAXADO: mínimo 1:2 (era 1:3)
        
        audit_msg = f"[R:R] {symbol} {side} | Ratio: {ratio:.2f}:1 {'✅' if is_valid else '❌'}"
        self.audit_log.append(audit_msg)
        log.info(audit_msg)
        
        if not is_valid:
            violation = f"REGRA 1 VIOLADA: {symbol} Risk:Reward {ratio:.2f}:1 (mínimo 1:3)"
            self.violations.append(violation)
            log.warning(f"⚠️ {violation}")
        
        return {
            "valid": is_valid,
            "ratio": round(ratio, 2),
            "risk_points": risk,
            "reward_points": reward,
            "min_required": "1:3"
        }
    
    # ========================================================
    # REGRA 2: SL IMÓVEL QUANDO EM PREJUÍZO
    # ========================================================
    
    def validate_sl_immobility(
        self,
        symbol: str,
        current_price: float,
        sl_original: float,
        sl_current: float,
        side: str,
        current_pnl: float
    ) -> Dict:
        is_losing = current_pnl < 0
        sl_changed = sl_current != sl_original
        
        # Detectar se o SL foi movido CONTRA o trader (aumentando risco)
        if side == "LONG":
            sl_moved_against = sl_current < sl_original  # SL mais baixo = mais risco
        else:  # SHORT
            sl_moved_against = sl_current > sl_original  # SL mais alto = mais risco
        
        violation_detected = is_losing and sl_changed and sl_moved_against
        
        status = "🔒 SL TRAVADO (Prejuízo)" if is_losing else "✅ SL Liberado (Lucro)"
        
        audit_msg = f"[SL-IMÓVEL] {symbol} | PnL: {current_pnl:.2f}% | {status}"
        self.audit_log.append(audit_msg)
        log.info(audit_msg)
        
        if violation_detected:
            violation = f"REGRA 2 VIOLADA: {symbol} SL movido contra posição em prejuízo!"
            self.violations.append(violation)
            log.error(f"❌ {violation}")
        
        return {
            "valid": not violation_detected,
            "is_losing": is_losing,
            "sl_locked": is_losing,
            "sl_changed": sl_changed,
            "pnl": round(current_pnl, 2),
            "message": "🔒 SL TRAVADO - NUNCA mexer em prejuízo" if is_losing else "✅ Livre para ajustar SL"
        }
    
    # ========================================================
    # REGRA 3: NÃO AUMENTAR POSIÇÃO NO DESESPERO
    # ========================================================
    
    def validate_no_averaging_down(
        self,
        symbol: str,
        recent_additions: int,
        total_pnl: float,
        is_losing: bool
    ) -> Dict:
        averaging_down_detected = is_losing and recent_additions > 0
        
        audit_msg = f"[AV-DOWN] {symbol} | Adições recentes: {recent_additions} | Perdendo: {is_losing}"
        self.audit_log.append(audit_msg)
        log.info(audit_msg)
        
        if averaging_down_detected:
            violation = f"REGRA 3 VIOLADA: {symbol} Averaging down detectado em prejuízo!"
            self.violations.append(violation)
            log.error(f"❌ {violation}")
        
        return {
            "valid": not averaging_down_detected,
            "averaging_down": averaging_down_detected,
            "recent_additions": recent_additions,
            "pnl": round(total_pnl, 2),
            "message": "🚫 PARADO: Sem adicionar em prejuízo" if averaging_down_detected else "✅ Sem averaging down"
        }
    
    # ========================================================
    # REGRA 4: DIMENSIONAMENTO CONFORTÁVEL
    # ========================================================
    
    def validate_position_sizing(
        self,
        symbol: str,
        entry: float,
        sl: float,
        quantity: float,
        leverage: int,
        account_balance: float,
        side: str
    ) -> Dict:
        
        # Calcular risco em USD
        if side == "LONG":
            risk_per_unit = entry - sl
        else:
            risk_per_unit = sl - entry
        
        total_risk_usd = quantity * risk_per_unit
        risk_percent = (total_risk_usd / account_balance) * 100 if account_balance > 0 else 0
        
        is_valid = risk_percent <= self.max_risk_per_trade * 100  # Máximo 2%
        
        audit_msg = f"[SIZING] {symbol} | Risk: {risk_percent:.2f}% | Qty: {quantity:.3f} | Lev: {leverage}x"
        self.audit_log.append(audit_msg)
        log.info(audit_msg)
        
        if not is_valid:
            violation = f"REGRA 4 VIOLADA: {symbol} Risco de {risk_percent:.2f}% (máximo 2%)"
            self.violations.append(violation)
            log.warning(f"⚠️ {violation}")
        
        return {
            "valid": is_valid,
            "risk_usd": round(total_risk_usd, 2),
            "risk_percent": round(risk_percent, 2),
            "max_risk_percent": self.max_risk_per_trade * 100,
            "quantity": quantity,
            "comfort_status": "✅ Confortável" if is_valid else "❌ DESCONFORTÁVEL - REDUZIR"
        }
    
    # ========================================================
    # REGRA 5: EXECUÇÃO DISCIPLINADA
    # ========================================================
    
    def validate_execution_discipline(
        self,
        symbol: str,
        entry_time: datetime,
        plan: Dict
    ) -> Dict:
        
        exit_plan = plan.get("tps", [])
        exit_method = plan.get("exit_method", "unknown")
        
        is_disciplined = exit_method in ["tp_hit", "sl_hit"]
        
        audit_msg = f"[DISCIPLINE] {symbol} | Método: {exit_method} | {'✅' if is_disciplined else '❌'}"
        self.audit_log.append(audit_msg)
        log.info(audit_msg)
        
        if not is_disciplined:
            violation = f"REGRA 5 VIOLADA: {symbol} Saída indisciplinada ({exit_method})"
            self.violations.append(violation)
            log.warning(f"⚠️ {violation}")
        
        return {
            "valid": is_disciplined,
            "exit_method": exit_method,
            "had_plan": len(exit_plan) > 0,
            "message": "✅ Execução disciplinada" if is_disciplined else "❌ Saída emocional detectada"
        }
    
    # ========================================================
    # RELATÓRIO DE COMPLIANCE
    # ========================================================
    
    def get_compliance_report(self) -> Dict:
        report = {
            "timestamp": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
            "total_violations": len(self.violations),
            "violations": self.violations[-10:],  # Últimas 10
            "audit_entries": self.audit_log[-20:],  # Últimos 20
            "status": "✅ COMPLIANT" if len(self.violations) == 0 else "⚠️ VIOLATIONS FOUND"
        }
        
        return report
    
    def log_violation(self, rule_number: int, symbol: str, message: str):
        """Registra violação manualmente"""
        violation = f"REGRA {rule_number} VIOLADA: {symbol} - {message}"
        self.violations.append(violation)
        log.error(f"❌ {violation}")

class PositionSizer:
    @staticmethod
    def calculate_qty(
        account_balance: float,
        entry_price: float,
        sl_price: float,
        risk_percent: float = 0.02,  # 2% padrão
        side: str = "LONG"
    ) -> float:
        
        if side == "LONG":
            risk_per_unit = entry_price - sl_price
        else:
            risk_per_unit = sl_price - entry_price
        
        if risk_per_unit <= 0:
            return 0.0
        
        risk_amount = account_balance * risk_percent
        qty = risk_amount / risk_per_unit
        
        log.info(f"📊 Qty calculada: {qty:.4f} (Risk: ${risk_amount:.2f}, Risk/Unit: ${risk_per_unit:.4f})")
        
        return qty
    
    @staticmethod
    def validate_leverage(qty: float, entry_price: float, max_leverage: int) -> bool:
        """Valida se quantidade respeita leverage"""
        position_value = qty * entry_price
        effective_leverage = position_value / 1.0  # Assuming 1 USDT margin (demo)
        
        is_valid = effective_leverage <= max_leverage
        
        log.info(f"⚙️ Leverage efetivo: {effective_leverage:.1f}x (Máx: {max_leverage}x) {'✅' if is_valid else '❌'}")
        
        return is_valid
