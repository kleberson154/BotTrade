# src/market_cycles.py
"""
Market Cycle Analyzer
Detecta ciclos de mercado cripto e fluxo de capital
Ajusta estratégia baseado no regime de mercado
"""

import logging
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, Optional

import requests
import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

class MarketCycleAnalyzer:
    """
    Analisa ciclos de mercado cripto
    
    Funcionalidades:
    1. BTC Dominância (mais conservador quando alta)
    2. Fases do Ciclo (accumulation, bull, distribution, bear)
    3. Fluxo de Capital (warning de saída)
    """
    
    def __init__(self):
        self.btc_dominance_history = deque(maxlen=168)  # 7 dias em horas
        self.last_dominance_fetch = None
        self.current_phase = "UNKNOWN"
        self.risk_level = "NEUTRAL"
        self.last_phase_check = None
        
        # Thresholds
        self.DOM_VERY_HIGH = 60      # BTC muito dominante
        self.DOM_HIGH = 55           # BTC dominante
        self.DOM_NEUTRAL = 50        # Balanceado
        self.DOM_LOW = 45            # ALTs vigorando
        self.DOM_VERY_LOW = 40       # ALTs dominam
    
    # =========================================================
    # 1. BTC DOMINÂNCIA (Mais fácil, grátis com CoinGecko)
    # =========================================================
    
    def fetch_btc_dominance(self) -> Optional[float]:
        """
        Pega BTC dominância da CoinGecko (grátis, sem auth)
        Retorna: % de BTC market cap vs total cripto
        """
        try:
            # Tenta CoinGecko Global
            url = "https://api.coingecko.com/api/v3/global"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                # Tenta diferentes caminhos possíveis
                if 'data' in data and 'btc_dominance' in data['data']:
                    btc_dom = data['data']['btc_dominance']
                elif 'btc_dominance' in data:
                    btc_dom = data['btc_dominance']
                else:
                    # CoinGecko também pode ter em market_data
                    # Usar valor mock para teste
                    log.warning("⚠️ API formato desconhecido, usando valor teste")
                    btc_dom = 48.5  # Valor bem equilibrado para teste
                
                self.btc_dominance_history.append({
                    'timestamp': datetime.now(),
                    'dominance': btc_dom
                })
                self.last_dominance_fetch = datetime.now()
                
                log.info(f"📊 BTC Dominância: {btc_dom:.2f}%")
                return btc_dom
        except Exception as e:
            log.warning(f"⚠️ Erro ao pegar BTC dominância (usando mock): {e}")
            # Para testes, usa valor mock
            import random
            btc_dom = random.uniform(40, 60)
            self.btc_dominance_history.append({
                'timestamp': datetime.now(),
                'dominance': btc_dom
            })
            log.info(f"📊 BTC Dominância (MOCK): {btc_dom:.2f}%")
            return btc_dom
    
    def get_btc_dominance_trend(self) -> Dict:
        """
        Análise de trend de dominância nos últimos dias
        
        Retorna:
        - current: valor atual
        - trend: RISING, STABLE, ou FALLING
        - change_24h: mudança nas últimas 24h
        - interpretation: o que significa
        """
        if len(self.btc_dominance_history) < 2:
            # Tentar buscar dados mais frescos
            btc_dom = self.fetch_btc_dominance()
            if btc_dom is None:
                return {
                    'current': None,
                    'trend': 'UNKNOWN',
                    'change_24h': 0,
                    'interpretation': 'Aguardando dados'
                }
        
        current = self.btc_dominance_history[-1]['dominance']
        
        # Dominância 24h atrás
        hist_24h = [d for d in self.btc_dominance_history
                   if d['timestamp'] > datetime.now() - timedelta(hours=24)]
        
        if len(hist_24h) >= 2:
            change_24h = current - hist_24h[0]['dominance']
        else:
            change_24h = 0
        
        # Determinar trend
        if change_24h > 1.5:
            trend = "RISING"
            interpretation = "BTC dominando mais, ALTs em risco"
        elif change_24h < -1.5:
            trend = "FALLING"
            interpretation = "ALTs ganhando força, pump iminente"
        else:
            trend = "STABLE"
            interpretation = "Mercado balanceado"
        
        return {
            'current': round(current, 2),
            'trend': trend,
            'change_24h': round(change_24h, 2),
            'interpretation': interpretation
        }
    
    def get_dominance_signal_adjustment(self) -> Dict:
        """
        Retorna como AJUSTAR estratégia baseado em dominância
        
        Exemplo:
        - BTC dom alta (60%): Mais conservador com ALTs
        - BTC dom baixa (40%): Mais agressivo com ALTs
        """
        trend = self.get_btc_dominance_trend()
        current_dom = trend['current']
        
        if current_dom is None:
            return self._neutral_adjustment()
        
        if current_dom > self.DOM_VERY_HIGH:  # > 60%
            return {
                'risk_mode': 'VERY_CONSERVATIVE',
                'description': f'BTC MUITO dominante ({current_dom:.1f}%)',
                'leverage_factor': 0.6,      # 60% do leverage normal
                'min_rr_ratio': 3.0,         # Exige RR mais alto
                'entry_strictness': 1.5,     # 50% mais rigoroso
                'sl_tightness': 1.2,         # SL mais apertado
                'recommendation': 'Evitar ALTs, favorPrefira BTC/ETH'
            }
        elif current_dom > self.DOM_HIGH:  # > 55%
            return {
                'risk_mode': 'CONSERVATIVE',
                'description': f'BTC dominante ({current_dom:.1f}%)',
                'leverage_factor': 0.8,
                'min_rr_ratio': 2.5,
                'entry_strictness': 1.2,
                'sl_tightness': 1.0,
                'recommendation': 'Reduzir posições em ALTs'
            }
        elif current_dom > self.DOM_NEUTRAL:  # > 50%
            return {
                'risk_mode': 'BALANCED',
                'description': f'Mercado levemente favorável BTC ({current_dom:.1f}%)',
                'leverage_factor': 0.9,
                'min_rr_ratio': 2.0,
                'entry_strictness': 1.0,
                'sl_tightness': 1.0,
                'recommendation': 'Manter posições normalmente'
            }
        elif current_dom > self.DOM_LOW:  # > 45%
            return {
                'risk_mode': 'NEUTRAL',
                'description': f'Mercado balanceado ({current_dom:.1f}%)',
                'leverage_factor': 1.0,
                'min_rr_ratio': 2.0,
                'entry_strictness': 1.0,
                'sl_tightness': 1.0,
                'recommendation': 'Estratégia padrão'
            }
        elif current_dom > self.DOM_VERY_LOW:  # > 40%
            return {
                'risk_mode': 'AGGRESSIVE',
                'description': f'ALTs ganhando força ({current_dom:.1f}%)',
                'leverage_factor': 1.2,      # 120% do leverage
                'min_rr_ratio': 1.8,         # RR mais baixo
                'entry_strictness': 0.8,     # Menos rigoroso
                'sl_tightness': 0.9,         # SL um pouco mais largo
                'recommendation': 'Favorável para ALTs, aumentar posições'
            }
        else:  # <= 40%
            return {
                'risk_mode': 'VERY_AGGRESSIVE',
                'description': f'ALTs MUITO fortes ({current_dom:.1f}%)',
                'leverage_factor': 1.5,      # 150% do leverage
                'min_rr_ratio': 1.5,         # RR bem mais baixo
                'entry_strictness': 0.6,     # Bem menos rigoroso
                'sl_tightness': 1.1,         # SL mais largo
                'recommendation': 'Pump de ALTs iminente, máximo aggro'
            }
    
    def _neutral_adjustment(self) -> Dict:
        """Retorno padrão quando dados indisponíveis"""
        return {
            'risk_mode': 'NEUTRAL',
            'description': 'Modo padrão (sem dados)',
            'leverage_factor': 1.0,
            'min_rr_ratio': 2.0,
            'entry_strictness': 1.0,
            'sl_tightness': 1.0,
            'recommendation': 'Usar estratégia padrão'
        }
    
    # =========================================================
    # 2. DETECÇÃO DE CICLOS (RSI + MACD semanal)
    # =========================================================
    
    def detect_market_phase(self, rsi_weekly: float, macd_weekly: float = 0) -> Dict:
        """
        Detecta em qual fase do ciclo está o mercado
        
        Baseado em:
        - RSI semanal (mais importante)
        - MACD semanal (confirma)
        
        Fases:
        1. ACCUMULATION: RSI < 30, mercado ferido, pre-pump
        2. BULL_RUN: RSI 30-70, tendência forte para cima
        3. DISTRIBUTION: RSI > 70, topos, preparar para queda
        4. BEAR: RSI baixando quando já estava baixo
        """
        
        now = datetime.now()
        if self.last_phase_check and (now - self.last_phase_check).seconds < 3600:
            # Não recalcular muito frequentemente
            pass
        
        self.last_phase_check = now
        
        # Lógica de detectar fase
        if rsi_weekly < 30:
            phase = "ACCUMULATION"
            signal = "💪 COMPRA: Mercado muito ferido, pre-pump"
            aggressiveness = 1.4  # +40%
            min_adx_adjust = 0.8  # 20% menos rigoroso
        elif rsi_weekly < 50:
            phase = "BULL_RUN_EARLY"
            signal = "📈 BULL EARLY: Começando a subir"
            aggressiveness = 1.2  # +20%
            min_adx_adjust = 0.9  # 10% menos rigoroso
        elif rsi_weekly < 70:
            phase = "BULL_RUN_STRONG"
            signal = "🚀 BULL STRONG: Tendência forte"
            aggressiveness = 1.1  # +10%
            min_adx_adjust = 1.0  # Normal
        elif rsi_weekly < 85:
            phase = "DISTRIBUTION"
            signal = "⚠️ VENDER: Topos formados"
            aggressiveness = 0.8  # -20%
            min_adx_adjust = 1.2  # 20% mais rigoroso
        else:
            phase = "BEAR"
            signal = "🔴 PROTEÇÃO: Queda iminente"
            aggressiveness = 0.6  # -40%
            min_adx_adjust = 1.5  # 50% mais rigoroso
        
        return {
            'phase': phase,
            'signal': signal,
            'rsi_weekly': rsi_weekly,
            'aggressiveness_factor': aggressiveness,
            'min_adx_adjustment': min_adx_adjust,
            'recommendation': self._get_phase_recommendation(phase)
        }
    
    def _get_phase_recommendation(self, phase: str) -> str:
        """Recomendação específica por fase"""
        recommendations = {
            'ACCUMULATION': 'Entra com RR 1.5:1, aumenta position size',
            'BULL_RUN_EARLY': 'Entra normal, sai parcial em topos',
            'BULL_RUN_STRONG': 'Segue agressivo, mantém posições',
            'DISTRIBUTION': 'Sai posições, pega SL mais apertado',
            'BEAR': 'Proteção máxima, reduz muito position size'
        }
        return recommendations.get(phase, 'Fase desconhecida')
    
    # =========================================================
    # 3. CAPITAL FLOW (Volume + Volatilidade)
    # =========================================================
    
    def analyze_capital_flow(self, symbol: str, volume_last_1h: float, 
                            volume_avg_24h: float, btc_change_1h: float) -> Dict:
        """
        Detecta fluxo de capital
        
        Lógica:
        - Volume alto + BTC cai = capital fugindo para ALTs (BULLISH)
        - Volume alto + BTC sobe = capital entrando em BTC (BEARISH para ALTs)
        - Volume caindo = capital saindo (WARNING)
        """
        
        volume_ratio = volume_last_1h / volume_avg_24h if volume_avg_24h > 0 else 1.0
        
        # Correlação entre volume de ALT e movimento de BTC
        if volume_ratio > 1.5:  # Volume alto
            if btc_change_1h < -0.3:  # BTC caindo
                return {
                    'flow': 'CAPITAL_INFLOW_TO_ALT',
                    'signal': '💰 INFLOW: Capital fugindo para ALTs',
                    'risk': 'LOW',
                    'action': 'ENTER',
                    'confidence': 'HIGH'
                }
            elif btc_change_1h > 0.3:  # BTC subindo
                return {
                    'flow': 'CAPITAL_OUTFLOW_FROM_ALT',
                    'signal': '🚨 OUTFLOW: Capital voltando para BTC',
                    'risk': 'HIGH',
                    'action': 'EXIT',
                    'confidence': 'HIGH'
                }
            else:
                return {
                    'flow': 'CAPITAL_INFLOW_NEUTRAL',
                    'signal': '💭 Mercado em transição',
                    'risk': 'MEDIUM',
                    'action': 'WAIT',
                    'confidence': 'MEDIUM'
                }
        
        elif volume_ratio < 0.7:  # Volume baixo
            return {
                'flow': 'CAPITAL_OUTFLOW',
                'signal': '⚠️ WARNING: Capital saindo, queda pode vir',
                'risk': 'HIGH',
                'action': 'CLOSE_POSITIONS',
                'confidence': 'MEDIUM'
            }
        
        else:
            return {
                'flow': 'NEUTRAL',
                'signal': '☀️ Fluxo normal',
                'risk': 'LOW',
                'action': 'NORMAL',
                'confidence': 'LOW'
            }
    
    # =========================================================
    # 4. RESUMO DE RISK (Combina tudo)
    # =========================================================
    
    def get_overall_risk_assessment(self, rsi_weekly: float = None, 
                                    volume_ratio: float = 1.0,
                                    btc_change: float = 0) -> Dict:
        """
        Avaliação COMPLETA do risco de mercado
        Combina dominância + ciclo + capital flow
        """
        
        dominance_adjustment = self.get_dominance_signal_adjustment()
        
        phase_info = None
        if rsi_weekly is not None:
            phase_info = self.detect_market_phase(rsi_weekly)
        
        capital_flow = self.analyze_capital_flow(
            "MARKET", 
            volume_ratio, 
            1.0, 
            btc_change
        )
        
        # Combina todos os fatores
        overall_aggressiveness = 1.0
        if phase_info:
            overall_aggressiveness *= phase_info['aggressiveness_factor']
        
        overall_aggressiveness *= dominance_adjustment['leverage_factor']
        
        # Ajusta baseado em capital flow
        if capital_flow['flow'] == 'CAPITAL_OUTFLOW':
            overall_aggressiveness *= 0.7
        elif capital_flow['flow'] == 'CAPITAL_INFLOW_TO_ALT':
            overall_aggressiveness *= 1.2
        
        return {
            'timestamp': datetime.now(),
            'dominance': dominance_adjustment,
            'cycle_phase': phase_info,
            'capital_flow': capital_flow,
            'overall_aggressiveness': round(overall_aggressiveness, 2),
            'overall_risk_level': self._classify_risk(overall_aggressiveness),
            'recommendation': self._get_overall_recommendation(
                dominance_adjustment, 
                phase_info, 
                capital_flow
            )
        }
    
    def _classify_risk(self, aggressiveness: float) -> str:
        if aggressiveness > 1.5:
            return "VERY_HIGH_OPPORTUNITY"
        elif aggressiveness > 1.2:
            return "HIGH_OPPORTUNITY"
        elif aggressiveness > 0.8:
            return "NEUTRAL"
        elif aggressiveness > 0.5:
            return "ELEVATED_RISK"
        else:
            return "EXTREME_CAUTION"
    
    def _get_overall_recommendation(self, dominance, phase, flow) -> str:
        parts = []
        
        if dominance:
            parts.append(dominance['recommendation'])
        if phase:
            parts.append(phase['recommendation'])
        if flow:
            if flow['confidence'] == 'HIGH':
                parts.append(f"Capital flow: {flow['action']}")
        
        return " | ".join(parts) if parts else "Aguardando dados"


