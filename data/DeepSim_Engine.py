import pandas as pd
import numpy as np
import sys
import os
import time
from pandas.errors import ParserError

# --- AJUSTE DE CAMINHO ---
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from src.strategy import TradingStrategy

class DeepSimulator:
    def __init__(self, symbol, csv_path, verbose=True):
        self.symbol = symbol
        self.verbose = verbose
        base_path_coins = os.path.join(os.getcwd(), 'data', 'coins')
        base_path_root = os.path.join(os.getcwd(), 'data')

        if os.path.isabs(csv_path):
            self.csv_full_path = csv_path
        else:
            candidate_coins = os.path.join(base_path_coins, csv_path)
            candidate_root = os.path.join(base_path_root, csv_path)
            if os.path.exists(candidate_coins):
                self.csv_full_path = candidate_coins
            else:
                self.csv_full_path = candidate_root
            
        if not os.path.exists(self.csv_full_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {self.csv_full_path}")

        usecols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        dtypes = {
            'open': 'float32',
            'high': 'float32',
            'low': 'float32',
            'close': 'float32',
            'volume': 'float32',
        }

        try:
            self.df = pd.read_csv(
                self.csv_full_path,
                usecols=usecols,
                dtype=dtypes,
                low_memory=False,
            )
        except (ParserError, MemoryError, ValueError):
            self.df = pd.read_csv(
                self.csv_full_path,
                usecols=usecols,
                dtype=dtypes,
                engine='python',
            )

        self.df['timestamp'] = pd.to_datetime(self.df['timestamp'], errors='coerce')
        self.df = self.df.dropna(subset=['timestamp', 'open', 'high', 'low', 'close', 'volume']).reset_index(drop=True)
        
        self.fee_rate = 0.0006 
        self.strat = TradingStrategy(symbol, notifier=None)
        self.trades = []
        self.max_drawdown = 0.0 # Inicializa para evitar o erro de atributo
        self.signal_check_interval = 3
        self.invert_signal = False

    def run(self):
        start_time = time.time()
        if self.verbose:
            print(f"Simulando {self.symbol}...")

        # Ajuste dinâmico de aquecimento
        available_15m = max(2, len(self.df) // 15)
        adaptive_period = min(200, max(30, available_15m - 1))
        self.strat.ema_15m_period = adaptive_period
        self.strat.min_15m_candles = adaptive_period

        # 1. Warmup
        target_warmup = self.strat.min_15m_candles * 15
        warmup = min(target_warmup, max(1, len(self.df) - 1))
        warmup_rows = self.df.iloc[:warmup].to_dict("records")
        
        for candle in warmup_rows:
            self.strat.add_new_candle("1m", candle)

        if self.verbose:
            print(f"🔄 Iniciando Simulação: {len(self.df)} velas...")

        ts_arr = self.df['timestamp'].to_numpy()
        open_arr = self.df['open'].to_numpy()
        high_arr = self.df['high'].to_numpy()
        low_arr = self.df['low'].to_numpy()
        close_arr = self.df['close'].to_numpy()
        vol_arr = self.df['volume'].to_numpy()

        # 2. Simulação
        m15_accumulator = []
        total_steps = len(self.df)
        for i in range(warmup, len(self.df)):
            if self.verbose and i % 5000 == 0:
                elapsed = time.time() - start_time
                print(f"   > Progresso: {i}/{total_steps} ({(i/total_steps):.1%}) | Tempo: {elapsed:.1f}s")
            row_open = open_arr[i]
            row_high = high_arr[i]
            row_low = low_arr[i]
            row_close = close_arr[i]
            row_volume = vol_arr[i]
            current_ts = pd.Timestamp(ts_arr[i])

            row = {
                'timestamp': current_ts,
                'open': row_open,
                'high': row_high,
                'low': row_low,
                'close': row_close,
                'volume': row_volume
            }
            
            self.strat.add_new_candle("1m", row)
            m15_accumulator.append(row)
            
            if len(m15_accumulator) == 15:
                m15_candle = {
                    'timestamp': m15_accumulator[0]['timestamp'],
                    'open': m15_accumulator[0]['open'],
                    'high': max(c['high'] for c in m15_accumulator),
                    'low': min(c['low'] for c in m15_accumulator),
                    'close': m15_accumulator[-1]['close'],
                    'volume': sum(c['volume'] for c in m15_accumulator)
                }
                self.strat.add_new_candle("15m", m15_candle)
                m15_accumulator = []

            if not self.strat.is_positioned:
                if i % self.signal_check_interval != 0:
                    continue
                signal, atr = self.strat.check_signal(current_time=current_ts)
                if self.invert_signal and signal in ["BUY", "SELL"]:
                    signal = "SELL" if signal == "BUY" else "BUY"
                if signal in ["BUY", "SELL"]:
                    entry_price = row_close * (1.0002 if signal == "BUY" else 0.9998)
                    atr_pct = atr / row_close if atr > 0 else 0.01
                    atr_mult_sl = getattr(self.strat, 'atr_multiplier_sl', 1.5)
                    atr_mult_tp = getattr(self.strat, 'atr_multiplier_tp', 4.0)
                    sl = entry_price * (1 - atr_pct * atr_mult_sl) if signal == "BUY" else entry_price * (1 + atr_pct * atr_mult_sl)
                    tp = entry_price * (1 + atr_pct * atr_mult_tp) if signal == "BUY" else entry_price * (1 - atr_pct * atr_mult_tp)

                    self.trades.append({
                        'entry_time': current_ts, 'side': signal, 'entry_price': entry_price,
                        'sl_price': sl, 'tp_price': tp, 'partial_executed': False
                    })
                    self.strat.is_positioned, self.strat.side = True, signal
                    self.strat.entry_price, self.strat.sl_price, self.strat.tp_price = entry_price, sl, tp
            else:
                res = self.strat.monitor_protection(row_close)
                if res == "PARTIAL_EXIT" and not self.trades[-1]['partial_executed']:
                    self.trades[-1]['partial_price'] = row_close
                    self.trades[-1]['partial_executed'] = True
                if res == "UPDATE_SL":
                    self.trades[-1]['sl_price'] = self.strat.sl_price

                exit_trigger, exit_price, exit_reason = False, 0, ""
                if self.strat.side == "BUY":
                    if row_high >= self.strat.tp_price:
                        exit_price, exit_reason, exit_trigger = self.strat.tp_price, "TP", True
                    elif row_low <= self.strat.sl_price:
                        exit_price, exit_reason, exit_trigger = self.strat.sl_price, "SL", True
                else:
                    if row_low <= self.strat.tp_price:
                        exit_price, exit_reason, exit_trigger = self.strat.tp_price, "TP", True
                    elif row_high >= self.strat.sl_price:
                        exit_price, exit_reason, exit_trigger = self.strat.sl_price, "SL", True

                if exit_trigger:
                    entry = self.strat.entry_price
                    if self.trades[-1]['partial_executed']:
                        p_price = self.trades[-1]['partial_price']
                        pnl_p = (p_price - entry)/entry if self.strat.side == "BUY" else (entry - p_price)/entry
                        pnl_f = (exit_price - entry)/entry if self.strat.side == "BUY" else (entry - exit_price)/entry
                        raw_pnl = (pnl_p * 0.5) + (pnl_f * 0.5)
                    else:
                        raw_pnl = (exit_price - entry)/entry if self.strat.side == "BUY" else (entry - exit_price)/entry
                    
                    self.trades[-1].update({
                        'exit_time': current_ts, 'exit_price': exit_price,
                        'exit_reason': exit_reason, 'net_pnl': raw_pnl - (self.fee_rate * 2)
                    })
                    self.strat.is_positioned = False
                    self.strat.side = None
                    self.strat.entry_price = 0
                    self.strat.sl_price = 0
                    self.strat.tp_price = 0
                    self.strat.be_activated = False
                    self.strat.partial_taken = False

        report = pd.DataFrame([t for t in self.trades if 'net_pnl' in t])
        
        # --- CÁLCULO DE DRAWDOWN ---
        if not report.empty:
            report['cum_pnl'] = report['net_pnl'].cumsum()
            report['peak'] = report['cum_pnl'].cummax()
            report['drawdown'] = report['cum_pnl'] - report['peak']
            self.max_drawdown = report['drawdown'].min()
            
            # Colunas para o save_report
            report['tp_exits'] = (report['exit_reason'] == 'TP').astype(int)
            report['sl_exits'] = (report['exit_reason'] == 'SL').astype(int)
        
        return report

# --- BLOCO DE EXECUÇÃO ---
if __name__ == "__main__":
    # Certifique-se que este arquivo existe na pasta data/coins para o teste individual
    try:
        tester = DeepSimulator("BTCUSDT", "data_BTCUSDT_90d.csv")
        results = tester.run()
        if not results.empty:
            print(f"PnL: {results['net_pnl'].sum():.2%}")
            print(f"Max Drawdown: {tester.max_drawdown:.2%}")
    except Exception as e:
        print(f"Erro no teste individual: {e}")