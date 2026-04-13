# example_mack_integration.py
"""
EXEMPLOS PRÁTICOS: Como integrar as regras do Mack no bot

Este arquivo demonstra como usar os novos módulos:
1. signal_formatter.py - Formatação profissional de sinais
2. mack_compliance.py - Validação das 5 regras
3. mack_notifier.py - Notificações melhoradas
4. multi_tp_manager.py - Gestão de múltiplos TPs
"""

from src.signal_formatter import (
    TradeSignal, SignalProfile, TradeSignalBuilder, SignalFormatter
)
from src.mack_compliance import MackCompliance, PositionSizer
from src.mack_notifier import MackNotifier
from src.multi_tp_manager import SMCTPManager, TradingSession

import logging

log = logging.getLogger(__name__)


# ==============================================================================
# EXEMPLO 1: Criar um sinal profissional (LAB/USDT do anexo)
# ==============================================================================

def example_create_signal():
    """Cria o sinal LAB/USDT do exemplo fornecido"""
    
    print("\n" + "="*60)
    print("EXEMPLO 1: Criar Sinal Profissional")
    print("="*60)
    
    # Builder pattern para criar sinal complexo
    signal = (TradeSignalBuilder(symbol="LABUSDT", side="LONG", entry=0.4818)
        .with_stops(sl=0.437224, tp=0.660105)
        .with_leverage(75)
        .with_profile(SignalProfile.AGGRESSIVE)
        .with_strength(0.725)  # 72.5% de força
        .with_daily_rank(41)
        .with_origin("Estrutural SMC")
        .add_rationale("[TREND] ADX 31")
        .add_rationale("DI+ 47 > DI- 10")
        .add_rationale("EMAs alinhadas alta")
        .add_rationale("Vol 6.0x")
        .add_rationale("Breakout R2")
        .add_rationale("MACD+")
        .add_rationale("funding contra (+0.054%/8h)")
        .add_rationale("SMC: CHoCH bull 4c atrás + HTF ? + sweep abaixo + reclaim altista")
        # Gestão SMC
        .add_partial_tp(tp_price=0.541235, tp_percent=40, action="CLOSE_PARTIAL", 
                       desc="TP1: Close 40%, mover SL para Entry")
        .add_partial_tp(tp_price=0.60067, tp_percent=40, action="CLOSE_PARTIAL",
                       desc="TP2: Close 40%, mover SL para TP1")
        .add_partial_tp(tp_price=0.660105, tp_percent=20, action="CLOSE_ALL",
                       desc="TP3: Runner final / saída total")
        .build()
    )
    
    # Exibir sinal formatado
    formatter = SignalFormatter()
    print("\n📤 SINAL FORMATADO PARA TELEGRAM:")
    print(formatter.format_signal_for_notification(signal))
    
    # Dados estruturados
    print("\n📊 DADOS ESTRUTURADOS:")
    signal_data = formatter.format_signal_data(signal)
    for key, value in signal_data.items():
        print(f"  {key}: {value}")
    
    return signal


# ==============================================================================
# EXEMPLO 2: Validar Regra 1 (Risk:Reward 1:2)
# ==============================================================================

def example_validate_rr():
    """Valida Risk:Reward"""
    
    print("\n" + "="*60)
    print("EXEMPLO 2: Validar Risk:Reward (Regra 1 do Mack)")
    print("="*60)
    
    compliance = MackCompliance(account_balance=1000.0)
    
    # Teste 1: ✅ VÁLIDO (1:2 ou melhor)
    result1 = compliance.validate_rr_ratio(
        entry=100.0,
        sl=95.0,
        tp=110.0,  # Risk=5, Reward=10 → 1:2 ✅
        side="LONG",
        symbol="TESTUSDT"
    )
    
    print(f"\n✅ Teste 1 (VÁLIDO):")
    print(f"   Entry: 100 | SL: 95 | TP: 110")
    print(f"   Risk: {result1['risk_points']:.2f} | Reward: {result1['reward_points']:.2f}")
    print(f"   Ratio: {result1['ratio']}:1")
    print(f"   Status: {'✅ APROVADO' if result1['valid'] else '❌ REPROVADO'}")
    
    # Teste 2: ❌ INVÁLIDO (menos de 1:2)
    result2 = compliance.validate_rr_ratio(
        entry=100.0,
        sl=95.0,
        tp=101.0,  # Risk=5, Reward=1 → 0.2:1 ❌
        side="LONG",
        symbol="TESTUSDT2"
    )
    
    print(f"\n❌ Teste 2 (INVÁLIDO):")
    print(f"   Entry: 100 | SL: 95 | TP: 101")
    print(f"   Risk: {result2['risk_points']:.2f} | Reward: {result2['reward_points']:.2f}")
    print(f"   Ratio: {result2['ratio']}:1")
    print(f"   Status: {'✅ APROVADO' if result2['valid'] else '❌ REPROVADO'}")


