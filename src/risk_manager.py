class RiskManager:
    def __init__(self):
        self.max_positions = 3
        self.risk_per_trade_pct = 0.02  # 2% fixo aqui
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (3, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (1, 4), "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        try:
            # Calcula a variação decimal (ex: 0.01 para 1%)
            price_variation = abs(current_price - sl_price) / current_price
            if price_variation < 0.001: price_variation = 0.001 # Trava mínima

            # Alavancagem para arriscar 2% do saldo
            ideal_leverage = self.risk_per_trade_pct / price_variation
            leverage = min(max(int(ideal_leverage), 1), 20) 

            # Qty para perder exatamente os 2% se bater no SL
            qty_usdt = (balance * self.risk_per_trade_pct) / price_variation
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception as e:
            return 5, 0

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # Trava para o ATR não ser maior que 3% do preço (evita SL de 0.53 no XRP)
        max_atr = current_price * 0.03
        safe_atr = min(current_atr, max_atr)

        dist_sl = safe_atr * 1.5
        dist_tp = safe_atr * 3.0

        if side == "Buy":
            sl = current_price - dist_sl
            tp = current_price + dist_tp
        else:
            sl = current_price + dist_sl
            tp = current_price - dist_tp
            
        return round(sl, p_prec), round(tp, p_prec)