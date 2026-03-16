class ExecutionManager:
    def __init__(self, session):
        self.session = session

    def has_open_position(self, symbol):
        """
        Verifica se já existe uma posição aberta para o símbolo.
        """
        try:
            resp = self.session.get_positions(
                category="linear",
                symbol=symbol
            )
            # Na Bybit V5, se size > 0, há uma posição aberta
            positions = resp.get('result', {}).get('list', [])
            for pos in positions:
                if float(pos.get('size', 0)) > 0:
                    return True
            return False
        except Exception as e:
            print(f"❌ Erro ao verificar posições: {e}")
            return True # Retorna True por segurança para evitar ordens duplicadas

    def place_market_order(self, symbol, side, qty, sl, tp):
        """
        Executa a ordem a mercado com SL e TP.
        """
        try:
            return self.session.place_order(
                category="linear",
                symbol=symbol,
                side=side,
                orderType="Market",
                qty=str(qty),
                takeProfit=str(tp),
                stopLoss=str(sl),
                tpOrderType="Market",
                slOrderType="Market",
                tpslMode="Full"
            )
        except Exception as e:
            print(f"❌ Falha na execução da ordem em {symbol}: {e}")
            return None
        
    def update_stop_loss(self, symbol, new_sl):
        try:
            # Na Bybit V5, usamos o set_trading_stop para atualizar SL/TP
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
        """
        Cancela todas as ordens LIMIT que ainda não foram preenchidas.
        """
        try:
            response = self.session.cancel_all_orders(
                category="linear",
                symbol=symbol
            )
            if response.get('retCode') == 0:
                return True
            return False
        except Exception as e:
            print(f"❌ Erro ao cancelar ordens: {e}")
            return False