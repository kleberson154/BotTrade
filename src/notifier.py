# src/notifier.py
import requests
import os
import datetime
import logging

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from src.signal_formatter import SignalFormatter, TradeSignalBuilder, SignalProfile

log = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = all([self.token, self.chat_id])
        self.formatter = SignalFormatter()

    def send_message(self, text):
        if not self.enabled:
            log.warning("Telegram notifier desabilitado: token ou chat_id ausente")
            return
        
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "Markdown"}
        
        try:
            requests.post(url, json=payload)
        except Exception as e:
            log.error(f"⚠️ Erro ao enviar Telegram: {e}")
            
    def send_heartbeat(self, risk_mgr, cache_balance, message_queue):
        total, wins, prot, wr, sr, pnl_net = risk_mgr.get_performance_stats()
    
        balance_total = cache_balance.get('total', 0.0)
    
        status_cor = "🟢" if pnl_net >= 0 else "🔴"
        queue_size = message_queue.qsize()
        status_fila = "⚠️ ATRASADO" if queue_size > 50 else "Normal"

        if ZoneInfo is not None:
            horario_brasil = datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).strftime('%H:%M')
        else:
            horario_brasil = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-3))).strftime('%H:%M')
    
        msg = (
            f"📊 *DASHBOARD DE PERFORMANCE*\n"
            f"📅 Período: {risk_mgr.reset_date_str}\n"
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
    
    def notify_trade_opened(self, symbol, side, entry, sl, tp, leverage, profile, strength, rationale):
        """
        Envia sinal profissional no formato Mack
        """
        try:
            profile_enum = SignalProfile[profile.upper()]
        except KeyError:
            profile_enum = SignalProfile.BALANCED
        
        msg = (
                f"*TRADE ABERTA*\n"
                f"---\n"
                f"*{symbol}* {side}\n"
                f"📊 Entrada: `${entry:.2f}`\n"
                f"🛡️ SL: `${sl:.2f}`\n"
                f"🎯 TP: `${tp:.2f}`\n"
                f"⚡ Lev: `{leverage}x`\n"
                f"📈 Perfil: `{profile_enum.value}`\n"
                f"💪 Força: `{strength}`\n"
                f"🧠 Racional: {rationale}\n"
            )
        
        return self.send_message(msg)
    
    def notify_trade_closed(self, trade_data):
        """
        Notifica quando uma trade é fechada (SL ou TP)
        
        Args:
            trade_data: dict com dados da trade fechada
                - symbol: str (ex: BTCUSDT)
                - side: str (BUY ou SELL)
                - qty: str ou float (quantidade)
                - avgEntryPrice: str ou float (preço de entrada)
                - avgExitPrice: str ou float (preço de saída)
                - closedPnl: str ou float (PnL em USDT)
                - cumEntryValue: str ou float (valor acumulado entrada)
                - cumExitValue: str ou float (valor acumulado saída)
        """
        try:
            symbol = trade_data.get('symbol', 'UNKNOWN')
            side = trade_data.get('side', 'BUY')
            qty = float(trade_data.get('qty', 0))
            entry_price = float(trade_data.get('avgEntryPrice', 0))
            exit_price = float(trade_data.get('avgExitPrice', 0))
            pnl = float(trade_data.get('closedPnl', 0))
            
            # Calcular taxa (estimativa: 0.06% por lado = 0.12% total)
            cum_entry = float(trade_data.get('cumEntryValue', 0))
            cum_exit = float(trade_data.get('cumExitValue', 0))
            fees = (cum_entry + cum_exit) * 0.0006
            pnl_net = pnl - fees
            
            # Determinar emoji e tipo de fechamento
            win_emoji = "✅" if pnl_net > 0 else "❌"
            side_emoji = "📈" if side == "BUY" else "📉"
            
            # Calcular movimento
            if side == "BUY":
                movimento = ((exit_price - entry_price) / entry_price) * 100
            else:
                movimento = ((entry_price - exit_price) / entry_price) * 100
            
            movimento_str = f"{movimento:+.2f}%" if movimento != 0 else "0%"
            
            msg = (
                f"{win_emoji} *TRADE FECHADO*\n"
                f"---\n"
                f"{side_emoji} *{symbol}* {side}\n"
                f"📊 Qty: `{qty}`\n"
                f"💵 Entrada: `${entry_price:.2f}`\n"
                f"🎯 Saída: `${exit_price:.2f}` ({movimento_str})\n"
                f"---\n"
                f"💰 *PnL Bruto:* `${pnl:+.2f}`\n"
                f"💸 *Taxas:* `-${fees:.2f}`\n"
                f"📈 *PnL Líquido:* `${pnl_net:+.2f}` {win_emoji}\n"
            )
            
            self.send_message(msg)
        except Exception as e:
            log.error(f"Erro ao notificar trade fechado: {e}")