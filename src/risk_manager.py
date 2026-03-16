class RiskManager:
    def __init__(self):
        self.max_positions = 3
        self.risk_per_trade_pct = 0.02  # Arrisca 2% do saldo no SL
        
        # Mapeamento: (Qty Decimal, Price Decimal)
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2),
            "ETHUSDT": (2, 2),
            "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3),
            "AVAXUSDT": (1, 3),
            "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), # ADA costuma ser 0 ou 1 casa no Qty
            "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        try:
            # 1. Calcula variação do preço
            price_variation = abs(current_price - sl_price) / current_price
            if price_variation < 0.002: price_variation = 0.002 # Mínimo 0.2%

            # 2. Alavancagem ideal
            ideal_leverage = self.risk_per_trade_pct / price_variation
            leverage = min(max(int(ideal_leverage), 1), 20) 

            # 3. Cálculo de Quantidade com TRAVA DE MARGEM
            # Não permite que a posição nominal exceda (Saldo * Alavancagem * 0.8)
            max_nominal_power = (balance * leverage) * 0.8
            
            qty_usdt = (balance * self.risk_per_trade_pct) / price_variation
            
            # Se o Qty calculado for maior que nosso poder de compra, reduzimos
            if qty_usdt > max_nominal_power:
                qty_usdt = max_nominal_power
                
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception as e:
            return 5, 0

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # Trava para ATR não ser absurdo
        max_atr = current_price * 0.015 
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