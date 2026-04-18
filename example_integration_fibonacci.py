"""
Exemplo Prático: Integração Completa Fibonacci + Multi-Timeframe + TPs
"""

# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
import numpy as np
from src.fibonacci_multi_timeframe import (
    FibonacciAnalyzer,
    MultiTimeframeValidator,
    MultipleTPManager
)


def load_or_create_sample_data():
    """Cria dados de exemplo ou carrega dados reais"""
    
    # Simular dados BTCUSDT 1h e 15m
    np.random.seed(42)
    
    # 1h: 100 candles (100 horas = ~4 dias)
    base_price_1h = 45000
    prices_1h = []
    for i in range(100):
        trend = (i * 10) + np.random.normal(0, 50)
        prices_1h.append(base_price_1h + trend)
    
    df_1h = pd.DataFrame({
        'open': prices_1h + np.random.uniform(-50, 50, 100),
        'high': prices_1h + np.abs(np.random.normal(100, 30, 100)),
        'low': prices_1h - np.abs(np.random.normal(100, 30, 100)),
        'close': prices_1h,
        'volume': np.random.uniform(100, 500, 100) * 1000
    })
    
    # 15m: 400 candles (400 * 15min = ~100 horas = mesma duração de 1h, mas em 15m)
    base_price_15m = prices_1h[-1]
    prices_15m = []
    for i in range(400):
        trend = (i * 2) + np.random.normal(0, 20)
        prices_15m.append(base_price_15m + trend)
    
    df_15m = pd.DataFrame({
        'open': prices_15m + np.random.uniform(-20, 20, 400),
        'high': prices_15m + np.abs(np.random.normal(40, 15, 400)),
        'low': prices_15m - np.abs(np.random.normal(40, 15, 400)),
        'close': prices_15m,
        'volume': np.random.uniform(50, 200, 400) * 1000
    })
    
    return df_1h, df_15m


