#!/bin/bash
# Script de Deploy Mack Framework em DEMO Mode

set -e

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="logs"
LOG_FILE="$LOG_DIR/mack_demo_$TIMESTAMP.log"
PID_FILE="$LOG_DIR/bot_demo.pid"

# Garantir que diretório de logs existe
mkdir -p $LOG_DIR

echo "🚀 INICIANDO DEPLOY MACK FRAMEWORK v1.0 - DEMO MODE"
echo "⏰ Timestamp: $TIMESTAMP"
echo "📋 Log: $LOG_FILE"
echo ""

# Verificação de ambiente
echo "📋 VERIFICAÇÕES PRÉ-DEPLOYMENT:"

# 1. Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 não encontrado"
    exit 1
fi
echo "✅ Python3 instalado"

# 2. Verificar venv
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment não encontrado"
    exit 1
fi
echo "✅ Virtual environment existe"

# 3. Verificar .env
if [ ! -f ".env" ]; then
    echo "❌ Arquivo .env não encontrado"
    exit 1
fi
echo "✅ Arquivo .env existe"

# 4. Verificar mode
MODE=$(grep "BYBIT_MODE" .env | cut -d= -f2)
if [ "$MODE" != "demo" ]; then
    echo "❌ BYBIT_MODE não é 'demo' (atual: $MODE)"
    exit 1
fi
echo "✅ BYBIT_MODE = demo"

# 5. Verificar imports
echo "✅ Verificando imports..."
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate
python -c "
from src.strategy import TradingStrategy
from src.mack_compliance import MackCompliance
print('✅ Imports verificados')
" || exit 1

echo ""
echo "🎯 INICIANDO BOT EM DEMO MODE..."
echo ""

# Iniciar bot em background
nohup python main.py > "$LOG_FILE" 2>&1 &
BOT_PID=$!

# Guardar PID
echo $BOT_PID > "$PID_FILE"

# Aguardar inicialização
sleep 3

# Verificar se está rodando
if ps -p $BOT_PID > /dev/null 2>&1; then
    echo "✅ Bot iniciado com sucesso!"
    echo "   PID: $BOT_PID"
    echo "   Log file: $LOG_FILE"
    echo ""
    echo "📊 PRÓXIMOS PASSOS:"
    echo "   1. Monitorar dashboard em outro terminal:"
    echo "      python monitoring_dashboard.py"
    echo ""
    echo "   2. Ver logs em tempo real:"
    echo "      tail -f $LOG_FILE | grep -E '✅|❌|🎯|⚠️'"
    echo ""
    echo "   3. Parar bot quando desejar:"
    echo "      kill $BOT_PID"
    echo ""
    echo "⏰ Executando em DEMO por 2-6 horas..."
    echo "   Critério de sucesso: WR >= 25%"
    exit 0
else
    echo "❌ Falha ao iniciar bot"
    echo "   Verificar log:"
    cat "$LOG_FILE"
    exit 1
fi
