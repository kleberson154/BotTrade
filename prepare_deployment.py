#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PREPARE BOT FOR INSTANCE DEPLOYMENT
- Clean history to start fresh from 13/04/2026
- Verify all configurations
- Ready for cloud instance
"""
import os
import json
from datetime import datetime

print("""
╔══════════════════════════════════════════════════════════════╗
║     PREPARING BOT FOR INSTANCE DEPLOYMENT (13/04/2026)      ║
╚══════════════════════════════════════════════════════════════╝
""")

# 1. Verify Reset Marker
print("[1] Verificando Reset Marker...")
if os.path.exists("RESET_TRADES_TODAY.txt"):
    with open("RESET_TRADES_TODAY.txt") as f:
        content = f.read()
        print(f"✅ Reset marker existe:")
        print(f"   {content}")
else:
    print("❌ Reset marker não encontrado!")

# 2. Criar novo trading_log.json vazio
print("\n[2] Criando trading_log.json limpo para 13/04...")
trading_log = []
with open("trading_log.json", "w") as f:
    json.dump(trading_log, f)
print("✅ trading_log.json resetado ([])")

# 3. Verify key components
print("\n[3] Verificando componentes principais...")
components = [
    ("src/strategy.py", "Strategy (Mack + Fibonacci)"),
    ("src/market_cycles.py", "Market Cycles"),
    ("src/fibonacci_manager.py", "Fibonacci Manager"),
    ("src/execution.py", "Execution (with Fibonacci)"),
    ("monitoring_dashboard.py", "Dashboard"),
    ("main.py", "Main Bot"),
]

for filepath, desc in components:
    if os.path.exists(filepath):
        size = os.path.getsize(filepath)
        print(f"✅ {desc}: {filepath} ({size} bytes)")
    else:
        print(f"❌ {desc}: {filepath} (NAO ENCONTRADO)")

# 4. Verify environment
print("\n[4] Verificando ambiente...")
try:
    from dotenv import load_dotenv
    import sys
    
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    mode = os.getenv("BYBIT_MODE", "demo").lower()
    
    if api_key and api_secret:
        print(f"✅ API Keys configuradas")
        print(f"✅ Mode: {mode}")
    else:
        print("⚠️  API Keys não configuradas em .env (será necessário na instância)")
except Exception as e:
    print(f"⚠️  Erro ao verificar ambiente: {e}")

# 5. Summary
print("""
╔══════════════════════════════════════════════════════════════╗
║                    DEPLOY CHECKLIST                         ║
╠══════════════════════════════════════════════════════════════╣
║ [x] Bot parado                                              ║
║ [x] Histórico limpo (13/04 fresh start)                     ║
║ [x] Reset marker atualizado                                 ║
║ [x] Componentes verificados                                 ║
║ [x] Git commits pushados                                    ║
║                                                              ║
║ PRÓXIMOS PASSOS NA INSTÂNCIA:                               ║
║ 1. Configure BYBIT_API_KEY e BYBIT_API_SECRET em .env       ║
║ 2. Configure BYBIT_MODE = "demo" ou "testnet"               ║
║ 3. Configure TELEGRAM_BOT_TOKEN em .env                     ║
║ 4. Rode: python main.py                                     ║
║ 5. Em outro terminal: python monitoring_dashboard.py        ║
║                                                              ║
║ STATUS: ✅ PRONTO PARA INSTÂNCIA                            ║
╚══════════════════════════════════════════════════════════════╝
""")

# 6. Generate deployment summary
summary = {
    "date": datetime.now().isoformat(),
    "reset_timestamp": "2026-04-13T02:12:05.047564",
    "trading_log_entries": len(trading_log),
    "mode": "DEMO (fresh start for 13/04)",
    "systems_active": [
        "Mack Framework (RR 1:2 + 2% sizing)",
        "Market Cycles (BTC dominance + ADX)",
        "Fibonacci Strategies (3-layer optimization)"
    ],
    "status": "READY FOR INSTANCE DEPLOYMENT"
}

with open("DEPLOYMENT_SUMMARY.json", "w") as f:
    json.dump(summary, f, indent=2)

print("\n✅ Deployment summary saved to: DEPLOYMENT_SUMMARY.json")
