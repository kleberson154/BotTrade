#!/usr/bin/env python
"""Pipeline de backtest em passada única por moeda com risco dinâmico."""
import os
import sys
import pandas as pd
from datetime import datetime

data_dir = os.path.join(os.path.dirname(__file__), 'data')
src_dir = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, data_dir)
sys.path.insert(0, src_dir)

from data.DeepSim_Engine import DeepSimulator

BASE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'coins')
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT",  "AVAXUSDT", "XRPUSDT"
    ,"ADAUSDT", "NEARUSDT", "DOTUSDT", "LINKUSDT", "SUIUSDT", "OPUSDT"
]

DEFAULT_CONFIG = {
    "atr_mult": 2.0,
    "min_pnl_be": 0.005,
    "dist_respiro": 0.018,
    "min_adx": 30,
    "signal_interval": 5,
    "invert_signal": False,
    "use_regime_filter": False,
    "regime_ema_fast": 50,
    "regime_ema_slow": 200,
    "regime_min_gap": 0.0015,
    "allow_long": True,
    "allow_short": True,
}
COIN_CONFIGS = {
    "BTCUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": True,
    },
    "ETHUSDT":  {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 30,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": False,
    },
    "SOLUSDT": {
        "atr_mult": 2.2,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.022,
        "min_adx": 34,
        "signal_interval": 6,
        "invert_signal": False,
        "use_regime_filter": False,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.0015,
        "allow_long": True,
        "allow_short": True,
    },
    "AVAXUSDT": {
        "atr_mult": 1.6,
        "min_pnl_be": 0.0045,
        "dist_respiro": 0.012,
        "min_adx": 24,
        "signal_interval": 4,
        "invert_signal": False,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.0015,
        "allow_long": True,
        "allow_short": True,
    },
    "XRPUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": True,
    },

    "ADAUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 5,
        "invert_signal": False,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.0015,
        "allow_long": True,
        "allow_short": True,
    },
    "NEARUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": True,
    },
    "DOTUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": True,
    },
    "LINKUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 30,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": False,
    },
    "SUIUSDT": {
        "atr_mult": 1.8,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.015,
        "min_adx": 28,
        "signal_interval": 6,
        "invert_signal": True,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.002,
        "allow_long": True,
        "allow_short": True,
    },
    "OPUSDT": {
        "atr_mult": 2.0,
        "min_pnl_be": 0.005,
        "dist_respiro": 0.018,
        "min_adx": 32,
        "signal_interval": 6,
        "invert_signal": False,
        "use_regime_filter": True,
        "regime_ema_fast": 50,
        "regime_ema_slow": 200,
        "regime_min_gap": 0.0025,
        "allow_long": True,
        "allow_short": False,
    },
}


def find_symbol_file(symbol):
    for name in os.listdir(BASE_DIR):
        if symbol in name and name.endswith('.csv'):
            return name
    return None


def check_all_data_ready():
    if not os.path.exists(BASE_DIR):
        print(f"⚠️ Erro: Pasta não encontrada em {BASE_DIR}")
        return False, SYMBOLS

    missing = []
    for symbol in SYMBOLS:
        if find_symbol_file(symbol) is None:
            missing.append(symbol)
    return len(missing) == 0, missing


def apply_config_to_strategy(strat, conf):
    strat.atr_multiplier_sl = conf['atr_mult']
    strat.min_pnl_be = conf['min_pnl_be']
    strat.distancia_respiro = conf['dist_respiro']
    strat.min_adx = conf['min_adx']
    strat.use_regime_filter = conf.get('use_regime_filter', False)
    strat.regime_ema_fast = conf.get('regime_ema_fast', 50)
    strat.regime_ema_slow = conf.get('regime_ema_slow', 200)
    strat.regime_min_gap = conf.get('regime_min_gap', 0.0015)
    strat.allow_long = conf.get('allow_long', True)
    strat.allow_short = conf.get('allow_short', True)


