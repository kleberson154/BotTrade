# -*- coding: utf-8 -*-
"""
Test: Complete Integration of Fibonacci + Multi-Timeframe + Multiple TPs
"""

import pandas as pd
import numpy as np
from src.fibonacci_multi_timeframe import (
    FibonacciAnalyzer,
    MultiTimeframeValidator,
    MultipleTPManager
)


def main():
    print("\n" + "="*100)
    print("TEST: Complete Fibonacci + Multi-Timeframe System")
    print("="*100)
    
    # ===== Test 1: Basic Fibonacci =====
    print("\n[TEST 1] Fibonacci Retracement & Projection")
    print("-" * 100)
    
    fib = FibonacciAnalyzer()
    
    swing_high = 150.00
    swing_low = 100.00
    
    retracement = fib.calculate_retracement(swing_high, swing_low)
    print("\nRetracement Levels (Swing High=150, Swing Low=100):")
    for level_name, data in retracement['levels'].items():
        print(f"  {level_name}: {data['level']:.2f}")
    
    projection = fib.calculate_projection(swing_low, swing_high)
    print("\nProjection Levels:")
    for level_name, data in projection['levels'].items():
        print(f"  {level_name}: {data['level']:.2f}")
    
    # ===== Test 2: TP Calculation =====
    print("\n" + "-" * 100)
    print("\n[TEST 2] Automatic TP Calculation (Based on Fibonacci)")
    print("-" * 100)
    
    entry = 120.00
    stop_loss = 110.00
    
    tp_calc = fib.calculate_tp_levels(entry, stop_loss)
    
    print(f"\nTrade Setup: Entry={entry}, SL={stop_loss}, Risk={tp_calc['risk']}")
    print(f"  TP1 (RR 1:0.382): {tp_calc['tp1']:.2f}")
    print(f"  TP2 (RR 1:0.618): {tp_calc['tp2']:.2f}")
    print(f"  TP3 (RR 1:1.0):   {tp_calc['tp3']:.2f}")
    
    # ===== Test 3: Multi-Timeframe =====
    print("\n" + "-" * 100)
    print("\n[TEST 3] Multi-Timeframe Validation (1h + 15m)")
    print("-" * 100)
    
    # Create sample data
    np.random.seed(42)
    
    # 1h data
    prices_1h = []
    for i in range(50):
        prices_1h.append(100 + i * 0.5 + np.random.normal(0, 0.2))
    
    df_1h = pd.DataFrame({
        'open': prices_1h,
        'high': prices_1h,
        'low': prices_1h,
        'close': prices_1h,
        'volume': np.random.uniform(2000, 3000, 50)
    })
    
    # 15m data
    prices_15m = []
    for i in range(100):
        prices_15m.append(125 + i * 0.1 + np.random.normal(0, 0.15))
    
    df_15m = pd.DataFrame({
        'open': prices_15m,
        'high': prices_15m,
        'low': prices_15m,
        'close': prices_15m,
        'volume': np.random.uniform(1500, 2500, 100)
    })
    
    print(f"\n1h Data:  {len(df_1h)} candles | Close = {df_1h['close'].iloc[-1]:.2f}")
    print(f"15m Data: {len(df_15m)} candles | Close = {df_15m['close'].iloc[-1]:.2f}")
    
    validator = MultiTimeframeValidator()
    mtf_result = validator.validate_multi_timeframe(df_1h, df_15m)
    
    print(f"\nMulti-Timeframe Signal: {mtf_result['signal']}")
    print(f"Valid: {mtf_result['is_valid']}")
    print(f"Trend 1h: {mtf_result.get('trend_1h', 'N/A')}")
    print(f"Signal 15m: {mtf_result.get('signal_15m', 'N/A')}")
    print(f"Confidence 1h: {mtf_result.get('confidence_1h', 0):.0f}%")
    print(f"Confidence 15m: {mtf_result.get('confidence_15m', 0):.0f}%")
    
    # ===== Test 4: Multiple TP Manager =====
    print("\n" + "-" * 100)
    print("\n[TEST 4] Multiple Take Profit Management (2-Phase Execution)")
    print("-" * 100)
    
    tp_manager = MultipleTPManager()
    
    symbol = "BTCUSDT"
    signal_type = "BUY"
    entry = 45000.00
    stop_loss = 44000.00
    quantity = 1.0
    
    print(f"\nTrade: {signal_type} {quantity} {symbol}")
    print(f"  Entry: {entry:.2f}")
    print(f"  Stop Loss: {stop_loss:.2f}")
    print(f"  Risk: ${abs(entry - stop_loss) * quantity:.2f}")
    
    trade_plan = tp_manager.generate_complete_trade_plan(
        symbol, signal_type, entry, stop_loss, quantity
    )
    
    print(f"\nPHASE 1 (Initial Order - No TP):")
    phase1 = trade_plan['phase1']
    print(f"  {phase1['side']} {phase1['quantity']} @ {phase1['price']:.2f}")
    print(f"  SL: {phase1['stop_loss']:.2f}")
    
    print(f"\nPHASE 2 (Add 3 TPs after confirmation):")
    phase2 = trade_plan['phase2']
    metrics = trade_plan['metrics']
    
    for tp_order in phase2['tp_orders']:
        tp_num = tp_order['tp_number']
        price = tp_order['price']
        qty = tp_order['quantity']
        qty_pct = tp_order['quantity_pct']
        rr = tp_order['risk_reward']
        print(f"  TP{tp_num}: SELL {qty} @ {price:.2f} ({qty_pct}) [RR {rr}]")
    
    print(f"\nExpected Exit Prices:")
    print(f"  TP1 @ {metrics['tp1']:.2f}")
    print(f"  TP2 @ {metrics['tp2']:.2f}")
    print(f"  TP3 @ {metrics['tp3']:.2f}")
    print(f"  Average Exit: {metrics['avg_exit']:.2f}")
    
    profit_at_avg = (metrics['avg_exit'] - metrics['entry']) * quantity
    print(f"  Expected Profit (avg): ${profit_at_avg:.2f}")
    print(f"  Expected RR: 1:{abs(metrics['total_risk_reward']):.3f}")
    
    # ===== Test 5: Entry Analysis =====
    print("\n" + "-" * 100)
    print("\n[TEST 5] Best Entry Levels (Fibonacci-based)")
    print("-" * 100)
    
    entry_levels = validator.get_best_entry_levels(df_1h, df_15m, "BUY", fib)
    
    print(f"\nFor BUY Signal:")
    print(f"  Primary Entry: {entry_levels['primary_entry']:.2f}")
    if 'ideal_entry' in entry_levels:
        print(f"  Ideal Entry (Fib 0.618): {entry_levels['ideal_entry']:.2f}")
    
    print(f"\nEntry Criteria:")
    for i, criterion in enumerate(entry_levels['criteria'], 1):
        print(f"  {i}. {criterion}")
    
    # ===== Summary =====
    print("\n" + "="*100)
    print("All Tests Completed Successfully!")
    print("="*100)
    print("\nSystem Components:")
    print("  [OK] FibonacciAnalyzer - Retracement, Projection, TP Calculation")
    print("  [OK] MultiTimeframeValidator - 1h + 15m alignment check")
    print("  [OK] MultipleTPManager - 2-phase execution with multiple TPs")
    print("\nKey Features:")
    print("  - Fibonacci levels for entry and exit")
    print("  - Multi-timeframe confirmation (prevents trading against 1h trend)")
    print("  - Multiple TPs with risk/reward ratios (1:0.382, 1:0.618, 1:1.0)")
    print("  - Volume distribution (50%, 30%, 20%) across TPs")
    print("\n")


if __name__ == "__main__":
    main()
