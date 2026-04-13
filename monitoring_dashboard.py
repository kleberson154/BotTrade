#!/usr/bin/env python
"""
Real-time Monitoring Dashboard
Tracks actual WR vs expected (backtest) WR
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, asdict
from src.logger import setup_logger

log = setup_logger()

@dataclass
class TradeStats:
    symbol: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    wr: float = 0.0  # Win Rate %
    total_pnl: float = 0.0  # Total PnL %
    
    @property
    def wr_pct(self):
        if self.trades == 0:
            return 0.0
        return (self.wins / self.trades) * 100

class TradingDashboard:
    """
    Tracks live trading performance vs backtest baseline
    """
    
    BASELINE = {
        "BTCUSDT":  {"expected_wr": 28.2, "expected_pnl": -0.951},
        "XRPUSDT":  {"expected_wr": 28.9, "expected_pnl": 4.963},
        "NEARUSDT": {"expected_wr": 32.9, "expected_pnl": 2.333},
        "LINKUSDT": {"expected_wr": 38.1, "expected_pnl": 5.773},
        "SUIUSDT":  {"expected_wr": 30.5, "expected_pnl": 6.982},
        "OPUSDT":   {"expected_wr": 26.7, "expected_pnl": 1.175},
    }
    
    PORTFOLIO_BASELINE = {
        "total_trades": 287,
        "expected_wr": 30.87,
        "expected_pnl": 20.274,
    }
    
    def __init__(self, log_file="trading_log.json"):
        self.log_file = log_file
        self.stats = defaultdict(lambda: TradeStats(symbol=""))
        self.global_start = datetime.now()
        self.trade_history = []
        self.reset_marker_file = "RESET_TRADES_TODAY.txt"
        self.reset_timestamp = self._load_reset_marker()
        self._load_history()
    
    def reset_today(self):
        """Reset statistics to start fresh tracking from today (for Market Cycles deployment)"""
        log.info("🔄 Resetando histórico de trades para rastreamento apenas de hoje...")
        self.trade_history = []
        self.stats = defaultdict(lambda: TradeStats(symbol=""))
        self.global_start = datetime.now()
        self.reset_timestamp = datetime.now()
        
        # Save reset marker
        self._save_reset_marker()
        
        # Save empty history
        self._save_history()
        
        log.info("✅ Histórico resetado. Win Rate tracking começará do zero a partir de agora.")
    
    def _load_reset_marker(self):
        """Load timestamp of when trades were last reset"""
        if os.path.exists(self.reset_marker_file):
            try:
                with open(self.reset_marker_file) as f:
                    line = f.readline().strip()
                    if line.startswith("Reset timestamp: "):
                        ts_str = line.split("Reset timestamp: ")[1]
                        return datetime.fromisoformat(ts_str)
            except:
                pass
        # Default: load all trades (no reset)
        return datetime.min
    
    def _save_reset_marker(self):
        """Save timestamp of when trades were reset"""
        with open(self.reset_marker_file, "w") as f:
            f.write(f"Reset timestamp: {self.reset_timestamp.isoformat()}\n")
            f.write(f"Reason: Market Cycles Integration - Fresh tracking\n")


    
    def _load_history(self):
        """Load trade history from persistent log, filtering by reset marker"""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file) as f:
                    all_trades = json.load(f)
                    # Filter trades: only include those after reset timestamp
                    self.trade_history = [
                        t for t in all_trades 
                        if datetime.fromisoformat(t["timestamp"]) >= self.reset_timestamp
                    ]
                    self._recalculate_stats()
            except:
                pass
    
    def _recalculate_stats(self):
        """Recalculate statistics from trade history"""
        self.stats = defaultdict(lambda: TradeStats(symbol=""))
        for trade in self.trade_history:
            symbol = trade["symbol"]
            if symbol not in self.stats:
                self.stats[symbol] = TradeStats(symbol=symbol)
            
            stat = self.stats[symbol]
            stat.trades += 1
            if trade["result"] == "WIN":
                stat.wins += 1
            elif trade["result"] == "LOSS":
                stat.losses += 1
            stat.total_pnl += trade.get("pnl", 0.0)
    
    def log_trade(self, symbol, side, entry_price, exit_price, result, pnl):
        """Log a trade execution"""
        trade = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "result": result,  # WIN / LOSS
            "pnl": pnl,  # PnL %
        }
        self.trade_history.append(trade)
        self._recalculate_stats()
        self._save_history()
    
    def _save_history(self):
        """Persist trade history to file"""
        with open(self.log_file, "w") as f:
            json.dump(self.trade_history, f, indent=2)
    
    def get_portfolio_summary(self):
        """Get summary across all coins"""
        total_trades = sum(s.trades for s in self.stats.values())
        total_wins = sum(s.wins for s in self.stats.values())
        total_pnl = sum(s.total_pnl for s in self.stats.values())
        
        actual_wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "actual_wr": actual_wr,
            "expected_wr": self.PORTFOLIO_BASELINE["expected_wr"],
            "wr_diff": actual_wr - self.PORTFOLIO_BASELINE["expected_wr"],
            "total_pnl": total_pnl,
            "expected_pnl": self.PORTFOLIO_BASELINE["expected_pnl"],
            "pnl_diff": total_pnl - self.PORTFOLIO_BASELINE["expected_pnl"],
            "status": self._get_portfolio_status(actual_wr),
        }
    
    def _get_portfolio_status(self, actual_wr):
        """Determine portfolio health status"""
        if actual_wr < 20:
            return "🔴 CRITICAL - Below 20% WR"
        elif actual_wr < 25:
            return "🟠 WARNING - Below 25% WR"
        elif actual_wr >= 30:
            return "🟢 GOOD - At or above expectations"
        else:
            return "🟡 OK - Within tolerance"
    
    def print_dashboard(self):
        """Print formatted dashboard to console"""
        summary = self.get_portfolio_summary()
        
        print("\n" + "="*80)
        print(" "*20 + "📊 TRADING DASHBOARD")
        print("="*80)
        print(f"Runtime: {(datetime.now() - self.global_start).total_seconds()/3600:.1f}h")
        print(f"Status: {summary['status']}")
        
        print("\n📈 PORTFOLIO SUMMARY")
        print("-" *80)
        print(f"Trades:  {summary['total_trades']:3d} (Expected: {self.PORTFOLIO_BASELINE['total_trades']})")
        print(f"Win Rate: {summary['actual_wr']:5.2f}% (Expected: {summary['expected_wr']:5.2f}%) | Diff: {summary['wr_diff']:+6.2f}pp")
        print(f"PnL:     {summary['total_pnl']:+7.3f}% (Expected: {summary['expected_pnl']:+7.3f}%) | Diff: {summary['pnl_diff']:+7.3f}pp")
        
        print("\n📋 COIN BREAKDOWN")
        print("-" * 80)
        print(f"{'Coin':<12} {'Trades':>6} {'WR':>8} {'Expected':>10} {'PnL':>10} {'Expected':>10} {'Status':>15}")
        print("-" * 80)
        
        for symbol in sorted(self.BASELINE.keys()):
            stat = self.stats.get(symbol, TradeStats(symbol=symbol))
            baseline = self.BASELINE[symbol]
            wr_status = "🟢" if stat.wr_pct >= baseline['expected_wr']*0.9 else "🟡" if stat.wr_pct >= 20 else "🔴"
            
            print(f"{symbol:<12} {stat.trades:>6d} {stat.wr_pct:>7.1f}% {baseline['expected_wr']:>9.1f}% {stat.total_pnl:>9.2f}% {baseline['expected_pnl']:>9.2f}% {wr_status}")
        
        print("="*80 + "\n")
    
    def get_alerts(self):
        """Get critical alerts"""
        alerts = []
        for symbol in self.BASELINE.keys():
            stat = self.stats.get(symbol)
            if not stat or stat.trades == 0:
                continue
            
            baseline = self.BASELINE[symbol]
            
            # Alert if WR < 80% of expected for this coin
            if stat.wr_pct < baseline['expected_wr'] * 0.8:
                alerts.append(f"⚠️  {symbol}: WR {stat.wr_pct:.1f}% vs expected {baseline['expected_wr']:.1f}%")
            
            # Alert if PnL severely negative
            if stat.total_pnl < baseline['expected_pnl'] - 10:
                alerts.append(f"❌ {symbol}: PnL {stat.total_pnl:.2f}% vs expected {baseline['expected_pnl']:.2f}%")
        
        # Portfolio-level alerts
        summary = self.get_portfolio_summary()
        if summary['actual_wr'] < 20:
            alerts.insert(0, "🚨 CRITICAL: Portfolio WR < 20% - Activate rollback plan!")
        
        return alerts


# Example usage
if __name__ == "__main__":
    dashboard = TradingDashboard()
    
    # Simulate some trades for testing
    dashboard.log_trade("BTCUSDT", "BUY", 65000, 65500, "WIN", 0.76)
    dashboard.log_trade("BTCUSDT", "SELL", 65000, 64800, "LOSS", -0.30)
    dashboard.log_trade("LINKUSDT", "BUY", 15.5, 16.2, "WIN", 4.5)
    
    dashboard.print_dashboard()
    
    # Check for alerts
    alerts = dashboard.get_alerts()
    if alerts:
        print("⚠️  ALERTS:")
        for alert in alerts:
            print(f"   {alert}")
