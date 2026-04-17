#!/usr/bin/env python3
"""
🧪 Teste da validação de quantidade para evitar erros 110007 e 10001
"""

import sys
sys.path.insert(0, '/c/Users/zed15/OneDrive/Documentos/projetos/BotTrade')

# Mock do cache_balance global
cache_balance = {"total": 120.0, "avail": 100.0, "last_update": 0}

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
    """
    ⚠️ VALIDAÇÃO DE SEGURANÇA - Evita erros 110007 e 10001
    
    Retorna: (é_válido, quantidade_ajustada, razão)
    """
    q_prec, p_prec = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
    
    # 1. NOTIONAL MÍNIMO BYBIT: ~5 USDT
    notional = price * qty
    min_notional = 5.0
    
    if notional < min_notional:
        adjusted_qty = max(0.1, min_notional / price)
        # Ajustar à precisão
        if q_prec == 0:
            adjusted_qty = int(adjusted_qty)
        else:
            adjusted_qty = round(adjusted_qty, q_prec)
        
        new_notional = price * adjusted_qty
        if new_notional < min_notional:
            return False, adjusted_qty, f"Notional {notional:.2f} USDT < mínimo {min_notional} USDT"
    
    # 2. PRECISÃO DE QUANTIDADE
    if q_prec == 0:
        qty_final = int(qty)
    else:
        qty_final = round(qty, q_prec)
    
    # 3. Quantidade positiva
    if qty_final <= 0:
        return False, qty_final, "Quantidade <= 0"
    
    # 4. VALIDAÇÃO DE SALDO - Bybit bloqueia se não há margem suficiente
    # Com alavancagem, calcula quanto de saldo é necessário
    margin_needed = (price * qty_final) / 10  # Assumindo leverage 10x como máximo
    available_margin = cache_balance['avail'] * 0.9  # Buffer de 10% de segurança
    
    if margin_needed > available_margin:
        # Reduzir a quantidade proporcionalmente
        qty_final = (available_margin * 10) / price
        if q_prec == 0:
            qty_final = int(qty_final)
        else:
            qty_final = round(qty_final, q_prec)
        
        return False, qty_final, f"Margem insuficiente: precisa {margin_needed:.2f}, disponível {available_margin:.2f}"
    
    return True, qty_final, "OK"

# =========================================================
# TESTES
# =========================================================

test_cases = [
    # (symbol, price, qty_calculada, descricao_esperada)
    ("AVAXUSDT", 10.77, 22.3, "Normal - deve passar"),
    ("IRYSUSDT", 0.00312, 7611.1, "Atômico baixo - deve rejeitar por qty"),
    ("BTCUSDT", 100000, 0.0001, "Micro-posição - deve rejeitar por notional"),
    ("SOLUSDT", 200.0, 0.5, "Teste de saldo insuficiente"),
]

print("=" * 70)
print("🧪 TESTES DE VALIDAÇÃO DE QUANTIDADE")
print("=" * 70)

for symbol, price, qty, desc in test_cases:
    is_valid, validated_qty, reason = validate_order_quantity(symbol, price, qty)
    q_prec, _ = risk_mgr.PRECISION_MAP.get(symbol, (1, 4))
    notional = price * qty
    validated_notional = price * validated_qty
    
    status = "✅ PASSA" if is_valid else "❌ REJEITA"
    
    print(f"\n{status} | {symbol} - {desc}")
    print(f"   Entrada: qty={qty:.2f}, preço={price:.6f}, notional={notional:.2f}")
    print(f"   Validada: qty={validated_qty:.2f}, notional={validated_notional:.2f}")
    print(f"   Razão: {reason}")

print("\n" + "=" * 70)
print("✅ Testes concluídos!")
print("=" * 70)
