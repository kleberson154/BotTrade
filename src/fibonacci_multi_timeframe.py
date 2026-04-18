"""
Fibonacci Retracement/Projection + Multi-Timeframe (1h + 15m) + Multiple TPs System
Para BotTrade
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional

log = logging.getLogger(__name__)


class FibonacciAnalyzer:
    """
    Analisador de Fibonacci com Retração e Projeção
    
    Níveis usados: 0, 0.382, 0.5, 0.618, 1.0
    
    Uso:
    1. Como indicador de entrada (níveis de suporte/resistência)
    2. Para definir stops (abaixo/acima dos níveis)
    3. Para definir TPs múltiplos (0.382, 0.618, 1.0)
    4. Integração com liquidez (esperar momento certo nos níveis)
    """
    
    # Níveis Fibonacci padrão
    FIBONACCI_LEVELS = [0, 0.382, 0.5, 0.618, 1.0]
    
    def __init__(self):
        self.last_swing_high = None
        self.last_swing_low = None
        self.retracement_levels = {}
        self.projection_levels = {}
    
    def calculate_retracement(self, swing_high: float, swing_low: float, 
                             current_price: float = None) -> Dict:
        """
        Calcula níveis de retração Fibonacci
        
        Retração = quando preço puxa para trás em um uptrend/downtrend
        
        Uso: Encontrar suportes dinâmicos para entrada
        
        Args:
            swing_high: Ponto alto da onda
            swing_low: Ponto baixo da onda
            current_price: Preço atual (opcional, para análise)
            
        Returns:
            Dict com níveis e análise
        """
        if swing_high <= swing_low:
            return {'error': 'Swing high deve ser maior que swing low'}
        
        price_range = swing_high - swing_low
        
        levels = {}
        for level in self.FIBONACCI_LEVELS:
            retracement_price = swing_high - (price_range * level)
            levels[f'{int(level*100)}%'] = {
                'level': retracement_price,
                'percentage': level * 100
            }
        
        self.retracement_levels = levels
        
        # Análise: onde está o preço atual?
        analysis = {}
        if current_price:
            for level_name, level_data in levels.items():
                analysis[level_name] = {
                    'price': level_data['level'],
                    'distance_pct': ((current_price - level_data['level']) / level_data['level']) * 100
                }
        
        return {
            'type': 'RETRACEMENT',
            'swing_high': swing_high,
            'swing_low': swing_low,
            'range': price_range,
            'levels': levels,
            'analysis': analysis,
            'description': f'Retração: {swing_high:.2f} - {swing_low:.2f} | Range: {price_range:.2f}'
        }
    
    def calculate_projection(self, swing_low: float, swing_high: float, 
                            breakout_point: float = None) -> Dict:
        """
        Calcula níveis de projeção Fibonacci
        
        Projeção = quando preço avança ALÉM do nível anterior
        
        Uso: Encontrar resistências dinâmicas para TPs
        
        Args:
            swing_low: Ponto baixo inicial
            swing_high: Ponto alto (origem da projeção)
            breakout_point: Ponto onde preço quebrou (opcional)
            
        Returns:
            Dict com níveis de projeção
        """
        if swing_high <= swing_low:
            return {'error': 'Swing high deve ser maior que swing low'}
        
        price_range = swing_high - swing_low
        
        levels = {}
        for level in self.FIBONACCI_LEVELS:
            if level == 0:
                projection_price = swing_high
            else:
                projection_price = swing_high + (price_range * level)
            
            levels[f'{int(level*100)}%'] = {
                'level': projection_price,
                'percentage': level * 100
            }
        
        self.projection_levels = levels
        
        return {
            'type': 'PROJECTION',
            'swing_low': swing_low,
            'swing_high': swing_high,
            'range': price_range,
            'levels': levels,
            'description': f'Projeção: {swing_low:.2f} → {swing_high:.2f} | Range: {price_range:.2f}'
        }
    
    def calculate_tp_levels(self, entry_price: float, stop_loss: float, 
                           use_projection: bool = True) -> Dict:
        """
        Calcula 3 TPs (Take Profit) usando Fibonacci
        
        TP1 = 0.382 retração do SL até entrada
        TP2 = 0.618 retração do SL até entrada
        TP3 = 1.0 retração = distância SL duplicada
        
        Args:
            entry_price: Preço de entrada
            stop_loss: Preço do stop loss
            use_projection: Se True, usa projeção em vez de retração
            
        Returns:
            Dict com 3 TPs calculados
        """
        if entry_price == stop_loss:
            return {'error': 'Entry price não pode ser igual ao stop loss'}
        
        # Determinar direção do trade
        is_long = entry_price > stop_loss
        
        risk = abs(entry_price - stop_loss)
        
        if is_long:
            # Trade LONG: entry > stop loss
            tp1 = entry_price + (risk * 0.382)
            tp2 = entry_price + (risk * 0.618)
            tp3 = entry_price + (risk * 1.0)
        else:
            # Trade SHORT: entry < stop loss
            tp1 = entry_price - (risk * 0.382)
            tp2 = entry_price - (risk * 0.618)
            tp3 = entry_price - (risk * 1.0)
        
        return {
            'entry': entry_price,
            'stop_loss': stop_loss,
            'risk': risk,
            'direction': 'LONG' if is_long else 'SHORT',
            'tp1': round(tp1, 8),
            'tp2': round(tp2, 8),
            'tp3': round(tp3, 8),
            'tp1_risk_reward': '1:0.382',
            'tp2_risk_reward': '1:0.618',
            'tp3_risk_reward': '1:1.0',
            'description': f"TPs: {tp1:.8f} | {tp2:.8f} | {tp3:.8f}"
        }
    
    def analyze_price_at_fib_level(self, current_price: float, 
                                   fib_levels: Dict) -> Dict:
        """
        Analisa posição do preço em relação aos níveis Fibonacci
        
        Útil para determinar melhor entrada na zona de liquidez
        
        Args:
            current_price: Preço atual
            fib_levels: Dict de níveis Fibonacci
            
        Returns:
            Análise detalhada
        """
        analysis = {
            'current_price': current_price,
            'nearest_level': None,
            'distance_to_nearest': float('inf'),
            'levels_nearby': []
        }
        
        for level_name, level_data in fib_levels.items():
            level_price = level_data['level']
            distance = abs(current_price - level_price)
            distance_pct = (distance / current_price) * 100
            
            # Registrar nível
            analysis['levels_nearby'].append({
                'level': level_name,
                'price': level_price,
                'distance': distance,
                'distance_pct': distance_pct
            })
            
            # Encontrar mais próximo
            if distance < analysis['distance_to_nearest']:
                analysis['distance_to_nearest'] = distance
                analysis['nearest_level'] = level_name
                analysis['nearest_level_price'] = level_price
        
        # Ordenar por distância
        analysis['levels_nearby'].sort(key=lambda x: x['distance'])
        
        return analysis
    
    @staticmethod
    def find_swing_high_low(df: pd.DataFrame, lookback: int = 20) -> Tuple[float, float]:
        """
        Encontra últimos swing high e low para usar como base de Fibonacci
        
        Args:
            df: DataFrame com OHLCV
            lookback: Quantas velas voltar
            
        Returns:
            Tuple (swing_high, swing_low)
        """
        if len(df) < lookback:
            lookback = len(df)
        
        recent = df.tail(lookback)
        swing_high = recent['high'].max()
        swing_low = recent['low'].min()
        
        return swing_high, swing_low


class MultiTimeframeValidator:
    """
    Validador Multi-Timeframe: 1h (confirmação) + 15m (sinal)
    
    Estratégia:
    1. Confirmar tendência em 1h (Dow Theory + SMA + Volume)
    2. Gerar sinais em 15m usando mesmos indicadores
    3. Entrada quando ambas TF alinhadas
    4. Melhor risk/reward: Entrada precisa em 15m, SL baseado em 1h
    
    Regra: NUNCA entrar contra a tendência de 1h!
    """
    
    def __init__(self):
        from .indicators import EnhancedSignalValidator
        self.validator = EnhancedSignalValidator()
    
    def validate_multi_timeframe(self, df_1h: pd.DataFrame, 
                                df_15m: pd.DataFrame) -> Dict:
        """
        Valida sinal multi-timeframe (1h + 15m)
        
        Args:
            df_1h: DataFrame de 1h com OHLCV
            df_15m: DataFrame de 15m com OHLCV
            
        Returns:
            Dict com validação multi-timeframe
        """
        if len(df_1h) < 20 or len(df_15m) < 20:
            return {
                'signal': 'HOLD',
                'is_valid': False,
                'reason': 'Dados insuficientes em uma ou ambas timeframes'
            }
        
        # 1️⃣ Análise 1h (Confirmação de Tendência)
        signal_1h = self.validator.validate_complete_enhanced(df_1h)
        trend_1h = signal_1h['signal']
        confidence_1h = signal_1h['confidence']
        
        # 2️⃣ Análise 15m (Gerador de Sinais)
        signal_15m = self.validator.validate_complete_enhanced(df_15m)
        signal_15m_type = signal_15m['signal']
        confidence_15m = signal_15m['confidence']
        
        # 3️⃣ Validação: 15m deve estar alinhado com 1h
        is_aligned = (trend_1h == signal_15m_type) or (trend_1h == 'HOLD')
        
        # 4️⃣ Regra crítica: NUNCA contra 1h
        is_against_1h = (trend_1h == 'BUY' and signal_15m_type == 'SELL') or \
                       (trend_1h == 'SELL' and signal_15m_type == 'BUY')
        
        if is_against_1h:
            return {
                'signal': 'HOLD',
                'is_valid': False,
                'reason': f'VETO: Sinal 15m ({signal_15m_type}) contra tendência 1h ({trend_1h})',
                'trend_1h': trend_1h,
                'signal_15m': signal_15m_type,
                'confidence_1h': confidence_1h,
                'confidence_15m': confidence_15m,
                'analysis': '❌ Não operar contra 1h!'
            }
        
        # 5️⃣ Validar confiança mínima
        min_confidence_threshold = 50
        
        if confidence_1h < min_confidence_threshold:
            return {
                'signal': 'HOLD',
                'is_valid': False,
                'reason': f'Confiança 1h muito baixa ({confidence_1h:.0f}% < {min_confidence_threshold}%)',
                'trend_1h': trend_1h,
                'signal_15m': signal_15m_type,
                'confidence_1h': confidence_1h,
                'confidence_15m': confidence_15m,
                'analysis': '🟡 Esperar confirmação em 1h'
            }
        
        # 6️⃣ Sinal VÁLIDO
        if is_aligned and signal_15m_type != 'HOLD':
            # Usar o sinal que tem maior confiança
            if confidence_15m >= min_confidence_threshold:
                final_signal = signal_15m_type
                final_confidence = (confidence_1h + confidence_15m) / 2
                is_strong = final_confidence >= 70
                
                return {
                    'signal': final_signal,
                    'is_valid': True,
                    'is_strong': is_strong,
                    'reason': f'{trend_1h} 1h + {signal_15m_type} 15m = ALINHADO',
                    'trend_1h': trend_1h,
                    'signal_15m': signal_15m_type,
                    'confidence_1h': confidence_1h,
                    'confidence_15m': confidence_15m,
                    'final_confidence': final_confidence,
                    'signal_1h_data': signal_1h,
                    'signal_15m_data': signal_15m,
                    'analysis': f'✅ ENTRADA VÁLIDA: {final_signal} | Confiança: {final_confidence:.0f}%'
                }
        
        return {
            'signal': 'HOLD',
            'is_valid': False,
            'reason': 'Esperando alinhamento entre timeframes ou confiança insuficiente',
            'trend_1h': trend_1h,
            'signal_15m': signal_15m_type,
            'confidence_1h': confidence_1h,
            'confidence_15m': confidence_15m,
            'analysis': '🟡 Aguardando momento certo'
        }
    
    def get_best_entry_levels(self, df_1h: pd.DataFrame, df_15m: pd.DataFrame,
                             signal: str, fibonacci_analyzer: 'FibonacciAnalyzer' = None) -> Dict:
        """
        Encontra melhores níveis de entrada usando:
        1. Fibonacci (retração)
        2. Suporte/Resistência de 1h
        3. Liquidez (POI + FVG)
        
        Args:
            df_1h: DataFrame de 1h
            df_15m: DataFrame de 15m
            signal: BUY ou SELL
            fibonacci_analyzer: Analisador Fibonacci (opcional)
            
        Returns:
            Dict com níveis ideais de entrada
        """
        
        # Dados 1h
        current_price_1h = df_1h['close'].iloc[-1]
        swing_high_1h, swing_low_1h = FibonacciAnalyzer.find_swing_high_low(df_1h)
        
        # Dados 15m
        current_price_15m = df_15m['close'].iloc[-1]
        
        entry_levels = {
            'signal': signal,
            'primary_entry': current_price_15m,
            'alternative_entries': [],
            'criteria': []
        }
        
        if signal == 'BUY':
            # Para BUY: procurar suportes / níveis Fib em retração
            entry_levels['criteria'].append('Procurar retração de Fibonacci 0.618')
            entry_levels['criteria'].append('Aguardar teste de suporte de 1h')
            entry_levels['criteria'].append('Confirmar com volume (entrada em liquidez)')
            
            if fibonacci_analyzer:
                fib_retracement = fibonacci_analyzer.calculate_retracement(
                    swing_high_1h, swing_low_1h
                )
                entry_levels['fib_levels'] = fib_retracement['levels']
                
                # Nível ideal: 0.618 retração
                entry_levels['ideal_entry'] = fib_retracement['levels']['61%']['level']
        
        elif signal == 'SELL':
            # Para SELL: procurar resistências / níveis Fib em projeção
            entry_levels['criteria'].append('Procurar projeção de Fibonacci 0.382-0.618')
            entry_levels['criteria'].append('Aguardar teste de resistência de 1h')
            entry_levels['criteria'].append('Confirmar com volume (entrada em liquidez)')
            
            if fibonacci_analyzer:
                fib_projection = fibonacci_analyzer.calculate_projection(
                    swing_low_1h, swing_high_1h
                )
                entry_levels['fib_levels'] = fib_projection['levels']
                
                # Nível ideal: 0.618 projeção
                entry_levels['ideal_entry'] = fib_projection['levels']['61%']['level']
        
        return entry_levels


class MultipleTPManager:
    """
    Gerenciador de Múltiplos TPs
    
    Problema: Bybit não suporta enviar 3 TPs em um único sinal
    
    Solução:
    1. Criar trade sem TP (order aberta)
    2. Após confirmação do ordem, adicionar os 3 TPs
    
    Estrutura de TPs:
    - TP1 (0.382 RR): 50% do volume
    - TP2 (0.618 RR): 30% do volume
    - TP3 (1.0 RR): 20% do volume
    
    Vantagem: Tomar lucro em fases, preservar capital
    """
    
    def __init__(self):
        pass
    
    def create_signal_without_tp(self, symbol: str, signal_type: str,
                                entry: float, stop_loss: float,
                                quantity: float, leverage: int = 1) -> Dict:
        """
        Cria sinal/ordem SEM take profit
        
        Este será o primeiro trade aberto
        
        Args:
            symbol: Par (ex: BTCUSDT)
            signal_type: BUY ou SELL
            entry: Preço de entrada
            stop_loss: Preço de stop loss
            quantity: Quantidade
            leverage: Alavancagem
            
        Returns:
            Dict com sinal para enviar à exchange
        """
        
        signal = {
            'symbol': symbol,
            'side': signal_type,  # BUY ou SELL
            'type': 'LIMIT',  # ou MARKET
            'price': entry,
            'quantity': quantity,
            'leverage': leverage,
            'stop_loss': stop_loss,
            'take_profit': None,  # ❌ Sem TP inicialmente
            'order_tag': f'{symbol}_{signal_type}_NO_TP',
            'description': 'Ordem sem TP - aguardando confirmação para adicionar 3 TPs'
        }
        
        return signal
    
    def create_tp_orders(self, symbol: str, entry: float, stop_loss: float,
                        quantity: float, signal_type: str) -> Dict:
        """
        Cria 3 ordens de TP após confirmação da entrada
        
        Estas serão SUBORDENES da ordem principal
        
        Args:
            symbol: Par
            entry: Preço que entrou
            stop_loss: Stop loss confirmado
            quantity: Quantidade (será dividida entre TPs)
            signal_type: BUY ou SELL
            
        Returns:
            Dict com 3 TPs estruturados
        """
        
        # Calcular TPs usando Fibonacci
        fib_calc = FibonacciAnalyzer().calculate_tp_levels(entry, stop_loss)
        
        # Dividir quantidade entre os 3 TPs
        # TP1: 50% do volume | TP2: 30% | TP3: 20%
        qty_tp1 = quantity * 0.5
        qty_tp2 = quantity * 0.3
        qty_tp3 = quantity * 0.2
        
        # Determinar lado oposto ao sinal
        tp_side = 'SELL' if signal_type == 'BUY' else 'BUY'
        
        tp_orders = {
            'parent_signal': f'{symbol}_{signal_type}',
            'entry': entry,
            'stop_loss': stop_loss,
            'total_quantity': quantity,
            'tp_orders': [
                {
                    'tp_number': 1,
                    'side': tp_side,
                    'price': fib_calc['tp1'],
                    'quantity': qty_tp1,
                    'quantity_pct': '50%',
                    'risk_reward': '1:0.382',
                    'type': 'LIMIT',
                    'order_tag': f'{symbol}_TP1_0382'
                },
                {
                    'tp_number': 2,
                    'side': tp_side,
                    'price': fib_calc['tp2'],
                    'quantity': qty_tp2,
                    'quantity_pct': '30%',
                    'risk_reward': '1:0.618',
                    'type': 'LIMIT',
                    'order_tag': f'{symbol}_TP2_0618'
                },
                {
                    'tp_number': 3,
                    'side': tp_side,
                    'price': fib_calc['tp3'],
                    'quantity': qty_tp3,
                    'quantity_pct': '20%',
                    'risk_reward': '1:1.0',
                    'type': 'LIMIT',
                    'order_tag': f'{symbol}_TP3_1000'
                }
            ],
            'total_tp_quantity': qty_tp1 + qty_tp2 + qty_tp3,
            'description': f'3 TPs: {fib_calc["tp1"]:.8f} | {fib_calc["tp2"]:.8f} | {fib_calc["tp3"]:.8f}'
        }
        
        return tp_orders
    
    def generate_complete_trade_plan(self, symbol: str, signal_type: str,
                                    entry: float, stop_loss: float,
                                    quantity: float, leverage: int = 1) -> Dict:
        """
        Gera plano completo de trading com fase 1 (entrada) + fase 2 (TPs)
        
        Args:
            symbol: Par
            signal_type: BUY ou SELL
            entry: Preço de entrada
            stop_loss: Preço de stop loss
            quantity: Quantidade total
            leverage: Alavancagem
            
        Returns:
            Dict com plano completo em 2 fases
        """
        
        # Fase 1: Criar ordem sem TP
        phase1 = self.create_signal_without_tp(symbol, signal_type, entry, 
                                              stop_loss, quantity, leverage)
        
        # Fase 2: Preparar TPs (para enviar após confirmação)
        phase2 = self.create_tp_orders(symbol, entry, stop_loss, quantity, signal_type)
        
        # Calcular métricas
        fib_calc = FibonacciAnalyzer().calculate_tp_levels(entry, stop_loss)
        risk = abs(entry - stop_loss)
        
        # Preço medio esperado da carteira (media ponderada dos TPs)
        weighted_exit = (
            phase2['tp_orders'][0]['price'] * 0.5 +
            phase2['tp_orders'][1]['price'] * 0.3 +
            phase2['tp_orders'][2]['price'] * 0.2
        )
        
        return {
            'symbol': symbol,
            'signal_type': signal_type,
            'phase1': phase1,  # Enviar imediatamente
            'phase2': phase2,  # Enviar após confirmação de entrada
            'metrics': {
                'entry': entry,
                'stop_loss': stop_loss,
                'risk': risk,
                'tp1': fib_calc['tp1'],
                'tp2': fib_calc['tp2'],
                'tp3': fib_calc['tp3'],
                'avg_exit': weighted_exit,
                'total_risk_reward': ((weighted_exit - entry) / risk) if signal_type == 'BUY' else ((entry - weighted_exit) / risk)
            },
            'execution_plan': [
                '1. Enviar PHASE 1: ordem sem TP',
                '2. Aguardar confirmação (ordem aberta)',
                '3. Enviar PHASE 2: adicionar 3 TP orders',
                '4. Gerenciar: observar TP1 → TP2 → TP3'
            ]
        }
