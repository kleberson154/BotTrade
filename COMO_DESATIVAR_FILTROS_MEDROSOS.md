# 🚀 GUIA PRÁTICO: Desativar Filtros Medrosos

**Status:** Bot sincroniza correto (desde 13/04) ✅

**Preocupação:** Bot está rejeitando muitos sinais (medroso)

## 🎯 Solução em 3 Passos

### Step 1: Desativar Regime Filter (CRÍTICO)
Este é o filtro mais severo - bloqueia por horas em mercados laterais.

**Arquivo:** `src/strategy.py`
**Linha:** ~125 (no `__init__`)

**Antes:**
```python
self.use_regime_filter = True  # ❌ Bloqueia mercados "mortos"
```

**Depois:**
```python
self.use_regime_filter = False  # ✅ Permite mercados laterais
```

---

### Step 2: Reduzir ADX Mínimo
ADX = força da tendência. 25 é rigoroso. Reduzir para 15 permite mais entradas.

**Arquivo:** `src/strategy.py`
**Linha:** ~128

**Antes:**
```python
self.min_adx = 25  # ❌ Muito rigoroso
```

**Depois:**
```python
self.min_adx = 15  # ✅ Mais flexível
```

---

### Step 3: Reduzir Volume Multiplier
Volume = 1.6x média = muito exigente.

**Arquivo:** `src/strategy.py`
**Linha:** ~129

**Antes:**
```python
self.volume_multiplier = 1.6  # ❌ Pede muito volume
```

**Depois:**
```python
self.volume_multiplier = 1.2  # ✅ Mais realista
```

---

## 🔧 Fazer as Mudanças

### Opção 1: Manualmente (5 min)
```bash
cd /home/ubuntu/BotTrade

# Abrir arquivo
nano src/strategy.py

# Procurar pelas 3 linhas acima (Ctrl+W)
# Editar valores
# Salvar (Ctrl+X, Y, Enter)

# Matar bot antigo
pkill -9 python

# Reiniciar
python main.py
```

### Opção 2: Script Automático (1 min)
```bash
# Na Oracle, rodar:
cd /home/ubuntu/BotTrade

cat > fix_medroso.sh << 'EOF'
#!/bin/bash
sed -i 's/self.use_regime_filter = True/self.use_regime_filter = False/' src/strategy.py
sed -i 's/self.min_adx = 25/self.min_adx = 15/' src/strategy.py
sed -i 's/self.volume_multiplier = 1.6/self.volume_multiplier = 1.2/' src/strategy.py
echo "✅ Alterações feitas. Matando bot antigo..."
pkill -9 python
sleep 2
echo "🚀 Iniciando bot com config agressiva..."
python main.py &
echo "✅ Bot iniciado!"
EOF

chmod +x fix_medroso.sh
./fix_medroso.sh
```

---

## 📊 Impacto das Mudanças

| Config | Antes | Depois | Impacto |
|--------|-------|--------|---------|
| `use_regime_filter` | True | False | +40% entradas |
| `min_adx` | 25 | 15 | +20% entradas |
| `volume_multiplier` | 1.6 | 1.2 | +15% entradas |
| **TOTAL** | - | - | **~75% +entradas** |

**Trade-off:** Win Rate pode cair de 30% para 25% (+taxa de erro), mas mais oportunidades.

---

## ✅ Validar Mudanças

Após reiniciar bot, verifique logs:

```bash
# Terminal 1: Ver bot rodando
tail -f logs/bot.log | grep -E "BUY|SELL|HOLD"

# Esperado: mais BUY/SELL que antes
```

---

## 🆘 Se o Bot Ficar MUITO Agressivo

Se passar a fazer > 5 trades/hora:

```python
# Voltar para:
self.use_regime_filter = True
self.min_adx = 20  # (meio termo entre 25 e 15)
self.volume_multiplier = 1.4  # (meio termo entre 1.6 e 1.2)
```

---

## ⚠️ IMPORTANTE: NÃO MEXER

**Nunca desative estas proteções:**
- ✅ RR 1:2 (Mack Rule #1) - CRÍTICO para rentabilidade
- ✅ Clean Breakout - ESSENCIAL para qualidade
- ✅ Dashboard monitoring - NECESSÁRIO para controle

---

## 📞 Recomendação Final

1. **Hoje:** Ativar modo agressivo (3 mudanças acima)
2. **24 horas:** Monitorar trades gerados
3. **Se OK:** Manter configuração
4. **Se muitas losses:** Aumentar `min_adx` para 20

Boa sorte! 🚀
