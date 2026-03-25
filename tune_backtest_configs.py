#!/usr/bin/env python
import os
import json
import random
import pandas as pd
from copy import deepcopy

from data.DeepSim_Engine import DeepSimulator

BASE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'coins')

DEFAULT_CONFIG = {
    "atr_mult": 1.8,
    "min_pnl_be": 0.007,
    "dist_respiro": 0.015,
    "min_adx": 25,
    "signal_interval": 3,
}

INITIAL_CONFIGS = {
    "BTCUSDT":  {"atr_mult": 1.6, "min_pnl_be": 0.005, "dist_respiro": 0.012, "min_adx": 25, "signal_interval": 3},
    "ETHUSDT":  {"atr_mult": 1.7, "min_pnl_be": 0.006, "dist_respiro": 0.015, "min_adx": 25, "signal_interval": 3},
    "SOLUSDT":  {"atr_mult": 2.2, "min_pnl_be": 0.005, "dist_respiro": 0.018, "min_adx": 32, "signal_interval": 4},
    "AVAXUSDT": {"atr_mult": 2.5, "min_pnl_be": 0.005, "dist_respiro": 0.022, "min_adx": 35, "signal_interval": 4},
    "XRPUSDT":  {"atr_mult": 1.8, "min_pnl_be": 0.004, "dist_respiro": 0.010, "min_adx": 28, "signal_interval": 3},
}

ATR_OPTS = [1.2, 1.5, 1.8, 2.0, 2.2, 2.5]
BE_OPTS = [0.0035, 0.0045, 0.0055, 0.0065, 0.0075]
RESP_OPTS = [0.008, 0.010, 0.012, 0.015, 0.018, 0.022]
ADX_OPTS = [20, 22, 25, 28, 30, 32, 35]
INTERVAL_OPTS = [3, 4, 5]


def list_symbols():
    symbols = []
    for name in os.listdir(BASE_DIR):
        if name.startswith('data_') and name.endswith('_90d.csv'):
            sym = name.replace('data_', '').replace('_90d.csv', '')
            symbols.append(sym)
    symbols.sort()
    return symbols


def find_file(symbol):
    return f"data_{symbol}_90d.csv"


def apply_config(tester, conf):
    tester.strat.atr_multiplier_sl = conf['atr_mult']
    tester.strat.min_pnl_be = conf['min_pnl_be']
    tester.strat.distancia_respiro = conf['dist_respiro']
    tester.strat.min_adx = conf['min_adx']
    tester.signal_check_interval = conf.get('signal_interval', 3)


def eval_symbol(symbol, conf, use_subset=True):
    csv_path = find_file(symbol)

    if use_subset:
        full_path = os.path.join(BASE_DIR, csv_path)
        tmp_path = os.path.join(BASE_DIR, f"_tune_{symbol}.csv")
        df = pd.read_csv(full_path)
        df.tail(min(10000, len(df))).to_csv(tmp_path, index=False)
        run_path = f"_tune_{symbol}.csv"
    else:
        run_path = csv_path

    tester = DeepSimulator(symbol, run_path)
    apply_config(tester, conf)
    rep = tester.run()

    if rep.empty:
        return {
            'trades': 0,
            'wr': 0.0,
            'pnl_total': -999.0,
            'tp': 0,
            'sl': 0,
        }

    exit_reason = rep['exit_reason'] if 'exit_reason' in rep.columns else pd.Series('', index=rep.index)
    net_pnl = rep['net_pnl'] if 'net_pnl' in rep.columns else pd.Series(0.0, index=rep.index)
    tp_exits = int(((exit_reason == 'TP') | ((exit_reason == 'SL') & (net_pnl > 0))).sum())
    sl_exits = int(((exit_reason == 'SL') & (net_pnl <= 0)).sum())

    return {
        'trades': int(len(rep)),
        'wr': float((rep['net_pnl'] > 0).mean()),
        'pnl_total': float(rep['net_pnl'].sum()),
        'tp': tp_exits,
        'sl': sl_exits,
    }


def random_candidates(base_conf, n=4, seed=42):
    rnd = random.Random(seed)
    cands = [deepcopy(base_conf)]
    seen = {json.dumps(base_conf, sort_keys=True)}
    while len(cands) < n:
        c = {
            'atr_mult': rnd.choice(ATR_OPTS),
            'min_pnl_be': rnd.choice(BE_OPTS),
            'dist_respiro': rnd.choice(RESP_OPTS),
            'min_adx': rnd.choice(ADX_OPTS),
            'signal_interval': rnd.choice(INTERVAL_OPTS),
        }
        key = json.dumps(c, sort_keys=True)
        if key not in seen:
            seen.add(key)
            cands.append(c)
    return cands


def main():
    symbols = list_symbols()
    print(f"Symbols detectados: {symbols}")

    tuned = {}
    quick_results = []

    for idx, symbol in enumerate(symbols, 1):
        base = deepcopy(INITIAL_CONFIGS.get(symbol, DEFAULT_CONFIG))
        candidates = random_candidates(base, n=4, seed=100 + idx)

        best_conf = None
        best_eval = None

        print(f"\n[{idx}/{len(symbols)}] Tuning {symbol} ({len(candidates)} candidatos)...")
        for ci, conf in enumerate(candidates, 1):
            ev = eval_symbol(symbol, conf, use_subset=True)
            print(f"  - cand {ci}: pnl={ev['pnl_total']:+.3%} wr={ev['wr']:.1%} t={ev['trades']} cfg={conf}")

            if best_eval is None:
                best_conf, best_eval = conf, ev
                continue

            if (ev['pnl_total'], ev['wr']) > (best_eval['pnl_total'], best_eval['wr']):
                best_conf, best_eval = conf, ev

        tuned[symbol] = best_conf
        quick_results.append({
            'symbol': symbol,
            'pnl_total_subset': best_eval['pnl_total'],
            'wr_subset': best_eval['wr'],
            'trades_subset': best_eval['trades'],
            **best_conf,
        })

    with open('tuned_configs.json', 'w', encoding='utf-8') as f:
        json.dump(tuned, f, indent=2, ensure_ascii=False)

    pd.DataFrame(quick_results).to_csv('tuned_configs_subset_results.csv', index=False)

    positives = (pd.DataFrame(quick_results)['pnl_total_subset'] > 0).sum()
    print(f"\nSubset (10k) com PnL positivo: {positives}/{len(quick_results)}")
    print("Arquivos gerados: tuned_configs.json, tuned_configs_subset_results.csv")


if __name__ == '__main__':
    main()
