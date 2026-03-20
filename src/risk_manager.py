import datetime
import pandas as pd

class RiskManager:
    # =========================================================
    # 1. INICIALIZAÇÃO E CONFIGURAÇÕES DE PRECISÃO
    # =========================================================
    def __init__(self):
        self.max_positions = 3  
        self.total_pnl_bruto = 0.0
        self.total_fees = 0.0
        self.trades_history = []
        
        self.stats = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "pnl_history": {} # Armazena lucro/prejuízo acumulado por par
        }
        
        # Mapeamento de precisão da Bybit: (Quantidade, Preço)
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), "DEFAULT": (1, 4)
        }

    # =========================================================
    # 2. GESTÃO DE DESEMPENHO (DASHBOARD)
    # =========================================================
    def update_dashboard(self, symbol, profit_loss):
        """Atualiza as estatísticas e exibe o resumo no console"""
        self.stats["total_trades"] += 1
        
        if profit_loss > 0: 
            self.stats["wins"] += 1
        else: 
            self.stats["losses"] += 1
        
        # Acumula o PnL por símbolo
        if symbol not in self.stats["pnl_history"]:
            self.stats["pnl_history"][symbol] = 0.0
        self.stats["pnl_history"][symbol] += profit_loss
        
        # Renderização visual do Dashboard
        self._print_terminal_dashboard()

    def _print_terminal_dashboard(self):
        """Função interna para formatação do print"""
        total = max(1, self.stats['total_trades'])
        win_rate = (self.stats['wins'] / total) * 100
        
        print("\n" + "="*30)
        print(f"📊 DASHBOARD DE PERFORMANCE")
        print(f"Trades: {self.stats['total_trades']} | Win Rate: {win_rate:.1f}%")
        
        for sym, val in self.stats["pnl_history"].items():
            cor = "🟢" if val >= 0 else "🔴"
            print(f"{cor} {sym}: ${val:.2f}")
        print("="*30 + "\n")
        
    def get_total_pnl(self):
        """Retorna a soma de todo o PnL acumulado no histórico"""
        return sum(self.stats["pnl_history"].values())
    
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

    def get_performance_stats(self):
        if not self.trades_history:
            return 0, 0, 0
        
        wins = [t for t in self.trades_history if t['is_win']]
        win_rate = (len(wins) / len(self.trades_history)) * 100
        pnl_liquido_total = sum(t['pnl_net'] for t in self.trades_history)
        
        return len(self.trades_history), win_rate, pnl_liquido_total

    # =========================================================
    # 3. CÁLCULOS DINÂMICOS DE RISCO (ALAVANCAGEM E QTY)
    # =========================================================
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        """Calcula alavancagem ideal e tamanho da mão baseado no risco"""
        try:
            # 1. Calcula a variação percentual até o Stop Loss
            price_variation = abs(current_price - sl_price) / current_price
            # Filtro para evitar divisões por zero ou variações ínfimas
            if price_variation < 0.008: price_variation = 0.008

            # 2. Alavancagem Ideal: Risco fixo de 3% da banca por trade
            ideal_leverage = 0.03 / price_variation
            
            # Ajuste de segurança: Mínimo 8x, Máximo 12x para bancas pequenas
            leverage = int(min(max(ideal_leverage, 8), 12))
            
            # 3. Cálculo da Quantidade (Margem de 45% do saldo total)
            margin_to_use = balance * 0.45
            qty_usdt = margin_to_use * leverage
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception:
            # Fallback de segurança em caso de erro matemático
            return 10, 0

    # =========================================================
    # 4. CÁLCULOS DE STOP LOSS E TAKE PROFIT ADAPTATIVO
    # =========================================================
    def get_sl_tp_adaptive(self, symbol, side, current_price, atr, leverage):
        """Define SL e TP baseados na volatilidade (ATR) e alavancagem"""
        # Busca precisão do par ou usa o padrão
        prec_info = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        price_precision = prec_info[1]
        
        price = float(current_price)
        
        # Distâncias baseadas no ATR (Volatilidade atual)
        sl_distance = atr * 3.5
        tp_distance = atr * 6.0
        
        # --- TRAVA ANTI-LIQUIDAÇÃO ---
        # Garante que o Stop Loss esteja sempre antes de 70% da margem de liquidação
        max_safe_dist = (0.7 / leverage) * price
        if sl_distance > max_safe_dist:
            sl_distance = max_safe_dist

        if side == "Buy":
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance
            
        return round(sl, price_precision), round(tp, price_precision)