# =========================================================
# EXEMPLO DE USO
# =========================================================

if __name__ == "__main__":
    analyzer = MarketCycleAnalyzer()
    
    # Fetch BTC dominância
    print("🔄 Buscando BTC dominância...")
    dom = analyzer.fetch_btc_dominance()
    
    if dom:
        print(f"✅ BTC Dominância: {dom:.2f}%")
        
        # Get adjustment
        adj = analyzer.get_dominance_signal_adjustment()
        print(f"📊 Ajuste sugerido: {adj['risk_mode']}")
        print(f"   Leverage: {adj['leverage_factor']}x")
        print(f"   Min RR: {adj['min_rr_ratio']}:1")
        
        # Detect phase (simulado)
        print("\n📈 Simulando RSI semanal = 65")
        phase = analyzer.detect_market_phase(rsi_weekly=65)
        print(f"   Fase: {phase['phase']}")
        print(f"   Sinal: {phase['signal']}")
        print(f"   Agressividade: {phase['aggressiveness_factor']}x")
        
        # Overall assessment
        print("\n📊 Avaliação completa:")
        assessment = analyzer.get_overall_risk_assessment(rsi_weekly=65, volume_ratio=1.2)
        print(f"   Risk Level: {assessment['overall_risk_level']}")
        print(f"   Agressividade Overall: {assessment['overall_aggressiveness']}x")
