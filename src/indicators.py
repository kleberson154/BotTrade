"""
📊 BIBLIOTECA CENTRALIZADA DE INDICADORES TÉCNICOS
Consolida todos os cálculos de indicadores em um único local para evitar duplicação.

Indicadores Implementados:
  1. RSI (Relative Strength Index) - Momentum
  2. ADX (Average Directional Index) - Força da tendência
  3. ATR (Average True Range) - Volatilidade absoluta
  4. ATR% (ATR em %) - Volatilidade relativa
  5. MFI (Money Flow Index) - Fluxo de dinheiro
  6. EMA (Exponential Moving Average) - Média móvel exponencial
  7. Volume Analysis - Análise de volume
  8. True Range - Base para ATR e ADX
"""

import pandas as pd
import numpy as np
import logging

log = logging.getLogger(__name__)


class TechnicalIndicators:
    """Classe centralizada para todos os indicadores técnicos"""
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calcula RSI (Relative Strength Index)
        
        Args:
            prices: Series de preços (close)
            period: Período de cálculo (padrão 14)
            
        Returns:
            Series com valores de RSI
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 0.001)
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def calculate_true_range(df: pd.DataFrame) -> pd.Series:
        """
        Calcula True Range (base para ATR e ADX)
        
        Args:
            df: DataFrame com colunas 'high', 'low', 'close'
            
        Returns:
            Series com True Range
        """
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        return tr
    
    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calcula ATR (Average True Range)
        
        Args:
            df: DataFrame com colunas 'high', 'low', 'close'
            period: Período de cálculo (padrão 14)
            
        Returns:
            Series com ATR
        """
        tr = TechnicalIndicators.calculate_true_range(df)
        return tr.rolling(period).mean()
    
    @staticmethod
    def calculate_atr_pct(df: pd.DataFrame, period: int = 14) -> float:
        """
        Calcula ATR em % (volatilidade relativa)
        
        Args:
            df: DataFrame com colunas OHLCV
            period: Período de cálculo (padrão 14)
            
        Returns:
            Float com ATR% do último candle
        """
        atr = TechnicalIndicators.calculate_atr(df, period)
        atr_value = atr.iloc[-1]
        current_price = df['close'].iloc[-1]
        return atr_value / current_price if current_price > 0 else 0.0
    
    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calcula ADX (Average Directional Index)
        
        Args:
            df: DataFrame com colunas 'high', 'low', 'close'
            period: Período de cálculo (padrão 14)
            
        Returns:
            Series com ADX
        """
        plus_dm = df['high'].diff().clip(lower=0)
        minus_dm = -df['low'].diff().clip(upper=0)
        
        tr = TechnicalIndicators.calculate_true_range(df)
        atr = tr.rolling(period).mean()
        
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr).replace([np.inf, -np.inf], 0).fillna(0)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1)
        adx = dx.rolling(period).mean().bfill()
        
        return adx
    
    @staticmethod
    def calculate_mfi(df: pd.DataFrame, period: int = 14) -> float:
        """
        Calcula MFI (Money Flow Index)
        
        Args:
            df: DataFrame com colunas OHLCV
            period: Período de cálculo (padrão 14)
            
        Returns:
            Float com valor de MFI
        """
        # Money Flow = típico × volume
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        money_flow = typical_price * df['volume']
        
        # Positive/Negative MF
        price_change = df['close'].diff()
        positive_mf = money_flow.where(price_change > 0, 0)
        negative_mf = money_flow.where(price_change < 0, 0)
        
        positive_mf_sum = positive_mf.tail(period).sum()
        negative_mf_sum = negative_mf.tail(period).sum()
        
        money_flow_ratio = positive_mf_sum / negative_mf_sum if negative_mf_sum > 0 else 0
        mfi = 100 - (100 / (1 + money_flow_ratio))
        
        return mfi
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int = 20) -> pd.Series:
        """
        Calcula EMA (Exponential Moving Average)
        
        Args:
            prices: Series de preços
            period: Período de cálculo (padrão 20)
            
        Returns:
            Series com EMA
        """
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_volume_momentum(df: pd.DataFrame, lookback: int = 5) -> float:
        """
        Calcula momentum de volume (ratio entre volume atual e média)
        
        Args:
            df: DataFrame com coluna 'volume'
            lookback: Candles para média (padrão 5)
            
        Returns:
            Float com ratio de volume
        """
        if len(df) < lookback:
            return 1.0
        
        vol_recent = df['volume'].iloc[-1]
        vol_avg = df['volume'].iloc[-lookback:-1].mean()
        
        return vol_recent / vol_avg if vol_avg > 0 else 1.0
    
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame, rsi_period: int = 14, 
                                 ema_periods: list = None, volume_lookback: int = 5) -> dict:
        """
        Calcula TODOS os indicadores de uma vez
        
        Args:
            df: DataFrame com OHLCV
            rsi_period: Período para RSI (padrão 14)
            ema_periods: Lista de períodos para EMA (padrão [20, 50, 200])
            volume_lookback: Lookback para volume (padrão 5)
            
        Returns:
            Dict com todos os indicadores calculados
        """
        if ema_periods is None:
            ema_periods = [20, 50, 200]
        
        indicators = {}
        
        # RSI
        indicators['rsi'] = TechnicalIndicators.calculate_rsi(df['close'], rsi_period).iloc[-1]
        
        # ADX
        indicators['adx'] = TechnicalIndicators.calculate_adx(df, rsi_period).iloc[-1]
        
        # ATR
        indicators['atr'] = TechnicalIndicators.calculate_atr(df, rsi_period).iloc[-1]
        indicators['atr_pct'] = TechnicalIndicators.calculate_atr_pct(df, rsi_period)
        
        # MFI
        indicators['mfi'] = TechnicalIndicators.calculate_mfi(df, rsi_period)
        
        # EMA
        for period in ema_periods:
            ema = TechnicalIndicators.calculate_ema(df['close'], period)
            indicators[f'ema_{period}'] = ema.iloc[-1]
        
        # Volume
        indicators['volume_momentum'] = TechnicalIndicators.calculate_volume_momentum(df, volume_lookback)
        indicators['volume_current'] = df['volume'].iloc[-1]
        indicators['volume_avg'] = df['volume'].tail(volume_lookback).mean()
        
        return indicators
