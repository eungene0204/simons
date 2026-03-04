import pandas as pd
import os
raw_file = os.path.join(os.getcwd(), '..', 'data', 'training_data_raw.parquet')
if not os.path.exists(raw_file):
    print(f"ERROR: {raw_file} not found")
    sys.exit(1)

df = pd.read_parquet(raw_file, columns=None)
print("Columns in raw parquet:", df.columns.tolist())
features = ['ret_close', 'ret_obv', 'dist_sma_20', 'boll_pos']
for f in features:
    if f in df.columns:
        print(f"{f} present. Sample values:", df[f].head().tolist())
    else:
        print(f"{f} MISSING from parquet!")
