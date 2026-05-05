#!/usr/bin/env python3
"""
Download de 90 dias partindo de data ANTIGA e trazendo para frente
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

def download_90_days_from_past():
    """Baixar 90 dias comecando de uma data no passado"""
    
    session = get_http_session(API_KEY, API_SECRET, testnet=IS_TESTNET, demo=IS_DEMO)
    symbol = "BTCUSDT"
    interval = "5"
    
    # Começar 100 dias no passado (para garantir 90)
    start_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=100)
    end_date = datetime.datetime.now(datetime.timezone.utc)
    
    print("[*] Objetivo: Coletar 90 dias de dados")
    print("    Data inicio: {}".format(start_date.strftime('%Y-%m-%d')))
    print("    Data fim: {}".format(end_date.strftime('%Y-%m-%d')))
    print()
    
    all_candles = []
    current_time = start_date
    batch = 0
    max_batches = 35  # Max 35 batches para ~100 dias (3.47 dias/batch)
    
    print("[*] Estrategia: Comecar do PASSADO e ir para frente")
    print()
    
    while batch < max_batches and current_time < end_date:
        batch += 1
        start_ts = int(current_time.timestamp() * 1000)
        
        print("[Batch {:2d}] Tempo: {} ".format(batch, current_time.strftime('%Y-%m-%d %H:%M')), end="", flush=True)
        
        try:
            resp = session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                start=start_ts,
                limit=1000
            )
            
            if resp['retCode'] != 0:
                print("-> Erro: {}".format(resp['retMsg']))
                time.sleep(1)
                continue
            
            candles = resp['result']['list']
            if not candles:
                print("-> Sem dados")
                break
            
            print("-> {} velas ".format(len(candles)), end="", flush=True)
            
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
            
            # Proximo lote: avancar a partir do candle mais recente (que na Bybit e o indice 0 do retorno DESC)
            last_ts = int(candles[0][0])
            current_time = datetime.datetime.fromtimestamp(last_ts / 1000, tz=datetime.timezone.utc) + datetime.timedelta(minutes=5)
            
            print("(Total: {})".format(len(all_candles)))
            time.sleep(0.2)
            
        except Exception as e:
            print("-> Erro: {}".format(str(e)[:50]))
            time.sleep(1)
    
    print()
    print("[+] Total de velas coletadas: {}".format(len(all_candles)))
    
    if len(all_candles) > 0:
        # Converter para DataFrame e remover duplicatas
        df = pd.DataFrame(all_candles)
        df = df.drop_duplicates(subset=['timestamp'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        inicio = df['timestamp'].min()
        fim = df['timestamp'].max()
        duracao = fim - inicio
        dias = duracao.days
        
        print()
        print("[*] Dados coletados (apos remocao de duplicatas):")
        print("    Primeiro candle: {}".format(inicio.strftime('%Y-%m-%d %H:%M:%S')))
        print("    Ultimo candle: {}".format(fim.strftime('%Y-%m-%d %H:%M:%S')))
        print("    Duracao: {} dias, {} horas, {} minutos".format(
            dias, 
            (duracao.seconds // 3600),
            (duracao.seconds // 60) % 60
        ))
        print("    Total de velas: {}".format(len(df)))
        print("    Velas por dia (media): {:.0f}".format(len(df) / (dias + 1)))
        print()
        print("    Open (primeiro): ${:.2f}".format(df['open'].iloc[0]))
        print("    High: ${:.2f}".format(df['high'].max()))
        print("    Low: ${:.2f}".format(df['low'].min()))
        print("    Close (ultimo): ${:.2f}".format(df['close'].iloc[-1]))
        
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
        if dias >= 88:
            print()
            print("[OK] SUCESSO: {} dias coletados (alvo: 90+)".format(dias))
            return True
        else:
            print()
            print("[!] PARCIAL: {} dias coletados (alvo: 90)".format(dias))
            return False
    
    return False

if __name__ == "__main__":
    print("="*60)
    print("DOWNLOAD 90 DIAS - VERSAO 2 (PASSADO PARA FRENTE)")
    print("="*60)
    print()
    
    success = download_90_days_from_past()
    
    if success:
        print()
        print("[OK] Pronto para backteste de 90 dias!")
    else:
        print()
        print("[!] Dados parciais coletados - executando backteste")
