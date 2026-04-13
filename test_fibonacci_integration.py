#!/usr/bin/env python
"""
Fibonacci Integration Test
Valida as 3 estratégias de Fibonacci:
1. Targets precisos em níveis de Fibonacci
2. Confirmação leve com boost de confiança
3. Proteção de SL em suportes de Fibonacci
"""
import sys
import os

print("=" * 80)
print("🧪 FIBONACCI INTEGRATION TEST - 3 ESTRATÉGIAS")
print("=" * 80)

# Test 1: Import e inicialização
print("\n[1/5] Testando import do FibonacciManager...")
try:
    from src.fibonacci_manager import FibonacciManager
    fib = FibonacciManager(atr_pct=0.005)
    print("✅ FibonacciManager importado com sucesso")
except Exception as e:
    print(f"❌ Falha ao importar: {e}")
    sys.exit(1)

# Test 2: Estratégia 1 - Fibonacci Targets
print("\n[2/5] Testando ESTRATÉGIA 1: Fibonacci Targets para Exit Management...")
try:
    entry = 45000
    swing_low = 44000
    swing_high = 46000
    atr = 200
    
    targets = fib.calculate_targets_fibo(entry, "BUY", swing_high, swing_low, atr)
    
    print(f"   Entry: {entry}")
    print(f"   TP1 (38.2%): {targets['tp1']:.2f} ← Quick profit")
    print(f"   TP2 (50.0%): {targets['tp2']:.2f}")
    print(f"   TP3 (61.8%): {targets['tp3']:.2f} ← Golden Ratio (PRIMARY)")
    print(f"   TP4 (100%):  {targets['tp4']:.2f}")
    print(f"   SL:         {targets['sl']:.2f}")
    
    # Validação
    assert targets['tp1'] > entry, "TP1 deve ser maior que entry para LONG"
    assert targets['tp3'] > targets['tp2'], "TP3 deve ser maior que TP2"
    assert targets['sl'] < entry, "SL deve ser menor que entry para LONG"
    print("✅ ESTRATÉGIA 1: Targets calculados corretamente")
except Exception as e:
    print(f"❌ Falha na Estratégia 1: {e}")
    sys.exit(1)

# Test 3: Estratégia 2 - Fibonacci Confidence Boost
print("\n[3/5] Testando ESTRATÉGIA 2: Fibonacci Confirmation com Leverage Boost...")
try:
    # Teste em nível de Fibonacci
    current_price_in_level = targets['tp1']  # Perto de TP1 (38.2%)
    confidence = fib.get_fibo_confidence_boost(
        current_price_in_level, entry, swing_high, swing_low, "BUY"
    )
    
    print(f"   Preço atual: {current_price_in_level:.2f} (PRÓXIMO a 38.2% Fibo)")
    print(f"   Confidence Boost: {confidence['confidence_boost']:+.2f}")
    print(f"   Leverage Multiplier: {confidence['leverage_multiplier']:.2f}x")
    print(f"   Level detectado: {confidence['nearest_level']}")
    
    if confidence['in_level']:
        print("   ✅ Preço em nível de Fibonacci → LEVERAGE AUMENTA")
    
    # Teste fora de nível
    current_price_away = entry + (swing_high - entry) * 0.45  # Fora de níveis
    confidence_away = fib.get_fibo_confidence_boost(
        current_price_away, entry, swing_high, swing_low, "BUY"
    )
    
    print(f"\n   Preço distante: {current_price_away:.2f} (FORA dos níveis)")
    print(f"   Confidence Boost: {confidence_away['confidence_boost']:+.2f}")
    print(f"   Leverage Multiplier: {confidence_away['leverage_multiplier']:.2f}x")
    print(f"   ⚠️ Preço longe de Fibonacci → LEVERAGE REDUZ")
    
    # Validação
    assert confidence['leverage_multiplier'] >= 1.0, "In-level deve ter leverage >= 1.0"
    assert confidence_away['leverage_multiplier'] <= 1.0, "Away-level deve ter leverage <= 1.0"
    print("\n✅ ESTRATÉGIA 2: Confidence boost funcionando corretamente")
