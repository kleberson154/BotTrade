# src/notifier.py
import requests
import os

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
            
    def send_report(self, balance, pnl, pnl_pct, open_positions):
      status = "📈" if pnl >= 0 else "📉"
      text = (
          f"{status} *RELATÓRIO DIÁRIO DE PERFORMANCE*\n\n"
          f"💰 *Saldo Atual:* `${balance:.2f} USDT`\n"
          f"📊 *Lucro/Prejuízo:* `${pnl:.2f} USDT` ({pnl_pct:.2f}%)\n"
          f"📂 *Posições Abertas:* `{open_positions}`\n\n"
          f"🕒 _Próximo relatório em 24h_"
      )
      self.send_message(text)