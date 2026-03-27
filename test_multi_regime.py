#!/usr/bin/env python3
"""
TESTE DE REGIMES - Valida detecção automática e parâmetros de cada regime.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.strategy import TradingStrategy
from src.risk_manager import RiskManager
import pandas as pd

def test_regime_detection():
    """Testa detecção de regime com dados simulados."""
    
    print("=" * 70)
    print("TESTE DE REGIMES DE MERCADO")
    print("=" * 70)
    
    # Cria estratégia teste
    class FakeNotifier:
        def send_message(self, msg):
            pass
    
    strat = TradingStrategy("BTCUSDT", FakeNotifier())
    
    # Teste 1: COLD (ATR muito baixo)
    print("\n📋 TESTE 1: Simulando Regime COLD")
    print("-" * 70)
    
    df_cold = pd.DataFrame({
        'open': [100.1, 100.2, 100.15, 100.18, 100.12] * 20,
        'high': [100.2, 100.3, 100.25, 100.28, 100.22] * 20,
        'low': [100.0, 100.1, 100.05, 100.08, 100.02] * 20,
        'close': [100.15, 100.25, 100.2, 100.23, 100.17] * 20,
    })
    
    strat.candles_1m.extend([
        {'timestamp': i, 'open': df_cold.iloc[i]['open'], 'high': df_cold.iloc[i]['high'],
         'low': df_cold.iloc[i]['low'], 'close': df_cold.iloc[i]['close'], 'volume': 1000}
        for i in range(len(df_cold))
    ])
    strat._dirty_1m = True
    strat._sync_dataframes()
    
    regime = strat.detect_market_regime(strat.data_1m)
    print(f"Regime detectado: {regime}")
    print(f"Parâmetros COLD esperados:")
    print(f"  min_volatilidade_pct: {strat.regime_params_cold['min_volatilidade_pct']}")
    print(f"  volume_multiplier: {strat.regime_params_cold['volume_multiplier']}")
    print(f"  min_adx: {strat.regime_params_cold['min_adx']}")
    if regime == "COLD":
        print("✅ DETECÇÃO CORRECTA")
    else:
        print(f"⚠️ ESPERADO 'COLD', OBTEVE '{regime}'")
    
    # Teste 2: HOT (ATR muito alto)
    print("\n📋 TESTE 2: Simulando Regime HOT")
    print("-" * 70)
    
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
    print(f"Parâmetros HOT esperados:")
    print(f"  min_volatilidade_pct: {strat.regime_params_hot['min_volatilidade_pct']}")
    print(f"  volume_multiplier: {strat.regime_params_hot['volume_multiplier']}")
    print(f"  min_adx: {strat.regime_params_hot['min_adx']}")
    if regime == "HOT":
        print("✅ DETECÇÃO CORRECTA")
    else:
        print(f"⚠️ ESPERADO 'HOT', OBTEVE '{regime}'")
    
    # Teste 3: Aplicação de parâmetros
    print("\n📋 TESTE 3: Aplicação de Parâmetros por Regime")
    print("-" * 70)
    
    for regime_name in ["COLD", "LATERAL", "NORMAL", "HOT"]:
        strat.current_regime = regime_name
        strat.apply_regime_params()
        print(f"\n{regime_name}:")
        print(f"  min_volatilidade_pct: {strat.min_volatilidade_pct:.4f}")
        print(f"  volume_multiplier: {strat.volume_multiplier:.1f}")
        print(f"  min_adx: {strat.min_adx}")

def test_wr_validation():
    """Testa validação de WR e PnL."""
    
    print("\n" + "=" * 70)
    print("TESTE DE VALIDAÇÃO WR/PnL")
    print("=" * 70)
    
    risk_mgr = RiskManager()
    
    # Teste sem trades
    print("\n📋 TESTE 1: Sem trades")
    allowed, reason = risk_mgr.is_trading_allowed()
    print(f"Permitido: {allowed} | Motivo: {reason}")
    print("✅ ESPERADO: True (STARTUP)" if allowed and "STARTUP" in reason else "⚠️ INESPERADO")
    
    # Simula trades com WR baixo (25%)
    print("\n📋 TESTE 2: WR crítico (25%)")
    for i in range(4):
        risk_mgr.stats['total_trades'] += 1
        if i == 0:  # 1 win em 4 trades = 25%
            risk_mgr.stats['wins'] += 1
            risk_mgr.stats['pnl_history'][f'SYM{i}'] = 0.5
        else:
            risk_mgr.stats['pnl_history'][f'SYM{i}'] = -0.1
    
    total, wins, prot, wr, sr, pnl = risk_mgr.get_performance_stats()
    allowed, reason = risk_mgr.is_trading_allowed()
    print(f"WR: {wr:.1f}% | Trades: {total}")
    print(f"Permitido: {allowed} | Motivo: {reason}")
    print("✅ BLOQUEADO (WR < 32%)" if not allowed else "⚠️ DEVERIA ESTAR BLOQUEADO")
    
    # Simula trades com WR moderado (39%)
    print("\n📋 TESTE 3: WR moderado (39%)")
    risk_mgr.stats['total_trades'] = 0
    risk_mgr.stats['wins'] = 0
    risk_mgr.stats['pnl_history'] = {}
    
    for i in range(100):
        risk_mgr.stats['total_trades'] += 1
        if i % 100 < 39:  # 39 wins em 100 = 39%
            risk_mgr.stats['wins'] += 1
            risk_mgr.stats['pnl_history'][f'SYM{i}'] = 0.2
        else:
            risk_mgr.stats['pnl_history'][f'SYM{i}'] = -0.15
    
    total, wins, prot, wr, sr, pnl = risk_mgr.get_performance_stats()
    allowed, reason = risk_mgr.is_trading_allowed()
    lev_mult = risk_mgr.get_leverage_multiplier()
    print(f"WR: {wr:.1f}% | Trades: {total} | PnL: {pnl:.2f}")
    print(f"Permitido: {allowed} | Motivo: {reason}")
    print(f"Multiplicador alavancagem: {lev_mult:.1f}")
    print("✅ NORMAL COM LEVERAGE 100%" if lev_mult == 1.0 else "⚠️ DEVERIA SER 100%")
    
    # Simula trades com WR forte (45%)
    print("\n📋 TESTE 4: WR forte (45%)")
    risk_mgr.stats['wins'] = 45
    
    total, wins, prot, wr, sr, pnl = risk_mgr.get_performance_stats()
    allowed, reason = risk_mgr.is_trading_allowed()
    lev_mult = risk_mgr.get_leverage_multiplier()
    print(f"WR: {wr:.1f}% | Trades: {total} | PnL: {pnl:.2f}")
    print(f"Permitido: {allowed} | Motivo: {reason}")
    print(f"Multiplicador alavancagem: {lev_mult:.1f}")
    print("✅ MÁXIMO COM LEVERAGE 100%" if lev_mult == 1.0 else "⚠️ DEVERIA SER 100%")

if __name__ == "__main__":
    try:
        test_regime_detection()
        test_wr_validation()
        
        print("\n" + "=" * 70)
        print("✅ TODOS OS TESTES COMPLETADOS")
        print("=" * 70)
    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
