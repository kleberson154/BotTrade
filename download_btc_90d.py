#!/usr/bin/env python3
"""
Download histórico de 90 dias de BTC em velas de 5 minutos
"""
import sys
import os
import datetime
import time
import json
import pandas as pd
from pathlib import Path
import io

# Força encoding UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent))

from src.connection import get_http_session
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_MODE", "testnet") == "testnet"
IS_DEMO = os.getenv("BYBIT_MODE", "testnet") == "demo"

def download_historical_data():
    """Baixar 90 dias de dados de BTC em velas de 5 minutos"""
    
    session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
    symbol = "BTCUSDT"
    interval = "5"  # 5 minutos
    
    # Calcular datas
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=90)
    
    print("[*] Baixando dados históricos de", symbol)
    print("    Período:", start_date.strftime('%Y-%m-%d %H:%M'), "até", now.strftime('%Y-%m-%d %H:%M'))
    print("    Intervalo: 5m")
    print("    Timeframe: ~25.920 velas (90 dias * 24h * 12 velas/h)")
    print()
    
    all_candles = []
    current_start = int(start_date.timestamp() * 1000)
    limit = 1000  # Max per request
    
    request_count = 0
    while len(all_candles) < 26000:  # ~90 dias em 5m
        request_count += 1
        print("[Request {}] Baixando velas {}-{}...".format(request_count, len(all_candles)+1, len(all_candles)+limit), end=" ", flush=True)
        
        try:
            resp = session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                start=current_start,
                limit=limit
            )
            
            if resp['retCode'] != 0:
                print("\n[!] Erro API:", resp['retMsg'])
                break
            
            candles = resp['result']['list']
            if not candles:
                print("(nenhuma vela)")
                break
            
            # Bybit retorna em ordem crescente, cada item é [timestamp, open, high, low, close, volume, ...]
            for candle in candles:
                timestamp = int(candle[0])
                open_price = float(candle[1])
                high = float(candle[2])
                low = float(candle[3])
                close = float(candle[4])
                volume = float(candle[5])
                
                all_candles.append({
                    'timestamp': timestamp,
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume
                })
            
            print("[OK] ({} velas)".format(len(candles)))
            
            # Próxima request começa onde esta terminou
            last_timestamp = int(candles[-1][0])
            if last_timestamp == current_start:
                # Não progrediu, saír para evitar loop infinito
                print("[!] Sem progresso, parando...")
                break
            
            current_start = last_timestamp
            time.sleep(0.2)  # Rate limit
            
        except Exception as e:
            print("\n[!] Erro:", e)
            break
    
    print("\n[+] Total de velas baixadas:", len(all_candles))
    
    if not all_candles:
        print("[!] Nenhuma vela foi baixada!")
        return
    
    # Converter para DataFrame
    df = pd.DataFrame(all_candles)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    print("\n[*] Dados:")
    print("    Período:", df['timestamp'].min(), "a", df['timestamp'].max())
    print("    Duração:", (df['timestamp'].max() - df['timestamp'].min()))
    print("    Open: $", round(df['open'].iloc[0], 2))
    print("    High: $", round(df['high'].max(), 2))
    print("    Low: $", round(df['low'].min(), 2))
    print("    Close: $", round(df['close'].iloc[-1], 2))
    print("    Volume Total:", round(df['volume'].sum(), 2))
    
    # Salvar como CSV e JSON
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    csv_path = data_dir / "btc_5min_90d.csv"
    json_path = data_dir / "btc_5min_90d.json"
    
    df.to_csv(csv_path, index=False)
    df.to_json(json_path, orient='records', indent=2)
    
    print("\n[+] Arquivos salvos:")
    print("    CSV:", csv_path, "({:.1f} MB)".format(csv_path.stat().st_size / 1024 / 1024))
    print("    JSON:", json_path, "({:.1f} MB)".format(json_path.stat().st_size / 1024 / 1024))
    
    return df

if __name__ == "__main__":
    print("=" * 60)
    print("BTC HISTORICAL DATA DOWNLOADER - 90 DAYS")
    print("=" * 60)
    print()
    
    df = download_historical_data()
    
    if df is not None:
        print("\n[+] Download concluido com sucesso!")
        print("    {} velas de 5 minutos".format(len(df)))
        print("    Pronto para backteste")
