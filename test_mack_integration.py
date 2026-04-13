#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TESTE DE INTEGRAÇÃO: Framework Mack no Bot

Valida que todas as 5 regras estão funcionando corretamente.
"""

import sys
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

def test_imports():
    """Testa que todos os módulos importam corretamente"""
    print("\n[TEST 1] Testando imports...")
    try:
        from src.signal_formatter import TradeSignal, TradeSignalBuilder, SignalProfile
        from src.mack_compliance import MackCompliance, PositionSizer
        from src.mack_notifier import MackNotifier
        from src.multi_tp_manager import SMCTPManager
        from src.risk_manager import RiskManager
        from src.notifier import TelegramNotifier
        from src.execution import ExecutionManager
        print("[OK] Todos os imports funcionam!")
        return True
    except Exception as e:
        print(f"[ERRO] Import falhou: {e}")
        return False


def test_mack_validation():
    """Testa validação Regra 1 - Risk:Reward 1:2"""
    print("\n[TEST 2] Testando Risk:Reward (Regra 1)...")
    try:
        from src.mack_compliance import MackCompliance
        
        compliance = MackCompliance()
        
        # Teste 1: Válido (1:2)
        result1 = compliance.validate_rr_ratio(100, 95, 110, "LONG", "TEST1")
        assert result1['valid'] == True, "RR válido deveria passar"
        assert result1['ratio'] == 2.0, "Ratio deveria ser 2.0"
        
        # Teste 2: Inválido (menor que 1:2)
        result2 = compliance.validate_rr_ratio(100, 95, 101, "LONG", "TEST2")
        assert result2['valid'] == False, "RR inválido deveria falhar"
        
        print("[OK] Validação Risk:Reward funciona!")
        return True
    except Exception as e:
        print(f"[ERRO] Teste Risk:Reward falhou: {e}")
        return False


def test_position_sizing():
    """Testa Regra 4 - Dimensionamento Profissional"""
    print("\n[TEST 3] Testando Position Sizing (Regra 4)...")
    try:
        from src.mack_compliance import PositionSizer
        
        # Cenário: Account $1000, Entry $50000, SL $49000
        qty = PositionSizer.calculate_qty(
            account_balance=1000.0,
            entry_price=50000.0,
            sl_price=49000.0,
            risk_percent=0.02,
            side="LONG"
        )
        
        assert qty > 0, "Quantidade deveria ser positiva"
        expected_qty = (1000 * 0.02) / 1000  # = 0.02
        assert abs(qty - expected_qty) < 0.0001, f"Qty esperada {expected_qty}, got {qty}"
        
        print(f"[OK] Position Sizing funciona! Qty: {qty:.4f}")
        return True
    except Exception as e:
        print(f"[ERRO] Position Sizing falhou: {e}")
        return False


def test_smc_management():
    """Testa Gestão SMC com múltiplos TPs"""
    print("\n[TEST 4] Testando Gestão SMC (Regra 5)...")
    try:
        from src.multi_tp_manager import SMCTPManager
        
        # Criar gestão SMC
        tp_manager = SMCTPManager.create_smc_config(
            symbol="TEST",
            side="LONG",
            entry=100.0,
            sl=95.0,
            tp1=110.0,
            tp2=120.0,
            tp3=130.0
        )
        
        # Simular movimento de preço
        hits = tp_manager.check_tp_hit(110.0)  # Atinge TP1
        assert len(hits) > 0, "TP1 deveria ter sido atingido"
        assert hits[0]['tp_level'] == 1, "Deveria ser TP1"
        
        print(f"[OK] Gestão SMC funciona! TP1 detectado em 110.0")
        return True
    except Exception as e:
        print(f"[ERRO] Gestão SMC falhou: {e}")
        return False


def test_risk_manager_integration():
    """Testa integração Mack no RiskManager"""
    print("\n[TEST 5] Testando integração RiskManager...")
    try:
        from src.risk_manager import RiskManager
        
        risk_mgr = RiskManager()
        
        # Testar validação Mack
        result = risk_mgr.validate_trade_mack(
            entry=100.0,
            sl=95.0,
            tp=110.0,
            symbol="TEST",
            side="LONG"
        )
        
        assert result['valid'] == True, "Trade válido deveria passar"
        assert result['ratio'] == 2.0, "Ratio deveria ser 2.0"
        
        # Testar position sizing
        qty = risk_mgr.calculate_position_size_mack(
            entry=100.0,
            sl=95.0,
            account_balance=1000.0,
            side="LONG",
            risk_percent=0.02
        )
        
        assert qty > 0, "Quantidade deveria ser positiva"
        
        print(f"[OK] RiskManager integrado! Qty: {qty:.4f}")
        return True
    except Exception as e:
        print(f"[ERRO] RiskManager falhou: {e}")
        return False


def test_execution_manager_integration():
    """Testa integração Mack no ExecutionManager"""
    print("\n[TEST 6] Testando integração ExecutionManager...")
    try:
        from src.execution import ExecutionManager
        
        # Mock session
        class MockSession:
            pass
        
        exec_mgr = ExecutionManager(MockSession())
        
        # Testar setup SMC
        tp_mgr = exec_mgr.setup_smc_management(
            symbol="TEST",
            side="LONG",
            entry=100.0,
            sl=95.0,
            tp1=110.0,
            tp2=120.0,
            tp3=130.0
        )
        
        assert tp_mgr is not None, "TP Manager deveria ser criado"
        assert exec_mgr.tp_managers["TEST"] is not None, "TP Manager deveria estar armazenado"
        
        # Testar monitoramento
        hits = exec_mgr.monitor_tp_hits("TEST", 110.0)
        assert hits is not None, "Monitoramento deveria retornar resultado"
        
        print("[OK] ExecutionManager integrado!")
        return True
    except Exception as e:
        print(f"[ERRO] ExecutionManager falhou: {e}")
        return False


def test_signal_formatter():
    """Testa formatador de sinais profissional"""
    print("\n[TEST 7] Testando SignalFormatter...")
    try:
        from src.signal_formatter import TradeSignalBuilder, SignalProfile, SignalFormatter
        
        # Criar sinal
        signal = (TradeSignalBuilder("TEST", "LONG", 100.0)
            .with_stops(95.0, 110.0)
            .with_leverage(10)
            .with_profile(SignalProfile.AGGRESSIVE)
            .with_strength(0.75)
            .add_rationale("Test reason 1")
            .add_rationale("Test reason 2")
            .add_partial_tp(105.0, 40, "CLOSE_PARTIAL", "TP1")
            .build()
        )
        
        assert signal.symbol == "TEST", "Symbol deveria ser TEST"
        assert signal.entry == 100.0, "Entry deveria ser 100.0"
        assert len(signal.rationale) == 2, "Deveria ter 2 razões"
        assert len(signal.partial_tps) == 1, "Deveria ter 1 TP"
        
        # Testar formatação
        formatter = SignalFormatter()
        msg = formatter.format_signal_for_notification(signal)
        assert len(msg) > 0, "Mensagem deveria ter conteúdo"
        assert "AGGRESSIVE" in msg, "Deveria ter perfil"
        
        print("[OK] SignalFormatter funciona!")
        return True
    except Exception as e:
        print(f"[ERRO] SignalFormatter falhou: {e}")
        return False


def main():
    """Executa todos os testes"""
    print("="*60)
    print("TESTES DE INTEGRAÇÃO: FRAMEWORK MACK")
    print("="*60)
    
    tests = [
        ("Imports", test_imports),
        ("Risk:Reward Validation", test_mack_validation),
        ("Position Sizing", test_position_sizing),
        ("SMC Management", test_smc_management),
        ("RiskManager Integration", test_risk_manager_integration),
        ("ExecutionManager Integration", test_execution_manager_integration),
        ("SignalFormatter", test_signal_formatter),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"[ERRO] Teste {name} falhou com exceção: {e}")
            results.append((name, False))
    
    # Resumo
    print("\n" + "="*60)
    print("RESUMO DOS TESTES")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n[SUCESSO] Todos os testes passaram! Framework Mack integrado com sucesso!")
        return 0
    else:
        print(f"\n[FALHA] {total - passed} teste(s) falharam")
        return 1


if __name__ == "__main__":
    sys.exit(main())