# ==============================================================================
# EXEMPLO 3: Dimensionar posição (Regra 4 - Conforto)
# ==============================================================================

def example_position_sizing():
    """Calcula tamanho de posição Mack-compliant"""
    
    print("\n" + "="*60)
    print("EXEMPLO 3: Dimensionamento Profissional (Regra 4)")
    print("="*60)
    
    # Cenário: Conta de $1000, queremos arriscar 2%
    account = 1000.0
    entry = 50000.0  # BTC
    sl = 49000.0
    
    qty = PositionSizer.calculate_qty(
        account_balance=account,
        entry_price=entry,
        sl_price=sl,
        risk_percent=0.02,  # 2%
        side="LONG"
    )
    
    risk_per_unit = entry - sl
    total_risk = qty * risk_per_unit
    risk_percent = (total_risk / account) * 100
    
    print(f"\n📊 CALCULADORA DE POSIÇÃO:")
    print(f"   Conta: ${account:.2f}")
    print(f"   Entry: ${entry:.2f} | SL: ${sl:.2f}")
    print(f"   Risk/Unit: ${risk_per_unit:.2f}")
    print(f"   Risk Permitido: 2% = ${account * 0.02:.2f}")
    print(f"\n   ✅ QUANTIDADE CALCULADA: {qty:.4f}")
    print(f"   Risco Total: ${total_risk:.2f} ({risk_percent:.2f}%)")
    print(f"   Status: {'✅ CONFORTÁVEL' if risk_percent <= 2.0 else '❌ DESCONFORTÁVEL'}")
    
    # Validação de leverage
    is_valid_leverage = PositionSizer.validate_leverage(qty, entry, max_leverage=50)
    print(f"   Leverage: {'✅ OK' if is_valid_leverage else '❌ VIOLADO'}")


# ==============================================================================
# EXEMPLO 4: Gestão SMC com múltiplos TPs
# ==============================================================================

def example_smc_management():
    """Demonstra gestão SMC com closes parciais"""
    
    print("\n" + "="*60)
    print("EXEMPLO 4: Gestão SMC com Closes Parciais")
    print("="*60)
    
    # Criar gestão SMC
    tp_manager = SMCTPManager.create_smc_config(
        symbol="LABUSDT",
        side="LONG",
        entry=0.4818,
        sl=0.437224,
        tp1=0.541235,
        tp2=0.60067,
        tp3=0.660105
    )
    
    print("\n📋 CONFIGURAÇÃO INICIAL:")
    print(f"   Entry: 0.4818 | SL: 0.437224")
    print(f"   TP1: 0.541235 | TP2: 0.60067 | TP3: 0.660105")
    
    print("\n" + tp_manager.get_smc_summary())
    
    # Simular movimento de preço
    print("\n📈 SIMULAÇÃO DE MOVIMENTO:")
    
    prices = [0.500, 0.541235, 0.580, 0.60067, 0.650, 0.660105]
    
    for price in prices:
        hits = tp_manager.check_tp_hit(price)
        print(f"\n   Preço: {price}")
        
        if hits:
            for hit in hits:
                print(f"   🎯 TP{hit['tp_level']} atingido!")
                print(f"      Ação: {hit['action']}")
                print(f"      Novo SL: {hit['new_sl']}")
                
                # Registrar close
                tp_manager.register_close(
                    tp_level=hit['tp_level'],
                    closed_quantity=0,  # Ignorar por ora
                    close_price=price
                )
    
    print("\n\n📊 STATUS FINAL:")
    status = tp_manager.get_status()
    print(f"   Fechados: {status['closed_percent']}%")
    print(f"   Histórico de Closes: {len(status['close_history'])} operações")


