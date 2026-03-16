import os
import pandas as pd
from src.strategy import TradingStrategy
from src.connection import get_http_session
from dotenv import load_dotenv
import psutil

load_dotenv()
SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT").split(",")
session = get_http_session(os.getenv("BYBIT_API_KEY"), os.getenv("BYBIT_API_SECRET"))

def get_bot_status():
    print("\n" + "="*40)
    print("🤖 BOT STATUS REPORT")
    print("="*40)
    
    # Memória RAM
    import psutil
    process = psutil.Process()
    mem = process.memory_info().rss / (1024 * 1024)
    print(f"📊 Consumo de RAM: {mem:.2f} MB")

    # Mostrar as últimas linhas do log de forma universal
    log_path = os.path.expanduser("~/.pm2/logs/bot-bybit-out.log")
    
    print("\n📝 ÚLTIMAS LINHAS DO LOG:")
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Pega as últimas 5 linhas
            for line in lines[-5:]:
                print(f"  > {line.strip()}")
    else:
        print("  ⚠️ Arquivo de log não encontrado (comum se estiver rodando local).")
    print("="*40 + "\n")

if __name__ == "__main__":
    get_bot_status()

print(f"\n{'SYMBOL':<10} | {'PRICE':<10} | {'ATR':<8} | {'RSI':<6} | {'EMA200_15m':<10}")
print("-" * 60)

for symbol in SYMBOLS:
    strat = TradingStrategy(symbol=symbol)
    # Puxa dados atuais para o Dashboard
    h1 = session.get_kline(category="linear", symbol=symbol, interval=1, limit=50)
    h15 = session.get_kline(category="linear", symbol=symbol, interval=15, limit=200)
    
    if h1['retCode'] == 0 and h15['retCode'] == 0:
        strat.load_historical_data("1m", reversed(h1['result']['list']))
        strat.load_historical_data("15m", reversed(h15['result']['list']))
        
        price = strat.data_1m['close'].iloc[-1]
        atr = strat.calculate_atr(strat.data_1m, 14).iloc[-1]
        rsi = strat.calculate_rsi(strat.data_1m, 14).iloc[-1]
        ema200 = strat.calculate_ema(strat.data_15m, 200).iloc[-1]
        
        print(f"{symbol:<10} | {price:<10.2f} | {atr:<8.4f} | {rsi:<6.1f} | {ema200:<10.2f}")