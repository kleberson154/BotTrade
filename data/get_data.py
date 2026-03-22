from pybit.unified_trading import HTTP
import pandas as pd
import time

# Configuração da Sessão (Pode usar a conta real ou testnet, apenas para leitura)
session = HTTP(testnet=False)

def get_history(symbol, interval, limit=1000):
    """Busca dados históricos da Bybit e formata em DataFrame"""
    try:
        kline = session.get_kline(
            category="linear",
            symbol=symbol,
            interval=interval,
            limit=limit
        )
        
        data = kline['result']['list']
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
        ])
        
        # Conversão de tipos
        cols = ['open', 'high', 'low', 'close', 'volume']
        df[cols] = df[cols].apply(pd.to_numeric)
        df['timestamp'] = pd.to_datetime(pd.to_numeric(df['timestamp']), unit='ms')
        
        # Ordenar (Bybit manda do mais novo para o mais antigo)
        df = df.sort_values('timestamp').set_index('timestamp')
        return df
    except Exception as e:
        print(f"❌ Erro ao baixar {symbol} ({interval}m): {e}")
        return None

# --- LISTA DE MOEDAS PARA MONITORAR ---
moedas = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "AVAXUSDT", "XRPUSDT", "ADAUSDT", "NEARUSDT", "DOTUSDT", "FETUSDT", "SUIUSDT", "OPUSDT"]

print(f"📡 Iniciando coleta de dados para {len(moedas)} ativos...")

for symbol in moedas:
    print(f"⬇️ Baixando {symbol}...")
    
    # Baixa 1 minuto
    df_1m = get_history(symbol, 1)
    if df_1m is not None:
        df_1m.to_csv(f"{symbol.lower()}_1m.csv")
        
    # Baixa 15 minutos (para os filtros de tendência)
    df_15m = get_history(symbol, 15)
    if df_15m is not None:
        df_15m.to_csv(f"{symbol.lower()}_15m.csv")
        
    # Pequena pausa para evitar bloqueio de IP (Rate Limit)
    time.sleep(0.2)

print("\n✅ Coleta concluída! Todos os arquivos CSV estão na pasta 'data'.")