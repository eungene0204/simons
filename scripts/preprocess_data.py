import pandas as pd
import numpy as np
import polars as pl
from sklearn.preprocessing import RobustScaler
import joblib
import os

def preprocess_for_training(input_file, output_dir, lookback=60):
    """
    Prepares the raw data for Transformer + XGBoost training.
    """
    print(f"Loading raw data from {input_file}...")
    df = pd.read_parquet(input_file)
    
    # 1. Feature Selection
    # Transformer features (Time-series)
    ts_features = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'rsi_14']
    
    # XGBoost features (Point-in-time + Transformer Embedding)
    static_features = ['sector', 'symbol'] # To be encoded later
    
    # Target
    target = 'target_7pct_10d'
    
    # Scale Calculation might produce Inf/-Inf if prices are zero (rare but possible in bad data)
    print("Sanitizing data (Inf/NaN)...")
    df[ts_features] = df[ts_features].replace([np.inf, -np.inf], np.nan)
    df[ts_features] = df[ts_features].ffill().bfill().fillna(0)

    # 2. Scaling
    print("Scaling features...")
    scaler = RobustScaler()
    df[ts_features] = scaler.fit_transform(df[ts_features])
    
    # Save scaler for inference
    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(scaler, os.path.join(output_dir, 'feature_scaler.joblib'))
    
    # 3. Handle Categorical
    df['sector_code'] = df['sector'].astype('category').cat.codes
    
    # 4. Save processed dataframe
    # We don't create 3D windows here yet as it would explode file size.
    # We save the cleaned flat file and will use a custom PyTorch Dataset to create windows on the fly.
    processed_file = os.path.join(output_dir, 'training_data_processed.parquet')
    df.to_parquet(processed_file)
    
    print(f"Preprocessing complete. Processed data saved to {processed_file}")
    print(f"Features used for Transformer: {ts_features}")
    print(f"Total samples: {len(df)}")

if __name__ == "__main__":
    RAW_FILE = "/Users/eugene/nullalgo/simons/data/training_data_raw.parquet"
    OUTPUT_DIR = "/Users/eugene/nullalgo/simons/model"
    preprocess_for_training(RAW_FILE, OUTPUT_DIR)
