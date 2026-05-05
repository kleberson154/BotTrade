#!/usr/bin/env python3
"""
Backteste da estratégia BotTrade usando dados históricos de BTC
"""
import sys
import os
import io
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

# Force UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from src.indicators import TechnicalIndicators

class SimpleBacktestEngine:
    def __init__(self, data_file, initial_balance=1000.0):
        """Inicializar motor de backteste"""
        self.data_file = data_file
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        
        # Historico de trades
        self.trades = []
        self.current_trade = None
        
        # Parametros de entrada
        self.rsi_overbought = 80
        self.rsi_oversold = 35
        self.tp_percent = 0.02  # 2% TP (Apenas TP1)
        self.sl_percent = 0.005  # 0.5% SL
        self.qty_percent = 1.0   # 100% de alocação de saldo em cada trade
        
        # Estatisticas
        self.stats = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'pnl': 0,
            'max_drawdown': 0,
            'max_equity': initial_balance,
            'min_equity': initial_balance,
        }
        
    def load_data(self):
        """Carregar dados historicos"""
        if not os.path.exists(self.data_file):
            print("[!] Arquivo de dados nao encontrado:", self.data_file)
            return None
        
        try:
            df = pd.read_csv(self.data_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            print("[+] Dados carregados:")
            print("    Linhas:", len(df))
            print("    Periodo:", df['timestamp'].min(), "a", df['timestamp'].max())
            print("    Duracao:", (df['timestamp'].max() - df['timestamp'].min()))
            
            return df
        except Exception as e:
            print("[!] Erro ao carregar dados:", e)
            return None
    
    def run_backtest(self, df):
        """Executar backteste"""
        if df is None or len(df) < 50:
            print("[!] Dados insuficientes para backteste")
            return
        
        print("\n" + "="*60)
        print("INICIANDO BACKTESTE")
        print("="*60)
        print("[*] Simulando estrategia simples em", len(df), "velas de 5 minutos")
        print()
        
        # Calcular RSI
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
            
            # ===== LOGICA DE ENTRADA =====
            if not self.current_trade:
                # Sinal de entrada: RSI cruzando oversold (BUY)
                if rsi_value < self.rsi_oversold and idx > 0:
                    self.current_trade = {
                        'entry_time': timestamp,
                        'entry_price': close_price,
                        'entry_idx': idx,
                        'side': 'BUY',
                        'tp': close_price * (1 + self.tp_percent),
                        'sl': close_price * (1 - self.sl_percent),
                    }
                    self.stats['total_trades'] += 1
                    print("[+] ENTRADA #{}: BUY a ${:.2f} | TP ${:.2f} | SL ${:.2f}".format(
                        self.stats['total_trades'],
                        self.current_trade['entry_price'],
                        self.current_trade['tp'],
                        self.current_trade['sl']
                    ))
                
                # Sinal de entrada: RSI cruzando overbought (SELL)
                elif rsi_value > self.rsi_overbought and idx > 0:
                    self.current_trade = {
                        'entry_time': timestamp,
                        'entry_price': close_price,
                        'entry_idx': idx,
                        'side': 'SELL',
                        'tp': close_price * (1 - self.tp_percent),
                        'sl': close_price * (1 + self.sl_percent),
                    }
                    self.stats['total_trades'] += 1
                    print("[+] ENTRADA #{}: SELL a ${:.2f} | TP ${:.2f} | SL ${:.2f}".format(
                        self.stats['total_trades'],
                        self.current_trade['entry_price'],
                        self.current_trade['tp'],
                        self.current_trade['sl']
                    ))
            
            # ===== LOGICA DE SAIDA =====
            elif self.current_trade:
                side = self.current_trade['side']
                entry = self.current_trade['entry_price']
                tp = self.current_trade['tp']
                sl = self.current_trade['sl']
                
                exit_triggered = False
                reason = ""
                exit_price = 0
                
                # BUY: verificar TP (high toca TP) e SL
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
                
                # SELL: verificar TP e SL
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
                
                # Timeout: fechar apos 100 velas
                elif (idx - self.current_trade['entry_idx']) > 100:
                    pnl = (close_price - entry) / entry * 100 if side == 'BUY' else (entry - close_price) / entry * 100
                    exit_triggered = True
                    reason = "TIMEOUT"
                    exit_price = close_price
                
                if exit_triggered:
                    self.close_trade(timestamp, exit_price, pnl, reason)
        
        self.print_results()
    
    def close_trade(self, timestamp, close_price, pnl_pct, reason):
        """Fechar trade"""
        self.current_trade['close_time'] = timestamp
        self.current_trade['close_price'] = close_price
        self.current_trade['pnl_pct'] = pnl_pct
        self.current_trade['reason'] = reason
        
        # Atualizar saldo
        trade_pnl = self.current_balance * self.qty_percent * (pnl_pct / 100)
        self.current_balance += trade_pnl
        self.current_trade['pnl_usdt'] = trade_pnl
        
        # Atualizar estatisticas
        self.stats['pnl'] += trade_pnl
        if pnl_pct > 0:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        
        self.stats['max_equity'] = max(self.stats['max_equity'], self.current_balance)
        self.stats['min_equity'] = min(self.stats['min_equity'], self.current_balance)
        
        drawdown = (self.stats['max_equity'] - self.current_balance) / self.stats['max_equity'] * 100
        self.stats['max_drawdown'] = max(self.stats['max_drawdown'], drawdown)
        
        # Log
        status = "[WIN]" if pnl_pct > 0 else "[LOSS]"
        duration = (self.current_trade['close_time'] - self.current_trade['entry_time']).total_seconds() / 60
        print("    {} {} a ${:.2f} | PnL {:+.2f}% | Duracao: {:.0f}min | Saldo: ${:.2f}".format(
            status,
            reason,
            close_price,
            pnl_pct,
            duration,
            self.current_balance
        ))
        
        self.trades.append(self.current_trade)
        self.current_trade = None
    
    def print_results(self):
        """Imprimir resultados do backteste"""
        print("\n" + "="*60)
        print("RESULTADOS DO BACKTESTE")
        print("="*60)
        
        if self.stats['total_trades'] == 0:
            print("[!] Nenhuma trade foi executada")
            return
        
        wr = (self.stats['wins'] / self.stats['total_trades'] * 100) if self.stats['total_trades'] > 0 else 0
        total_return = ((self.current_balance - self.initial_balance) / self.initial_balance) * 100
        
        print("\n[TRADES]")
        print("  Total Trades:", self.stats['total_trades'])
        print("  Wins:", self.stats['wins'])
        print("  Losses:", self.stats['losses'])
        print("  Win Rate:", "{:.1f}%".format(wr))
        
        print("\n[FINANCEIRO]")
        print("  Saldo Inicial: ${:.2f}".format(self.initial_balance))
        print("  Saldo Final: ${:.2f}".format(self.current_balance))
        print("  PnL Total: ${:+.2f}".format(self.stats['pnl']))
        print("  Retorno: {:+.2f}%".format(total_return))
        
        print("\n[RISCO]")
        print("  Max Equity: ${:.2f}".format(self.stats['max_equity']))
        print("  Min Equity: ${:.2f}".format(self.stats['min_equity']))
        print("  Max Drawdown: {:.2f}%".format(self.stats['max_drawdown']))
        
        if len(self.trades) > 0:
            pnls = [t['pnl_usdt'] for t in self.trades]
            wins = [t['pnl_usdt'] for t in self.trades if t['pnl_usdt'] > 0]
            losses = [t['pnl_usdt'] for t in self.trades if t['pnl_usdt'] <= 0]
            
            avg_win = np.mean(wins) if wins else 0
            avg_loss = abs(np.mean(losses)) if losses else 0
            
            print("\n[ESTATISTICAS DE TRADES]")
            print("  Maior Win: ${:.2f}".format(max(pnls)))
            print("  Maior Loss: ${:.2f}".format(min(pnls)))
            print("  Avg Win: ${:.2f}".format(avg_win))
            print("  Avg Loss: ${:.2f}".format(avg_loss))
            
            if avg_win > 0 and avg_loss > 0:
                profit_factor = (self.stats['wins'] * avg_win) / (self.stats['losses'] * avg_loss)
                print("  Profit Factor: {:.2f}".format(profit_factor))
            
            # Expectancia
            if self.stats['total_trades'] > 0:
                expectancy = self.stats['pnl'] / self.stats['total_trades']
                print("  Expectancia por Trade: ${:.2f}".format(expectancy))
        
        print("\n" + "="*60)

def main():
    print("="*60)
    print("BACKTESTE - BOTTRADE BTC")
    print("="*60)
    print()
    
    # Backteste
    engine = SimpleBacktestEngine("data/btc_5min_90d.csv", initial_balance=1000.0)
    
    print("[*] Carregando dados...")
    df = engine.load_data()
    
    if df is not None:
        print("\n[*] Executando backteste...")
        engine.run_backtest(df)

if __name__ == "__main__":
    main()

