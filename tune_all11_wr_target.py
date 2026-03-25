#!/usr/bin/env python
import os
import sys
import json
import pandas as pd

ROOT = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT, 'data')
SRC_DIR = os.path.join(ROOT, 'src')
sys.path.insert(0, DATA_DIR)
sys.path.insert(0, SRC_DIR)

from data.DeepSim_Engine import DeepSimulator
from backtest_pipeline import find_symbol_file

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "XRPUSDT",
    "ADAUSDT", "NEARUSDT", "DOTUSDT", "LINKUSDT", "SUIUSDT", "OPUSDT"
]

CANDIDATES = [
    {
        'name': 'base',
        'atr_mult': 1.8, 'min_pnl_be': 0.005, 'dist_respiro': 0.015, 'min_adx': 28,
        'signal_interval': 5, 'invert_signal': False, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0015,
        'allow_long': True, 'allow_short': True,
    },
    {
        'name': 'strict_trend',
        'atr_mult': 2.0, 'min_pnl_be': 0.005, 'dist_respiro': 0.018, 'min_adx': 32,
        'signal_interval': 6, 'invert_signal': False, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0025,
        'allow_long': True, 'allow_short': True,
    },
    {
        'name': 'strict_long_only',
        'atr_mult': 2.0, 'min_pnl_be': 0.005, 'dist_respiro': 0.018, 'min_adx': 32,
        'signal_interval': 6, 'invert_signal': False, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0025,
        'allow_long': True, 'allow_short': False,
    },
    {
        'name': 'invert_regime',
        'atr_mult': 1.8, 'min_pnl_be': 0.005, 'dist_respiro': 0.015, 'min_adx': 28,
        'signal_interval': 6, 'invert_signal': True, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0020,
        'allow_long': True, 'allow_short': True,
    },
    {
        'name': 'invert_regime_long_only',
        'atr_mult': 1.8, 'min_pnl_be': 0.005, 'dist_respiro': 0.015, 'min_adx': 30,
        'signal_interval': 6, 'invert_signal': True, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0020,
        'allow_long': True, 'allow_short': False,
    },
    {
        'name': 'aggressive_but_filtered',
        'atr_mult': 1.6, 'min_pnl_be': 0.0045, 'dist_respiro': 0.012, 'min_adx': 24,
        'signal_interval': 4, 'invert_signal': False, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0015,
        'allow_long': True, 'allow_short': True,
    },
    {
        'name': 'aggressive_invert',
        'atr_mult': 1.6, 'min_pnl_be': 0.0045, 'dist_respiro': 0.012, 'min_adx': 24,
        'signal_interval': 4, 'invert_signal': True, 'use_regime_filter': True,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0015,
        'allow_long': True, 'allow_short': True,
    },
    {
        'name': 'conservative_no_regime',
        'atr_mult': 2.2, 'min_pnl_be': 0.005, 'dist_respiro': 0.022, 'min_adx': 34,
        'signal_interval': 6, 'invert_signal': False, 'use_regime_filter': False,
        'regime_ema_fast': 50, 'regime_ema_slow': 200, 'regime_min_gap': 0.0015,
        'allow_long': True, 'allow_short': True,
    },
]


def apply_conf(tester, conf):
    strat = tester.strat
    strat.atr_multiplier_sl = conf['atr_mult']
    strat.min_pnl_be = conf['min_pnl_be']
    strat.distancia_respiro = conf['dist_respiro']
    strat.min_adx = conf['min_adx']
    strat.use_regime_filter = conf['use_regime_filter']
    strat.regime_ema_fast = conf['regime_ema_fast']
    strat.regime_ema_slow = conf['regime_ema_slow']
    strat.regime_min_gap = conf['regime_min_gap']
    strat.allow_long = conf['allow_long']
    strat.allow_short = conf['allow_short']

    tester.signal_check_interval = conf['signal_interval']
    tester.invert_signal = conf['invert_signal']


def evaluate(symbol, csv_name, conf):
    tester = DeepSimulator(symbol, csv_name, verbose=False)
    apply_conf(tester, conf)
    trades = tester.run()

    if trades.empty:
        return {'pnl': -1.0, 'wr': 0.0, 'trades': 0}

    pnl = float(trades['net_pnl'].sum())
    wr = float((trades['net_pnl'] > 0).mean())
    n = int(len(trades))
    return {'pnl': pnl, 'wr': wr, 'trades': n}


def score_result(res):
    pnl = res['pnl']
    wr = res['wr']
    trades = res['trades']

    wr_target = 0.45
    wr_distance = abs(wr - wr_target)
    wr_in_range = 1.0 if 0.40 <= wr <= 0.50 else 0.0

    score = 0.0
    score += pnl * 1.8
    score -= wr_distance * 0.9
    score += wr_in_range * 0.25

    if pnl <= 0:
        score -= 0.60
    if trades < 8:
        score -= 0.15

    return score


def pick_best(symbol):
    csv_name = find_symbol_file(symbol)
    if not csv_name:
        return None

    best = None
    all_rows = []

    for conf in CANDIDATES:
        res = evaluate(symbol, csv_name, conf)
        scr = score_result(res)

        row = {
            'symbol': symbol,
            'candidate': conf['name'],
            'score': scr,
            'pnl': res['pnl'],
            'wr': res['wr'],
            'trades': res['trades'],
            **conf,
        }
        all_rows.append(row)

        if best is None or row['score'] > best['score']:
            best = row

    return best, all_rows


def main():
    chosen = {}
    summary = []

    for symbol in SYMBOLS:
        out = pick_best(symbol)
        if out is None:
            print(f"{symbol}: arquivo não encontrado")
            continue

        best, rows = out
        summary.extend(rows)

        chosen[symbol] = {
            'atr_mult': best['atr_mult'],
            'min_pnl_be': best['min_pnl_be'],
            'dist_respiro': best['dist_respiro'],
            'min_adx': best['min_adx'],
            'signal_interval': best['signal_interval'],
            'invert_signal': best['invert_signal'],
            'use_regime_filter': best['use_regime_filter'],
            'regime_ema_fast': best['regime_ema_fast'],
            'regime_ema_slow': best['regime_ema_slow'],
            'regime_min_gap': best['regime_min_gap'],
            'allow_long': best['allow_long'],
            'allow_short': best['allow_short'],
        }

        print(f"{symbol}: best={best['candidate']} pnl={best['pnl']:+.2%} wr={best['wr']:.1%} trades={best['trades']}")

    with open(os.path.join(ROOT, 'tuned_all11_wr_target.json'), 'w', encoding='utf-8') as f:
        json.dump(chosen, f, indent=2, ensure_ascii=False)

    pd.DataFrame(summary).to_csv(os.path.join(ROOT, 'tuned_all11_wr_target_summary.csv'), index=False)

    print("\nArquivos gerados:")
    print("- tuned_all11_wr_target.json")
    print("- tuned_all11_wr_target_summary.csv")


if __name__ == '__main__':
    main()
