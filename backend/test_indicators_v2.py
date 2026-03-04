import pandas as pd
import polars as pl
import sys
import os

sys.path.append(os.getcwd())
from engine.indicators import IndicatorEngine

df = pd.DataFrame({
    'date': pd.date_range('2024-01-01', periods=200),
    'open': [100.0] * 200,
    'high': [105.0] * 200,
    'low': [95.0] * 200,
    'close': [102.0] * 200,
    'volume': [1000000.0] * 200
})

conditions = [
    {'id': 'ma_crossover', 'params': {'short': 5, 'long': 20}},
    {'id': 'ema', 'params': {'period': 20}},
    {'id': 'rsi', 'params': {'period': 14}},
    {'id': 'macd', 'params': {}},
    {'id': 'stochastic', 'params': {}},
    {'id': 'cci', 'params': {'period': 14}},
    {'id': 'adx', 'params': {}},
    {'id': 'bollinger_bands', 'params': {'period': 20}},
    {'id': 'volume_spike', 'params': {'period': 20}}
]

try:
    res = IndicatorEngine.calculate(pl.from_pandas(df), conditions)
    print("Calculated columns:", res.columns)
except Exception as e:
    print("Error:", e)
    import traceback
    traceback.print_exc()
