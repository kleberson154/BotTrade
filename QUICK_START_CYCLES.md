# 🎯 QUICK START - Market Cycles Deployment

## PRÉ-REQUISITOS ✅
- [x] Market Cycles Analyzer criado (`src/market_cycles.py`)
- [x] Strategy.py integrado com ajustes dinâmicos  
- [x] Main.py integrado com leverage factor
- [x] Monitoring dashboard integrado com reset system
- [x] Win Rate resetado para hoje
- [x] Testes passaram (7/7 integration tests)
- [x] Git commit feito (7e2e854)

## 🚀 DEPLOY EM 3 PASSOS

### PASSO 1️⃣: START THE BOT
```bash
cd c:\Users\zed15\OneDrive\Documentos\projetos\BotTrade
python main.py
```

**Sinais de sucesso:**
```
✅ Market Cycles Analyzer: Load BTC dominance OK
✅ Strategies loaded for 6 coins
✅ WebSocket connecting...
✅ Ready for trading signals
```

**Duration:** Deixe rodando por 2-6 horas

---

### PASSO 2️⃣: MONITOR EM PARALELO (em outro terminal)
```bash
python monitoring_dashboard.py
```

**O que você vai ver:**
```
📊 LIVE PORTFOLIO STATS
├─ Win Rate: 0% → X% (crescente conforme trades chegam)
├─ Total PnL: 0% → X%
├─ Market Cycle: NEUTRAL (1.0x leverage)
└─ Status: TRACKING FRESH (desde 2026-04-13 02:12)
```

---

### PASSO 3️⃣: VALIDAÇÃO (Checklist)
Durante as 2-6 horas de DEMO:

- [ ] Bot está rodando sem crashes
- [ ] Pelo menos 5-10 trades foram abertos
- [ ] Win Rate >= 25% (mínimo aceitável)
- [ ] Nenhum erro de API ou conexão
- [ ] Leverage está sendo ajustado (verifique logs para "cycle adjustment")
- [ ] RSI está controlando dinamicamente filtros (RSI > 65 ou < 35)

---

## 📈 PERFORMANCE TARGET

| Métrica | Target | OK? |
|---------|--------|-----|
| Win Rate | >= 25% | |
| Trades/hora | >= 2 | |
| Erros | 0 | |
| API Latency | < 500ms | |
| Memory | < 300MB | |

---

## ✅ PRÓXIMOS STAGES

### Se WR >= 25% após 2h:
```
1. TESTNET: python main.py (com BYBIT_MODE="testnet")
2. Duration: 2-4 horas com real balance
3. Target: WR >= 28% e sem crashes
4. After: READY FOR LIVE (com cuidado e monitoring constante)
```

### Se WR < 20% ou erros frequentes:
```
1. DIAGNOSTICS
2. Possível tuning de parâmetros
3. Revisar logs: HOLD motivos sendo gravados?
4. Confirmar dados de mercado: BTC está saindo sinais?
```

---

## 🔧 USEFUL COMMANDS

### Ver logs em tempo real (últimas 50 linhas):
```bash
tail -50 trading_bot.log
```

### Grep por sinais específicos:
```bash
grep "BUY\|SELL" trading_bot.log | tail -20
```

### Grep por erros:
```bash
grep -i "error\|exception" trading_bot.log
```

### Check if .json history is growing:
```bash
wc -l trading_log.json
ls -lh trading_log.json
```

### Ver Market Cycles adjustments:
```bash
grep "Ajuste de ciclo\|leverage factor" trading_bot.log
```

---

## 🚨 EMERGENCY STOP

Quer parar tudo rapidamente?
```bash
Ctrl+C em main.py terminal
```

**Isso vai:**
- ✅ Fechar posições abertas
- ✅ Cancelar ordens pendentes
- ✅ Salvar estado final
- ❌ NÃO vai deletar histórico de trades

---

## 📞 KEY FILES TO WATCH

1. **Main logs:**
   - `trading_bot.log` - Todos os eventos
   - `RESET_TRADES_TODAY.txt` - Timestamp do reset (confirmar que existe)
   - `trading_log.json` - Histórico de trades (deve crescer)

2. **Code que está rodando:**
   - `src/market_cycles.py` - Ajustes de ciclo (import check)
   - `src/strategy.py` - Filtros dinâmicos (RSI-based)
   - `main.py` - Leverage aplicando factor (execute_new_trade)

3. **Dashboard monitoring:**
   - Você vai rodar `monitoring_dashboard.py` manualmente

---

## 🎯 META FINAL

**After 2-6h DEMO with WR >= 25%:**

```
✅ System is production-ready
✅ Market Cycles integration working
✅ Win Rate tracking from today only
✅ Ready for TESTNET with real balance
✅ Consider LIVE trading after TESTNET validation
```

---

## 💡 TROUBLESHOOTING TIPS

**Q: How do I know if Market Cycles is working?**
A: Check logs for "Ajuste de ciclo" when RSI crosses 35 or 65
```bash
grep "Ajuste de ciclo" trading_bot.log
```

**Q: Win Rate not moving up?**
A: Either:
- No trades being executed (check for "BUY/SELL" signals)
- Signals are all HOLDs (check HOLD motivos)
- Check internet/API connection

**Q: Bot crashed, do I lose trades?**
A: No - all trades saved in `trading_log.json`
- Restart: `python main.py` (will restore from file)

**Q: Want to revert to old Win Rate tracking?**
A: Delete `RESET_TRADES_TODAY.txt`
- Next restart will load all historical trades

---

## 🎊 VOCÊ ESTÁ PRONTO!

Tudo foi implementado, testado, e integrado.

**Time to shine:**
```
python main.py
```

Good luck! 🚀
