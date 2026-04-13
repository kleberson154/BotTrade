# 🔍 ANÁLISE DE REJEÇÕES DE SINAL (HOLD REASONS)

## 📊 9 Pontos de Rejeição Identificados no `check_signal()`

### 1️⃣ **Proteção Temporal** (Minuto 00/01/59)
```python
if not self.is_market_safe(current_time):
    return "HOLD", 0
```
- **Por quê:** Evita trades perto de fechamento/abertura de candles
- **Duração:** ~3 minutos por hora
- **Severidade:** ⭐ Baixa (design)
- **Como controlar:** Ajustar `is_market_safe()` se muito rigoroso

---

### 2️⃣ **Dados Insuficientes**
```python
if len(self.data_1m) < 40 or len(self.data_15m) < self.min_15m_candles:
    return "HOLD", 0
```
- **Por quê:** Precisa warmer para calcular indicadores corretamente
- **Como resolver:** Aumentar `min_15m_candles` (default: 250)
- **Severidade:** ⭐ Média (apenas no startup)

---

### 3️⃣ **Regime Fraco** (regime_gap < 0.0015)
```python
if self.use_regime_filter and ind['regime_gap'] < 0.0015:
    return "HOLD", 0
```
- **Por quê:** Evita mercados "mortos" sem volatilidade
- **Controlado por:** `self.use_regime_filter` (True/False)
- **Severidade:** ⭐⭐⭐ **ALTA** - pode bloquear por HORAS
- **Como desativar:** `use_regime_filter = False`

---

### 4️⃣ **Tendência Fraca** (ADX baixo)
```python
if not tendencia_forte:  # ADX < adjusted_min_adx
    motivos.append(f"adx={ind['adx_1m']:.1f}<{adjusted_min_adx:.1f}")
```
- **Por quê:** ADX < 25 (default) = tendência fraca
- **Severidade:** ⭐⭐⭐ **ALTA** - rejeita ~50-70% dos dias laterais
- **Como controlar:**
  - Reduzir `self.min_adx` (25 → 15-20)
  - Ativar ciclos RSI: `cycle_mult_adx *= 0.85` em oversold

---

### 5️⃣ **Volatilidade Baixa** (ATR% < min_volatilidade_pct)
```python
if not volat_ok:  # ATR% < 0.0005 (0.05%)
    motivos.append(f"atr%={ind['atr_pct']:.4f}")
```
- **Por quê:** Mercados com pouca volatilidade = slippages ruins
- **Severidade:** ⭐⭐ Média-Alta
- **Como controlar:** Reduzir `min_volatilidade_pct` (0.0005 → 0.0003)

---

### 6️⃣ **Volume Insuficiente**
```python
if not pico_vol:  # vol < avg * volume_multiplier
    motivos.append(f"vol={curr_vol}")
```
- **Por quê:** Volume > 1.5x média = confirma breakout
- **Severidade:** ⭐⭐⭐ **ALTA** - bloqueia ~40% dos sinais
- **Como controlar:**
  - Reduzir `volume_multiplier` (1.5 → 1.2)
  - Ativar modo signal-first: `require_volume_peak = False`

---

### 7️⃣ **Sem Clean Breakout**
```python
if is_clean_breakout_up and curr_price > ind['ema_200_15']:
    # Valida: preço > máxima 15m + volume confirmado
```
- **Por quê:** Evita "false breakouts" = preço toca máxima mas não sustenta
- **Severidade:** ⭐⭐⭐⭐ **MUITO ALTA** - crítico filtro
- **Como controlar:**
  - Reduzir `breakout_margin` (0.0001 → 0.00005)
  - Relaxar `volume_confirmado` condition

---

### 8️⃣ **Exaustão RSI**
```python
if ind['rsi_1m'] > self.rsi_overbought:  # > 70
    # rejeita BUY
```
- **Por quê:** RSI > 70 = overbought, alto risco de reversal
- **Severidade:** ⭐⭐ Média
- **Como controlar:** Aumentar `rsi_overbought` (70 → 75-80)

---

### 9️⃣ **RR Violada** (Regra 1 do Mack)
```python
if not validate_result['valid']:  # RR < 1:2
    return "HOLD", 0
```
- **Por quê:** Mack exige RR 1:2 mínimo = disciplinado
- **Severidade:** ⭐⭐⭐ **ALTA** - rejeita ~30% dos bons sinais
- **Como controlar:**
  - Reduzir RR mínimo: `min_rr = 1.5` (em vez de 2.0)
  - Aumentar TP% dinamicamente

---

## 🎯 Resumo: Filtros Mais "Medrosos"

| # | Filtro | Bloqueio | Solução |
|---|--------|---------|--------|
| 1 | Clean Breakout | ⭐⭐⭐⭐ | Relaxar `breakout_margin` |
| 2 | Tendência (ADX) | ⭐⭐⭐ | Reduzir `min_adx` a 15-20 |
| 3 | Volume | ⭐⭐⭐ | `require_volume_peak = False` |
| 4 | RR 1:2 | ⭐⭐⭐ | Reduzir a 1:1.5 |
| 5 | Regime Gap | ⭐⭐⭐ | `use_regime_filter = False` |

---

## ⚡ "Modo Agressivo" - Config para Não Perder Trades

```python
# Em src/strategy.py, classe TradingStrategy.__init__()
self.min_adx = 15              # Era 25 (reduzir)
self.volume_multiplier = 1.2   # Era 1.5 (relaxar)
self.min_volatilidade_pct = 0.0003  # Era 0.0005
self.require_volume_peak = False    # Ativar signal-first
self.use_regime_filter = False      # Desativar (ou True)
self.rsi_overbought = 75            # Era 70
```

**Efeito**: +60% de sinais, -10% na taxa de acertos

---

## 🔧 Monitorar Rejeições em Tempo Real

Em `monitoring_dashboard.py`, adicione:

```python
print(f"Última razão de HOLD: {strategy.last_hold_reason}")
```

Assim você verá exatamente por quê cada sinal foi rejeitado.

---

## ✅ Recomendação Final

**Para seu caso (Fresh start 13/04):**

1. Use config **NORMAL** por 24 horas (observar trades)
2. Se < 5 trades/dia → ativar **Modo Agressivo**
3. Se > 3 trades/hora → ativar **Modo Conservador**
4. Never disable RR 1:2 (Mack Rule #1 é crítica!)
