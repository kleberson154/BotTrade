class ExecutionManager:
    def __init__(self, session):
        self.session = session

    def has_open_position(self, symbol):
        try:
            resp = self.session.get_positions(category="linear", symbol=symbol)
            positions = resp.get('result', {}).get('list', [])
            for pos in positions:
                # Importante verificar se o size é maior que zero
                if float(pos.get('size', 0)) > 0:
                    return True
            return False
        except Exception as e:
            print(f"❌ Erro ao verificar posições em {symbol}: {e}")
            return True 

    def place_market_order(self, symbol, side, price, qty, sl, tp):
        try:
            # Proteção: Se a quantidade for zero ou negativa, nem tenta enviar
            if float(qty) <= 0:
                print(f"⚠️ Ordem cancelada: Qtd insuficiente para {symbol} (Saldo ou Alavancagem baixos)")
                return None

            return self.session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Limit",      # Mudamos para Limit
                price=str(price),       # Preço é OBRIGATÓRIO para Limit
                qty=str(qty),
                takeProfit=str(tp),
                stopLoss=str(sl),
                tpOrderType="Market",
                slOrderType="Market",
                tpslMode="Full",
                timeInForce="PostOnly"  # Garante que você seja MAKER (Taxa menor)
            )
        except Exception as e:
            print(f"❌ Falha na execução da ordem em {symbol}: {e}")
            return None
        
    def update_stop_loss(self, symbol, new_sl):
        try:
            return self.session.set_trading_stop(
                category="linear",
                symbol=symbol,
                stopLoss=str(new_sl),
                tpslMode="Full"
            )
        except Exception as e:
            print(f"⚠️ Erro ao atualizar Stop Loss em {symbol}: {e}")
            return None

    def cancel_all_pending_orders(self, symbol):
        try:
            response = self.session.cancel_all_orders(category="linear", symbol=symbol)
            return response.get('retCode') == 0
        except Exception as e:
            print(f"❌ Erro ao cancelar ordens em {symbol}: {e}")
            return False