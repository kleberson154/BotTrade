import pandas as pd
import numpy as np
import datetime
import logging

log = logging.getLogger(__name__)

class TradingStrategy:
    # =========================================================
    # 1. INICIALIZAÇÃO E CONFIGURAÇÃO
    # =========================================================
    def __init__(self, symbol, notifier):
        self.symbol = symbol
        self.notifier = notifier
        self.data_1m = pd.DataFrame()
        self.data_15m = pd.DataFrame()
        self.min_atr_threshold = 0.0002 # Filtro de 0.02% de volatilidade mínima
        
        # Variáveis de Controle de Posição
        self.is_positioned = False
        self.side = None  # "BUY" ou "SELL"
        self.entry_price = 0
        self.sl_price = 0
        self.tp_price = 0
        self.be_activated = False 
        self.partial_taken = False 

    # =========================================================
    # 2. LÓGICA DE SINAL (ESTRATÉGIA COM FILTRO M15)
    # =========================================================
    def check_signal(self):
        """Analisa indicadores e retorna (Sinal, ATR)"""
        try:
            # 1. Filtros de Segurança Básicos (M15 precisa de 200 períodos para a EMA)
            if not self.is_market_safe() or len(self.data_1m) < 35 or len(self.data_15m) < 200:
                return "HOLD", 0
            
            # --- FILTRO DE VOLATILIDADE SNIPER (VERSÃO CORRIGIDA) ---
            try:
                # Verifica se temos velas suficientes e se a coluna 'open' existe
                if len(self.data_1m) >= 20 and 'open' in self.data_1m.columns:
                    recent_candles = self.data_1m.tail(20)
                    # Cálculo da variação média
                    candle_variation = (abs(recent_candles['close'] - recent_candles['open']) / recent_candles['open']).mean()

                    if candle_variation < 0.0012:
                        return "HOLD", 0
                else:
                    # Se não tem dados suficientes ou falta a coluna, aguarda o próximo ciclo
                    return "HOLD", 0
            except Exception as e:
                log.error(f"Erro no cálculo de volatilidade ({self.symbol}): {e}")
                return "HOLD", 0
            
            # 2. Cálculo de ATR e Volume no M1
            atr_series = self.calculate_atr(self.data_1m, 14)
            if len(atr_series) == 0: return "HOLD", 0
            
            atr = atr_series.iloc[-1]
            current_price = self.data_1m['close'].iloc[-1]
            last_price = self.data_1m['close'].iloc[-2]
            current_volume = self.data_1m['volume'].iloc[-1]
            avg_volume = self.data_1m['volume'].tail(20).mean()
            
            volume_ok = current_volume > (avg_volume * 1.1)

            if atr <= 0 or (atr / current_price) < self.min_atr_threshold:
                return "HOLD", 0

            # 3. Indicadores Técnicos - O FILTRO SNIPER (EMA 200 no M15)
            ema_200_15m = self.calculate_ema(self.data_15m, 200).iloc[-1]
            
            # Adicione isso logo após calcular a ema_200_15m
            distancia_ema = abs(current_price - ema_200_15m) / ema_200_15m

            # Se o preço estiver MUITO longe da EMA 200 (> 5%), o risco de correção é alto.
            limite_exaustao = 0.03 if self.symbol in ["XRPUSDT", "ADAUSDT"] else 0.05

            if distancia_ema > limite_exaustao:
                log.warning(f"⚠️ {self.symbol} esticado demais ({distancia_ema:.2%}). Limite: {limite_exaustao:.0%}")
                return "HOLD", 0
            
            # Indicadores do M1 para o gatilho
            ema_20_1m = self.calculate_ema(self.data_1m, 20).iloc[-1]
            rsi_1m = self.calculate_rsi(self.data_1m, 14).iloc[-1]
            macd_line, macd_signal, _ = self.calculate_macd(self.data_1m)
            
            if pd.isna(macd_line.iloc[-1]) or pd.isna(macd_signal.iloc[-1]):
                return "HOLD", 0

            score = 0
            
            # --- LÓGICA DE COMPRA (LONG) - SÓ SE PREÇO > EMA 200 M15 ---
            if current_price > ema_200_15m:
                if rsi_1m < 45: score += 1
                if macd_line.iloc[-1] > macd_signal.iloc[-1]: score += 1
                if current_price < ema_20_1m: score += 1
                
                if score >= 3 and volume_ok:
                    # Filtros de Direção e Exaustão
                    if current_price <= last_price: return "HOLD", 0
                    
                    body_size = abs(current_price - last_price)
                    avg_body = abs(self.data_1m['close'].diff()).tail(10).mean()
                    if body_size > (avg_body * 2.5): return "HOLD", 0
                    
                    self.notifier.send_message(f"🚀 [SINAL COMPRA] {self.symbol} alinhado com tendência M15")
                    log.info(f"🚀 [SINAL COMPRA] {self.symbol} alinhado com tendência M15")
                    return "BUY", atr

            # --- LÓGICA DE VENDA (SHORT) - SÓ SE PREÇO < EMA 200 M15 ---
            elif current_price < ema_200_15m:
                if rsi_1m > 55: score += 1
                if macd_line.iloc[-1] < macd_signal.iloc[-1]: score += 1
                if current_price > ema_20_1m: score += 1
                
                if score >= 3 and volume_ok:
                    if current_price >= last_price: return "HOLD", 0
                    
                    body_size = abs(current_price - last_price)
                    avg_body = abs(self.data_1m['close'].diff()).tail(10).mean()
                    if body_size > (avg_body * 2.5): return "HOLD", 0

                    self.notifier.send_message(f"🚀 [SINAL VENDA] {self.symbol} alinhado com tendência M15")
                    log.info(f"🚀 [SINAL VENDA] {self.symbol} alinhado com tendência M15")
                    return "SELL", atr

            return "HOLD", 0 

        except Exception as e:
            log.error(f"Erro em check_signal ({self.symbol}): {e}")
            return "HOLD", 0 

    def is_market_safe(self):
        agora = datetime.datetime.now()
        # Evita volatilidade extrema de virada de hora (00-05 e 55-60)
        if agora.minute < 5 or agora.minute > 55:
            return False
        return True

    # =========================================================
    # 3. GESTÃO DE RISCO E PROTEÇÃO
    # =========================================================
    def monitor_protection(self, current_price):
        if not self.is_positioned: return None

        atr_series = self.calculate_atr(self.data_1m, 14)
        if len(atr_series) < 1: return None
        atr = atr_series.iloc[-1]
        if atr <= 0: return None

        changed = False
        
        # Cálculo de lucro atual (positivo para lucro, negativo para prejuízo)
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.side == "BUY" else (self.entry_price - current_price) / self.entry_price
    
        # --- A) DEFINIÇÃO DA DISTÂNCIA DE TRAILING (ADAPTATIVA) ---
        if pnl_pct < 0.015: 
            trail_dist = atr * 5.5   # Mais folga no início para não ser stopado por ruído
        elif pnl_pct < 0.03: 
            trail_dist = atr * 4.0   # Encurta a distância quando o lucro cresce
        else: 
            trail_dist = atr * 2.5   # "Enforca" o preço para garantir o lucro gordo

        # --- B) LÓGICA DE PROTEÇÃO (COMPRA) ---
        if self.side == "BUY":
            # 1. Break-even (Trava no lucro mínimo inicial)
            if not self.be_activated and pnl_pct >= 0.010:
                new_sl = self.entry_price * 1.0005
                if new_sl > self.sl_price:
                    self.sl_price = new_sl
                    self.be_activated = True
                    changed = True
                    self.notifier.send_message(f"🛡️ {self.symbol} - Break-even em {new_sl}")

            # 2. Trailing Stop (Sobe acompanhando o preço)
            trail_sl = current_price - trail_dist
            if trail_sl > self.sl_price:
                # Verifica se a mudança é significativa (> 0.12%) para evitar spam na API
                if (trail_sl - self.sl_price) / (self.sl_price if self.sl_price > 0 else 1) > 0.0012: 
                    self.sl_price = trail_sl
                    changed = True

        # --- C) LÓGICA DE PROTEÇÃO (VENDA) ---
        elif self.side == "SELL":
            # 1. Break-even (Trava no lucro mínimo inicial)
            if not self.be_activated and pnl_pct >= 0.014:
                new_sl = self.entry_price * 0.9995
                if new_sl < self.sl_price or self.sl_price == 0:
                    self.sl_price = new_sl
                    self.be_activated = True
                    changed = True
                    self.notifier.send_message(f"🛡️ {self.symbol} - Break-even em {new_sl}")

            # 2. Trailing Stop (Desce acompanhando o preço no Short)
            trail_sl = current_price + trail_dist
            if (self.sl_price == 0) or (trail_sl < self.sl_price):
                # Verifica se a mudança é significativa (> 0.12%)
                if self.sl_price > 0 and (self.sl_price - trail_sl) / trail_sl > 0.0012:
                    self.sl_price = trail_sl
                    changed = True

        # --- D) VERIFICAÇÃO DE SAÍDA PARCIAL ---
        # Só retorna PARTIAL_EXIT se ainda não foi feita e atingiu o alvo
        if not self.partial_taken:
            if (self.side == "BUY" and current_price >= self.entry_price * 1.012) or \
               (self.side == "SELL" and current_price <= self.entry_price * 0.988):
                return "PARTIAL_EXIT" 
    
        return "UPDATE_SL" if changed else None

    # =========================================================
    # 4. INDICADORES TÉCNICOS
    # =========================================================
    def calculate_atr(self, df, period=14):
        if len(df) < period: return pd.Series(0, index=df.index)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        return true_range.rolling(window=period).mean().fillna(0)

    def calculate_ema(self, df, period=200):
        if len(df) < period: return pd.Series(0, index=df.index)
        return df['close'].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, df, period=14):
        if len(df) < period: return pd.Series(50, index=df.index)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        if len(df) < slow: return pd.Series(0), pd.Series(0), pd.Series(0)
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        return macd_line, signal_line, macd_line - signal_line

    # =========================================================
    # 5. MANIPULAÇÃO DE DADOS
    # =========================================================
    def add_new_candle(self, timeframe, candle_data):
        """Adiciona ou atualiza velas em tempo real via WebSocket"""
        df = self.data_1m if timeframe == "1m" else self.data_15m
        
        if not df.empty and candle_data['timestamp'] == df.iloc[-1]['timestamp']:
            idx = df.index[-1]
            df.at[idx, 'close'] = candle_data['close']
            df.at[idx, 'volume'] = candle_data['volume']
            if candle_data['high'] > df.at[idx, 'high']: df.at[idx, 'high'] = candle_data['high']
            if candle_data['low'] < df.at[idx, 'low']: df.at[idx, 'low'] = candle_data['low']
        else:
            new_row = pd.DataFrame([candle_data])
            df = pd.concat([df, new_row], ignore_index=True).tail(300)
        
        if timeframe == "1m": self.data_1m = df.copy()
        else: self.data_15m = df.copy()

    def load_historical_data(self, timeframe, candles):
        """
        Carrega dados históricos formatados como lista de dicionários.
        """
        try:
            # Converte a lista de dicionários diretamente em um DataFrame
            df = pd.DataFrame(candles)
            
            # Lista de colunas que o bot PRECISA para os cálculos
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            
            # Garante que todas as colunas existam (evita o erro 'open')
            for col in required_columns:
                if col not in df.columns:
                    df[col] = 0.0

            # Garante que os tipos sejam numéricos (float)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            if timeframe == "1m":
                self.data_1m = df
            else:
                self.data_15m = df
                
            # log.info(f"✅ Histórico {timeframe} carregado para {self.symbol}")

        except Exception as e:
            print(f"❌ Erro crítico ao carregar histórico em {self.symbol}: {e}")
        
    def sync_position(self, side, entry_price, sl_price, tp_price):
        def safe_float(val):
            try: return float(val) if val and str(val).strip() != "" else 0.0
            except: return 0.0
        self.is_positioned = True
        self.side = "BUY" if side == "Buy" else "SELL"
        self.entry_price = safe_float(entry_price)
        self.sl_price = safe_float(sl_price)
        self.tp_price = safe_float(tp_price)
        
        # Detecta se a posição já está em BE no momento da sincronização
        if (self.side == "BUY" and self.sl_price >= self.entry_price > 0) or \
           (self.side == "SELL" and 0 < self.sl_price <= self.entry_price):
            self.be_activated = True