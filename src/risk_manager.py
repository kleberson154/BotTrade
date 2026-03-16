class RiskManager:
    def __init__(self):
        # Configurações para capital de R$ 100 (aprox. 18-20 USDT)
        self.max_positions = 3 # Reduzido para 3 para garantir margem com R$ 100
        self.risk_per_trade_pct = 0.02  # 2% de risco do capital total por operação

        # Tabela de precisão: (Quantidade, Preço)
        # BTCUSDT: 3 casas no Qty (0.001), 2 casas no Preço (0.01)
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2),
            "ETHUSDT": (3, 2),
            "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3),
            "AVAXUSDT": (1, 3),
            "XRPUSDT": (1, 4),
            "ADAUSDT": (1, 4),
            "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        """
        Retorna (leverage, qty) dinâmicos. 
        O Qty é calculado para que, se bater no SL, você perca exatamente risk_per_trade_pct.
        """
        try:
            # 1. Calcula a variação percentual real até o Stop Loss
            price_variation = abs(current_price - sl_price) / current_price

            if price_variation == 0: 
                return 1, 0

            # 2. Calcula a alavancagem ideal para o risco de 2%
            # Se a variação for 1%, alavancagem 2x. Se for 0.5%, alavancagem 4x.
            ideal_leverage = self.risk_per_trade_pct / price_variation
            
            # Trava de segurança: Mínimo 1x, Máximo 20x para não estourar a conta
            leverage = min(max(int(ideal_leverage), 1), 20) 

            # 3. Calcula o Qty USDT baseado no risco financeiro direto
            # R$ 100 * 0.02 = R$ 2,00 de perda máxima por trade.
            qty_usdt = (balance * self.risk_per_trade_pct) / price_variation
            qty = qty_usdt / current_price

            return leverage, qty

        except Exception as e:
            print(f"Erro no cálculo dinâmico: {e}")
            return 5, 0 # Fallback seguro

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        # Pega a precisão de preço (índice 1 do map)
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # Multiplicadores
        sl_mult = 1.5  
        tp_mult = 3.0  

        dist_sl = current_atr * sl_mult
        dist_tp = current_atr * tp_mult

        # Garante distância mínima de 0.1% para não dar erro de ordem colada
        min_dist = current_price * 0.001
        dist_sl = max(dist_sl, min_dist)

        if side == "Buy":
            sl = current_price - dist_sl
            tp = current_price + dist_tp
        else:
            sl = current_price + dist_sl
            tp = current_price - dist_tp
            
        return round(sl, p_prec), round(tp, p_prec)