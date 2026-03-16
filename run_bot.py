import subprocess
import time
import sys

def start_bot():
    filename = "main.py"
    while True:
        print(f"🚀 Iniciando o bot {filename}...")
        # Inicia o processo do main.py
        process = subprocess.Popen([sys.executable, filename])
        
        # Espera o processo terminar (se ele crashar)
        process.wait()
        
        if process.returncode != 0:
            print("⚠️ Bot travou ou caiu. Reiniciando em 10 segundos...")
            time.sleep(10)
        else:
            print("Bot finalizado manualmente.")
            break

if __name__ == "__main__":
    start_bot()