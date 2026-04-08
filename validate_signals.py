#!/usr/bin/env python
"""
DRY-RUN VALIDATION: Simula 2h de trading sem colocar ordens reais
Valida que signals aparecem como esperado
"""
import sys, os, json, time, datetime
from collections import defaultdict

sys.path.insert(0, 'src')
sys.path.insert(0, 'data')

from dotenv import load_dotenv
from src.strategy import TradingStrategy
from src.connection import get_http_session, get_websocket_session
from src.logger import setup_logger
from src.notifier import TelegramNotifier

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_DEMO = os.getenv("BYBIT_MODE", "demo").lower() == "demo"

# Only test with 1 coin for quick validation
TEST_SYMBOL = "BTCUSDT"
TEST_DURATION_SECONDS = 3600  # 1 hour
CANDLE_INTERVAL_SECONDS = 60  # Check every minute

log = setup_logger()
session = get_http_session(API_KEY, API_SECRET, testnet=False, demo=IS_DEMO)
notifier = TelegramNotifier()

class SignalCapture:
    def __init__(self):
        self.signals = defaultdict(list)
        self.trade_count = 0
        self.start_time = time.time()
        self.last_price = {}
        
    def log_signal(self, symbol, signal, confidence):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.signals[symbol].append({
            "time": timestamp,
            "signal": signal,
            "confidence": confidence
        })
        if signal != "HOLD":
            self.trade_count += 1
            log.info(f"[SIGNAL] {symbol} {signal} @ {confidence:.2f}")
    
    def report(self):
        elapsed = time.time() - self.start_time
        print("\n" + "="*60)
        print(f"DRY-RUN VALIDATION REPORT (Duration: {elapsed:.0f}s)")
        print("="*60)
        for symbol in sorted(self.signals.keys()):
            sigs = self.signals[symbol]
            trades = [s for s in sigs if s["signal"] != "HOLD"]
            print(f"\n{symbol}:")
            print(f"  Signals generated: {len(trades)}")
            print(f"  Avg per hour: {len(trades) * 3600 / elapsed:.1f}")
            if trades:
                print(f"  Breakdown:")
                buy_count = len([s for s in trades if s["signal"] == "BUY"])
                sell_count = len([s for s in trades if s["signal"] == "SELL"])
                print(f"    - BUY:  {buy_count}")
                print(f"    - SELL: {sell_count}")

capture = SignalCapture()

print(f"\n🔍 VALIDATION MODE (DRY-RUN)")
print(f"   Symbol: {TEST_SYMBOL}")
print(f"   Duration: {TEST_DURATION_SECONDS}s")
print(f"   Mode: DEMO (no real orders)")
print(f"   Check interval: {CANDLE_INTERVAL_SECONDS}s\n")

# Initialize strategy
strat = TradingStrategy(symbol=TEST_SYMBOL, notifier=notifier)
strat.invert_signal = True  # BTC config

# Fetch initial data
try:
    print("📥 Fetching initial candle data...")
    klines_1m = session.get_kline(category="linear", symbol=TEST_SYMBOL, interval="1", limit=200)
    klines_15m = session.get_kline(category="linear", symbol=TEST_SYMBOL, interval="15", limit=200)
    
    for kline in klines_1m["result"]["list"][::-1]:
        strat.add_new_candle("1m", {
            "open": float(kline[1]),
            "close": float(kline[4]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "volume": float(kline[7])
        })
    
    for kline in klines_15m["result"]["list"][::-1]:
        strat.add_new_candle("15m", {
            "open": float(kline[1]),
            "close": float(kline[4]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "volume": float(kline[7])
        })
    
    print(f"✅ Loaded {len(strat.data_1m)} 1m candles")
    print(f"✅ Loaded {len(strat.data_15m)} 15m candles\n")
    
except Exception as e:
    print(f"❌ Failed to fetch data: {e}")
    sys.exit(1)

# Run validation loop
start_time = time.time()
print("🚀 Starting validation loop...\n")

while time.time() - start_time < TEST_DURATION_SECONDS:
    try:
        # Get latest candle
        latest_1m = session.get_kline(category="linear", symbol=TEST_SYMBOL, interval="1", limit=5)
        new_candle = latest_1m["result"]["list"][0]
        
        strat.add_new_candle("1m", {
            "open": float(new_candle[1]),
            "close": float(new_candle[4]),
            "high": float(new_candle[2]),
            "low": float(new_candle[3]),
            "volume": float(new_candle[7])
        })
        
        # Check signal (without executing trade)
        signal, dist_sl = strat.check_signal()
        
        if signal != "HOLD":
            price = strat.data_1m['close'].iloc[-1]
            capture.log_signal(TEST_SYMBOL, signal, price)
        
        # Progress indicator
        elapsed = time.time() - start_time
        pct = (elapsed / TEST_DURATION_SECONDS) * 100
        print(f"⏳ {pct:3.0f}% | Signals: {capture.trade_count:3d} | Price: {strat.data_1m['close'].iloc[-1]:.2f}")
        
        time.sleep(CANDLE_INTERVAL_SECONDS)
        
    except KeyboardInterrupt:
        print("\n⚠️  Validation interrupted by user")
        break
    except Exception as e:
        log.error(f"Error in validation: {e}")
        time.sleep(5)

# Report
capture.report()

print("\n✅ VALIDATION COMPLETE")
print(f"   Ready for live trading? {capture.trade_count > 0}")
