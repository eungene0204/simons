import vectorbt as vbt
import pandas as pd
import numpy as np

# init_cash 10M
init_cash = 10000000.0

# 1. Test Inconsistent Prices
dates = pd.date_range('2023-01-01', periods=10)
val_prices = pd.Series([100]*10, index=dates) # Val stays at 100
exec_prices = pd.Series([10, 1000, 10, 1000, 10, 1000, 10, 1000, 10, 1000], index=dates)

entries = pd.Series([True, False, True, False, True, False, True, False, True, False], index=dates)
exits = pd.Series([False, True, False, True, False, True, False, True, False, True], index=dates)

pf_inconsistent = vbt.Portfolio.from_signals(
    close=val_prices,
    price=exec_prices,
    entries=entries,
    exits=exits,
    init_cash=init_cash,
    size=1.0,
    size_type='Percent',
    accumulate=False,
    fees=0.0015
)

print(f"--- Inconsistent Prices Test ---")
print(f"Final Value: {pf_inconsistent.value().iloc[-1]:,.0f}")
print(f"Total Return: {pf_inconsistent.total_return():.2%}")

# 2. Test Negative Cash Potential
# Each buy at 1000, Val is 100. 
# Buying 100% of 10M at 1000 means buying 10k shares. 
# Valuation says you have 10k * 100 = 1M. 
# Next buy tries to buy 100% of 1M? 
# Let's see if cash goes negative.
print(f"Min Cash: {pf_inconsistent.cash().min():,.0f}")

# 3. What if Fees are based on NOTional?
# Some systems allow bankrupt portfolios to keep trading.
