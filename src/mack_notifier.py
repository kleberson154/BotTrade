# src/mack_notifier.py
"""
Notificador avançado que envia sinais no formato Mack + compliance
Integra: Telegram, logging, auditoria de regras
"""

import requests
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from src.signal_formatter import TradeSignal, SignalFormatter
from src.mack_compliance import MackCompliance

log = logging.getLogger(__name__)

class MackNotifier:
    """
    Notificador profissional com formatação Mack + compliance
    """
    
    def __init__(self, compliance: MackCompliance = None):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = all([self.token, self.chat_id])
        
        self.compliance = compliance or MackCompliance()
        self.formatter = SignalFormatter()
        
        self.sent_signals = []
        self.sent_trades = []
    
    def get_brasil_time(self) -> str:
        """Retorna hora de Brasília formatada"""
        if ZoneInfo is not None:
            return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%H:%M:%S')
        else:
            return datetime.now(timezone(timedelta(hours=-3))).strftime('%H:%M:%S')
    
    def send_telegram(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Envia mensagem para Telegram"""
        if not self.enabled:
            log.warning("⚠️ Telegram desabilitado - mensagens não serão enviadas")
            return False
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            log.error(f"❌ Erro ao enviar Telegram: {e}")
            return False
    
    # ========================================================
    # NOTIFICAÇÕES DE SINAIS
    # ========================================================
    
    def notify_signal(self, signal: TradeSignal) -> bool:
        """
        Notifica novo sinal no formato Mack
        
        Exemplo:
        SINAL AGRESSIVO — ZEC/USDT:USDT
        ─────────────────────────
        🔥 Perfil: AGGRESSIVE
        🏁 Ranking do dia: #41
        📍 Entry: 363.27
        🛑 SL: 365.5404375
        🎯 TP: 358.729125
        ...
        """
        
        msg = self.formatter.format_signal_for_notification(signal)
        
        success = self.send_telegram(msg)
        
        if success:
            self.sent_signals.append({
                "symbol": signal.symbol,
                "signal_hash": signal.signal_hash,
                "timestamp": self.get_brasil_time(),
                "side": signal.side,
                "entry": signal.entry
            })
            log.info(f"📤 Sinal {signal.symbol} enviado com sucesso")
        
        return success
    
    def notify_trade_entry(
        self,
        symbol: str,
        side: str,
        entry: float,
        sl: float,
        tp: float,
        qty: float,
        leverage: int,
        profile: str,
        strength: float
    ) -> bool:
        """
        Notifica entrada efetiva de trade
        """
        
        # Calcular dados
        if side == "LONG":
            risk = entry - sl
            reward = tp - entry
        else:
            risk = sl - entry
            reward = entry - tp
        
        ratio = reward / risk if risk > 0 else 0
        
        msg = f"""
✅ *TRADE ABERTO* — {symbol}
{'━' * 40}

📊 Perfil: {profile} | Força: ⭐ {strength:.2f}
↕️ Direção: {side} | Alavancagem: {leverage}x
📍 Entry: `{entry}`
🛑 SL: `{sl}` (Risk: `${risk*qty:.2f}`)
🎯 TP: `{tp}` (Reward: `${reward*qty:.2f}`)
⚖️ Risk:Reward: `{ratio:.2f}:1`
📦 Quantidade: `{qty:.4f}`

🕒 Hora: {self.get_brasil_time()}
"""
        
        success = self.send_telegram(msg)
        
        if success:
            self.sent_trades.append({
                "symbol": symbol,
                "side": side,
                "entry": entry,
                "timestamp": self.get_brasil_time(),
                "rr_ratio": round(ratio, 2)
            })
            log.info(f"🚀 Trade {symbol} ({side}) notificado")
        
        return success
    
    def notify_trade_exit(
        self,
        symbol: str,
        side: str,
        entry: float,
        exit_price: float,
        exit_method: str,
        pnl_usd: float,
        pnl_percent: float
    ) -> bool:
        """
        Notifica saída de trade
        
        Métodos: TP_HIT, SL_HIT, MANUAL, TIMEOUT, etc
        """
        
        status_emoji = "✅" if pnl_usd > 0 else "❌" if pnl_usd < 0 else "⚪"
        
        msg = f"""
{status_emoji} *TRADE FECHADO* — {symbol}
{'━' * 40}

↕️ Tipo: {side}
📍 Entry: `{entry}`
🚪 Exit: `{exit_price}`
🔔 Motivo: `{exit_method}`

💰 *PnL:* `${pnl_usd:.2f}` ({pnl_percent:.2f}%)

🕒 Hora: {self.get_brasil_time()}
"""
        
        success = self.send_telegram(msg)
        
        if success:
            log.info(f"📤 Saída {symbol} notificada ({exit_method})")
        
        return success
    
    # ========================================================
    # NOTIFICAÇÕES DE COMPLIANCE
    # ========================================================
    
    def notify_compliance_violation(
        self,
        rule_number: int,
        symbol: str,
        message: str,
        severity: str = "WARNING"  # WARNING, CRITICAL
    ) -> bool:
        """
        Notifica violação de regra Mack
        """
        
        emoji = "⚠️" if severity == "WARNING" else "🚨"
        
        msg = f"""
{emoji} *REGRA {rule_number} DO MACK VIOLADA*
{'━' * 40}

💔 Moeda: `{symbol}`
⚠️ Violação: {message}
🔴 Severidade: {severity}

📝 Corrir IMEDIATAMENTE e revisar entrada!

🕒 Hora: {self.get_brasil_time()}
"""
        
        success = self.send_telegram(msg)
        
        if success:
            log.error(f"🚨 Violação Regra {rule_number} notificada: {symbol}")
        
        return success
    
    def notify_compliance_report(self) -> bool:
        """
        Envia relatório de compliance do período
        """
        
        report = self.compliance.get_compliance_report()
        total_violations = report['total_violations']
        status = report['status']
        
        violations_text = ""
        for v in report['violations'][-5:]:  # Últimas 5
            violations_text += f"• {v}\n"
        
        # Construir mensagem fora do f-string para evitar problemas com backslash
        violations_section = ""
        if total_violations > 0:
            violations_section = f"⚠️ Últimas Violações:\n{violations_text}"
        else:
            violations_section = "✅ Sem violações!"
        
        msg = f"""
{status}
{'━' * 40}

📊 Total de Violações: `{total_violations}`

{violations_section}

🕒 Relatório: {report['timestamp']}
"""
        
        success = self.send_telegram(msg)
        
        if success:
            log.info("📊 Relatório de compliance enviado")
        
        return success
    
    # ========================================================
    # DASHBOARD E ESTATÍSTICAS
    # ========================================================
    
    def notify_dashboard(
        self,
        total_trades: int,
        wins: int,
        losses: int,
        pnl_usd: float,
        pnl_percent: float,
        win_rate: float,
        balance: float
    ) -> bool:
        """
        Envia dashboard de performance
        """
        
        status_icon = "🟢" if pnl_usd >= 0 else "🔴"
        
        msg = f"""
📊 *DASHBOARD MACK COMPLIANCE*
{'━' * 40}

💰 *PnL:* `${pnl_usd:.2f}` ({pnl_percent:.2f}%) {status_icon}
📈 *Win Rate:* `{win_rate:.1f}%`
🏦 *Saldo USDT:* `${balance:.2f}`

📋 *Estatísticas:*
• Total Trades: `{total_trades}`
• ✅ Wins: `{wins}`
• ❌ Losses: `{losses}`
• Taxa: `{(wins/total_trades*100):.1f}%` se total_trades > 0 else 0

🇧🇷 Hora: {self.get_brasil_time()}
"""
        
        success = self.send_telegram(msg)
        
        if success:
            log.info("📊 Dashboard enviado")
        
        return success
    
    # ========================================================
    # ALERTAS ESPECIAIS
    # ========================================================
    
    def notify_alert(self, title: str, message: str, emoji: str = "🔔") -> bool:
        """Envia alerta genérico"""
        
        msg = f"""
{emoji} *{title}*
{'━' * 40}

{message}

🕒 {self.get_brasil_time()}
"""
        
        return self.send_telegram(msg)
    
    def notify_ruin_risk(self, current_balance: float, daily_loss: float) -> bool:
        """Alerta de risco de ruína (regra 4 do Mack)"""
        
        loss_percent = (daily_loss / current_balance * 100) if current_balance > 0 else 0
        
        msg = f"""
🚨 *ALERTA: RISCO DE RUÍNA*
{'━' * 40}

⚠️ Perda do dia: `${daily_loss:.2f}` ({loss_percent:.2f}%)
💰 Saldo Atual: `${current_balance:.2f}`

🔒 *BOT PAUSADO TEMPORARIAMENTE*

Revisar estratégia e esperar reset (00:00 BRT)

🕒 {self.get_brasil_time()}
"""
        
        return self.send_telegram(msg)
    
    def notify_bot_status(self, status: str, message: str = "") -> bool:
        """
        Notifica status do bot
        
        status: STARTED, STOPPED, ERROR, RECONNECTING, etc
        """
        
        emoji_map = {
            "STARTED": "🟢",
            "STOPPED": "🔴",
            "ERROR": "⚠️",
            "RECONNECTING": "🔄",
            "PAUSED": "⏸️"
        }
        
        emoji = emoji_map.get(status, "ℹ️")
        
        msg = f"""
{emoji} *STATUS: {status}*
{'━' * 40}

{message}

🕒 {self.get_brasil_time()}
"""
        
        return self.send_telegram(msg)


# Extensão da classe TelegramNotifier original
class EnhancedTelegramNotifier:
    """
    Mantém compatibilidade com código antigo + novos recursos
    """
    
    def __init__(self):
        self._mack = MackNotifier()
    
    def send_message(self, text: str):
        """Compatibilidade com interface antiga"""
        self._mack.send_telegram(text)
    
    def send_heartbeat(self, risk_mgr, cache_balance, message_queue):
        """Compatibilidade com dashboard antigo"""
        pass  # Implementar se necessário
    
    # Novos métodos
    def notify_signal(self, signal: TradeSignal) -> bool:
        return self._mack.notify_signal(signal)
    
    def notify_trade_entry(self, **kwargs) -> bool:
        return self._mack.notify_trade_entry(**kwargs)
    
    def notify_trade_exit(self, **kwargs) -> bool:
        return self._mack.notify_trade_exit(**kwargs)
    
    def notify_compliance_violation(self, **kwargs) -> bool:
        return self._mack.notify_compliance_violation(**kwargs)