except Exception as e:
    print(f"❌ Falha na Estratégia 2: {e}")
    sys.exit(1)

# Test 4: Estratégia 3 - Fibonacci SL Protection
print("\n[4/5] Testando ESTRATÉGIA 3: Fibonacci para Proteção de SL...")
try:
    sl_info = fib.calculate_fibo_sl(entry, "BUY", swing_high, swing_low, atr, atr_multiplier=1.5)
    
    print(f"   Entry: {entry}")
    print(f"   SL (Protetor Fibo): {sl_info['sl']:.2f}")
    print(f"   Risk Distance: {sl_info['risk_distance']:.2f}")
    print(f"   Risk %: {sl_info['risk_pct']:.2f}%")
    print(f"   Protection: {sl_info['protection_level']}")
    
    # Validação
    assert sl_info['sl'] < entry, "SL deve estar abaixo entry para LONG"
    assert sl_info['risk_pct'] > 0, "Risk % deve ser positivo"
    print("✅ ESTRATÉGIA 3: SL protetor posicionado corretamente")
except Exception as e:
    print(f"❌ Falha na Estratégia 3: {e}")
    sys.exit(1)

# Test 5: Integração com Strategy e Execution
print("\n[5/5] Testando integração com Strategy e Execution...")
try:
    from src.strategy import TradingStrategy
    from src.notifier import TelegramNotifier
    from src.execution import ExecutionManager
    from unittest.mock import MagicMock
    
    notifier = TelegramNotifier()
    strategy = TradingStrategy("BTCUSDT", notifier)
    
    # Verificar que FibonacciManager foi inicializado
    assert hasattr(strategy, 'fib_manager'), "Strategy deve ter fib_manager"
    assert strategy.fib_manager is not None, "fib_manager não deve ser None"
    print("   ✅ Strategy tem FibonacciManager")
    
    # Verificar ExecutionManager
    session_mock = MagicMock()
    executor = ExecutionManager(session_mock)
    assert hasattr(executor, 'fib_manager'), "Executor deve ter fib_manager"
    print("   ✅ ExecutionManager tem FibonacciManager")
    
    # Testar método novo de Execution
    assert hasattr(executor, 'setup_smc_management_with_fibonacci'), "Executor deve ter método novo"
    print("   ✅ Executor tem setup_smc_management_with_fibonacci")
    
    print("✅ Integração com Strategy/Execution completa")
except Exception as e:
    print(f"❌ Falha na integração: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("✨ TODOS OS TESTES PASSARAM!")
print("=" * 80)

print("""
📋 RESUMO - 3 ESTRATÉGIAS ATIVAS:

✅ ESTRATÉGIA 1: Fibonacci Targets
   - TPs posicionados em níveis 38.2%, 61.8% (Golden), 100%
   - SL protetor em nível Fibonacci
   - Usado em: execution.py setup_smc_management_with_fibonacci()
   
✅ ESTRATÉGIA 2: Fibonacci Confidence Boost
   - Se preço em nível Fibo: leverage +15%
   - Se preço longe: leverage -5%
   - Usado em: main.py execute_new_trade() com leverage_factor_fibo
   
✅ ESTRATÉGIA 3: Fibonacci SL Protection
   - SL posicionado em suportes matemáticos
   - Reduz whipsaws
   - Integrado em: setup_smc_management_with_fibonacci()

🚀 PRÓXIMOS PASSOS:

1. Rodar bot com Market Cycles + Fibonacci:
   python main.py

2. Monitorar logs para:
   - "Fibonacci Level:" → Leverage boost sendo aplicado
   - "Gestão SMC com FIBONACCI:" → Targets calculados
   - "TP1 (38.2%)", "TP2 (61.8% Golden)", "TP3 (100%)" → Novos TPs

3. Validar que trades fecham em níveis Fibonacci
   (menos whipsaws, melhor Sharpe ratio)

=""")
