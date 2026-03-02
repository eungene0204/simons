import pandas as pd
import numpy as np
import sys
sys.path.append("/Users/eugene/nullalgo/simons/backend")
from engine.simulator import Simulator

sim = Simulator()
dates = pd.date_range("2024-01-01", periods=5)
syms = ["SYM0"]
price = pd.DataFrame(np.ones((5, 1)) * 100, index=dates, columns=syms)
exec_price = price.copy()
entries = pd.DataFrame(np.zeros((5, 1), dtype=bool), index=dates, columns=syms)
entries.iloc[0, 0] = True
exits = pd.DataFrame(np.zeros((5, 1), dtype=bool), index=dates, columns=syms)
exits.iloc[2, 0] = True

pf = sim.run(price, exec_price, entries, exits, {"skip_risk_management": True}, {})
print(pf.trades.records_readable.columns)
