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
    def update_dashboard(self, symbol, profit_loss):
        """Atualiza as estatísticas com distinção entre Loss e Proteção"""
        self.stats["total_trades"] += 1
        
        # CATEGORIZAÇÃO
        if profit_loss > 0: 
            self.stats["wins"] += 1
        elif profit_loss > -0.15: # Se perdeu só as taxas, é Proteção (Break-even)
            if "protected" not in self.stats: self.stats["protected"] = 0
            self.stats["protected"] += 1
        else: 
            self.stats["losses"] += 1
        
        # Acumula o PnL por símbolo
        if symbol not in self.stats["pnl_history"]:
            self.stats["pnl_history"][symbol] = 0.0
        self.stats["pnl_history"][symbol] += profit_loss
        
        self._print_terminal_dashboard()

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
        """Calcula estatísticas baseadas no histórico real injetado"""
        total_trades = self.stats.get('total_trades', 0)
        wins = self.stats.get('wins', 0)

        # Win Rate baseado nos contadores que o sync_historical_pnl atualiza
        win_rate = (wins / max(1, total_trades)) * 100

        # PnL Líquido somando o histórico de todas as moedas
        pnl_net_total = sum(self.stats["pnl_history"].values())

        return total_trades, win_rate, pnl_net_total

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
        prec_info = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        price_precision = prec_info[1]
        
        price = float(current_price)
        
        # --- AJUSTE SNIPER: MAIS FOLGA E ALVO MAIOR ---
        # Aumentamos o SL de 3.5 para 4.5 para evitar "violinadas" (ruído)
        # Aumentamos o TP de 6.0 para 9.0 para buscar o 2:1 real (pós-taxas)
        sl_distance = atr * 4.5
        tp_distance = atr * 9.0
        
        # --- FILTRO DE VIABILIDADE (ANTI-TAXA) ---
        # Se a volatilidade (ATR) for tão baixa que o TP não cobre as taxas (0.12%), 
        # forçamos uma distância mínima de 0.6% para o TP
        min_tp_dist = price * 0.006 
        if tp_distance < min_tp_dist:
            tp_distance = min_tp_dist
            # Ajustamos o SL proporcionalmente para manter o gerenciamento
            sl_distance = tp_distance / 2 

        # --- TRAVA ANTI-LIQUIDAÇÃO ---
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