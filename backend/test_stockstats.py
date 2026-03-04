from stockstats import StockDataFrame
import pandas as pd

df = pd.DataFrame({
    'date': pd.date_range('2024-01-01', periods=100),
    'open': [100.0] * 100,
    'high': [105.0] * 100,
    'low': [95.0] * 100,
    'close': [100.0, 101.0, 99.0, 102.0, 100.0] * 20,
    'volume': [1000000.0, 1200000.0, 900000.0, 1100000.0, 1000000.0] * 20
})

sdf = StockDataFrame.retype(df.copy())
print("Testing OBV...")
try:
    obv = sdf['obv']
    print("OBV success! Head:", obv.head())
except Exception as e:
    print("OBV Error:", e)

print("Columns in sdf after OBV access:", sdf.columns)
