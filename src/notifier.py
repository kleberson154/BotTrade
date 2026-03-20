# src/notifier.py
import requests
import os
import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = all([self.token, self.chat_id])

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
        # RECEBENDO AS 6 VARIÁVEIS (Ordem: total, wins, prot, wr, sr, pnl_net)
        total, wins, prot, wr, sr, pnl_net = risk_mgr.get_performance_stats()
    
        # Validação para o saldo
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
            f"📅 Período: Desde 18/03\n"
            f"---\n"
            f"💰 *PnL Líquido:* `${pnl_net:.2f}` {status_cor}\n"
            f"📈 *Win Rate:* `{wr:.1f}%` 🎯\n"
            f"🛡️ *Sobrevivência:* `{sr:.1f}%` (Proteção)\n"
            f"---\n"
            f"✅ Wins: `{wins}` | 🛡️ BE: `{prot}` | ❌ Losses: `{total - wins - prot}`\n"
            f"💸 *Taxas Est.:* `-${risk_mgr.total_fees:.2f}`\n"
            f"---\n"
            f"🏦 *Saldo USDT:* `${balance_total:.2f}`\n"
            f"📡 *Fila:* `{queue_size}` ({status_fila})\n"
            f"🕒 *Atualiz.:* `{horario_brasil}`"
        )
    
        self.send_message(msg)