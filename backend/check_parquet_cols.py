import pandas as pd
df = pd.read_parquet('data/training_data_raw.parquet', columns=None)
print("Columns in raw parquet:", df.columns.tolist())
print("First few rows of features:")
print(df[['ret_close', 'ret_obv', 'dist_sma_20', 'boll_pos']].head())
