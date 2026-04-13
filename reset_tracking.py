#!/usr/bin/env python
"""
Reset Win Rate Tracking to Today
Used when deploying new bot versions to measure fresh performance

Usage: python reset_tracking.py
"""
import os
from monitoring_dashboard import TradingDashboard

if __name__ == "__main__":
    dashboard = TradingDashboard()
    dashboard.reset_today()
    
    print("\n" + "="*60)
    print("🎯 WIN RATE TRACKING RESET")
    print("="*60)
    print("✅ Statistics reset successfully!")
    print("📊 Starting fresh tracking from now")
    print("🕐 Reset timestamp saved to: RESET_TRADES_TODAY.txt")
    print("\n💡 Tip: Run the bot now with 'python main.py'")
    print("="*60)
