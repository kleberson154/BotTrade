#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Backtest regime-adaptável 90d com suporte UTF-8."""
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
import io

# Force UTF-8 output
import codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

data_dir = os.path.join(os.path.dirname(__file__), 'data')
src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, data_dir)
sys.path.insert(0, src_dir)

from data.DeepSim_Engine import DeepSimulator

BASE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'coins')
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "XRPUSDT",
           "ADAUSDT", "NEARUSDT", "DOTUSDT", "LINKUSDT", "SUIUSDT", "OPUSDT"]

COIN_CONFIGS = {
    "BTCUSDT": {
        "atr_mult": 1.8, "min_pnl_be": 0.005, "dist_respiro": 0.015, "min_adx": 28,
        "signal_interval": 6, "invert_signal": True, "use_regime_filter": True,
        "allow_long": True, "allow_short": True,
    },
    "ETHUSDT": {
        "atr_mult": 1.8, "min_pnl_be": 0.005, "dist_respiro": 0.015, "min_adx": 30,
        "signal_interval": 6, "invert_signal": True, "use_regime_filter": True,
        "allow_long": True, "allow_short": False,
    },
    "SOLUSDT": {
        "atr_mult": 2.2, "min_pnl_be": 0.005, "dist_respiro": 0.022, "min_adx": 34,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "AVAXUSDT": {
        "atr_mult": 1.6, "min_pnl_be": 0.0045, "dist_respiro": 0.02, "min_adx": 32,
        "signal_interval": 5, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "XRPUSDT": {
        "atr_mult": 1.8, "min_pnl_be": 0.005, "dist_respiro": 0.02, "min_adx": 30,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": False,
    },
    "ADAUSDT": {
        "atr_mult": 1.8, "min_pnl_be": 0.005, "dist_respiro": 0.018, "min_adx": 28,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": False,
    },
    "NEARUSDT": {
        "atr_mult": 2.0, "min_pnl_be": 0.0055, "dist_respiro": 0.022, "min_adx": 32,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "DOTUSDT": {
        "atr_mult": 2.0, "min_pnl_be": 0.0055, "dist_respiro": 0.022, "min_adx": 30,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "LINKUSDT": {
        "atr_mult": 1.8, "min_pnl_be": 0.005, "dist_respiro": 0.018, "min_adx": 28,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "SUIUSDT": {
        "atr_mult": 2.2, "min_pnl_be": 0.006, "dist_respiro": 0.025, "min_adx": 34,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": True,
    },
    "OPUSDT": {
        "atr_mult": 2.0, "min_pnl_be": 0.006, "dist_respiro": 0.025, "min_adx": 32,
        "signal_interval": 6, "invert_signal": False, "use_regime_filter": False,
        "allow_long": True, "allow_short": False,
    },
}

def run_backtest_regime():
    """Executa backtest com regime adaptation ativado."""
    print("\n" + "="*60)
    print("BACKTEST REGIME-ADAPTAVEL [90 DIAS]")
    print("="*60)
    
    results = []
    all_trades = []
    
    for symbol in SYMBOLS:
        csv_path = os.path.join(BASE_DIR, f"data_{symbol}_90d.csv")
        if not os.path.exists(csv_path):
            print(f"[SKIP] {symbol}: arquivo nao encontrado")
            continue
        
        print(f"\n[RODANDO] {symbol}...")
        try:
            if not os.path.exists(csv_path):
                print(f"[SKIP] {symbol}: arquivo nao encontrado")
                continue
            
            tester = DeepSimulator(symbol, csv_path)
            df_trades = tester.run()
            
            # Métricas
            total_trades = len(df_trades)
            wins = len(df_trades[df_trades['profit_pct'] > 0])
            losses = len(df_trades[df_trades['profit_pct'] <= 0])
            wr = (wins / total_trades * 100) if total_trades > 0 else 0
            total_pnl = df_trades['profit_pct'].sum() * 100 if total_trades > 0 else 0
            avg_win = df_trades[df_trades['profit_pct'] > 0]['profit_pct'].mean() * 100 if wins > 0 else 0
            avg_loss = df_trades[df_trades['profit_pct'] <= 0]['profit_pct'].mean() * 100 if losses > 0 else 0
            
            print(f"   Trades: {total_trades} | Wins: {wins} | Loss: {losses} | WR: {wr:.1f}%")
            print(f"   PnL: {total_pnl:+.2f}% | Avg Win: {avg_win:+.3f}% | Avg Loss: {avg_loss:+.3f}%")
            
            results.append({
                'symbol': symbol,
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'wr_pct': wr,
                'total_pnl': total_pnl,
                'avg_win_pct': avg_win,
                'avg_loss_pct': avg_loss,
            })
            
            if total_trades > 0:
                df_trades['symbol'] = symbol
                all_trades.append(df_trades)
        
        except Exception as e:
            print(f"[ERRO] {symbol}: {str(e)[:100]}")
            continue
    
    # Resumo Geral
    if results:
        df_results = pd.DataFrame(results)
        print("\n" + "="*60)
        print("RESUMO GERAL - REGIME ADAPTATION")
        print("="*60)
        
        total_trades_all = df_results['total_trades'].sum()
        total_wins = df_results['wins'].sum()
        total_losses = df_results['losses'].sum()
        wr_geral = (total_wins / total_trades_all * 100) if total_trades_all > 0 else 0
        total_pnl_geral = df_results['total_pnl'].sum()
        
        print(f"\nTotal Trades (11 coins): {total_trades_all}")
        print(f"Wins: {total_wins} | Losses: {total_losses} | WR Global: {wr_geral:.1f}%")
        print(f"PnL Global: {total_pnl_geral:+.2f}%")
        print(f"\nPor Moeda:")
        for _, row in df_results.iterrows():
            print(f"  {row['symbol']:10s} - {row['total_trades']:3d}t | {row['wr_pct']:5.1f}% WR | {row['total_pnl']:+7.2f}% PnL")
        
        # Salva resultados
        df_results.to_csv('backtest_regime_90d_summary.csv', index=False)
        
        if all_trades:
            df_all = pd.concat(all_trades, ignore_index=True)
            df_all.to_csv('backtest_regime_90d_trades.csv', index=False)
            print(f"\nArquivos salvos:")
            print(f"  - backtest_regime_90d_summary.csv")
            print(f"  - backtest_regime_90d_trades.csv")
    
    print("\n" + "="*60)
    print("BACKTEST CONCLUÍDO")
    print("="*60)

if __name__ == '__main__':
    run_backtest_regime()
