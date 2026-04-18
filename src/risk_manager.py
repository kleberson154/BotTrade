import datetime
import pandas as pd
import logging
import os
from pathlib import Path

from src.mack_compliance import MackCompliance, PositionSizer

log = logging.getLogger(__name__)

class RiskManager:
    # =========================================================
    # 1. INICIALIZAÇÃO E CONFIGURAÇÕES DE PRECISÃO
    # =========================================================
    def __init__(self, account_balance: float = 100.0):
        """Inicializa RiskManager com saldo da conta Bybit"""
        self.max_positions = 5  # Aumentado para 15 moedas, banca 120 USDT
        self.fixed_leverage = 10.0  # Leverage base (será ajustada por regime)
        self.total_pnl_bruto = 0.0
        self.total_pnl = 0.0  # PnL acumulado total
        self.total_fees = 0.0
        self.trades_history = []
        self.performance = {}  # Rastreamento de performance por moeda
        
        # � Timestamp de reset dos stats
        self.reset_date_str = "2026-04-18 03:00:00"
        
        # �💰 Balance sincronizado com Bybit
        self.account_balance = account_balance
        
        # 🆕 INTEGRAÇÃO MACK: 5 Regras de Trading Disciplinado
        self.compliance = MackCompliance(account_balance=account_balance)
        self.position_sizer = PositionSizer()
        
        self.stats = {
            'wins': 0,
            'losses': 0,
            'total_trades': 0,
            'pnl_history': {},
            'exit_methods': {  # Auditoria de como cada trade saiu
                'tp_hit': 0,      # Saiu no TP
                'sl_hit': 0,      # Saiu no SL (mesmo que com lucro)
                'sl_profit': 0,   # Saiu no SL MAS com lucro
                'sl_loss': 0,     # Saiu no SL com prejuízo
                'manual_close': 0, # Fechado manualmente
                'other': 0        # Outros motivos
            }
        }
        
        # Mapeamento de precisão da Bybit: (Quantidade, Preço)
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), "NEARUSDT": (1, 3), "DOTUSDT": (1, 3),  
            "SUIUSDT": (1, 4), "OPUSDT": (1, 4), 
            # 🆕 Novos símbolos com precisão ajustada
            "RAVEUSDT": (1, 4), "LYNUSDT": (0, 4), "HYPEUSDT": (1, 4), 
            "IRYSUSDT": (0, 4),
            "DEFAULT": (1, 4)
        }

    # =========================================================
    # 2. GESTÃO DE DESEMPENHO (DASHBOARD)
    # =========================================================
    def update_dashboard(self, symbol, pnl_liquido):
        self.stats['total_trades'] += 1
        
        if pnl_liquido > 0.05:
            self.stats['wins'] += 1
            status = "WIN"
        else:
            self.stats['losses'] += 1
            status = "LOSS"
    
        self.stats['pnl_history'][symbol] = self.stats['pnl_history'].get(symbol, 0) + pnl_liquido
        return status

    def get_performance_stats(self):
        total = self.stats["total_trades"]
        wins = self.stats["wins"]
        win_rate = (wins / total * 100) if total > 0 else 0
        pnl_net = sum(self.stats["pnl_history"].values())
        
        # Calcula proteção (SL hits vs total) e taxa de sucesso
        sl_hits = self.stats['exit_methods'].get('sl_hit', 0)
        protection_rate = (sl_hits / total * 100) if total > 0 else 0
        success_rate = win_rate  # Mesmo que win_rate (% de trades lucrativos)
        
        return total, wins, protection_rate, win_rate, success_rate, pnl_net
    
    def add_historical_trade(self, symbol, pnl_net):
        if symbol not in self.performance:
            self.performance[symbol] = []
            self.performance[symbol].append(pnl_net)
            self.total_pnl += pnl_net
    
    def add_trade_result(self, symbol, pnl_bruto, fees):
        pnl_net = pnl_bruto - fees
        self.total_pnl_bruto += pnl_bruto
        self.total_fees += fees
        
        trade_data = {
            'symbol': symbol,
            'pnl_net': pnl_net,
            'is_win': pnl_net > 0,
            'timestamp': datetime.datetime.now()
        }
        self.trades_history.append(trade_data)
        return pnl_net

    # =========================================================
    # 3. CÁLCULOS DINÂMICOS DE RISCO (ALAVANCAGEM E QTY)
    # =========================================================
    def set_leverage_for_regime(self, regime):
        regime_leverage_map = {
            "COLD": 5.0,
            "LATERAL": 3.0,
            "NORMAL": 10.0,
            "HOT": 15.0,
        }
        self.fixed_leverage = regime_leverage_map.get(regime, 10.0)
    
    def get_dynamic_risk_params(self, entry_price, sl_price, total_balance):
        margin_per_trade = total_balance / self.max_positions 
        position_value = margin_per_trade * self.fixed_leverage
        qty = position_value / entry_price
        
        return self.fixed_leverage, qty

    # =========================================================
    # 4. CÁLCULOS DE STOP LOSS E TAKE PROFIT ADAPTATIVO
    # =========================================================
    def get_sl_tp_adaptive(self, symbol, side, price, atr, leverage):
        """
        Define o Stop Loss inicial.
        O SL é baseado no ATR (volatilidade), e então a cascata de TPs
        (check_cascade_tp) vai gerenciar saídas parciais em TP1, TP2, TP3.
        """
        distancia_sl = atr * 2.2 # Stop técnico curto
        
        if side == "Buy":
            sl = price - distancia_sl
            tp = price + (distancia_sl * 2.5) # Alvo inicial de 2.5x o risco
        else:
            sl = price + distancia_sl
            tp = price - (distancia_sl * 2.5)
            
        return sl, tp
    
    # =========================================================
    # 🆕 5. MACK COMPLIANCE - 5 REGRAS DE TRADING DISCIPLINADO
    # =========================================================
    
    def validate_trade_mack(self, entry, sl, tp, symbol, side="LONG"):
        """
        🚨 REGRA 1 DO MACK: Risco:Retorno 1:2 MÍNIMO
        
        Rejeita qualquer trade que não tenha pelo menos 1:2
        Por quê? Precisaria de 80% de acerto para ganhar dinheiro com RR<1:2
        """
        result = self.compliance.validate_rr_ratio(entry, sl, tp, side, symbol)
        
        if not result['valid']:
            log.error(f"❌ {symbol} REJEITADO: RR {result['ratio']}:1 < 1:2 (Mack Rule #1)")
            return {"valid": False, "reason": result, "ratio": result['ratio']}
        
        log.info(f"✅ {symbol} {side} | RR: {result['ratio']}:1 APROVADO (Mack Rule #1)")
        return {"valid": True, "ratio": result['ratio']}
    
    def calculate_position_size_mack(self, entry, sl, account_balance=None, side="LONG", risk_percent=0.02):
        """
        🚨 REGRA 4 DO MACK: Dimensionamento Confortável
        
        Fórmula Mack: Qty = (Account × Risk%) / |Entry - SL|
        Risco máximo: 2% por trade (padrão profissional)
        
        Resultado: Você dorme tranquilo com a posição!
        """
        if account_balance is None:
            account_balance = self.account_balance
        
        qty = self.position_sizer.calculate_qty(
            account_balance=account_balance,
            entry_price=entry,
            sl_price=sl,
            risk_percent=risk_percent,
            side=side
        )
        
        # Validar se posição está confortável
        sizing_result = self.compliance.validate_position_sizing(
            symbol="",
            entry=entry,
            sl=sl,
            quantity=qty,
            leverage=int(self.fixed_leverage),
            account_balance=account_balance,
            side=side
        )
        
        if not sizing_result['valid']:
            log.warning(f"⚠️ {sizing_result['comfort_status']}")
        
        return qty
    
    def check_sl_violation(self, symbol, old_sl, new_sl, side, current_pnl):
        """
        🚨 REGRA 2 DO MACK: SL Imóvel em Prejuízo
        
        Detecta violações: SL nunca deve se mover CONTRA trader quando em perda
        Se isso acontecer, é erro emocional grave!
        """
        result = self.compliance.validate_sl_immobility(
            symbol=symbol,
            current_price=0,  # Não usado aqui
            sl_original=old_sl,
            sl_current=new_sl,
            side=side,
            current_pnl=current_pnl
        )
        
        if not result['valid']:
            log.error(f"🚨 REGRA 2 VIOLADA ({symbol}): SL mexido de {old_sl} para {new_sl} em {current_pnl:.2f}% PnL")
            self.compliance.log_violation(
                rule_number=2,
                symbol=symbol,
                message=f"SL movido contra trader em {current_pnl:.2f}% perda"
            )
            return False
        
        return True
    
    def check_averaging_down(self, symbol, recent_additions, total_pnl, is_losing):
        """
        🚨 REGRA 3 DO MACK: Sem Averaging Down
        
        Averaging down (pirâmide invertida) é o caminho mais rápido para ruína!
        Detecta se está adicionando capital enquanto perde.
        """
        result = self.compliance.validate_no_averaging_down(
            symbol=symbol,
            recent_additions=recent_additions,
            total_pnl=total_pnl,
            is_losing=is_losing
        )
        
        if result['averaging_down']:
            log.error(f"🚨 REGRA 3 VIOLADA ({symbol}): Averaging Down detectado! {recent_additions} adições em {total_pnl:.2f}% perda")
        
        return result['valid']
    
    def get_compliance_report(self):
        """Retorna auditoria completa das 5 regras do Mack"""
        return self.compliance.get_compliance_report()
    
    def update_compliance(self, account_balance):
        """Atualiza saldo de compliance (chamar após trade fechado)"""
        self.account_balance = account_balance
        self.compliance.account_balance = account_balance

    def calculate_dynamic_tp(self, price, side, atr_pct, adx, regime="NORMAL"):
        """
        Calcula TP dinâmico baseado em regime, volatilidade (ATR%) e trend force (ADX).
        
        Regimes:
        - COLD: ATR% < 0.10%, TP% = 12-15%
        - LATERAL: 0.10% < ATR% < 0.18%, TP% = 14-18%
        - NORMAL: ATR% padrão, TP% = 18-22%
        - HOT: ATR% >= 0.18%, TP% = 22-28%
        
        ADX modula adicionalmente:
        - ADX > 30: Tendência forte, +3% no TP
        - ADX < 20: Tendência fraca, -2% no TP
        """
        base_tp_pct = {
            "COLD": 0.14,      # 14% base
            "LATERAL": 0.16,   # 16% base
            "NORMAL": 0.20,    # 20% base (padrão anterior)
            "HOT": 0.25,       # 25% base (mais agressivo)
        }
        
        tp_pct = base_tp_pct.get(regime, 0.20)
        
        # 1. Ajusta baseado em volatilidade adicional (ATR%)
        # Se ATR% > 0.20, aumenta um pouco o TP (mercado é volátil, consegue mover mais)
        volatility_bonus = 0.0
        if atr_pct > 0.0020:  # > 0.20%
            volatility_bonus = (atr_pct - 0.0020) * 2.5  # Até +0.05 extra
        
        tp_pct += volatility_bonus
        
        # 2. Ajusta baseado na força da tendência (ADX)
        if adx > 30:
            tp_pct += 0.03  # +3% em tendências muito fortes
        elif adx < 20:
            tp_pct -= 0.02  # -2% em tendências fracas
        
        # 3. Assegura limites razoáveis
        tp_pct = max(0.10, min(0.40, tp_pct))  # Min 10%, Max 40%
        
        # 4. Calcula o preço de TP
        if side.upper() == "BUY":
            tp_price = price * (1.0 + tp_pct)
        else:  # SELL
            tp_price = price * (1.0 - tp_pct)
        
        return tp_price