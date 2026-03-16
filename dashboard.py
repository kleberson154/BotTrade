import re
import os

def parse_logs():
    log_path = 'logs/trading_history.log'
    if not os.path.exists(log_path):
        print("Arquivo de log ainda não criado.")
        return

    trades = 0
    total_estimated_profit = 0.0
    
    # Regex para capturar os dados do log
    # Exemplo esperado: ✅ ORDEM EXECUTADA: Buy 0.001 BTCUSDT em 60000. TP: 61500, SL: 59400
    with open(log_path, 'r') as f:
        for line in f:
            if "ORDEM EXECUTADA" in line:
                trades += 1
                # Aqui você pode expandir para ler o fechamento da ordem via API
                # Por agora, vamos listar as execuções
                print(line.strip())

    print("\n" + "="*30)
    print(f"📊 RESUMO DO BOT")
    print(f"Trades disparados: {trades}")
    print(f"Capital Inicial: R$ 100,00")
    print("Nota: Para lucro real, verifique o painel 'Demo Trading' na Bybit.")
    print("="*30)

if __name__ == "__main__":
    parse_logs()