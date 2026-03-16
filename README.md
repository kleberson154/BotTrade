# 1% Scalper Bot - Bybit 🤖📈

Este é um bot de trading quantitativo para o mercado de **Futuros da Bybit (Perpetual Linear)**. Ele utiliza uma estratégia de Scalping baseada em indicadores técnicos, ordens **Limit (Post-Only)** para economia de taxas e gestão de risco adaptativa via **ATR**.

## 🚀 Funcionalidades

- **Estratégia Tripla:** Filtro de tendência com **EMA 200/20**, confirmação de momentum com **MACD** e pontos de entrada via **RSI**.
- **Execução Inteligente:** Utiliza ordens `Limit Post-Only` para garantir o recebimento de taxas de _maker_ e evitar o _slippage_.
- **Gestão de Risco Adaptativa:** Stop Loss e Take Profit calculados dinamicamente com base na volatilidade real do mercado (**ATR**).
- **Proteção de Capital:**
  - **Break-even:** Move o Stop Loss para o preço de entrada (mais uma pequena margem) após 1.5% de lucro.
  - **Trailing Stop:** Rastreia o preço para garantir lucros em tendências fortes usando volatilidade como respiro.
  - **Limpeza de Ordens:** Cancela ordens pendentes não preenchidas após 2 minutos para liberar margem.
- **Multi-Ativos:** Suporte a múltiplos símbolos simultâneos com trava de segurança de margem (limite de 3 posições abertas).
- **Notificações:** Alertas de operações e relatórios diários de PNL via **Telegram**.

---

## 🛠️ Instalação e Configuração

### 1. Clonar o Repositório

```bash
git clone [https://github.com/kleberson154/BotTrade](https://github.com/kleberson154/BotTrade)
cd BotTrade
```

### 2. Configurar Ambiente Virtual

```bash
python3 -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Variáveis de Ambiente

Crie um arquivo .env na raiz do projeto baseado no exemplo abaixo:

```bash
cp .env.example .env
nano .env
```

### ⚙️ Configuração do .env

| Variável         | Descrição                             | Exemplo                                                   |
| ---------------- | ------------------------------------- | --------------------------------------------------------- |
| BYBIT_API_KEY    | Sua chave de API da Bybit             | xxxxXXXXXXXX                                              |
| BYBIT_API_SECRET | Seu segredo de API da Bybit           | yyyyYYYYYYYY                                              |
| BYBIT_MODE       | Modo de execução                      | demo, testnet ou real                                     |
| SYMBOLS          | Lista de moedas separadas por vírgula | BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,AVAXUSDT,XRPUSDT,ADAUSDT |
| TELEGRAM_TOKEN   | Token do bot (via BotFather)          | 123456:ABC-DEF                                            |
| TELEGRAM_CHAT_ID | Seu ID de usuário no Telegram         | 987654321                                                 |

### 📈 Estratégia Técnica

O bot monitora o mercado via WebSockets nos timeframes de 1m (execução) e 15m (tendência).

#### Condições de Entrada:

- **LONG (Compra):** Preço acima da EMA 200.
  - Histograma MACD positivo (acima de 0).
  - RSI cruzando o nível 30 para cima.
- **SHORT (Venda):** Preço abaixo da EMA 200.
  - Histograma MACD negativo (abaixo de 0).
  - RSI cruzando o nível 70 para baixo.

#### Saída e Risco:

- **Stop Loss:** 2 X ATR(distância baseada na volatilidade).
- **Take Profit:** 3 X ATR(proporção 1.5:1).

### 🛡️ Hospedagem (VPS - Oracle Cloud)

Para manter o bot rodando 24/7, recomenda-se o uso do PM2:

```bash
# Instalar PM2
sudo npm install pm2 -g

# Iniciar o Bot
pm2 start main.py --name "bot-bybit" --interpreter ./venv/bin/python3

# Configurar para iniciar com o sistema
pm2 save
pm2 startup
```

### ⚠️ Aviso Legal

Este software é apenas para fins educacionais. O mercado de criptomoedas envolve alto risco e volatilidade. O uso de alavancagem pode resultar em perda total do capital. Teste sempre em conta Demo antes de utilizar capital real. O autor não se responsabiliza por quaisquer perdas financeiras.
