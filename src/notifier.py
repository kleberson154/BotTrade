# src/notifier.py
import requests
import os
import datetime
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from src.mack_notifier import MackNotifier
from src.signal_formatter import TradeSignalBuilder, SignalProfile

log = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = all([self.token, self.chat_id])
        
        # 🆕 Integração Mack
        self.mack = MackNotifier()

    def send_message(self, text):
        if not self.enabled:
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"⚠️ Erro ao enviar Telegram: {e}")
            
    def send_heartbeat(self, risk_mgr, cache_balance, message_queue):
        total, wins, wr, pnl_net = risk_mgr.get_performance_stats()
    
        balance_total = cache_balance.get('total', 0.0)
    
        status_cor = "🟢" if pnl_net >= 0 else "🔴"
        queue_size = message_queue.qsize()
        status_fila = "⚠️ ATRASADO" if queue_size > 50 else "Normal"

        if ZoneInfo is not None:
            horario_brasil = datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%H:%M:%S')
        else:
            horario_brasil = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime('%H:%M:%S')
    
        msg = (
            f"📊 *DASHBOARD DE PERFORMANCE*\n"
            f"📅 Período: Desde {risk_mgr.reset_date_str}\n"
            f"---\n"
            f"🏦 *Saldo USDT:* `${balance_total:.2f}`\n"
            f"💰 *PnL Líquido:* `${pnl_net:.2f}` {status_cor}\n"
            f"✅ Wins: `{wins}` | ❌ Losses: `{total - wins}`\n"
            f"📈 *Win Rate:* `{wr:.1f}%` 🎯\n"
            f"---\n"
            f"💸 *Taxas Est.:* `-${risk_mgr.total_fees:.2f}`\n"
            f"📡 *Fila:* `{queue_size}` ({status_fila})\n"
            f"🕒 *Atualiz.:* `{horario_brasil}`"
        )
    
        self.send_message(msg)
    
    # =========================================================
    # 🆕 MACK NOTIFIER - Notificações Profissionais
    # =========================================================
    # (Integração Mack será inicializada no __init__ acima)
    
    def notify_signal_mack(self, symbol, side, entry, sl, tp, leverage, profile, strength, rationale, partials):
        """
        Envia sinal profissional no formato Mack
        
        Exemplo de entrada:
        notify_signal_mack(
            symbol="LABUSDT",
            side="LONG",
            entry=0.4818,
            sl=0.437224,
            tp=0.660105,
            leverage=75,
            profile="AGGRESSIVE",
            strength=0.725,
            rationale=["[TREND] ADX 31", "Vol 6.0x"],
            partials=[
                {"tp": 0.541235, "percent": 40, "action": "CLOSE_PARTIAL", "desc": "TP1"},
                ...
            ]
        )
        """
        try:
            profile_enum = SignalProfile[profile.upper()]
        except KeyError:
            profile_enum = SignalProfile.BALANCED
        
        signal = (TradeSignalBuilder(symbol, side, entry)
            .with_stops(sl, tp)
            .with_leverage(int(leverage))
            .with_profile(profile_enum)
            .with_strength(strength)
            .with_origin("Strategy")
        )
        
        for reason in rationale:
            signal.add_rationale(reason)
        
        for partial in partials:
            signal.add_partial_tp(
                tp_price=partial['tp'],
                tp_percent=partial['percent'],
                action=partial.get('action', 'CLOSE_PARTIAL'),
                desc=partial.get('desc', '')
            )
        
        signal_obj = signal.build()
        return self.mack.notify_signal(signal_obj)
    
    def notify_entry_mack(self, symbol, side, entry, sl, tp, qty, leverage):
        """Notifica entrada de trade"""
        return self.mack.notify_trade_entry(
            symbol=symbol,
            side=side,
            entry=entry,
            sl=sl,
            tp=tp,
            qty=qty,
            leverage=int(leverage),
            profile="AGGRESSIVE",
            strength=0.7
        )
    
    def notify_exit_mack(self, symbol, side, entry, exit_price, method, pnl_usd, pnl_percent):
        """Notifica saída de trade"""
        return self.mack.notify_trade_exit(
            symbol=symbol,
            side=side,
            entry=entry,
            exit_price=exit_price,
            exit_method=method,
            pnl_usd=pnl_usd,
            pnl_percent=pnl_percent
        )
    
    def notify_violation_mack(self, rule_number, symbol, message, severity="WARNING"):
        """Notifica violação de regra Mack"""
        return self.mack.notify_compliance_violation(
            rule_number=rule_number,
            symbol=symbol,
            message=message,
            severity=severity
        )
    
    def notify_compliance_report_mack(self):
        """Envia relatório de compliance"""
        return self.mack.notify_compliance_report()