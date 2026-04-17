#!/usr/bin/env python3
"""
✅ Teste completo de cenários de execução
"""
import sys
sys.path.insert(0, '/c/Users/zed15/OneDrive/Documentos/projetos/BotTrade')

# Mock do cache_balance global
cache_balance = {"total": 120.0, "avail": 50.0, "last_update": 0}

class MockRiskManager:
    PRECISION_MAP = {
        "BTCUSDT": (3, 2), "ETHUSDT": (2, 2), "SOLUSDT": (1, 3),
        "LINKUSDT": (1, 3), "AVAXUSDT": (1, 3), "XRPUSDT": (1, 4),
        "ADAUSDT": (0, 4), "NEARUSDT": (1, 3), "DOTUSDT": (1, 3),  
        "SUIUSDT": (1, 4), "OPUSDT": (1, 4), 
        "RAVEUSDT": (1, 4), "LYNUSDT": (0, 4), "HYPEUSDT": (1, 4), 
        "IRYSUSDT": (0, 4),
        "DEFAULT": (1, 4)
    }

risk_mgr = MockRiskManager()

def validate_order_quantity(symbol, price, qty):
    q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
    
    notional = price * qty
    min_notional = 5.0
    
    if notional < min_notional:
        adjusted_qty = max(0.1, min_notional / price)
        if q_prec == 0:
            adjusted_qty = int(adjusted_qty)
        else:
            adjusted_qty = round(adjusted_qty, q_prec)
        
        new_notional = price * adjusted_qty
        if new_notional < min_notional:
            return False, adjusted_qty, f"Notional {notional:.2f} USDT < mínimo {min_notional} USDT"
    
    if q_prec == 0:
        qty_final = int(qty)
    else:
        qty_final = round(qty, q_prec)
    
    if qty_final <= 0:
        return False, qty_final, "Quantidade <= 0"
    
    margin_needed = (price * qty_final) / 10.0
    available_for_new = cache_balance['avail'] * 0.85
    
    if margin_needed > available_for_new:
        qty_reduced = (available_for_new * 10.0) / price
        if q_prec == 0:
            qty_reduced = int(qty_reduced)
        else:
            qty_reduced = round(qty_reduced, q_prec)
        
        if qty_reduced <= 0:
            return False, qty_final, f"Margem insuficiente: precisa {margin_needed:.2f}, disponível {available_for_new:.2f}"
        
        qty_final = qty_reduced
        return False, qty_final, f"Quantidade reduzida por margem: {qty:.2f} → {qty_final:.2f}"
    
    return True, qty_final, "OK"

# =========================================================
# TESTES DE CENÁRIOS REALISTAS
# =========================================================

scenarios = [
    ("AVAXUSDT", 10.77, 22.3, "Cenário 1: Ordem normal (logs mostram)"),
    ("IRYSUSDT", 0.00312, 7611.1, "Cenário 2: Qtd absurda → corrigida"),
    ("HYPEUSDT", 45.3416, 4.9, "Cenário 3: Erro 110007 → reduz quantidade"),
    ("LINKUSDT", 9.856, 22.6, "Cenário 4: Erro 110007 → reduz quantidade"),
]

print("\n" + "=" * 80)
print("🧪 SIMULAÇÃO DE CENÁRIOS DE EXECUÇÃO DO BOT")
print("=" * 80)
print(f"Saldo disponível: ${cache_balance['avail']:.2f}")
print()

results = []

for symbol, price, qty, scenario in scenarios:
    is_valid, validated_qty, reason = validate_order_quantity(symbol, price, qty)
    q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
    
    # Formatação final
    if q_prec == 0:
        qty_str = str(int(validated_qty))
    else:
        qty_str = str(validated_qty)
    
    notional = price * validated_qty
    margin_needed = (price * validated_qty) / 10.0
    
    status = "✅ EXECUTA" if is_valid else "⚠️ REJEITA"
    
    print(f"{status} | {scenario}")
    print(f"  Símbolo: {symbol} | Preço: ${price:.6f}")
    print(f"  Qty entrada: {qty:.2f} → Qty final: {validated_qty:.2f}")
    print(f"  Qty string (API): \"{qty_str}\"")
    print(f"  Notional: ${notional:.2f} | Margem: ${margin_needed:.2f}")
    print(f"  Razão: {reason}")
    print()
    
    results.append({
        "symbol": symbol,
        "valid": is_valid,
        "qty_str": qty_str,
        "qty": validated_qty,
        "notional": notional
    })

print("=" * 80)
print("📊 RESUMO DE EXECUÇÃO")
print("=" * 80)
for r in results:
    status = "✅" if r['valid'] else "⚠️"
    print(f"{status} {r['symbol']:12} | qty_str=\"{r['qty_str']:8}\" | notional=${r['notional']:8.2f}")

print("\n✅ Simulação concluída!")
print("💡 Próximo: Remover teste e executar bot real\n")
