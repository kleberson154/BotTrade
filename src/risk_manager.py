class RiskManager:
    def __init__(self):
        self.max_positions = 2 
        self.risk_per_trade_pct = 0.03 # 3% do saldo por trade 
        
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        try:
            price_variation = abs(current_price - sl_price) / current_price
            # Aumentei a variação mínima para 0.8% para evitar alavancagem explosiva
            if price_variation < 0.008: price_variation = 0.008 

            ideal_leverage = self.risk_per_trade_pct / price_variation
            leverage = min(max(int(ideal_leverage), 1), 10) # Limite de 10x para preservar margem

            # Segurança: Posição nominal total não deve exceder 40% do saldo (mais conservador)
            max_pos_nominal = balance * 0.4 * leverage 
            
            qty_usdt = (balance * self.risk_per_trade_pct) / price_variation
            qty_usdt = min(qty_usdt, max_pos_nominal)
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception as e:
            return 5, 0

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # --- AJUSTE CRÍTICO: DISTÂNCIA DO STOP ---
        # 1.2 era muito curto. Aumentamos para 2.5 para sobreviver ao ruído.
        dist_sl = current_atr * 2.5
        
        # Take Profit maior para manter o Risk:Reward favorável (1:1.5 ou mais)
        dist_tp = current_atr * 4.0

        # Filtro de segurança: O Stop não pode ser menor que 0.6% nem maior que 3%
        min_sl = current_price * 0.006
        max_sl = current_price * 0.03
        dist_sl = max(min(dist_sl, max_sl), min_sl)

        if side == "Buy":
            sl = current_price - dist_sl
            tp = current_price + dist_tp
        else:
            sl = current_price + dist_sl
            tp = current_price - dist_tp
            
        return round(sl, p_prec), round(tp, p_prec)