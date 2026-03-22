class SimpleBacktester:
    def __init__(self, strategy_class, df_1m, df_15m):
        self.df_1m = df_1m
        self.df_15m = df_15m
        self.strat = strategy_class
        self.results = []
        self.balance = 1000 # USDT inicial
        
    def run(self):
        print("🚀 Iniciando Simulação...")
        
        # Começamos após 200 velas para ter média móvel pronta
        for i in range(200, len(self.df_1m)):
            current_row = self.df_1m.iloc[i]
            current_price = current_row['close']
            current_time = self.df_1m.index[i]
            
            # 1. Atualiza os dados "vistos" pelo bot até este minuto
            self.strat.data_1m = self.df_1m.iloc[:i+1]
            self.strat.data_15m = self.df_15m[self.df_15m.index <= current_time]
            
            # 2. Lógica de Monitoramento
            if self.strat.is_positioned:
                status = self.strat.monitor_protection(current_price)
                
                if status == "PARTIAL_EXIT":
                    if not self.strat.partial_taken:
                        profit = (self.strat.entry_price - current_price) / self.strat.entry_price if self.strat.side == "SELL" else (current_price - self.strat.entry_price) / self.strat.entry_price
                        print(f"💰 [{current_time}] PARCIAL EXECUTADA: +{profit:.2%} de lucro em 50% da mão.")
                        # (Aqui você somaria ao balance simulações de taxas)
                
                # Checa se bateu no Stop Loss
                if self.strat.side == "BUY" and current_price <= self.strat.sl_price:
                    self.close_trade("STOP LOSS", current_price, current_time)
                elif self.strat.side == "SELL" and current_price >= self.strat.sl_price:
                    self.close_trade("STOP LOSS", current_price, current_time)

            # 3. Lógica de Entrada
            else:
                signal, atr = self.strat.check_signal()
                if signal in ["BUY", "SELL"]:
                    self.strat.is_positioned = True
                    self.strat.side = signal
                    self.strat.entry_price = current_price
                    self.strat.sl_price = current_price - (atr * 7.5) if signal == "BUY" else current_price + (atr * 7.5)
                    self.strat.partial_taken = False
                    print(f"⚡ [{current_time}] ENTRADA {signal} em {current_price}")

    def close_trade(self, reason, price, time):
        pnl = (self.strat.entry_price - price) / self.strat.entry_price if self.strat.side == "SELL" else (price - self.strat.entry_price) / self.strat.entry_price
        print(f"🛑 [{time}] FECHAMENTO: {reason} | PnL Final: {pnl:.2%}")
        self.strat.is_positioned = False
        self.results.append(pnl)

# Para rodar:
# bt = SimpleBacktester(sua_instancia_de_estrategia, df_1m, df_15m)
# bt.run()