# src/notifier.py
import requests
import os
import datetime

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
            
    def send_heartbeat(risk_mgr, cache_balance, message_queue):
        """
        Agora a função recebe as dependências de fora para dentro.
        """
        total_trades, win_rate, pnl_net = risk_mgr.get_performance_stats()

        # Validação simples para evitar erro se o saldo ainda não carregou
        balance_total = cache_balance.get('total', 0.0)

        status_cor = "🟢" if pnl_net >= 0 else "🔴"
        queue_size = message_queue.qsize()
        status_fila = "⚠️ ATRASADO" if queue_size > 50 else "Normal"

        msg = (
            f"📊 *DASHBOARD DE PERFORMANCE*\n"
            f"📅 Período: Desde 18/03\n"
            f"---\n"
            f"💰 *PnL Líquido:* `${pnl_net:.2f}` {status_cor}\n"
            f"📈 *Win Rate:* `{win_rate:.1f}%` ({total_trades} trades)\n"
            f"💸 *Taxas Est.:* `-${risk_mgr.total_fees:.2f}`\n"
            f"---\n"
            f"🏦 *Saldo USDT:* `${balance_total:.2f}`\n"
            f"📡 *Fila:* `{queue_size}` ({status_fila})\n"
            f"🕒 *Atualiz.:* `{datetime.datetime.now().strftime('%H:%M:%S')}`"
        )

        notifier.send_message(msg)