import vectorbt as vbt
import pandas as pd
import numpy as np

init_cash = 10000000.0
dates = pd.date_range('2023-01-01', periods=5)
# Sizing Price = 100. Exec Price = 1000.
val_prices = pd.Series([100]*5, index=dates)
exec_prices = pd.Series([1000]*5, index=dates)

entries = pd.Series([True, False, False, False, False], index=dates)
exits = pd.Series([False, False, False, False, False], index=dates)

print("--- Default (Expect -90M cash) ---")
pf = vbt.Portfolio.from_signals(
    close=val_prices,
    price=exec_prices,
    entries=entries,
    exits=exits,
    init_cash=init_cash,
    size=1.0,
    size_type='Percent',
    accumulate=False
)
print(f"Cash after buy: {pf.cash().iloc[1]:,.0f}")
print(f"Equity after buy: {pf.value().iloc[1]:,.0f}")

print("\n--- with allow_partial=True (Expect 0 cash) ---")
pf2 = vbt.Portfolio.from_signals(
    close=val_prices,
    price=exec_prices,
    entries=entries,
    exits=exits,
    init_cash=init_cash,
    size=1.0,
    size_type='Percent',
    accumulate=False,
    allow_partial=True
)
print(f"Cash after buy: {pf2.cash().iloc[1]:,.0f}")
print(f"Equity after buy: {pf2.value().iloc[1]:,.0f}")

