#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Teste simples de regime detection com novo HOT threshold."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.strategy import TradingStrategy
import pandas as pd

class FakeNotifier:
    def send_message(self, msg):
        pass

strat = TradingStrategy("BTCUSDT", FakeNotifier())

# Teste 1: Simulate HOT regime com ATR 0.18%
print("="*60)
print("TESTE: HOT regime com ATR 0.0018 (0.18%)")
print("="*60)

df_hot = pd.DataFrame({
    'open': [100 + i*0.5 for i in range(100)],
    'high': [105 + i*0.5 for i in range(100)],
    'low': [95 + i*0.5 for i in range(100)],
    'close': [102 + i*0.5 for i in range(100)],
})

strat.candles_1m.clear()
strat.candles_1m.extend([
    {'timestamp': i, 'open': df_hot.iloc[i]['open'], 'high': df_hot.iloc[i]['high'],
     'low': df_hot.iloc[i]['low'], 'close': df_hot.iloc[i]['close'], 'volume': 10000}
    for i in range(len(df_hot))
])
strat._dirty_1m = True
strat._sync_dataframes()

regime = strat.detect_market_regime(strat.data_1m)
print(f"Regime detectado: {regime}")
print(f"Status: {'OK' if regime == 'HOT' else 'ERRO'}")

if regime == 'HOT':
    strat.apply_regime_params()
    print(f"  min_volatilidade_pct: {strat.min_volatilidade_pct}")
    print(f"  volume_multiplier: {strat.volume_multiplier}")
    print(f"  min_adx: {strat.min_adx}")
    print("  [ESPERADO] Parametros HOT aplicados corretamente")

# Teste 2: NORMAL (ATR 0.0012-0.0015)
print("\n" + "="*60)
print("TESTE: NORMAL regime com ATR 0.0012-0.0015")
print("="*60)

# Oscilacao media: high-low = 0.12 (0.12% do preco)
df_normal = pd.DataFrame({
    'open': [100.03 + i*0.01 for i in range(100)],
    'high': [100.10 + i*0.01 for i in range(100)],
    'low': [99.98 + i*0.01 for i in range(100)],
    'close': [100.06 + i*0.01 for i in range(100)],
})

strat.candles_1m.clear()
strat.candles_1m.extend([
    {'timestamp': i, 'open': df_normal.iloc[i]['open'], 'high': df_normal.iloc[i]['high'],
     'low': df_normal.iloc[i]['low'], 'close': df_normal.iloc[i]['close'], 'volume': 5000}
    for i in range(len(df_normal))
])
strat._dirty_1m = True
strat._sync_dataframes()

regime = strat.detect_market_regime(strat.data_1m)
print(f"Regime detectado: {regime}")
print(f"Status: {'OK' if regime == 'NORMAL' else 'ERRO'}")

if regime == 'NORMAL':
    strat.apply_regime_params()
    print(f"  min_volatilidade_pct: {strat.min_volatilidade_pct}")
    print(f"  volume_multiplier: {strat.volume_multiplier}")
    print(f"  min_adx: {strat.min_adx}")
else:
    # Debug: calcular ATR para ver qual valor está sendo detectado
    recent = strat.data_1m.tail(30)
    tr = pd.concat([recent['high'] - recent['low'],
                    (recent['high'] - recent['close'].shift()).abs(),
                    (recent['low'] - recent['close'].shift()).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(14).mean().iloc[-1] / recent['close'].iloc[-1]
    print(f"  DEBUG ATR calculado: {atr_pct:.6f}")

print("\n" + "="*60)
print("TESTES COMPLETOS")
print("="*60)
