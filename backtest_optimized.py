#!/usr/bin/env python3
"""
Backteste avancado com otimizacao de parametros
Testa diferentes combinacoes de RSI e TP/SL
"""
import sys
import os
import io
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from src.indicators import TechnicalIndicators

class OptimizedBacktest:
    def __init__(self, data_file, initial_balance=1000.0):
        """Inicializar backteste otimizado"""
        self.data_file = data_file
        self.initial_balance = initial_balance
        self.results = []
        
    def load_data(self):
        """Carregar dados"""
        if not os.path.exists(self.data_file):
            print("[!] Arquivo nao encontrado: {}".format(self.data_file))
            return None
        
        try:
            df = pd.read_csv(self.data_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        except Exception as e:
            print("[!] Erro ao carregar: {}".format(e))
            return None
    
    def run_backtest(self, df, rsi_oversold, rsi_overbought, tp_pct, sl_pct):
        """Executar um backteste com parametros especificos"""
        
        if df is None or len(df) < 50:
            return None
        
        current_balance = self.initial_balance
        trades = []
        current_trade = None
        
        closes = df['close'].values
        rsi = TechnicalIndicators.calculate_rsi(df['close'])
        
        for idx in range(50, len(df)):
            close_price = closes[idx]
            rsi_value = rsi.iloc[idx] if idx < len(rsi) else None
            timestamp = df.iloc[idx]['timestamp']
            high = df.iloc[idx]['high']
            low = df.iloc[idx]['low']
            
            if rsi_value is None or np.isnan(rsi_value):
                continue
            
            # ENTRADA
            if not current_trade:
                if rsi_value < rsi_oversold:
                    current_trade = {
                        'entry_time': timestamp,
                        'entry_price': close_price,
                        'entry_idx': idx,
                        'side': 'BUY',
                        'tp': close_price * (1 + tp_pct),
                        'sl': close_price * (1 - sl_pct),
                    }
                
                elif rsi_value > rsi_overbought:
                    current_trade = {
                        'entry_time': timestamp,
                        'entry_price': close_price,
                        'entry_idx': idx,
                        'side': 'SELL',
                        'tp': close_price * (1 - tp_pct),
                        'sl': close_price * (1 + sl_pct),
                    }
            
            # SAIDA
            elif current_trade:
                side = current_trade['side']
                entry = current_trade['entry_price']
                tp = current_trade['tp']
                sl = current_trade['sl']
                
                exit_triggered = False
                reason = ""
                exit_price = 0
                
                if side == 'BUY':
                    if high >= tp:
                        pnl = (tp - entry) / entry * 100
                        exit_triggered = True
                        reason = "TP"
                        exit_price = tp
                    elif low <= sl:
                        pnl = (sl - entry) / entry * 100
                        exit_triggered = True
                        reason = "SL"
                        exit_price = sl
                
                elif side == 'SELL':
                    if low <= tp:
                        pnl = (entry - tp) / entry * 100
                        exit_triggered = True
                        reason = "TP"
                        exit_price = tp
                    elif high >= sl:
                        pnl = (entry - sl) / entry * 100
                        exit_triggered = True
                        reason = "SL"
                        exit_price = sl
                
                elif (idx - current_trade['entry_idx']) > 100:
                    pnl = (close_price - entry) / entry * 100 if side == 'BUY' else (entry - close_price) / entry * 100
                    exit_triggered = True
                    reason = "TIMEOUT"
                    exit_price = close_price
                
                if exit_triggered:
                    trade_pnl = current_balance * (pnl / 100)
                    current_balance += trade_pnl
                    
                    trades.append({
                        'pnl_pct': pnl,
                        'pnl_usdt': trade_pnl,
                        'reason': reason,
                    })
                    
                    current_trade = None
        
        # Calcular estatisticas
        if len(trades) == 0:
            return None
        
        total_trades = len(trades)
        wins = sum(1 for t in trades if t['pnl_pct'] > 0)
        losses = total_trades - wins
        total_pnl = sum(t['pnl_usdt'] for t in trades)
        wr = (wins / total_trades * 100) if total_trades > 0 else 0
        
        return {
            'rsi_oversold': rsi_oversold,
            'rsi_overbought': rsi_overbought,
            'tp_pct': tp_pct,
            'sl_pct': sl_pct,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'wr': wr,
            'pnl_total': total_pnl,
            'balance_final': current_balance,
            'return_pct': ((current_balance - self.initial_balance) / self.initial_balance) * 100,
        }
    
    def optimize(self, df):
        """Otimizar parametros testando multiplas combinacoes"""
        
        print()
        print("[*] Testando multiplas combinacoes de parametros...")
        print()
        
        # Parametros a testar
        rsi_oversold_values = [20, 25, 30, 35]
        rsi_overbought_values = [65, 70, 75, 80]
        tp_values = [0.005, 0.01, 0.015, 0.02]  # 0.5%, 1%, 1.5%, 2%
        sl_values = [0.003, 0.005, 0.01]  # 0.3%, 0.5%, 1%
        
        best_result = None
        total_combinations = len(rsi_oversold_values) * len(rsi_overbought_values) * len(tp_values) * len(sl_values)
        current = 0
        
        for rsi_os in rsi_oversold_values:
            for rsi_ob in rsi_overbought_values:
                for tp in tp_values:
                    for sl in sl_values:
                        current += 1
                        result = self.run_backtest(df, rsi_os, rsi_ob, tp, sl)
                        
                        if result:
                            self.results.append(result)
                            
                            if best_result is None or result['pnl_total'] > best_result['pnl_total']:
                                best_result = result
        
        print("[+] Testadas {} combinacoes".format(total_combinations))
        print()
        
        return best_result
    
    def print_top_results(self, n=10):
        """Imprimir top N resultados"""
        
        if not self.results:
            print("[!] Nenhum resultado disponivel")
            return
        
        sorted_results = sorted(self.results, key=lambda x: x['pnl_total'], reverse=True)
        
        print("[*] TOP {} RESULTADOS:".format(min(n, len(sorted_results))))
        print()
        print("Pos | RSI(os/ob) | TP/SL  | Trades | WR    | PnL    | Retorno")
        print("----+----------+-------+-------+-------+-------+---------")
        
        for i, r in enumerate(sorted_results[:n], 1):
            print("{:3d} | {:2d}/{:2d}    | {:3.1f}/{:3.1f}% | {:6d} | {:5.1f}% | {:+6.2f}$ | {:+6.2f}%".format(
                i,
                r['rsi_oversold'],
                r['rsi_overbought'],
                r['tp_pct'] * 100,
                r['sl_pct'] * 100,
                r['total_trades'],
                r['wr'],
                r['pnl_total'],
                r['return_pct']
            ))
        
        print()

def main():
    print("="*80)
    print("BACKTESTE AVANCADO COM OTIMIZACAO DE PARAMETROS")
    print("="*80)
    print()
    
    engine = OptimizedBacktest("data/btc_5min_90d.csv", initial_balance=1000.0)
    
    print("[*] Carregando dados...")
    df = engine.load_data()
    
    if df is not None:
        print("[+] Dados carregados: {} velas".format(len(df)))
        print("    Periodo: {} a {}".format(
            df['timestamp'].min().strftime('%Y-%m-%d %H:%M'),
            df['timestamp'].max().strftime('%Y-%m-%d %H:%M')
        ))
        print("    Duracao: {}".format(df['timestamp'].max() - df['timestamp'].min()))
        
        best = engine.optimize(df)
        
        if best:
            print()
            print("="*80)
            print("MELHOR CONFIGURACAO")
            print("="*80)
            print()
            print("Parametros Otimos:")
            print("  RSI Oversold: {}".format(best['rsi_oversold']))
            print("  RSI Overbought: {}".format(best['rsi_overbought']))
            print("  Take Profit: {:.2f}%".format(best['tp_pct'] * 100))
            print("  Stop Loss: {:.2f}%".format(best['sl_pct'] * 100))
            print()
            print("Resultados:")
            print("  Total Trades: {}".format(best['total_trades']))
            print("  Win Rate: {:.1f}%".format(best['wr']))
            print("  Wins: {} | Losses: {}".format(best['wins'], best['losses']))
            print("  PnL Total: ${:+.2f}".format(best['pnl_total']))
            print("  Saldo Final: ${:.2f}".format(best['balance_final']))
            print("  Retorno: {:+.2f}%".format(best['return_pct']))
        
        engine.print_top_results(10)

if __name__ == "__main__":
    main()
