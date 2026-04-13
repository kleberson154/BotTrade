#!/usr/bin/env python3
"""
Teste Simples de Integração Mack
Verifica que TradeSignalBuilder e MackCompliance funcionam em strategy.py
"""

import sys
sys.path.insert(0, 'src')
sys.path.insert(0, 'data')

import logging
import pandas as pd
from src.strategy import TradingStrategy
from src.notifier import TelegramNotifier
from src.signal_formatter import TradeSignalBuilder, SignalProfile
from src.mack_compliance import MackCompliance

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def test_trade_signal_builder():
    """Testa criação de TradeSignal"""
    log.info("=" * 80)
    log.info("🧪 TESTE 1: TradeSignalBuilder")
    log.info("=" * 80)
    
    try:
        signal = (TradeSignalBuilder("BTCUSDT", "BUY", 65000)
            .with_stops(64000, 67000)
            .with_leverage(10)
            .with_profile(SignalProfile.BALANCED)
            .build())
        
        log.info(f"✅ TradeSignal criado com sucesso!")
        log.info(f"   • Símbolo: {signal.symbol}")
        log.info(f"   • Side: {signal.side}")
        log.info(f"   • Entry: {signal.entry}")
        log.info(f"   • SL: {signal.sl}")
        log.info(f"   • TP: {signal.tp}")
        return True
    except Exception as e:
        log.error(f"❌ Erro ao criar TradeSignal: {e}")
        return False


def test_mack_compliance():
    """Testa validação Mack"""
    log.info("\n" + "=" * 80)
    log.info("🧪 TESTE 2: MackCompliance - Validação RR")
    log.info("=" * 80)
    
    try:
        compliance = MackCompliance()
        
        # Teste 1: RR válido (1:2)
        result_valid = compliance.validate_rr_ratio(
            entry=100,
            sl=90,
            tp=120,
            side="LONG",
            symbol="TEST"
        )
        
        log.info(f"✅ RR Válido (1:2):")
        log.info(f"   • Ratio: {result_valid['ratio']}:1")
        log.info(f"   • Valid: {result_valid['valid']}")
        
        # Teste 2: RR inválido (<1:2)
        result_invalid = compliance.validate_rr_ratio(
            entry=100,
            sl=95,
            tp=105,
            side="LONG",
            symbol="TEST"
        )
        
        log.info(f"✅ RR Inválido (<1:2):")
        log.info(f"   • Ratio: {result_invalid['ratio']}:1")
        log.info(f"   • Valid: {result_invalid['valid']}")
        
        return True
    except Exception as e:
        log.error(f"❌ Erro em MackCompliance: {e}")
        return False


def test_strategy_integration():
    """Testa integração em TradingStrategy"""
    log.info("\n" + "=" * 80)
    log.info("🧪 TESTE 3: Integração em TradingStrategy")
    log.info("=" * 80)
    
    try:
        notifier = TelegramNotifier()
        strategy = TradingStrategy("BTCUSDT", notifier)
        
        log.info(f"✅ TradingStrategy instanciada com sucesso!")
        log.info(f"   • Símbolo: {strategy.symbol}")
        log.info(f"   • Compliance: {strategy.compliance is not None}")
        log.info(f"   • PositionSizer: {strategy.position_sizer is not None}")
        log.info(f"   • Account Balance: {strategy.account_balance}")
        
        # Carrega dados reais
        data = pd.read_csv("data/coins/data_BTCUSDT_90d.csv")
        log.info(f"✅ Dados carregados: {len(data)} candles")
        
        # Simula chegada de primeiros 200 candles
        for idx in range(min(200, len(data))):
            row = data.iloc[idx]
            candle = {
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row.get('volume', 1))
            }
            strategy.candles_1m.append(candle)
            strategy._dirty_1m = True
            
            if idx % 15 == 0:
                strategy.candles_15m.append(candle)
                strategy._dirty_15m = True
        
        # Tenta check_signal
        signal, dist_sl = strategy.check_signal()
        
        log.info(f"✅ check_signal() executada com sucesso!")
        log.info(f"   • Sinal: {signal}")
        log.info(f"   • Distância SL: {dist_sl}")
        
        if strategy.last_trade_signal:
            log.info(f"✅ TradeSignal foi criado e guardado!")
            log.info(f"   • Signal Side: {strategy.last_trade_signal.side}")
            log.info(f"   • Signal Entry: {strategy.last_trade_signal.entry}")
        else:
            log.info(f"⚠️  Nenhum TradeSignal criado (sinal pode ser HOLD)")
        
        return True
    except Exception as e:
        log.error(f"❌ Erro em Strategy Integration: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    log.info("\n🚀 TESTES DE INTEGRAÇÃO MACK\n")
    
    results = {
        "TradeSignalBuilder": test_trade_signal_builder(),
        "MackCompliance": test_mack_compliance(),
        "Strategy Integration": test_strategy_integration()
    }
    
    log.info("\n" + "=" * 80)
    log.info("📋 RESUMO DOS TESTES")
    log.info("=" * 80)
    
    for test_name, result in results.items():
        status = "✅ PASSOU" if result else "❌ FALHOU"
        log.info(f"{test_name}: {status}")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    log.info(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        log.info("🎉 Todos os testes passaram!")
    else:
        log.warning(f"⚠️  {total - passed} teste(s) falharam")


if __name__ == "__main__":
    main()