def run_backtest_single_pass(label):
    moedas = SYMBOLS
    results = []

    print(f"\n{'='*60}")
    print(f"INICIANDO BACKTEST [{label}] EM {len(moedas)} MOEDAS")
    print(f"Pasta de origem: {BASE_DIR}")
    print(f"{'='*60}\n")

    for i, symbol in enumerate(moedas, 1):
        target_file = find_symbol_file(symbol)
        if not target_file:
            print(f"[{i:2d}/{len(moedas)}] {symbol:11s}: ⚠️ Arquivo não encontrado")
            continue

        try:
            tester = DeepSimulator(symbol, target_file)
            conf = COIN_CONFIGS.get(symbol, DEFAULT_CONFIG)
            apply_config_to_strategy(tester.strat, conf)
            tester.signal_check_interval = conf.get('signal_interval', DEFAULT_CONFIG.get('signal_interval', 5))
            tester.invert_signal = conf.get('invert_signal', DEFAULT_CONFIG.get('invert_signal', False))

            df_trades = tester.run()
            if df_trades.empty:
                print(f"[{i:2d}/{len(moedas)}] {symbol:11s}: [NO TRADES]")
                continue

            exit_reason = df_trades['exit_reason'] if 'exit_reason' in df_trades.columns else pd.Series('', index=df_trades.index)
            net_pnl = df_trades['net_pnl'] if 'net_pnl' in df_trades.columns else pd.Series(0.0, index=df_trades.index)
            tp_exits = ((exit_reason == 'TP') | ((exit_reason == 'SL') & (net_pnl > 0))).sum()
            sl_exits = ((exit_reason == 'SL') & (net_pnl <= 0)).sum()

            resumo = {
                'symbol': symbol,
                'trades': len(df_trades),
                'wr': (df_trades['net_pnl'] > 0).mean(),
                'pnl_total': df_trades['net_pnl'].sum(),
                'pnl_avg': df_trades['net_pnl'].mean(),
                'pnl_best': df_trades['net_pnl'].max(),
                'pnl_worst': df_trades['net_pnl'].min(),
                'tp_exits': int(tp_exits),
                'sl_exits': int(sl_exits),
                'wins': (df_trades['net_pnl'] > 0.0005).sum(),
                'protected': (df_trades['net_pnl'].between(-0.0005, 0.0005)).sum(),
                'losses': (df_trades['net_pnl'] < -0.0005).sum()
            }
            results.append(resumo)

            print(
                f"[{i:2d}/{len(moedas)}] {symbol:11s}: "
                f"T: {resumo['trades']:3d} | WR:{resumo['wr']:5.1%} | "
                f"PnL: {resumo['pnl_total']:+6.2%} | "
                f"✅W:{resumo['wins']} 🛡️P:{resumo['protected']} ❌L:{resumo['losses']}"
            )
        except Exception as e:
            print(f"❌ Erro ao processar {symbol}: {e}")

    return results


def save_report(results, report_csv_path, summary_txt_path, title="BACKTEST SUMMARY - 90 DIAS x 12 MOEDAS"):
    if not results:
        print("Sem resultados para salvar.")
        return pd.DataFrame()

    df = pd.DataFrame(results)
    cols = ['symbol', 'trades', 'wr', 'pnl_total', 'pnl_avg', 'pnl_best', 'pnl_worst', 'tp_exits', 'sl_exits']
    df[cols].to_csv(report_csv_path, index=False)

    with open(summary_txt_path, 'w', encoding='utf-8') as f:
        f.write(f"{title}\n")
        f.write("=" * 60 + "\n")
        f.write(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("RESULTADOS AGREGADOS:\n")
        f.write(f"  Moedas testadas: {len(df)}\n")
        f.write(f"  Total de trades: {int(df['trades'].sum())}\n")
        f.write(f"  Taxa média de vitória: {df['wr'].mean():.2%}\n")
        f.write(f"  PnL total: {df['pnl_total'].sum():+.3%}\n")
        f.write(f"  PnL médio por trade: {df['pnl_avg'].mean():+.3%}\n")
        f.write(f"  Melhor trade: {df['pnl_best'].max():+.3%}\n")
        f.write(f"  Pior trade: {df['pnl_worst'].min():+.3%}\n")
        f.write(f"  Saídas TP: {int(df['tp_exits'].sum())} | Saídas SL: {int(df['sl_exits'].sum())}\n\n")

        f.write("DETALHES POR MOEDA:\n")
        f.write("-" * 60 + "\n")
        for symbol in SYMBOLS:
            row = df[df['symbol'] == symbol]
            if row.empty:
                continue
            row = row.iloc[0]
            f.write(
                f"{symbol:<10s} | {int(row['trades']):3d}T | {row['wr']:4.1%}WR | "
                f"{row['pnl_total']:+7.3%} | TP:{int(row['tp_exits']):2d} SL:{int(row['sl_exits']):2d}\n"
            )

    return df


def run_full_backtest():
    ready, missing = check_all_data_ready()
    if not ready:
        print(f"Aguardando CSVs: {missing}")
        return

    results = run_backtest_single_pass("RISCO DINÂMICO")
    save_report(
        results,
        report_csv_path='backtest_report_90d.csv',
        summary_txt_path='backtest_summary_90d.txt',
        title='BACKTEST SUMMARY - 90 DIAS x 12 MOEDAS'
    )
    print("\n✅ Relatórios salvos: backtest_report_90d.csv e backtest_summary_90d.txt")


if __name__ == "__main__":
    run_full_backtest()
