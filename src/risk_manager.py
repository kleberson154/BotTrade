class RiskManager:
    def __init__(self):
        # Configurações para capital de R$ 100 (aprox. 18 USDT)
        # Dividimos o risco por 4 para permitir 4 ativos simultâneos sem "estourar" a margem
        self.max_positions = 4
        self.risk_per_trade = 0.20  # 20% da banca por ativo (total 60%)
        
        # Tabela de precisão atualizada
        self.PRECISION_MAP = {
            "BTCUSDT": (3, 2),
            "ETHUSDT": (2, 2),
            "SOLUSDT": (1, 3),
            "LINKUSDT": (1, 3),
            "AVAXUSDT": (1, 3),
            "XRPUSDT": (1, 4),
            "ADAUSDT": (0, 4),
            "DEFAULT": (0, 4)
        }

    def calculate_position_size(self, symbol, balance, current_price, leverage=3):
        # 1. Pega a precisão
        qty_precision = self.PRECISION_MAP.get(symbol, self.PRECISION_MAP["DEFAULT"])[0]
        
        # 2. Calcula quanto USDT será usado (ex: 18 USDT * 0.30 = 5.4 USDT por trade)
        risk_amount = float(balance) * float(self.risk_per_trade)
        
        # 3. Aplica a alavancagem no valor financeiro antes de converter para Qty
        # Ex: 5.4 USDT * 3x = 16.2 USDT de poder de compra
        notional_value = risk_amount * float(leverage)
        
        qty = notional_value / float(current_price)
        
        # 4. Arredonda conforme a regra da Bybit
        if qty_precision == 0:
            return int(qty)
        return round(float(qty), qty_precision)

    def get_sl_tp_adaptive(self, symbol, side, current_price, current_atr):
        # Obtém a precisão correta para cada moeda (Ex: XRP=4 casas, BTC=2 casas)
        tick_size, p_prec = self.PRECISION_MAP.get(symbol, (0.0001, 4))
        
        # Multiplicadores de risco (ajuste conforme seu perfil)
        sl_mult = 1.5  # Stop Loss a 1.5x a volatilidade atual
        tp_mult = 3.0  # Take Profit a 3x a volatilidade atual (Risco:Retorno 1:2)

        # Distância mínima de segurança (0.1% do preço) 
        # para evitar o erro de "SL acima do preço atual"
        min_dist = current_price * 0.001 
        dist_sl = max(current_atr * sl_mult, min_dist)
        dist_tp = max(current_atr * tp_mult, min_dist * 2)

        if side == "Buy":
            sl = min(current_price - dist_sl, current_price - tick_size) # Garante que está ABAIXO
            tp = current_price + dist_tp
        else:
            sl = max(current_price + dist_sl, current_price + tick_size) # Garante que está ACIMA
            tp = current_price - dist_tp
            
        # Arredonda conforme as regras da exchange
        return round(sl, p_prec), round(tp, p_prec)