import vectorbt as vbt
import pandas as pd
import numpy as np

# Simulate User Scenario
init_cash = 10000000.0
fee_rate = 0.0015
slippage_rate = 0.0020

# Create dummy data: 100 days
dates = pd.date_range('2023-01-01', periods=100)
# Price starts at 10000, drops to 1 over 100 days (drastic loss)
prices = pd.Series(np.linspace(10000, 1, 100), index=dates)

# Signals: Buy on day 1, Sell on day 2, Buy on day 3... (excessive trading)
entries = pd.Series([i % 2 == 0 for i in range(100)], index=dates)
exits = pd.Series([i % 2 != 0 for i in range(100)], index=dates)

vbt_kwargs = dict(
    size=1.0, # 100%
    size_type='Percent',
    init_cash=init_cash,
    fees=fee_rate,
    slippage=slippage_rate,
    freq='D'
)

pf = vbt.Portfolio.from_signals(
    close=prices,
    entries=entries,
    exits=exits,
    accumulate=False,
    **vbt_kwargs
)

print(f"Initial Cash: {init_cash}")
print(f"Final Value: {pf.value().iloc[-1]}")
print(f"Total Return %: {pf.total_return() * 100}")
print(f"Net Profit: {pf.total_profit()}")

# What if we have REALLY high fees?
vbt_kwargs_crazy_fees = vbt_kwargs.copy()
vbt_kwargs_crazy_fees['fees'] = 1.0 # 100% fee per trade!

pf_crazy = vbt.Portfolio.from_signals(
    close=prices,
    entries=entries,
    exits=exits,
    accumulate=False,
    **vbt_kwargs_crazy_fees
)

print(f"\n[With 100% Fees]")
print(f"Final Value: {pf_crazy.value().iloc[-1]}")
