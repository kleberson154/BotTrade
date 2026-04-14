import pandas as pd
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.strategy import TradingStrategy


class SilentNotifier:
    def send_message(self, _message):
        pass

class MultiBacktester:
    def __init__(self, symbols, initial_balance=1000, leverage=10):
        self.symbols = symbols
        self.initial_balance = initial_balance
        self.leverage = leverage
        self.taxa_bybit = 0.0006
        self.global_results = []

    def run_all(self):
        print(f"🚀 Iniciando Varredura em {len(self.symbols)} moedas...")
        
        for symbol in self.symbols:
            try:
                # 1. Carregar dados específicos de cada moeda
                df_1m = pd.read_csv(f"{symbol.lower()}_1m.csv", index_col='timestamp', parse_dates=True)
                df_15m = pd.read_csv(f"{symbol.lower()}_15m.csv", index_col='timestamp', parse_dates=True)
                
                # 2. Executar backtest para esta moeda
                balance_final, trades_count, pnl_total = self.simulate(symbol, df_1m, df_15m)
                
                self.global_results.append({
                    'Moeda': symbol,
                    'Trades': trades_count,
                    'PnL_Final_%': f"{pnl_total:.2f}%",
                    'Saldo_Final': f"{balance_final:.2f} USDT"
                })
            except FileNotFoundError:
                print(f"⚠️ Arquivos para {symbol} não encontrados. Pulei essa.")

        self.show_final_leaderboard()

    def simulate(self, symbol, df_1m, df_15m):
        strat = TradingStrategy(symbol, notifier=SilentNotifier())
        current_balance = self.initial_balance
        trades_done = 0
        
        for i in range(200, len(df_1m)):
            current_price = df_1m['close'].iloc[i]
            current_time = df_1m.index[i]
            
            strat.data_1m = df_1m.iloc[:i+1]
            strat.data_15m = df_15m[df_15m.index <= current_time]

            if strat.is_positioned:
                # Lógica de Saída/Proteção
                # Monitorar cascata de TPs
                status = strat.check_cascade_tp(current_price)
                
                # Checagem de Stop
                is_stop = (strat.side == "BUY" and current_price <= strat.sl_price) or \
                          (strat.side == "SELL" and current_price >= strat.sl_price)
                
                if is_stop:
                    pnl_pct = (current_price - strat.entry_price) / strat.entry_price if strat.side == "BUY" else (strat.entry_price - current_price) / strat.entry_price
                    # Cálculo com Alavancagem e Taxas
                    multi = 0.5 if strat.partial_taken else 1.0
                    lucro_usdt = (current_balance * 0.1) * multi * (pnl_pct * self.leverage - self.taxa_bybit)
                    current_balance += lucro_usdt
                    strat.is_positioned = False
                    trades_done += 1

            else:
                # Lógica de Entrada
                signal, atr = strat.check_signal()
                if signal in ["BUY", "SELL"]:
                    strat.is_positioned = True
                    strat.side = signal
                    strat.entry_price = current_price
                    strat.sl_price = current_price - (atr * 7.5) if signal == "BUY" else current_price + (atr * 7.5)
                    strat.partial_taken = False

        total_pnl_pct = ((current_balance - self.initial_balance) / self.initial_balance) * 100
        return current_balance, trades_done, total_pnl_pct

    def show_final_leaderboard(self):
        df = pd.DataFrame(self.global_results)
        print("\n" + "🏆 RANKING DE PERFORMANCE " + "="*20)
        print(df.sort_values(by='Saldo_Final', ascending=False))
        print("="*45)

if __name__ == "__main__":
    # Lista de moedas para testar
    moedas = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT", "NEARUSDT", "DOTUSDT", "FETUSDT", "SUIUSDT", "OPUSDT"]
    
    tester = MultiBacktester(moedas)
    tester.run_all()