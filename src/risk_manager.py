import datetime
import pandas as pd

class RiskManager:
    # =========================================================
    # 1. INICIALIZAÇÃO E CONFIGURAÇÕES DE PRECISÃO
    # =========================================================
    def __init__(self):
        self.max_positions = 3
        self.fixed_leverage = 10.0  # Leverage base (será ajustada por regime)
        self.total_pnl_bruto = 0.0
        self.total_pnl = 0.0  # PnL acumulado total
        self.total_fees = 0.0
        self.trades_history = []
        self.performance = {}  # Rastreamento de performance por moeda
        
        self.stats = {
            'wins': 0,
            'losses': 0,
            'protected': 0, # <-- Nova categoria
            'total_trades': 0,
            'pnl_history': {}
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
        print(f" 📊  DASHBOARD DE PERFORMANCE (Desde 18/03)")
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