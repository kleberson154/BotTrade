#!/usr/bin/env python
"""Emergency position close script for rollback procedures"""
import sys
import argparse
from dotenv import load_dotenv
import os

sys.path.insert(0, 'src')

from connection import get_http_session
from src.logger import setup_logger

load_dotenv()
log = setup_logger()

def close_positions(mode="full", amount=100):
    """
    Close positions on Bybit
    
    Args:
        mode: 'full' (close all) or 'partial' (close % of each)
        amount: percentage to close (for partial mode)
    """
    
    API_KEY = os.getenv("BYBIT_API_KEY")
    API_SECRET = os.getenv("BYBIT_API_SECRET")
    IS_DEMO = os.getenv("BYBIT_MODE", "demo").lower() == "demo"
    
    session = get_http_session(API_KEY, API_SECRET, testnet=False, demo=IS_DEMO)
    
    print(f"\n🔴 EMERGENCY POSITION CLOSE - Mode: {mode.upper()}")
    print(f"   Environment: {'DEMO' if IS_DEMO else 'REAL'}")
    print(f"   Close Amount: {amount}%\n")
    
    if not IS_DEMO:
        response = input("⚠️  REAL MONEY MODE - Are you absolutely sure? (type 'YES' to confirm): ")
        if response != "YES":
            print("Aborted.")
            return
    
    try:
        # Get all positions
        resp = session.get_positions(category='linear', settleCoin='USDT')
        positions = resp['result']['list']
        
        active = [p for p in positions if float(p['size']) > 0]
        
        if not active:
            print("✅ No open positions.")
            return
        
        print(f"Found {len(active)} open positions:\n")
        
        closed_count = 0
        for pos in active:
            symbol = pos['symbol']
            side = pos['side']
            size = float(pos['size'])
            entry_price = float(pos['avgPrice'])
            current_price = float(pos['markPrice'])
            
            # Calculate how much to close
            qty_to_close = size * (amount / 100)
            
            # Determine close side
            close_side = 'Sell' if side == 'Buy' else 'Buy'
            
            print(f"{symbol}:")
            print(f"  Side: {side} | Size: {size} | Pos Value: ${size * current_price:.2f}")
            print(f"  Entry: ${entry_price:.2f} | Current: ${current_price:.2f}")
            print(f"  Closing: {qty_to_close:.4f} ({amount}%)")
            
            try:
                # Place close order
                order = session.place_order(
                    category='linear',
                    symbol=symbol,
                    side=close_side,
                    orderType='Market',
                    qty=str(qty_to_close)
                )
                
                if order['retCode'] == 0:
                    print(f"  ✅ Order placed: {order['result']['orderId']}")
                    closed_count += 1
                else:
                    print(f"  ❌ Order failed: {order['retMsg']}")
                    
            except Exception as e:
                print(f"  ❌ Error: {str(e)[:150]}")
            
            print()
        
        print(f"\n✅ {closed_count}/{len(active)} positions processed")
        
        # Verify remaining positions
        resp = session.get_positions(category='linear', settleCoin='USDT')
        remaining = [p for p in resp['result']['list'] if float(p['size']) > 0]
        print(f"   Remaining open positions: {len(remaining)}")
        
    except Exception as e:
        log.error(f"Critical error: {e}")
        print(f"\n❌ FAILED: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', default='full', choices=['full', 'partial'])
    parser.add_argument('--amount', type=float, default=100, help='% to close (for partial)')
    
    args = parser.parse_args()
    
    close_positions(mode=args.mode, amount=args.amount)
