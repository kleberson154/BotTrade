import logging
from src.multi_tp_manager import SMCTPManager

log = logging.getLogger(__name__)

class ExecutionManager:
    def __init__(self, session):
        self.session = session
        
        # 🆕 Gerenciamento SMC (Múltiplos TPs)
        self.tp_managers = {}  # {symbol: SMCTPManager}
        self.active_sessions = {}  # {symbol: TradingSession}

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
    
    # =========================================================
    # 🆕 GESTÃO SMC (MÚLTIPLOS TPS) - MACK FRAMEWORK
    # =========================================================
    
    def setup_smc_management(self, symbol, side, entry, sl, tp1, tp2, tp3):
        """
        Configura gestão SMC com 3 níveis de TP
        
        TP1 (40%): Close + SL para Entry (Risco zerado)
        TP2 (40%): Close + SL para TP1 (Protegido)
        TP3 (20%): Runner final (Saída total)
        
        Chamada: setup_smc_management("LABUSDT", "LONG", 0.4818, 0.437224, 0.541235, 0.60067, 0.660105)
        """
        
        tp_manager = SMCTPManager.create_smc_config(
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3
        )
        
        self.tp_managers[symbol] = tp_manager
        
        log.info(f"✅ Gestão SMC ativada para {symbol}")
        log.info(f"   TP1: {tp1} (40%, SL→Entry)")
        log.info(f"   TP2: {tp2} (40%, SL→TP1)")
        log.info(f"   TP3: {tp3} (20%, Runner)")
        
        return tp_manager
    
    def monitor_tp_hits(self, symbol, current_price):
        """
        Monitora preço e detecta se algum TP foi atingido
        
        Retorna: lista de TPs atingidos ou None
        Deve ser chamado continuamente no loop principal
        """
        
        if symbol not in self.tp_managers:
            return None
        
        tp_manager = self.tp_managers[symbol]
        hits = tp_manager.check_tp_hit(current_price)
        
        if hits:
            for hit in hits:
                log.info(f"🎯 {symbol} TP{hit['tp_level']} atingido em {current_price}!")
                log.info(f"   Ação: {hit['action']}")
                if hit['new_sl']:
                    log.info(f"   Novo SL: {hit['new_sl']}")
        
        return hits
    
    def execute_tp_close(self, symbol, tp_level, qty, close_price):
        """
        Executa fechamento em um nível de TP
        
        Registra o evento no gerenciador SMC para rastreamento
        """
        
        if symbol not in self.tp_managers:
            log.error(f"❌ {symbol} não tem gestor SMC configurado")
            return False
        
        tp_manager = self.tp_managers[symbol]
        
        # Registrar close
        close_record = tp_manager.register_close(
            tp_level=tp_level,
            closed_quantity=qty,
            close_price=close_price
        )
        
        log.info(f"✅ {symbol} TP{tp_level} fechado: {close_record['total_closed']}% da posição")
        
        return True
    
    def get_next_tp(self, symbol):
        """Retorna o próximo TP pendente para o símbolo"""
        
        if symbol not in self.tp_managers:
            return None
        
        return self.tp_managers[symbol].get_remaining_tp_for_exit()
    
    def get_current_sl(self, symbol):
        """Retorna o SL atual (pode ter sido movido após TPs)"""
        
        if symbol not in self.tp_managers:
            return None
        
        return self.tp_managers[symbol].current_sl
    
    def get_smc_status(self, symbol):
        """Retorna status completo da gestão SMC"""
        
        if symbol not in self.tp_managers:
            return None
        
        return self.tp_managers[symbol].get_status()