# ==============================================================================
# EXEMPLO 5: Auditoria de Compliance
# ==============================================================================

def example_compliance_audit():
    """Demonstra auditoria de compliance"""
    
    print("\n" + "="*60)
    print("EXEMPLO 5: Auditoria de Compliance")
    print("="*60)
    
    compliance = MackCompliance(account_balance=1000.0)
    
    # Simular algumas violações
    print("\n🔍 TESTANDO CENÁRIOS:")
    
    # Cenário 1: Posição muito grande
    print("\n1️⃣ Posição Desconfortável:")
    sizing_result = compliance.validate_position_sizing(
        symbol="BTCUSDT",
        entry=50000.0,
        sl=45000.0,
        quantity=1.0,  # Posição MUITO grande para conta de $1000
        leverage=50,
        account_balance=1000.0,
        side="LONG"
    )
    print(f"   Risco: {sizing_result['risk_percent']:.2f}% | Status: {sizing_result['comfort_status']}")
    
    # Cenário 2: SL sendo mexido em prejuízo
    print("\n2️⃣ SL Mexido em Prejuízo:")
    sl_result = compliance.validate_sl_immobility(
        symbol="ETHUSDT",
        current_price=1800.0,
        sl_original=1900.0,
        sl_current=1850.0,  # SL afastado (risco aumentado)
        side="LONG",
        current_pnl=-3.5
    )
    print(f"   PnL: {sl_result['pnl']}% | Status: {sl_result['message']}")
    
    # Cenário 3: Averaging down
    print("\n3️⃣ Averaging Down (Pirâmide Invertida):")
    averaging_result = compliance.validate_no_averaging_down(
        symbol="SOLUSDT",
        recent_additions=3,  # Adicionou capital 3 vezes
        total_pnl=-5.0,      # Em prejuízo
        is_losing=True
    )
    print(f"   Adições: {averaging_result['recent_additions']} | Status: {averaging_result['message']}")
    
    # Relatório final
    print("\n\n📊 RELATÓRIO DE COMPLIANCE:")
    report = compliance.get_compliance_report()
    print(f"   Status Geral: {report['status']}")
    print(f"   Total Violações: {report['total_violations']}")
    if report['violations']:
        print(f"   Violações Detectadas:")
        for v in report['violations']:
            print(f"      • {v}")


# ==============================================================================
# EXEMPLO 6: Notificações Mack
# ==============================================================================

def example_notifications():
    """Demonstra sistema de notificações"""
    
    print("\n" + "="*60)
    print("EXEMPLO 6: Sistema de Notificações")
    print("="*60)
    
    notifier = MackNotifier()
    
    print("\n📤 NOTIFICAÇÕES DISPONÍVEIS:")
    print("   1. notify_signal() - Novo sinal")
    print("   2. notify_trade_entry() - Entrada executada")
    print("   3. notify_trade_exit() - Saída executada")
    print("   4. notify_compliance_violation() - Violação de regra")
    print("   5. notify_dashboard() - Dashboard de performance")
    print("   6. notify_alert() - Alerta genérico")
    print("   7. notify_ruin_risk() - Alerta de risco de ruína")
    print("   8. notify_bot_status() - Status do bot")
    
    print("\n⚠️ Para testar, você precisa:")
    print("   • TELEGRAM_TOKEN configurado")
    print("   • TELEGRAM_CHAT_ID configurado")
    print("   • Descomentar as chamadas abaixo")


# ==============================================================================
# MAIN: Executar todos os exemplos
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎓 EXEMPLOS PRÁTICOS: INTEGRAÇÃO DAS REGRAS DO MACK")
    print("="*60)
    
    # Executar exemplos
    signal = example_create_signal()
    example_validate_rr()
    example_position_sizing()
    example_smc_management()
    example_compliance_audit()
    example_notifications()
    
    print("\n\n" + "="*60)
    print("✅ EXEMPLOS COMPLETOS!")
    print("="*60)
    print("\n📚 Próximos passos:")
    print("   1. Integrar MackCompliance no RiskManager")
    print("   2. Integrar MackNotifier no ExecutionManager")
    print("   3. Usar TradeSignalBuilder na estratégia")
    print("   4. Implementar MultiTPManager no ExecutionManager")
    print("   5. Adicionar auditoria no dashboard")
