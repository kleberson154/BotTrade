#!/usr/bin/env python3
"""
Download melhorado: historico de 90 dias de BTC em velas de 5 minutos
Estrategia: começar de uma data bem no passado e ir trazendo dados em lotes
"""
import sys
import os
import io
import datetime
import time
import pandas as pd
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from src.connection import get_http_session
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET")
IS_TESTNET = os.getenv("BYBIT_MODE", "testnet") == "testnet"
IS_DEMO = os.getenv("BYBIT_MODE", "testnet") == "demo"

def download_90_days():
    """Baixar ate 90 dias de dados"""
    
    session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
    symbol = "BTCUSDT"
    interval = "5"
    
    now = datetime.datetime.now(datetime.timezone.utc)
    start_90d_ago = now - datetime.timedelta(days=90)
    
    print("[*] Objetivo: Coletar 90 dias de dados BTC 5m")
    print("    Data inicio alvo: {}".format(start_90d_ago.strftime('%Y-%m-%d')))
    print("    Data fim alvo: {}".format(now.strftime('%Y-%m-%d')))
    print()
    
    all_candles = []
    current_time = now
    batch = 0
    max_batches = 3  # Limitar a 3 tentativas
    
    print("[*] Estrategia: Comecar de HOJE e ir para tras")
    print()
    
    while batch < max_batches:
        batch += 1
        start_ts = int(current_time.timestamp() * 1000)
        
        print("[Batch {}] Tempo inicio: {}".format(batch, current_time.strftime('%Y-%m-%d %H:%M')), end="", flush=True)
        
        try:
            resp = session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                start=start_ts,
                limit=1000
            )
            
            if resp['retCode'] != 0:
                print(" -> Erro API: {}".format(resp['retMsg']))
                break
            
            candles = resp['result']['list']
            if not candles:
                print(" -> Sem dados")
                break
            
            print(" -> {} velas".format(len(candles)), end="", flush=True)
            
            # Processar velas
            for candle in candles:
                timestamp = int(candle[0])
                all_candles.append({
                    'timestamp': timestamp,
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5])
                })
            
            # Proxima iteracao: ir para tras
            # A ultima vela eh a mais antiga, entao usamos seu timestamp
            oldest_ts = int(candles[-1][0])
            oldest_time = datetime.datetime.fromtimestamp(oldest_ts / 1000, tz=datetime.timezone.utc)
            current_time = oldest_time - datetime.timedelta(minutes=5)
            
            print(" -> Proxima: {}".format(current_time.strftime('%Y-%m-%d %H:%M')))
            time.sleep(0.3)
            
        except Exception as e:
            print(" -> Erro: {}".format(e))
            break
    
    print()
    print("[+] Total de velas coletadas: {}".format(len(all_candles)))
    
    if len(all_candles) > 0:
        # Converter para DataFrame
        df = pd.DataFrame(all_candles)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        inicio = df['timestamp'].min()
        fim = df['timestamp'].max()
        duracao = fim - inicio
        dias = duracao.days
        
        print()
        print("[*] Dados coletados:")
        print("    Primeiro candle: {}".format(inicio.strftime('%Y-%m-%d %H:%M:%S')))
        print("    Ultimo candle: {}".format(fim.strftime('%Y-%m-%d %H:%M:%S')))
        print("    Duracao: {} dias, {} horas".format(dias, duracao.seconds // 3600))
        print("    Open: ${:.2f}".format(df['open'].iloc[0]))
        print("    High: ${:.2f}".format(df['high'].max()))
        print("    Low: ${:.2f}".format(df['low'].min()))
        print("    Close: ${:.2f}".format(df['close'].iloc[-1]))
        
        # Salvar
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        
        csv_path = data_dir / "btc_5min_90d.csv"
        json_path = data_dir / "btc_5min_90d.json"
        
        df.to_csv(csv_path, index=False)
        df.to_json(json_path, orient='records', indent=2)
        
        print()
        print("[+] Arquivos salvos:")
        print("    CSV: {} ({:.2f} MB)".format(csv_path, csv_path.stat().st_size / 1024 / 1024))
        print("    JSON: {} ({:.2f} MB)".format(json_path, json_path.stat().st_size / 1024 / 1024))
        
        # Verificar se temos 90 dias
        if dias >= 89:
            print()
            print("[OK] SUCESSO: Dados de 90+ dias coletados!")
            return True
        else:
            print()
            print("[!] PARCIAL: Apenas {} dias coletados (esperado 90)".format(dias))
            return False
    
    return False

if __name__ == "__main__":
    print("="*60)
    print("DOWNLOAD 90 DIAS - BTC HISTORICAL DATA")
    print("="*60)
    print()
    
    success = download_90_days()
    
    if success:
        print()
        print("[OK] Pronto para backteste de 90 dias!")
    else:
        print()
        print("[!] Dados limitados - usando o que conseguiu")
