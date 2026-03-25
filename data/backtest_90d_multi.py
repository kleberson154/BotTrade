#!/usr/bin/env python
"""
Backtest multi-moeda com relatório detalhado.
Aguarda os CSVs 90d de cada moeda e executa o simulador.
"""
import os, sys, glob
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from DeepSim_Engine import DeepSimulator

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT", "XRPUSDT", 
           "ADAUSDT", "NEARUSDT", "DOTUSDT", "SUIUSDT", "OPUSDT"]

results = []

print("Backtesting 12 moedas com 90 dias...\n")

for symbol in SYMBOLS:
    csv_path = f"../data_{symbol}_90d.csv"
    
    # Verifica se arquivo existe
    if not os.path.exists(csv_path):
        print(f"{symbol:12s}: [SKIP] arquivo nao encontrado")
        continue
    
    try:
        tester = DeepSimulator(symbol, csv_path)
        report = tester.run()
        
        if not report.empty:
            trades = len(report)
            wr = (report['net_pnl'] > 0).mean()
            pnl = report['net_pnl'].sum()
            avg = report['net_pnl'].mean()
            best = report['net_pnl'].max()
            worst = report['net_pnl'].min()
            
            results.append({
                'symbol': symbol,
                'trades': trades,
                'wr': wr,
                'pnl_total': pnl,
                'pnl_avg': avg,
                'pnl_best': best,
                'pnl_worst': worst
            })
            
            print(f"{symbol:12s}: trades={trades:3d} wr={wr:5.1%} pnl={pnl:7.2%} avg={avg:7.2%}")
        else:
            print(f"{symbol:12s}: [NO TRADES]")
            
    except Exception as e:
        print(f"{symbol:12s}: [ERRO] {e}")

# Relatorio agregado
if results:
    df = pd.DataFrame(results)
    total_trades = df['trades'].sum()
    avg_wr = df['wr'].mean()
    total_pnl = df['pnl_total'].sum()
    
    print(f"\n{'='*60}")
    print(f"RESUMO: {len(df)} moedas | {total_trades} trades totais | WR media: {avg_wr:.1%}")
    print(f"PnL AGREGADO: {total_pnl:+.2%}")
    print(f"{'='*60}")
    
    # Salva relatorio
    df_report = df[['symbol','trades','wr','pnl_total','pnl_avg','pnl_best','pnl_worst']]
    df_report.to_csv('../backtest_report_90d.csv', index=False)
    print("Relatorio salvo: backtest_report_90d.csv")
