#!/usr/bin/env python
"""
Downloader robusto para 90 dias com rate limit handling.
Trata erro 10006 (rate limit) com exponential backoff.
"""
import os, sys, time
import pandas as pd
import requests
from pybit.unified_trading import HTTP

sys.path.insert(0, os.path.dirname(__file__))

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT", "XRPUSDT", 
           "ADAUSDT", "NEARUSDT", "DOTUSDT", "SUIUSDT", "OPUSDT"]
DIAS = 90
INTERVALO = 1
EXPECTED_CANDLES = DIAS * 24 * 60

session = HTTP(testnet=False)

def download_with_retry(symbol, start_time, now, max_retries=5):
    """Baixa com retry exponencial para rate limit e falhas transitórias de rede."""
    all_candles = []
    retry_count = 0
    seen_timestamps = set()
    
    while start_time < now:
        try:
            resp = session.get_kline(
                category="linear",
                symbol=symbol,
                interval=INTERVALO,
                start=start_time,
                limit=1000
            )
            
            data = resp['result']['list']
            if not data:
                break

            before_count = len(all_candles)
            for row in data:
                ts = int(row[0])
                if ts not in seen_timestamps:
                    seen_timestamps.add(ts)
                    all_candles.append(row)

            max_ts = max(int(row[0]) for row in data)
            start_time = max_ts + INTERVALO * 60 * 1000
            
            progress = len(all_candles)
            eta_date = pd.to_datetime(start_time, unit='ms').strftime('%Y-%m-%d %H:%M')
            added = progress - before_count
            print(f"  {symbol}: {progress:6d} candles (+{added}) (~{eta_date})")

            if progress >= EXPECTED_CANDLES + 1000:
                break
            
            time.sleep(0.05)
            retry_count = 0  # Reset retry counter on success
            
            if start_time >= now - 60000:
                break
                
        except Exception as e:
            error_msg = str(e)
            network_error = (
                "name resolution" in error_msg.lower() or
                "failed to resolve" in error_msg.lower() or
                "read timed out" in error_msg.lower() or
                "max retries exceeded" in error_msg.lower() or
                isinstance(e, requests.exceptions.RequestException)
            )
            if "10006" in error_msg or "rate limit" in error_msg.lower() or network_error:
                retry_count += 1
                if retry_count > max_retries:
                    print(f"    [SKIP] {symbol} excedeu tentativas ({max_retries})")
                    break
                wait_time = min(2 ** retry_count, 90)
                print(f"    [RETRY {retry_count}/{max_retries}] erro transitório - esperando {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"    [ERRO] {symbol}: {e}")
                break
    
    return all_candles

def save_csv(symbol, candles):
    """Converte e salva candles em CSV."""
    if not candles:
        print(f"  [VAZIO] Nenhum candle para {symbol}")
        return False
    
    df = pd.DataFrame(candles, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
    ])
    
    cols = ['open', 'high', 'low', 'close', 'volume']
    df[cols] = df[cols].apply(pd.to_numeric)
    df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    csv_path = f"data_{symbol}_{DIAS}d.csv"
    df.to_csv(csv_path, index=False)
    print(f"  [OK] {csv_path} ({len(df)} candles, {df['timestamp'].min()} até {df['timestamp'].max()})")
    return True

def has_complete_csv(symbol):
    """Retorna True se já existe CSV com volume suficiente para 90 dias."""
    csv_path = f"data_{symbol}_{DIAS}d.csv"
    if not os.path.exists(csv_path):
        return False
    try:
        df = pd.read_csv(csv_path, usecols=['timestamp'])
        ts = pd.to_datetime(df['timestamp'], errors='coerce').dropna()
        if ts.empty:
            return False
        unique_count = ts.nunique()
        covered_minutes = (ts.max() - ts.min()).total_seconds() / 60

        count_ok = (EXPECTED_CANDLES * 0.95) <= unique_count <= (EXPECTED_CANDLES * 1.2)
        coverage_ok = covered_minutes >= (EXPECTED_CANDLES * 0.95)

        if count_ok and coverage_ok:
            print(f"  [SKIP] {csv_path} já completo ({unique_count} candles únicos)")
            return True
        print(f"  [REBUILD] {csv_path} incompleto/corrompido (unique={unique_count}, cobertura={covered_minutes:.0f}m)")
    except Exception:
        return False
    return False

print(f"Baixando {DIAS} dias para {len(SYMBOLS)} moedas...\n")

now = int(time.time() * 1000)
start_base = now - (DIAS * 24 * 60 * 60 * 1000)

for symbol in SYMBOLS:
    print(f"Processando {symbol}...")
    if has_complete_csv(symbol):
        print()
        continue
    candles = download_with_retry(symbol, start_base, now)
    save_csv(symbol, candles)
    print()

print("Download concluido!")
