import pandas as pd
import numpy as np
import datetime

class TradingStrategy:
    def __init__(self, symbol, notifier):
        self.symbol = symbol
        self.notifier = notifier
        self.data_1m = pd.DataFrame()
        self.data_15m = pd.DataFrame()
        self.min_atr_threshold = 0.0002 # Filtro de 0.02% de volatilidade mínima
        
        # --- NOVAS VARIÁVEIS DE CONTROLE ---
        self.is_positioned = False
        self.side = None  # "BUY" ou "SELL"
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.be_activated = False # Trava para não tentar mover o BE várias vezes
        
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
        histogram = macd_line - signal_line 
        return macd_line, signal_line, histogram

    def check_signal(self):
        # 1. Filtros de Segurança Básicos
        if not self.is_market_safe() or len(self.data_1m) < 35 or len(self.data_15m) < 200:
            return "HOLD", 0
        
        # 2. Dados Atuais
        atr = self.calculate_atr(self.data_1m, 14).iloc[-1]
        current_price = self.data_1m['close'].iloc[-1]
        last_price = self.data_1m['close'].iloc[-2]

        if atr <= 0 or (atr / current_price) < self.min_atr_threshold:
            return "HOLD", 0

        # 3. Indicadores
        ema_200_15m = self.calculate_ema(self.data_15m, 200).iloc[-1]
        ema_20_1m = self.calculate_ema(self.data_1m, 20).iloc[-1]
        rsi_1m = self.calculate_rsi(self.data_1m, 14).iloc[-1]
        
        macd_line, macd_signal, _ = self.calculate_macd(self.data_1m)
        
        if pd.isna(macd_line.iloc[-1]) or pd.isna(macd_signal.iloc[-1]):
            return "HOLD", 0

        score = 0
        
        # --- LÓGICA DE COMPRA (LONG) ---
        if current_price > ema_200_15m:
            if rsi_1m < 45: score += 1
            if macd_line.iloc[-1] > macd_signal.iloc[-1]: score += 1
            if current_price < ema_20_1m: score += 1
            
            if score >= 3 and current_price > last_price:
                return "BUY", atr

        # --- LÓGICA DE VENDA (SHORT) ---
        elif current_price < ema_200_15m:
            if rsi_1m > 55: score += 1
            if macd_line.iloc[-1] < macd_signal.iloc[-1]: score += 1
            if current_price > ema_20_1m: score += 1
            
            if score >= 3 and current_price < last_price:
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
        
    def monitor_protection(self, current_price):
        if not self.is_positioned:
            return None

        atr_series = self.calculate_atr(self.data_1m, 14)
        if len(atr_series) < 1: return None
        atr = atr_series.iloc[-1]
        if atr <= 0: return None

        changed = False
        
        # --- AJUSTE DE DISTÂNCIA ---
        # Aumentamos a folga do Trailing para 3.5x ATR
        # Assim ele só sobe o SL quando o lucro for realmente expressivo
        trail_dist = atr * 3.5

        if self.side == "BUY":
            # 1. BREAK-EVEN (Proteção rápida)
            # Movemos para o zero a zero apenas quando atingir 0.7% de lucro
            # Isso evita ser estopado na entrada por qualquer oscilação boba.
            if not self.be_activated and current_price >= self.entry_price * 1.012:
                new_sl = self.entry_price * 1.002 # Entrada + taxas
                if new_sl > self.sl_price:
                    self.sl_price = new_sl
                    self.be_activated = True
                    changed = True
                    self.notifier.send_message(f"🛡️ {self.symbol} - Break-even ativado em {new_sl}")

            # 2. TRAILING STOP (Seguindo o lucro)
            trail_sl = current_price - trail_dist
            if trail_sl > self.sl_price:
                # Só atualiza se a subida for relevante (> 0.1%) para poupar a API
                if (trail_sl - self.sl_price) / self.sl_price > 0.001: 
                    self.sl_price = trail_sl
                    changed = True

        elif self.side == "SELL":
            # 1. BREAK-EVEN
            if not self.be_activated and current_price <= self.entry_price * 0.993:
                new_sl = self.entry_price * 0.999 # Entrada - taxas
                if new_sl < self.sl_price or self.sl_price == 0:
                    self.sl_price = new_sl
                    self.be_activated = True
                    changed = True
                    self.notifier.send_message(f"🛡️ {self.symbol} - Break-even ativado em {new_sl}")

            # 2. TRAILING STOP
            trail_sl = current_price + trail_dist
            if trail_sl < self.sl_price or self.sl_price == 0:
                if (self.sl_price - trail_sl) / trail_sl > 0.001:
                    self.sl_price = trail_sl
                    changed = True

        return "UPDATE_SL" if changed else None
    
    def sync_position(self, side, entry_price, sl_price, tp_price):
        # Função auxiliar para evitar o erro de string vazia
        def safe_float(val):
            try:
                return float(val) if val and str(val).strip() != "" else 0.0
            except:
                return 0.0

        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = safe_float(entry_price)
        self.sl_price = safe_float(sl_price)
        self.tp_price = safe_float(tp_price)
        
        # Se o SL já estiver no preço de entrada ou melhor, ativa o BE
        if (self.side == "BUY" and self.sl_price >= self.entry_price and self.entry_price > 0) or \
           (self.side == "SELL" and self.sl_price <= self.entry_price and self.entry_price > 0):
            self.be_activated = True