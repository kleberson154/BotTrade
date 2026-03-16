class RiskManager:
    def __init__(self):
        self.max_positions = 2 # Reduzi para 2 para não dividir demais seus R$ 100
        self.risk_per_trade_pct = 0.015 # 1.5% de risco (mais conservador para banca pequena)
        
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        try:
            price_variation = abs(current_price - sl_price) / current_price
            if price_variation < 0.005: price_variation = 0.005 # SL mínimo de 0.5%

            # Alavancagem
            ideal_leverage = self.risk_per_trade_pct / price_variation
            leverage = min(max(int(ideal_leverage), 1), 20) 

            # CÁLCULO DE QTY PARA BANCA PEQUENA (R$ 100)
            # Vamos limitar a posição nominal a no máximo 50% do saldo total por trade
            # para garantir que a margem sempre exista.
            max_pos_nominal = balance * 0.5 * leverage 
            
            qty_usdt = (balance * self.risk_per_trade_pct) / price_variation
            
            # Escolhe o menor entre o risco calculado e o limite de segurança
            qty_usdt = min(qty_usdt, max_pos_nominal)
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception as e:
            return 5, 0

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # Reduzi os alvos para banca pequena (SL mais curto = Menos margem presa)
        max_atr = current_price * 0.01 
        safe_atr = min(current_atr, max_atr)

        dist_sl = safe_atr * 1.2
        dist_tp = safe_atr * 2.5

        if side == "Buy":
            sl = current_price - dist_sl
            tp = current_price + dist_tp
        else:
            sl = current_price + dist_sl
            tp = current_price - dist_tp
            
        return round(sl, p_prec), round(tp, p_prec)