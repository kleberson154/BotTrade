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
    def __init__(self):
        self.max_positions = 5  # Aumentado para 15 moedas, banca 120 USDT
        self.fixed_leverage = 10.0  # Leverage base (será ajustada por regime)
        self.total_pnl_bruto = 0.0
        self.total_pnl = 0.0  # PnL acumulado total
        self.total_fees = 0.0
        self.trades_history = []
        self.performance = {}  # Rastreamento de performance por moeda
        
        # 🔄 Sistema de Reset - Carrega timestamp de reset se existir
        self.reset_timestamp = self._load_reset_timestamp()
        self.reset_date_str = self._format_reset_date()
        
        # 🆕 INTEGRAÇÃO MACK: 5 Regras de Trading Disciplinado
        self.compliance = MackCompliance(account_balance=1000.0)
        self.position_sizer = PositionSizer()
        self.account_balance = 1000.0
        
        self.stats = {
            'wins': 0,
            'losses': 0,
            'protected': 0, # <-- Nova categoria
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
            "SUIUSDT": (1, 4),  "FETUSDT": (1, 4),  "OPUSDT": (1, 4),   
            "DEFAULT": (1, 4)
        }

    # =========================================================
    # 🆕 SISTEMA DE RESET - CARREGA TIMESTAMP DE REINÍCIO
    # =========================================================
    def _load_reset_timestamp(self):
        """
        Carrega o timestamp de reset do arquivo RESET_TRADES_TODAY.txt.
        Se não existir, retorna None (calcula desde o início).
        """
        reset_file = Path("RESET_TRADES_TODAY.txt")
        if reset_file.exists():
            try:
                with open(reset_file, 'r') as f:
                    timestamp_str = f.read().strip()
                    # Parse timestamp ISO format: 2026-04-13T02:12:05.047564
                    return datetime.datetime.fromisoformat(timestamp_str)
            except Exception as e:
                log.warning(f"⚠️ Erro ao carregar reset timestamp: {e}")
                return None
        return None
    
    def _format_reset_date(self):
        """
        Formata a data de reset em formato legível (DD/MM).
        Usado no dashboard.
        """
        if self.reset_timestamp:
            return self.reset_timestamp.strftime("%d/%m")
        return "18/03"  # Fallback histórico
    
    def _is_trade_after_reset(self, trade_timestamp):
        """
        Verifica se um trade ocorreu APÓS o reset.
        Se não há reset configurado, considera todos os trades.
        """
        if not self.reset_timestamp:
            return True  # Sem reset, aceita todos
        
        if isinstance(trade_timestamp, str):
            try:
                trade_timestamp = datetime.datetime.fromisoformat(trade_timestamp)
            except:
                return False
        
        return trade_timestamp >= self.reset_timestamp

    # =========================================================
    # 2. GESTÃO DE DESEMPENHO (DASHBOARD)
    # =========================================================
    def update_dashboard(self, symbol, pnl_liquido):
        self.stats['total_trades'] += 1
        
        # Se o PnL for positivo, é uma vitória, não importa se saiu no TP ou SL
        if pnl_liquido > 0.05: # Consideramos > 0.05 para cobrir variações de centavos
            self.stats['wins'] += 1
            status = "WIN"
        # Se o PnL for quase zero (positivo ou negativo muito baixo), foi Proteção
        elif pnl_liquido >= -0.10: 
            self.stats['protected'] = self.stats.get('protected', 0) + 1
            status = "PROTECTED"
        # Só é LOSS se o prejuízo for real
        else:
            self.stats['losses'] += 1
            status = "LOSS"
    
        self.stats['pnl_history'][symbol] = self.stats['pnl_history'].get(symbol, 0) + pnl_liquido
        return status

    def record_exit_method(self, method="other", pnl=0):
        """
        Registra como um trade foi fechado.
        method: 'tp_hit', 'sl_hit', 'manual_close', 'other'
        """
        if method == "sl_hit":
            self.stats['exit_methods']['sl_hit'] += 1
            if pnl > 0:
                self.stats['exit_methods']['sl_profit'] += 1
            else:
                self.stats['exit_methods']['sl_loss'] += 1
        elif method in self.stats['exit_methods']:
            self.stats['exit_methods'][method] += 1

    def get_exit_methods_summary(self):
        """Retorna resumo dos métodos de saída para auditoria"""
        em = self.stats['exit_methods']
        total_closed = em['tp_hit'] + em['sl_hit'] + em['manual_close'] + em['other']
        
        summary = {
            'tp_saidas': em['tp_hit'],
            'sl_saidas_total': em['sl_hit'],
            'sl_com_lucro': em['sl_profit'],
            'sl_com_prejuizo': em['sl_loss'],
            'fechos_manuais': em['manual_close'],
            'outros': em['other'],
            'total_fechados': total_closed
        }
        return summary

    def get_performance_stats(self):
        """Retorna estatísticas detalhadas para o Telegram"""
        total = self.stats["total_trades"]
        wins = self.stats["wins"]
        # Garante que a chave exista para evitar erros em contas novas
        protected = self.stats.get("protected", 0)
        
        # Win Rate Real (exclui os protegidos do cálculo de erro)
        win_rate = (wins / total * 100) if total > 0 else 0
        # Taxa de Sobrevivência (Trades que não machucaram a banca)
        survival_rate = ((wins + protected) / total * 100) if total > 0 else 0
        
        pnl_net = sum(self.stats["pnl_history"].values())
        
        return total, wins, protected, win_rate, survival_rate, pnl_net

    def _print_terminal_dashboard(self):
        """Exibe a performance acumulada detalhada no terminal"""
        # RECEBENDO OS 6 VALORES (Ordem correta: total, wins, prot, wr, sr, pnl_net)
        total, wins, prot, wr, sr, pnl_net = self.get_performance_stats()

        print("\n" + "═"*45)
        print(f" 📊  DASHBOARD DE PERFORMANCE (Desde {self.reset_date_str})")
        print(f" 📈  Win Rate Real: {wr:5.1f}% | 🛡️ Sobrevivência: {sr:5.1f}%")
        print(f" 🔄  Total: {total:3} (✅:{wins} | 🛡️:{prot} | ❌:{total-wins-prot})")
        print(f" 💰  PnL Líquido Total: ${pnl_net:8.2f}")
        print("-" * 45)

        # Itera sobre o histórico de cada moeda
        for sym, val in self.stats["pnl_history"].items():
            if abs(val) < 0.0001: continue # Pula moedas sem atividade real

            cor = "🟢" if val >= 0 else "🔴"
            print(f" {cor} {sym.ljust(12)}: ${val:>10.2f}")

        print("═"*45 + "\n")
        
    def get_total_pnl(self):
        """Retorna a soma de todo o PnL acumulado no histórico"""
        return sum(self.stats["pnl_history"].values())
    
    def is_trading_allowed(self):
        """Valida se o bot pode fazer trades baseado em WR e PnL acumulado."""
        total, wins, protected, wr, sr, pnl_net = self.get_performance_stats()
        
        # Sem trades ainda, permite
        if total == 0:
            return True, "STARTUP"
        
        # WR muito baixo: bloqueia
        if wr < 32.0:
            return False, f"⛔ WR crítico {wr:.1f}% (<32%) - BLOQUEADO"
        
        # WR entre 32-38: permite mas com leverage reduzida
        if wr < 38.0:
            return True, f"⚠️ WR baixo {wr:.1f}% - LEVERAGE REDUZIDA 50%"
        
        # WR entre 38-42: permite com leverage normal
        if wr < 42.0:
            return True, f"📊 WR moderado {wr:.1f}% - NORMAL"
        
        # WR >= 42: permite com leverage máximo
        return True, f"✅ WR forte {wr:.1f}% - MÁXIMO"
    
    def get_leverage_multiplier(self):
        """Retorna multiplicador de alavancagem baseado em WR."""
        total, wins, protected, wr, sr, pnl_net = self.get_performance_stats()
        
        if total == 0 or wr >= 42.0:
            return 1.0  # 100% da alavancagem normal
        elif wr >= 38.0:
            return 1.0  # 100%
        elif wr >= 32.0:
            return 0.5  # 50% da alavancagem (mais conservador)
        else:
            return 0.0  # Bloqueado
    
    def add_historical_trade(self, symbol, pnl_net):
        if symbol not in self.performance:
            self.performance[symbol] = []
            self.performance[symbol].append(pnl_net)
            self.total_pnl += pnl_net # Soma ao PnL acumulado do bot
    
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
        """Define alavancagem baseada no regime detectado."""
        regime_leverage_map = {
            "COLD": 5.0,
            "LATERAL": 3.0,
            "NORMAL": 10.0,
            "HOT": 15.0,
        }
        self.fixed_leverage = regime_leverage_map.get(regime, 10.0)
    
    def get_dynamic_risk_params(self, entry_price, sl_price, total_balance):
        """
        Calcula quanto de 'Qty' (lote) comprar para usar a banca de $20 com 20x.
        """
        # 1. Definimos quanto da banca vamos usar como margem
        # Para $20, vamos usar $6 de margem por trade (permitindo 3 trades)
        margin_per_trade = total_balance / self.max_positions 
        
        # 2. O valor real da posição (Margem * Alavancagem)
        # Ex: $6 * 20x = $120 de poder de compra
        position_value = margin_per_trade * self.fixed_leverage
        
        # 3. Quantidade de moedas (Qty)
        qty = position_value / entry_price
        
        # Retorna a alavancagem fixa e a quantidade calculada
        return self.fixed_leverage, qty

    # =========================================================
    # 4. CÁLCULOS DE STOP LOSS E TAKE PROFIT ADAPTATIVO
    # =========================================================
    def get_sl_tp_adaptive(self, symbol, side, price, atr, leverage):
        """
        Define o Stop Loss e Take Profit inicial.
        O SL é baseado no ATR (volatilidade), mas o monitor_protection 
        vai assumir o controle depois.
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