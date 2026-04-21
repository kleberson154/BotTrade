# src/multi_tp_manager.py
"""
Gestor de múltiplos Take Profits com closes parciais (estilo Mack)

Exemplo:
TP1 (50% da posição): 0.541235 → Close 50%, mova SL para Entry (0.481800)
TP2 (30% da posição): 0.600670 → Close 30%, mova SL para TP1 (0.541235)  
TP3 (20% da posição): 0.660105 → Runner final, saída total
"""

import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

log = logging.getLogger(__name__)


class TPStatus(Enum):
    """Estados de um TP"""
    PENDING = "PENDING"
    HIT = "HIT"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


@dataclass
class TPLevel:
    """Nível de Take Profit"""
    tp_price: float
    close_percent: float      # % da posição a fechar
    sl_move_to: Optional[float] = None  # Para onde mover SL
    status: TPStatus = TPStatus.PENDING
    description: str = ""


class MultiTPManager:
    """
    Gerencia múltiplos TPs com closes parciais
    """
    
    def __init__(self, symbol: str, side: str, entry: float, initial_sl: float):
        self.symbol = symbol
        self.side = side
        self.entry = entry
        self.initial_sl = initial_sl
        self.current_sl = initial_sl
        
        self.tp_levels: List[TPLevel] = []
        self.closed_percent = 0.0
        self.remaining_percent = 100.0
        
        # Histórico
        self.close_history = []
    
    def add_tp(
        self,
        tp_price: float,
        close_percent: float,
        sl_move_to: Optional[float] = None,
        description: str = ""
    ) -> 'MultiTPManager':
        """
        Adiciona um nível de TP
        
        close_percent: Quanto fechar dessa posição (em % da original)
        sl_move_to: Onde mover o SL após fechar
        """
        
        level = TPLevel(
            tp_price=tp_price,
            close_percent=close_percent,
            sl_move_to=sl_move_to,
            description=description
        )
        
        self.tp_levels.append(level)
        
        log.info(f"➕ TP adicionado: {tp_price} ({close_percent}%) - {description}")
        
        return self
    
    def check_tp_hit(self, current_price: float) -> List[Dict]:
        """
        Verifica se algum TP foi atingido
        
        Retorna lista de TPs atingidos
        """
        
        hits = []
        
        for i, tp in enumerate(self.tp_levels):
            if tp.status == TPStatus.PENDING:
                # Verificar se foi atingido
                is_hit = False
                
                if self.side == "LONG":
                    is_hit = current_price >= tp.tp_price
                else:  # SHORT
                    is_hit = current_price <= tp.tp_price
                
                if is_hit:
                    tp.status = TPStatus.HIT
                    
                    close_info = {
                        "tp_level": i + 1,
                        "tp_price": tp.tp_price,
                        "close_percent": tp.close_percent,
                        "action": self._get_action_after_tp(tp, i),
                        "new_sl": tp.sl_move_to,
                        "description": tp.description
                    }
                    
                    hits.append(close_info)
                    
                    log.info(f"🎯 TP{i+1} atingido em {self.symbol}: {current_price}")
        
        return hits
    
    def _get_action_after_tp(self, tp: TPLevel, index: int) -> str:
        """Define ação após TP ser atingido"""
        
        if index == len(self.tp_levels) - 1:
            return "CLOSE_ALL"  # Último TP = fechar tudo
        else:
            if tp.sl_move_to is not None:
                return "CLOSE_PARTIAL_MOVE_SL"
            else:
                return "CLOSE_PARTIAL_TRAIL"
    
    def register_close(self, tp_level: int, closed_quantity: float, close_price: float) -> Dict:
        """
        Registra fechamento de posição em um TP
        """
        
        self.closed_percent += self.tp_levels[tp_level - 1].close_percent
        self.remaining_percent = 100.0 - self.closed_percent
        
        # Atualizar SL se necessário
        if self.tp_levels[tp_level - 1].sl_move_to is not None:
            old_sl = self.current_sl
            self.current_sl = self.tp_levels[tp_level - 1].sl_move_to
            log.info(f"🔄 SL atualizado: {old_sl} → {self.current_sl}")
        
        close_record = {
            "tp_level": tp_level,
            "close_price": close_price,
            "close_percent": self.tp_levels[tp_level - 1].close_percent,
            "timestamp": datetime.now(timezone(timedelta(hours=-3))).isoformat(),
            "total_closed": self.closed_percent,
            "remaining": self.remaining_percent
        }
        
        self.close_history.append(close_record)
        
        log.info(f"✅ TP{tp_level} fechado: {self.closed_percent}% da posição")
        
        return close_record
    
    def get_tp_config_string(self) -> str:
        """Retorna configuração de TPs formatada para sinal"""
        
        config_str = "🪜 Gestão(Mack's Way)\n"
        
        for i, tp in enumerate(self.tp_levels, 1):
            action = "📍 CLOSE" if i == len(self.tp_levels) else "📊 CLOSE PARCIAL"
            config_str += f"• TP{i} {tp.tp_price}: {action} {tp.close_percent}% - {tp.description}\n"
        
        return config_str
    
    def get_remaining_tp_for_exit(self) -> Optional[float]:
        """Retorna o próximo TP a ser atingido"""
        
        for tp in self.tp_levels:
            if tp.status == TPStatus.PENDING:
                return tp.tp_price
        
        return None
    
    def get_status(self) -> Dict:
        """Retorna status atual da gestão"""
        
        pending_tps = sum(1 for tp in self.tp_levels if tp.status == TPStatus.PENDING)
        hit_tps = sum(1 for tp in self.tp_levels if tp.status == TPStatus.HIT)
        
        return {
            "total_tps": len(self.tp_levels),
            "pending": pending_tps,
            "hit": hit_tps,
            "closed_percent": self.closed_percent,
            "remaining_percent": self.remaining_percent,
            "current_sl": self.current_sl,
            "close_history": self.close_history
        }


