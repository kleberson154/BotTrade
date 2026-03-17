class RiskManager:
    def __init__(self):
        self.max_positions = 1 
        self.risk_per_trade_pct = 0.05 # 5% do saldo por trade 
        
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4), "DEFAULT": (1, 4)
        }
        
    def get_dynamic_risk_params(self, current_price, sl_price, balance):
        try:
            # 1. Calcula a variação real do preço até o Stop Loss
            price_variation = abs(current_price - sl_price) / current_price
            
            # Trava de segurança: Variação mínima de 1% para evitar alavancagem infinita
            if price_variation < 0.01: price_variation = 0.01 

            # 2. Cálculo da Alavancagem Ideal baseado no risco (3% a 5% da banca)
            # Usamos 0.04 (4%) como base de risco para banca pequena
            ideal_leverage = 0.04 / price_variation
            
            # --- NOVA DINÂMICA DE ALAVANCAGEM ---
            # Mínimo de 10x, máximo de 15x (para não ser liquidado rápido com $13)
            leverage = int(min(max(ideal_leverage, 10), 15))

            # 3. Cálculo do Tamanho da Posição (Quantity)
            # Com $13, precisamos de ordens que valham pelo menos $40~50 nominais (Margin * Leverage)
            # para que a Bybit não rejeite por "qty too low".
            
            # Forçamos o uso de pelo menos 60% do saldo como margem se a banca for < $20
            margin_to_use = balance * 0.6 if balance < 20 else balance * 0.4
            
            qty_usdt = margin_to_use * leverage
            qty = qty_usdt / current_price

            return leverage, qty
        except Exception as e:
            log.error(f"Erro no cálculo de risco: {e}")
            return 10, 0

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        _, p_prec = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])
        
        # --- AJUSTE CRÍTICO: DISTÂNCIA DO STOP ---
        # 1. Aumentamos o multiplicador do ATR para dar mais folga (de 2.5 para 3.0)
        dist_sl = current_atr * 3.0
        
        # 2. Definimos um Take Profit mais longo para compensar o stop maior
        dist_tp = current_atr * 5.5

        # 0.006 (0.6%) era muito pouco. Subimos para 0.015 (1.5%) como o MÍNIMO absoluto.
        # Assim, mesmo que o mercado esteja parado, o bot deixará 1.5% de espaço.
        min_sl = current_price * 0.015 
        max_sl = current_price * 0.04   # Máximo de 4% para não queimar a banca
        
        dist_sl = max(min(dist_sl, max_sl), min_sl)
        
        # Garante que o TP seja pelo menos 2x o tamanho do SL (Risk:Reward de 1:2)
        dist_tp = max(dist_tp, dist_sl * 2.0)

        if side == "Buy":
            sl = current_price - dist_sl
            tp = current_price + dist_tp
        else:
            sl = current_price + dist_sl
            tp = current_price - dist_tp
            
        return round(sl, p_prec), round(tp, p_prec)