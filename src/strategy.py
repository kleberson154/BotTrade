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
        """Analisa rompimentos e pullbacks com Filtros de Exaustão e Confirmação M15"""
        try:
            if not self.is_market_safe() or len(self.data_1m) < 35 or len(self.data_15m) < 200:
                return "HOLD", 0
            
            # --- 1. CÁLCULOS BASE ---
            current_price = self.data_1m['close'].iloc[-1]
            last_price = self.data_1m['close'].iloc[-2]
            current_volume = self.data_1m['volume'].iloc[-1]
            
            # Mínima/Máxima 15m (Caixote)
            minima_15m = self.data_1m['low'].tail(15).min()
            maxima_15m = self.data_1m['high'].tail(15).max()
            
            # Volume e Indicadores
            avg_vol_10 = self.data_1m['volume'].tail(10).mean()
            pico_volume = current_volume > (avg_vol_10 * 2.2)
            
            atr = self.calculate_atr(self.data_1m, 14).iloc[-1]
            ema_20_1m = self.calculate_ema(self.data_1m, 20).iloc[-1]
            ema_200_15m = self.calculate_ema(self.data_15m, 200).iloc[-1]
            rsi_1m = self.calculate_rsi(self.data_1m, 14).iloc[-1]
            macd_line, macd_signal, _ = self.calculate_macd(self.data_1m)

            # --- 2. CONFIRMAÇÃO DE TENDÊNCIA M15 (COR DO CANDLE ANTERIOR + ATUAL) ---
            # Pegamos a penúltima vela (fechada) para ter uma base sólida
            open_15m_prev = self.data_15m['open'].iloc[-2]
            close_15m_prev = self.data_15m['close'].iloc[-2]
            
            # E a atual para sentir o momento
            open_15m_curr = self.data_15m['open'].iloc[-1]
            close_15m_curr = self.data_15m['close'].iloc[-1]
        
            # Tendência Forte: Vela anterior confirmada + Vela atual na mesma direção
            m15_vermelho = (close_15m_prev < open_15m_prev) and (close_15m_curr < open_15m_curr)
            m15_verde = (close_15m_prev > open_15m_prev) and (close_15m_curr > open_15m_curr)
        
            # --- 3. LÓGICA DE VENDA (SHORT) ---
            if current_price < ema_200_15m:
                # Se o M15 estiver verde (revidando), o Sniper não atira em Short
                if not m15_vermelho:
                    return "HOLD", 0
        
                # TRAVA RSI: Não vende fundo (Aumentei para 38 conforme seu backtest)
                if rsi_1m < 38:
                    return "HOLD", 0
                    
                # GATILHO A: Rompimento com Volume (Seu código já está ótimo aqui)
                if current_price < minima_15m and pico_volume:
                    log.info(f"🔥 {self.symbol} Rompimento de Ignição detectado!")
                    return "SELL", atr

                # FILTRO DE EXAUSTÃO MÉDIA (0.8%)
                distancia_media = (ema_20_1m - current_price) / ema_20_1m
                if distancia_media > 0.008:
                    log.warning(f"🚫 {self.symbol} esticado ({distancia_media:.2%}).")
                    return "HOLD", 0

                # GATILHO B: Score de Pullback
                score = 0
                if rsi_1m > 50: score += 1
                if macd_line.iloc[-1] < macd_signal.iloc[-1]: score += 1
                if current_price > (ema_20_1m * 0.998): score += 1
                
                # Só entra se houver volume real (acima da média)
                if score >= 2 and current_volume > avg_vol_10:
                    if current_price >= last_price: return "HOLD", 0
                    return "SELL", atr

            # --- 4. LÓGICA DE COMPRA (LONG) ---
            elif current_price > ema_200_15m:
                # SÓ COMPRA SE O M15 ESTIVER SUBINDO
                if not m15_verde:
                    return "HOLD", 0

                # TRAVA RSI: Não compra topo (Overbought)
                if rsi_1m > 62:
                    log.info(f"🛑 {self.symbol} RSI Sobrecomprado ({rsi_1m:.2f}).")
                    return "HOLD", 0

                # GATILHO A: Rompimento de Ignição
                if current_price > maxima_15m and pico_volume:
                    return "BUY", atr

                # FILTRO DE EXAUSTÃO MÉDIA (0.8%)
                distancia_media = (current_price - ema_20_1m) / ema_20_1m
                if distancia_media > 0.008:
                    return "HOLD", 0

                # GATILHO B: Score de Pullback
                score = 0
                if rsi_1m < 50: score += 1
                if macd_line.iloc[-1] > macd_signal.iloc[-1]: score += 1
                if current_price < (ema_20_1m * 1.002): score += 1
                
                if score >= 2 and current_volume > avg_vol_10:
                    if current_price <= last_price: return "HOLD", 0
                    return "BUY", atr

            return "HOLD", 0
        except Exception as e:
            log.error(f"Erro no check_signal: {e}")
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
        
        pnl_pct = (current_price - self.entry_price) / self.entry_price if self.side == "BUY" else (self.entry_price - current_price) / self.entry_price
        changed = False

        # --- TRAILING ADAPTATIVO (MAIS FOLGA NO INÍCIO) ---
        if pnl_pct < 0.012:
            trail_dist = atr * 7.5   # Folga extra para aguentar o "repique" da LINK
        elif pnl_pct < 0.025:
            trail_dist = atr * 4.5
        else:
            trail_dist = atr * 2.2   # Enforca o lucro gordo

        # --- PROTEÇÃO BREAK-EVEN ---
        # Só ativa o zero-a-zero com 0.9% de lucro para não ser tirado no ruído
        if not self.be_activated and pnl_pct >= 0.009:
            self.sl_price = self.entry_price * (1.0003 if self.side == "BUY" else 0.9997)
            self.be_activated = True
            changed = True
            self.notifier.send_message(f"🛡️ {self.symbol} - Break-even ativado em {self.sl_price:.4f}")

        # --- AJUSTE DO STOP LOSS ---
        if self.side == "BUY":
            trail_sl = current_price - trail_dist
            if trail_sl > self.sl_price:
                if (trail_sl - self.sl_price) / (self.sl_price if self.sl_price > 0 else 1) > 0.0010:
                    self.sl_price = trail_sl
                    changed = True
        else:
            trail_sl = current_price + trail_dist
            if (self.sl_price == 0) or (trail_sl < self.sl_price):
                if self.sl_price > 0 and (self.sl_price - trail_sl) / trail_sl > 0.0010:
                    self.sl_price = trail_sl
                    changed = True

        # --- SAÍDA PARCIAL ---
        if not self.partial_taken and pnl_pct >= 0.012:
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
        # 1. Escolhe o DataFrame alvo (Referência direta, evita cópia precoce)
        df = self.data_1m if timeframe == "1m" else self.data_15m
        
        if not df.empty and candle_data['timestamp'] == df.iloc[-1]['timestamp']:
            # 2. ATUALIZAÇÃO (Mesmo minuto): 
            # Usamos .iloc[-1] para garantir que estamos mexendo na última linha
            idx = df.index[-1]
            
            df.at[idx, 'close'] = candle_data['close']
            df.at[idx, 'volume'] = candle_data['volume']
            
            # Atualiza High/Low apenas se o novo tick superar o anterior
            if candle_data['high'] > df.at[idx, 'high']: df.at[idx, 'high'] = candle_data['high']
            if candle_data['low'] < df.at[idx, 'low']: df.at[idx, 'low'] = candle_data['low']
            
            # IMPORTANTE: Garantir que o 'open' não se perca se houver micro-ajuste da Bybit
            if 'open' in candle_data: df.at[idx, 'open'] = candle_data['open']
            
        else:
            # 3. NOVO CANDLE (Virada de minuto):
            new_row = pd.DataFrame([candle_data])
            # .tail(300) impede que o bot consuma toda a RAM do seu PC/VPS com o passar dos dias
            df = pd.concat([df, new_row], ignore_index=True).tail(300)
        
        # 4. Salva de volta (Somente aqui atribuímos ao self)
        if timeframe == "1m":
            self.data_1m = df
        else:
            self.data_15m = df

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