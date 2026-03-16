import pandas as pd
import numpy as np
import datetime

class TradingStrategy:
    def __init__(self, symbol):
        self.symbol = symbol
        self.data_1m = pd.DataFrame()
        self.data_15m = pd.DataFrame()
        self.min_atr_threshold = 0.0002 # Filtro de 0.02% de volatilidade mínima
        
    def is_market_safe(self):
        agora = datetime.datetime.now()
        # Evita os primeiros e últimos 5 minutos de cada hora (volatilidade institucional)
        if agora.minute < 5 or agora.minute > 55:
            return False
        return True
    
    def calculate_atr(self, df, period=14):
        if len(df) < period:
            # Se não houver dados suficientes, retorna uma série de zeros
            return pd.Series(0, index=df.index)

        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()

        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)

        # Usamos o Simple Moving Average do True Range (SMA ATR)
        # fillna(0) garante que o bot não receba um "NaN" e quebre o cálculo do SL
        atr = true_range.rolling(window=period).mean().fillna(0)

        return atr

    def add_new_candle(self, timeframe, candle_data):
        df = self.data_1m if timeframe == "1m" else self.data_15m
        if not df.empty and candle_data['timestamp'] == df.iloc[-1]['timestamp']:
            idx = df.index[-1]
            df.at[idx, 'close'] = candle_data['close']
            if candle_data['high'] > df.at[idx, 'high']: df.at[idx, 'high'] = candle_data['high']
            if candle_data['low'] < df.at[idx, 'low']: df.at[idx, 'low'] = candle_data['low']
        else:
            new_row = pd.DataFrame([candle_data])
            df = pd.concat([df, new_row], ignore_index=True).tail(300)
        
        if timeframe == "1m": self.data_1m = df
        else: self.data_15m = df

    def calculate_ema(self, df, period=200):
        return df['close'].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        # Dentro do calculate_macd
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    def check_signal(self):
        # 1. Filtros de Segurança Básicos
        # Garantimos que existam dados suficientes para os indicadores (EMA 200 precisa de 200 candles)
        if len(self.data_1m) < 35 or len(self.data_15m) < 200:
            return "HOLD", 0
        
        # 2. Cálculo de Volatilidade (ATR)
        atr_series = self.calculate_atr(self.data_1m, 14)
        atr = atr_series.iloc[-1]
        current_price = self.data_1m['close'].iloc[-1]

        # Evita operar se o ATR falhar ou se o mercado estiver "morto"
        if atr <= 0 or (atr / current_price) < self.min_atr_threshold:
            return "HOLD", 0

        # 3. Tendência Macro (EMA 200 no 15m)
        ema_200_15m = self.calculate_ema(self.data_15m, 200).iloc[-1]
        
        # 4. Indicadores para Votação (no 1m)
        rsi_1m = self.calculate_rsi(self.data_1m, 14).iloc[-1]
        macd_line, macd_signal, _ = self.calculate_macd(self.data_1m)
        ema_20_1m = self.calculate_ema(self.data_1m, 20).iloc[-1]

        # Verificação anti-erro para MACD (garante que temos valores válidos)
        if pd.isna(macd_line.iloc[-1]) or pd.isna(macd_signal.iloc[-1]):
            return "HOLD", 0

        score = 0
        
        # --- LÓGICA DE COMPRA (LONG) ---
        # Tendência de alta no 15m
        if current_price > ema_200_15m:
            if rsi_1m < 40: score += 1                # RSI em zona de sobrevenda ou neutra-baixa
            if macd_line.iloc[-1] > macd_signal.iloc[-1]: score += 1 # Cruzamento de alta
            if current_price < ema_20_1m: score += 1  # Pullback (preço "barato" em relação à média curta)
            
            # Feedback visual para o usuário (apenas para monitoramento, não influencia a decisão)
            #if score > 0:
            
            if score >= 2: 
                print(f"🔍 {self.symbol} Score: {score}/3 | RSI: {rsi_1m:.2f} | EMA_15m: {ema_200_15m:.2f}")
                return "BUY", atr

        # --- LÓGICA DE VENDA (SHORT) ---
        # Tendência de baixa no 15m
        elif current_price < ema_200_15m:
            if rsi_1m > 60: score += 1                # RSI em zona de sobrecompra ou neutra-alta
            if macd_line.iloc[-1] < macd_signal.iloc[-1]: score += 1 # Cruzamento de baixa
            if current_price > ema_20_1m: score += 1  # Pullback (preço "caro" em relação à média curta)
            
            # Feedback visual para o usuário (apenas para monitoramento, não influencia a decisão)
            #if score > 0:
            
            if score >= 2: 
                print(f"🔍 {self.symbol} Score: {score}/3 | RSI: {rsi_1m:.2f} | EMA_15m: {ema_200_15m:.2f}")
                return "SELL", atr
            
        return "HOLD", 0
    
    def load_historical_data(self, timeframe_label, candles):
        df_data = []
        for c in candles:
            df_data.append({
                "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "timestamp": int(c[0])
            })
        new_df = pd.DataFrame(df_data)
        if timeframe_label == "1m": self.data_1m = new_df
        else: self.data_15m = new_df