"""
⚡ TP Cascade Manager - Scalping Edition
Gerencia 3 níveis de TP com closes parciais otimizados para scalping.

TPs Scalping (REALISTA & ALCANÇÁVEL):
  TP1 (50%): +0.5% de lucro → Move SL para Entry (zero-risk)
  TP2 (30%): +1.0% de lucro → Move SL para TP1 (ganho garantido)  
  TP3 (20%): +1.5% de lucro → Runner final (deixa correr)

Filosofia: Muitos pequenos ganhos CONSISTENTES > um grande ganho eventual
"""

import logging
from typing import Dict, List, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


class TPStatus(Enum):
    """Estados possíveis de um TP"""
    PENDING = "PENDING"
    HIT = "HIT"
    CANCELLED = "CANCELLED"


@dataclass
class CascadeTPLevel:
    """Nível individual de TP"""
    tp_num: int                          # 1, 2 ou 3
    tp_price: float                      # Preço alvo
    close_percent: float                 # % da posição a fechar (50%, 30%, 20%)
    sl_move_to: Optional[float] = None   # Novo SL após fechar este TP
    status: TPStatus = TPStatus.PENDING
    closed_at_time: Optional[str] = None
    closed_at_price: Optional[float] = None


class TPCascadeManager:
    """Gerencia cascata de TPs com closes parciais automáticos para scalping"""
    
    # ⚡ TPs SCALPING: muito menores e realistas
    SCALP_TARGETS = {
        "COLD":   {"tp1": 0.0035, "tp2": 0.0070, "tp3": 0.0100},  # Conservador
        "NORMAL": {"tp1": 0.0050, "tp2": 0.0100, "tp3": 0.0150},  # Padrão
        "HOT":    {"tp1": 0.0050, "tp2": 0.0100, "tp3": 0.0200},  # Agressivo
    }
    
    def __init__(self, symbol: str, side: str, entry: float, initial_sl: float, 
                 account_balance: float, leverage: int = 5):
        """Inicializa gerenciador de cascata"""
        self.symbol = symbol
        self.side = side  # LONG ou SHORT
        self.entry = entry
        self.initial_sl = initial_sl
        self.current_sl = initial_sl
        self.account_balance = account_balance
        self.leverage = leverage
        
        self.tp_levels: List[CascadeTPLevel] = []
        self.closed_percent = 0.0
        self.remaining_percent = 100.0
        self.close_history = []
        self.status = "ACTIVE"
    
    def calculate_scalp_tps(self, market_volatility: str = "NORMAL") -> 'TPCascadeManager':
        """Calcula TPs scalping conforme volatilidade"""
        # Obter % de lucro
        config = self.SCALP_TARGETS.get(market_volatility, self.SCALP_TARGETS["NORMAL"])
        tps = self._calc_tp_prices(config)
        self._add_levels(tps, config)
        
        log.info(
            f"📊 [{self.symbol}] Scalping {market_volatility}| Lev:{self.leverage}x\n"
            f"  TP1:{tps['tp1']:.8f}(+{config['tp1']*100:.2f}%|50%) "
            f"TP2:{tps['tp2']:.8f}(+{config['tp2']*100:.2f}%|30%) "
            f"TP3:{tps['tp3']:.8f}(+{config['tp3']*100:.2f}%|20%)"
        )
        return self
    
    def _calc_tp_prices(self, config: Dict) -> Dict[str, float]:
        """Calcula preços: multiplica por (1+gain) para LONG, (1-gain) para SHORT"""
        mult = 1 if self.side == "LONG" else -1
        return {
            "tp1": self.entry * (1 + mult * config["tp1"]),
            "tp2": self.entry * (1 + mult * config["tp2"]),
            "tp3": self.entry * (1 + mult * config["tp3"]),
        }
    
    def _add_levels(self, tps: Dict, config: Dict) -> None:
        """Adiciona 3 níveis: 50%, 30%, 20%"""
        # TP1: fecha 50%, SL vai para entry (zero risk)
        self._add_tp(1, tps["tp1"], 50.0, self.entry)
        # TP2: fecha 30%, SL vai para TP1 (ganho garantido)
        self._add_tp(2, tps["tp2"], 30.0, tps["tp1"])
        # TP3: fecha 20%, SL vai para TP2 (proteção)
        self._add_tp(3, tps["tp3"], 20.0, tps["tp2"])
    
    def _add_tp(self, num: int, price: float, pct: float, new_sl: float) -> None:
        """Adiciona um TP individual"""
        self.tp_levels.append(CascadeTPLevel(tp_num=num, tp_price=price, 
                                             close_percent=pct, sl_move_to=new_sl))
    
    def check_cascade_hit(self, current_price: float) -> Dict:
        """Verifica TPs neste tick - retorna {} se nada, ou dict com TP atingido"""
        for tp in self.tp_levels:
            if tp.status != TPStatus.PENDING:
                continue
            
            # Verificar se atingido (conforme lado)
            hit = (self.side == "LONG" and current_price >= tp.tp_price) or \
                  (self.side == "SHORT" and current_price <= tp.tp_price)
            
            if not hit:
                continue
            
            # 🎯 TP ATINGIDO
            return self._process_hit(tp, current_price)
        
        return {}  # Nada atingido
    
    def _process_hit(self, tp: CascadeTPLevel, price: float) -> Dict:
        """Processa TP atingido: marca, atualiza SL, registra"""
        tp.status = TPStatus.HIT
        tp.closed_at_time = datetime.now(timezone(timedelta(hours=-3))).isoformat()
        tp.closed_at_price = price
        
        # Atualizar estado
        self.closed_percent += tp.close_percent
        self.remaining_percent -= tp.close_percent
        self.current_sl = tp.sl_move_to or self.current_sl
        
        # Registrar
        self.close_history.append({"tp": tp.tp_num, "price": price, "pct": tp.close_percent})
        
        # Cascata completa?
        if self.remaining_percent <= 0:
            self.status = "COMPLETE"
            log.info(f"🏁 [{self.symbol}] 100% fechado!")
        
        log.info(f"✅ [{self.symbol}] TP{tp.tp_num}@{price:.8f} Fechar {tp.close_percent}%|"
                f"SL→{self.current_sl:.8f}|Restante:{self.remaining_percent:.0f}%")
        
        return {"tp_hit": tp.tp_num, "close_pct": tp.close_percent, 
                "new_sl": self.current_sl, "action": "CLOSE_PARTIAL"}
    
    def cancel(self) -> None:
        """Cancela cascata (SL acionado)"""
        for tp in self.tp_levels:
            if tp.status == TPStatus.PENDING:
                tp.status = TPStatus.CANCELLED
        self.status = "CANCELLED"
        log.info(f"🛑 [{self.symbol}] Cascata cancelada")
