"""
⭐ EXEMPLO: Sistema de Pontuação de Indicadores
Como usar o indicator_scorer em 3 passos
"""

# ============================================================
# PASSO 1: Importar (já feito em strategy.py)
# ============================================================
from src.indicator_scorer import IndicatorScorer


# ============================================================
# PASSO 2: Criar instância (já feito no __init__ de strategy.py)
# ============================================================
def setup_indicator_scorer():
    scorer = IndicatorScorer(min_score=3, symbol="BTCUSDT")
    # min_score: quantos indicadores precisam bater (1-5)
    # symbol: para logs e Telegram
    return scorer


# ============================================================
# PASSO 3: Calcular score durante check_signal() (já integrado)
# ============================================================
def exemplo_score_calculation():
    import pandas as pd
    
    # Simular dados
    df = pd.DataFrame({
        'close': [100, 101, 102, 103, 104],
        'high': [101, 102, 103, 104, 105],
        'low': [99, 100, 101, 102, 103],
        'volume': [1000, 1200, 1100, 1500, 1300]
    })
    
    # Criar scorer
    scorer = IndicatorScorer(min_score=3, symbol="BTCUSDT")
    
    # Calcular score
    result = scorer.calculate_score(
        df=df,
        min_adx=15,              # ADX mínimo para tendência
        min_volatilidade=0.0008, # ATR % mínimo (0.08%)
        volume_multiplier=1.2,   # Volume deve ser 1.2x da média
        rsi_period=14,           # Período RSI
        mfi_period=14            # Período MFI
    )
    
    # Análise do resultado
    print(f"Score: {result['score']}/{result['total_indicators']}")
    print(f"Mínimo necessário: {result['min_required']}")
    print(f"Triggered: {result['triggered']}")  # True se bate score mínimo
    
    # Detalhes de cada indicador
    for ind_name, ind_data in result['indicators'].items():
        status = ind_data['status']  # ✅ ou ❌
        value = ind_data['value']    # Valor do indicador
        reason = ind_data['reason']  # "RSI=75.5 (OVERBOUGHT)"
        print(f"{status} {ind_name}: {reason}")
    
    # Formatar para Telegram
    telegram_msg = scorer.get_telegram_message(direction="BUY")
    print(f"\n{telegram_msg}")
    
    return result


# ============================================================
# PASSO 4: Usar em strategy.py (já integrado)
# ============================================================
"""
Na função check_signal() de strategy.py:

# Valid RR
if not validate_result['valid']:
    final_signal = "HOLD"
else:
    # ⭐ NOVO: Validar Score
    score_result = self.indicator_scorer.calculate_score(
        df=self.data_1m.tail(100),
        min_adx=self.min_adx,
        min_volatilidade=self.min_volatilidade_pct,
        volume_multiplier=self.volume_multiplier
    )
    
    self.last_score_result = score_result
    
    if not score_result["triggered"]:
        # Score insuficiente
        final_signal = "HOLD"
        self.last_hold_reason = f"Score baixo: {score_result['score']}/{score_result['total_indicators']}"
    else:
        # ✅ Score OK, criar TradeSignal + TPCascade
        # ... resto do código
"""

# ============================================================
# PASSO 5: Enviar no Telegram (já integrado em main.py)
# ============================================================
"""
Em main.py, após place_order():

# Enviar mensagem da ordem
notifier.send_message(f"🚀 *{symbol} {side}*...")

# ⭐ NOVO: Enviar detalhes do score
score_msg = strat.get_score_message()
if score_msg and score_msg != "Nenhum score calculado":
    notifier.send_message(score_msg)
"""

# ============================================================
# CONFIGURAÇÃO RECOMENDADA POR TIPO DE MOEDA
# ============================================================
"""
CONFIGURAÇÃO AGRESSIVA (muitas entradas):
  min_score = 2
  min_adx = 15
  min_volatilidade = 0.0005
  volume_multiplier = 1.0
  → Score fácil de bater, mais operações

CONFIGURAÇÃO NORMAL (padrão):
  min_score = 3
  min_adx = 15
  min_volatilidade = 0.0008
  volume_multiplier = 1.2
  → Balanceado, bom para maioria

CONFIGURAÇÃO CONSERVADORA (poucas, mas boas):
  min_score = 4
  min_adx = 25
  min_volatilidade = 0.0012
  volume_multiplier = 1.5
  → Altamente seletivo, menos operações

CONFIGURAÇÃO ULTRA CONSERVADORA (principais):
  min_score = 5
  min_adx = 30
  min_volatilidade = 0.0015
  volume_multiplier = 2.0
  → Apenas operações muito confirmadas
"""

# ============================================================
# ESTATÍSTICAS DISPONÍVEIS
# ============================================================
def exemplo_statistics():
    scorer = IndicatorScorer(min_score=3, symbol="BTCUSDT")
    result = scorer.calculate_score(df)
    
    # Acessar estatísticas
    stats = result["stats"]
    print(f"RSI atual: {stats['rsi']:.2f}")
    print(f"MFI atual: {stats['mfi']:.2f}")
    print(f"ADX atual: {stats['adx']:.2f}")
    print(f"ATR %: {stats['atr_pct']:.4f}")
    print(f"Volume Ratio: {stats['volume_ratio']:.2f}x")
    
    # Use para análise posterior, alertas, etc.


if __name__ == "__main__":
    print("EXEMPLO: Sistema de Pontuação")
    print("=" * 50)
    resultado = exemplo_score_calculation()
    print("\n" + "=" * 50)
    print(f"✅ Sistema está funcionando!")
    print(f"Score final: {resultado['score']}/{resultado['total_indicators']}")
    print(f"Executa ordem: {'SIM ✅' if resultado['triggered'] else 'NÃO ❌'}")