def print_separator(title: str = "", width: int = 120):
    """Imprime separador visual"""
    if title:
        padding = "─" * ((width - len(title) - 2) // 2)
        print(f"\n{padding} {title} {padding}")
    else:
        print("─" * width)


def scenario_1_perfect_alignment():
    """
    Scenario 1: Perfect Alignment
    
    1h = Strong Uptrend
    15m = Pullback for entry
    
    Expected result: VALID BUY SIGNAL with high confidence
    """
    
    print("\n" + "="*120)
    print("SCENARIO 1: PERFECT ALIGNMENT (1h Uptrend + 15m Pullback)")
    print("="*120)
    
    df_1h, df_15m = load_or_create_sample_data()
    
    validator = MultiTimeframeValidator()
    fib = FibonacciAnalyzer()
    tp_manager = MultipleTPManager()
    
    # Validar multi-timeframe
    print_separator("Validação Multi-Timeframe")
    mtf_result = validator.validate_multi_timeframe(df_1h, df_15m)
    
    print(f"\n✅ Resultado: {mtf_result['signal']}")
    print(f"   Válido: {mtf_result['is_valid']}")
    print(f"   Trend 1h: {mtf_result.get('trend_1h', 'N/A')}")
    print(f"   Signal 15m: {mtf_result.get('signal_15m', 'N/A')}")
    print(f"   Confidence 1h: {mtf_result.get('confidence_1h', 0):.0f}%")
    print(f"   Confidence 15m: {mtf_result.get('confidence_15m', 0):.0f}%")
    if mtf_result['is_valid']:
        print(f"   Final Confidence: {mtf_result.get('final_confidence', 0):.0f}%")
    
    # Se válido, calcular entrada
    if mtf_result['is_valid'] or mtf_result.get('signal') == 'HOLD':
        print_separator("Análise Fibonacci para Entrada")
        
        current_price_1h = df_1h['close'].iloc[-1]
        swing_high_1h, swing_low_1h = FibonacciAnalyzer.find_swing_high_low(df_1h)
        
        print(f"\n📊 Dados 1h:")
        print(f"   Current: {current_price_1h:.2f}")
        print(f"   Swing High: {swing_high_1h:.2f}")
        print(f"   Swing Low: {swing_low_1h:.2f}")
        
        # Para BUY: procurar entrada na retração 0.618
        retracement = fib.calculate_retracement(swing_high_1h, swing_low_1h)
        ideal_entry_buy = retracement['levels']['61%']['level']
        
        print(f"\n🎯 Para BUY (Retração 0.618): {ideal_entry_buy:.2f}")
        print(f"   ├─ TP1 (50% vol, RR 1:0.382)")
        print(f"   ├─ TP2 (30% vol, RR 1:0.618)")
        print(f"   └─ TP3 (20% vol, RR 1:1.0)")


def scenario_2_conflict():
    """
    Cenário 2: Conflito Entre Timeframes
    
    1h = Downtrend
    15m = Tentando dar BUY (contra 1h)
    
    Resultado esperado: VETO - Não operar
    """
    
    print("\n\n" + "="*120)
    print("CENÁRIO 2: CONFLITO (1h Downtrend vs 15m BUY)")
    print("="*120)
    
    print("\n⚠️  REGRA CRÍTICA: NUNCA operar contra 1h!")
    print("   Se 1h = DOWNTREND, rejeitar BUY de 15m")
    
    df_1h, df_15m = load_or_create_sample_data()
    
    # Simular downtrend em 1h
    df_1h['close'] = df_1h['close'].iloc[-1] - np.arange(len(df_1h)) * 10
    
    validator = MultiTimeframeValidator()
    mtf_result = validator.validate_multi_timeframe(df_1h, df_15m)
    
    print_separator("Validação Multi-Timeframe")
    
    print(f"\n❌ Resultado: {mtf_result['signal']}")
    print(f"   Válido: {mtf_result['is_valid']}")
    print(f"   Razão: {mtf_result['reason']}")
    print(f"   Análise: {mtf_result.get('analysis', '')}")


def scenario_3_entry_to_tp_cascade():
    """
    Cenário 3: Da Entrada até Cascata de TPs
    
    Trade completo: Entry → TP1 → TP2 → TP3
    """
    
    print("\n\n" + "="*120)
    print("CENÁRIO 3: CICLO COMPLETO DE TRADE")
    print("="*120)
    
    tp_manager = MultipleTPManager()
    fib = FibonacciAnalyzer()
    
    # Setup do trade
    symbol = "BTCUSDT"
    signal_type = "BUY"
    entry = 45500.00
    stop_loss = 45000.00
    quantity = 2.0
    
    print_separator("Trade Setup")
    
    print(f"\n📋 Configuração:")
    print(f"   Symbol: {symbol}")
    print(f"   Type: {signal_type} (Longo)")
    print(f"   Entry: {entry:.2f}")
    print(f"   Stop Loss: {stop_loss:.2f}")
    print(f"   Risk: ${abs(entry - stop_loss) * quantity:,.2f}")
    print(f"   Total Volume: {quantity}")
    
    # Gerar plano completo
    trade_plan = tp_manager.generate_complete_trade_plan(
        symbol, signal_type, entry, stop_loss, quantity
    )
    
    print_separator("Fase 1: Executar Ordem Inicial")
    
    phase1 = trade_plan['phase1']
    print(f"\n🚀 Enviar Ordem:")
    print(f"   Side: {phase1['side']}")
    print(f"   Price: {phase1['price']:.2f}")
    print(f"   Quantity: {phase1['quantity']}")
    print(f"   Stop Loss: {phase1['stop_loss']:.2f}")
    print(f"   Take Profit: {phase1['take_profit']} ← SEM TP (será adicionado)")
    print(f"\n   ✅ Ordem enviada para Bybit")
    
    print_separator("Aguardando Confirmação")
    
    print(f"\n⏳ Status:")
    print(f"   ├─ Ordem BUY {quantity} {symbol} @ {entry:.2f}")
    print(f"   ├─ Stop Loss @ {stop_loss:.2f}")
    print(f"   └─ Aguardando fill...")
    
    print_separator("Fase 2: Adicionar TPs (após fill)")
    
    phase2 = trade_plan['phase2']
    
    print(f"\n📊 Estrutura de TPs:")
    print(f"   Total Quantity: {phase2['total_quantity']:.2f}")
    
    total_tp_qty = 0
    for tp_order in phase2['tp_orders']:
        total_tp_qty += tp_order['quantity']
        print(f"\n   TP{tp_order['tp_number']} (SELL {tp_order['quantity']:.2f} @ {tp_order['price']:.2f}):")
        print(f"      Volume: {tp_order['quantity_pct']}")
        print(f"      Expected Profit: ${(tp_order['price'] - entry) * tp_order['quantity']:,.2f}")
        print(f"      RR: {tp_order['risk_reward']}")
    
    print(f"\n   ✅ Total TP Quantity: {total_tp_qty:.2f}")
    
    print_separator("Simulação de Execução")
    
    metrics = trade_plan['metrics']
    
    # Simulação TP1
    print(f"\n🔴 TP1 @ {metrics['tp1']:.2f} ATINGIDO")
    profit_tp1 = (metrics['tp1'] - metrics['entry']) * phase2['tp_orders'][0]['quantity']
    print(f"    └─ Lucro: ${profit_tp1:,.2f} (50% de {quantity} vendido)")
    
    # Simulação TP2
    print(f"\n🟡 TP2 @ {metrics['tp2']:.2f} ATINGIDO")
    profit_tp2 = (metrics['tp2'] - metrics['entry']) * phase2['tp_orders'][1]['quantity']
    print(f"    └─ Lucro: ${profit_tp2:,.2f} (30% de {quantity} vendido)")
    
    # Simulação TP3
    print(f"\n🟢 TP3 @ {metrics['tp3']:.2f} ATINGIDO")
    profit_tp3 = (metrics['tp3'] - metrics['entry']) * phase2['tp_orders'][2]['quantity']
    print(f"    └─ Lucro: ${profit_tp3:,.2f} (20% de {quantity} vendido)")
    
    total_profit = profit_tp1 + profit_tp2 + profit_tp3
    print(f"\n💰 LUCRO TOTAL: ${total_profit:,.2f}")
    print(f"   └─ RR Final: 1:{abs(total_profit / (abs(entry - stop_loss) * quantity)):.3f}")
    
    print_separator("Análise Completa")
    
    print(f"\n📈 Métricas Finais:")
    print(f"   Entry: {metrics['entry']:.2f}")
    print(f"   Stop Loss: {metrics['stop_loss']:.2f}")
    print(f"   Risk: ${metrics['risk'] * quantity:,.2f}")
    print(f"   Average Exit: {metrics['avg_exit']:.2f}")
    print(f"   Expected Profit (avg): ${(metrics['avg_exit'] - metrics['entry']) * quantity:,.2f}")


def main():
    """Executa todos os cenários"""
    
    print("\n" + "="*120)
    print("[DEMO] FIBONACCI + MULTI-TIMEFRAME + MULTIPLE TPS SYSTEM")
    print("="*120)
    
    # Cenário 1
    scenario_1_perfect_alignment()
    
    # Cenário 2
    scenario_2_conflict()
    
    # Cenário 3
    scenario_3_entry_to_tp_cascade()
    
    print("\n" + "="*120)
    print("✅ DEMONSTRAÇÃO CONCLUÍDA")
    print("="*120)
    print("\n💡 DICAS:")
    print("   1. Sempre confirmar tendência em 1h antes de usar sinal de 15m")
    print("   2. NUNCA operar contra 1h (regra de ouro)")
    print("   3. Usar Fibonacci para encontrar entradas em zonas de suporte/resistência")
    print("   4. Usar multiple TPs para bloquear lucros graduais (0.382, 0.618, 1.0)")
    print("   5. Adaptar a quantidade em cada TP com base em risco/recompensa\n")


if __name__ == "__main__":
    main()