class SMCTPManager(MultiTPManager):
    """
    Gestor especializado para estratégia SMC (Smart Money Concepts)
    
    Tipicamente: 3 TPs com closes em cascata
    TP1: 30-40% de lucro imediato (estrutura menor)
    TP2: 60-70% de lucro (estrutura média)
    TP3: Runner (mercado livre, sem SL)
    """
    
    @staticmethod
    def create_smc_config(
        symbol: str,
        side: str,
        entry: float,
        sl: float,
        tp1: float,
        tp2: float,
        tp3: float
    ) -> 'SMCTPManager':
        """
        Factory para criar config padrão SMC
        
        TP1: Close 40%, mover SL para Entry
        TP2: Close 40%, mover SL para TP1
        TP3: Close 20%, Runner final
        """
        
        manager = SMCTPManager(symbol, side, entry, sl)
        
        # TP1
        manager.add_tp(
            tp_price=tp1,
            close_percent=40.0,
            sl_move_to=entry,
            description="Close parcial + SL para Entry"
        )
        
        # TP2
        manager.add_tp(
            tp_price=tp2,
            close_percent=40.0,
            sl_move_to=tp1,
            description="Close parcial + SL para TP1"
        )
        
        # TP3
        manager.add_tp(
            tp_price=tp3,
            close_percent=20.0,
            sl_move_to=None,
            description="Runner final / Saída total"
        )
        
        return manager
    
    def get_smc_summary(self) -> str:
        """Retorna resumo da gestão SMC formatado"""
        
        summary = "🪜 Gestão SMC\n"
        
        for i, tp in enumerate(self.tp_levels, 1):
            action = "realizar parcial e mover stop" if i < 3 else "runner final / saída total"
            summary += f"• TP{i} {tp.tp_price}: {action} ({tp.close_percent}%)\n"
        
        return summary
