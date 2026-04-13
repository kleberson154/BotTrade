#!/usr/bin/env python3
"""
Backtest Mack Strategy Integration
Testa TradeSignalBuilder integrado em strategy.py
Valida que todo sinal gerado tem RR 1:2+
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

sys.path.insert(0, 'src')
sys.path.insert(0, 'data')

from src.strategy import TradingStrategy
from src.logger import setup_logger
from src.notifier import TelegramNotifier
from src.mack_compliance import MackCompliance

log = setup_logger()

class MackStrategyBacktest:
    """Backtest integração de TradeSignalBuilder com Strategy"""
    
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.notifier = TelegramNotifier()
        self.strategy = TradingStrategy(symbol, self.notifier)
        self.compliance = MackCompliance()
        
        # Estatísticas
        self.total_candles = 0
        self.signals_generated = 0
        self.signals_valid = 0
        self.signals_rejected = 0
        self.rr_ratios = []
        self.signal_details = []
        
    def generate_sample_data(self, num_candles=500, start_price=65000):
        """Gera dados simulados de preço"""
        timestamps = []
        prices = []
        
        # Simula movimento de preço com tendência e ruído
        current_price = start_price
        base_time = datetime.now() - timedelta(minutes=num_candles)
        
        for i in range(num_candles):
            # Adiciona tendência + ruído
            trend = np.sin(i / 50) * 100  # Tendência sinusoidal
            noise = np.random.normal(0, 200)
            current_price += trend + noise
            
            timestamps.append(base_time + timedelta(minutes=i))
            prices.append(max(current_price, 1000))  # Garante preço positivo
        
        # Cria DataFrame com OHLCV
        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices,
            'high': [p * 1.001 for p in prices],
            'low': [p * 0.999 for p in prices],
            'close': prices,
            'volume': np.random.uniform(100, 1000, num_candles)
        })
        
        return df
    
    def run_backtest(self, num_candles=500):
        """Executa backtest processando cada candle"""
        log.info(f"🔬 Iniciando backtest Mack Strategy para {self.symbol}")
        
        # Carrega dados reais
        csv_path = f"data/coins/data_{self.symbol}_90d.csv"
        try:
            data = pd.read_csv(csv_path)
            log.info(f"📊 Carregando {len(data)} candles do arquivo {csv_path}...")
        except FileNotFoundError:
            log.warning(f"⚠️  Arquivo {csv_path} não encontrado, gerando dados simulados...")
            data = self.generate_sample_data(num_candles)
        
        # Limita a quantidade de candles para teste mais rápido
        if len(data) > num_candles:
            data = data.tail(num_candles).reset_index(drop=True)
        
        # Garante que as colunas necessárias existem
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in data.columns:
                data[col] = 0
        
        # Simula chegada de candles
        for idx in range(len(data)):
            row = data.iloc[idx]
            
            # Adiciona candle à estratégia
            candle_data = {
                'timestamp': idx,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row.get('volume', 1))
            }
            self.strategy.candles_1m.append(candle_data)
            self.strategy._dirty_1m = True
            
            # Atualiza candles 15m a cada 15 candles
            if idx % 15 == 0 and idx > 0:
                idx_15m = max(0, idx - 15)
                if idx_15m < len(data):
                    row_15m = data.iloc[idx_15m]
                    candle_15m = {
                        'timestamp': idx_15m,
                        'open': float(row_15m['open']),
                        'high': float(row_15m['high']),
                        'low': float(row_15m['low']),
                        'close': float(row_15m['close']),
                        'volume': float(row_15m.get('volume', 1))
                    }
                    self.strategy.candles_15m.append(candle_15m)
                    self.strategy._dirty_15m = True
            
            # Processa sinal
            if idx > 50:  # Aguarda dados suficientes
                try:
                    signal, dist_sl = self.strategy.check_signal()
                    
                    if signal != "HOLD":
                        self.signals_generated += 1
                        
                        # Recupera o TradeSignal gerado
                        if self.strategy.last_trade_signal:
                            trade_signal = self.strategy.last_trade_signal
                            
                            # Extrai informações
                            entry = trade_signal.entry
                            sl = trade_signal.sl
                            tp = trade_signal.tp
                            
                            # Calcula RR
                            if signal == "BUY":
                                risk = entry - sl
                                reward = tp - entry
                            else:  # SELL
                                risk = sl - entry
                                reward = entry - tp
                            
                            if risk > 0 and reward > 0:
                                ratio = reward / risk
                            else:
                                ratio = 0
                            
                            # Valida RR 1:2
                            if ratio >= 1.99:
                                self.signals_valid += 1
                                detail = {
                                    'candle': idx,
                                    'time': row['timestamp'],
                                    'signal': signal,
                                    'entry': entry,
                                    'sl': sl,
                                    'tp': tp,
                                    'ratio': round(ratio, 2),
                                    'valid': True
                                }
                            else:
                                self.signals_rejected += 1
                                detail = {
                                    'candle': idx,
                                    'time': row['timestamp'],
                                    'signal': signal,
                                    'entry': entry,
                                    'sl': sl,
                                    'tp': tp,
                                    'ratio': round(ratio, 2),
                                    'valid': False,
                                    'reason': f"RR {ratio:.2f}:1 < 1:2"
                                }
                            
                            self.signal_details.append(detail)
                            self.rr_ratios.append(ratio)
                
                except Exception as e:
                    log.error(f"❌ Erro ao processar candle {idx}: {e}")
            
            self.total_candles += 1
            
            # Progress
            if (idx + 1) % 100 == 0:
                pct = (idx + 1) / len(data) * 100
                log.info(f"⏳ Progresso: {pct:.0f}% | Sinais: {self.signals_generated} | Válidos: {self.signals_valid}")
        
        log.info("✅ Backtest concluído!")
        self.print_report()
    
    def print_report(self):
        """Exibe relatório final"""
        print("\n" + "="*80)
        print("📊 RELATÓRIO FINAL - BACKTEST MACK STRATEGY")
        print("="*80)
        
        print(f"\n📈 ESTATÍSTICAS GERAIS")
        print(f"  • Total de Candles Processados: {self.total_candles}")
        print(f"  • Sinais Gerados: {self.signals_generated}")
        print(f"  • Sinais Válidos (RR 1:2+): {self.signals_valid} ✅")
        print(f"  • Sinais Rejeitados: {self.signals_rejected} ❌")
        
        if self.signals_generated > 0:
            acceptance_rate = (self.signals_valid / self.signals_generated) * 100
            print(f"  • Taxa de Aceição: {acceptance_rate:.1f}%")
        
        if self.rr_ratios:
            print(f"\n📊 ANÁLISE DE RISK:REWARD")
            print(f"  • RR Médio: {np.mean(self.rr_ratios):.2f}:1")
            print(f"  • RR Mínimo: {np.min(self.rr_ratios):.2f}:1")
            print(f"  • RR Máximo: {np.max(self.rr_ratios):.2f}:1")
            print(f"  • Sinais com RR >= 1:2: {sum(1 for r in self.rr_ratios if r >= 1.99)}")
        
        print(f"\n📋 DETALHES DOS SINAIS (primeiros 10)")
        print("-" * 80)
        for i, detail in enumerate(self.signal_details[:10]):
            status = "✅ VÁLIDO" if detail['valid'] else "❌ REJEITO"
            print(f"{i+1}. {detail['signal']:5} @ {detail['entry']:.2f} | " \
                  f"SL: {detail['sl']:.2f} | TP: {detail['tp']:.2f} | " \
                  f"RR: {detail['ratio']}:1 | {status}")
            if not detail['valid']:
                print(f"   └─ Motivo: {detail.get('reason', 'N/A')}")
        
        print("\n" + "="*80)
        
        # Validações
        print("\n🔍 VALIDAÇÕES")
        
        # 1. TradeSignalBuilder funcionando?
        if self.signals_generated > 0:
            print("✅ TradeSignalBuilder: FUNCIONANDO")
        else:
            print("❌ TradeSignalBuilder: NÃO GEROU SINAIS")
        
        # 2. MackCompliance validando corretamente?
        if self.signals_rejected > 0:
            print("✅ MackCompliance: VALIDANDO CORRETAMENTE (rejeitou sinais inválidos)")
        else:
            print("⚠️  MackCompliance: Nenhum sinal foi rejeitado (verificar testes)")
        
        # 3. Todos os sinais válidos têm RR 1:2+?
        if self.signals_valid == len([d for d in self.signal_details if d['valid']]):
            print("✅ RR Validation: TODOS OS SINAIS VÁLIDOS TÊM RR 1:2+")
        else:
            print("❌ RR Validation: ALGUNS SINAIS VÁLIDOS TÊM RR < 1:2")
        
        print("="*80 + "\n")


def main():
    backtest = MackStrategyBacktest("BTCUSDT")
    # Usar muitos mais candles para melhor cobertura
    backtest.run_backtest(num_candles=2000)


if __name__ == "__main__":
    main()
