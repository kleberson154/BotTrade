import logging
import os
import sys
import io

def setup_logger():
    # 1. Cria a pasta logs se não existir
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # 2. Força o console do Windows a aceitar UTF-8 (Emojis)
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    logger = logging.getLogger("BybitBot")
    logger.setLevel(logging.INFO)
    
    # Evita duplicar logs se a função for chamada mais de uma vez
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # Handler para o arquivo (Com UTF-8)
        file_handler = logging.FileHandler('logs/trading_history.log', encoding='utf-8')
        file_handler.setFormatter(formatter)

        # Handler para o console (Com UTF-8)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger