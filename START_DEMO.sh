#!/bin/bash

# DEMO Trading Session - 2h validation
echo "🚀 Starting DEMO Trading Mode"
echo "================================="

# Step 1: Clear environment
unset SYMBOLS  # Clear any override

# Step 2: Verify config
export BYBIT_MODE=demo
echo "✅ Environment: DEMO mode"

# Step 3: Verify Python works
python -c "from src.strategy import TradingStrategy; print('✅ Strategy module OK')" || exit 1

# Step 4: Create log directory
mkdir -p logs

# Step 5: Start bot
LOG_FILE="logs/demo_run_$(date +%Y%m%d_%H%M%S).log"
echo "📝 Logging to: $LOG_FILE"
echo ""
echo "🔄 Bot starting..."
echo "📊 Monitor with: python monitoring_dashboard.py"
echo "⏹️  Stop with: pkill -f 'python main.py'"
echo ""

# Start bot in background
nohup python main.py > "$LOG_FILE" 2>&1 &
BOT_PID=$!

echo "✅ Bot started (PID: $BOT_PID)"
echo "⏱️  Running for 2h (monitoring recommended)"
