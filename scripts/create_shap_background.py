import pandas as pd
import numpy as np
import os
from backend.ai.ai_engine import AIEngine
from numpy.lib.stride_tricks import as_strided

def create_background():
    print("Initializing AIEngine to load Scaler...")
    try:
        engine = AIEngine(model_dir="model")
    except Exception as e:
        print(f"Failed to load AIEngine: {e}")
        return

    print("Loading prepared training data...")
    df = pd.read_parquet("model/training_data_processed.parquet")
    
    # We want a representative background, e.g. from 2023
    df['date'] = pd.to_datetime(df['date'])
    val_df = df[df['date'].dt.year == 2023].copy()
    
    # Sample a few random stocks
    symbols = val_df['symbol'].unique()
    sampled_symbols = np.random.choice(symbols, 20, replace=False)
    
    background_windows = []
    
    print("Generating windows for background dataset...")
    for sym in sampled_symbols:
        sym_df = val_df[val_df['symbol'] == sym].sort_values('date').copy()
        
        if len(sym_df) < engine.lookback:
            continue
            
        # 1. Feature Engineering
        for col in ['open', 'high', 'low', 'close']:
            sym_df[f'ret_{col}'] = sym_df[col].pct_change()
        sym_df['ret_volume'] = sym_df['volume'].pct_change()
        
        # Determine actual RSI column
        actual_rsi = next((c for c in sym_df.columns if c.startswith('rsi')), None)
        features_to_use = ['ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', actual_rsi]
        
        sym_df[features_to_use] = sym_df[features_to_use].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)
        scaled_data = engine.scaler.transform(sym_df[features_to_use].values).astype(np.float32)
        
        # Create windows
        n_windows = len(scaled_data) - engine.lookback + 1
        num_features = len(features_to_use)
        orig_strides = scaled_data.strides
        new_shape = (n_windows, engine.lookback, num_features)
        new_strides = (orig_strides[0], orig_strides[0], orig_strides[1])
        windows_arr = as_strided(scaled_data, shape=new_shape, strides=new_strides)
        
        # Append some random windows from this stock
        if len(windows_arr) > 0:
            idx = np.random.choice(len(windows_arr), min(10, len(windows_arr)), replace=False)
            background_windows.append(windows_arr[idx])

    if not background_windows:
        print("No windows generated.")
        return

    background_windows = np.concatenate(background_windows, axis=0)
    
    # We want exactly 100 background samples to keep KernelSHAP fast
    if len(background_windows) > 100:
        idx = np.random.choice(len(background_windows), 100, replace=False)
        background_windows = background_windows[idx]
        
    print(f"Generated background shape: {background_windows.shape}")
    
    out_path = "model/shap_background.npy"
    np.save(out_path, background_windows)
    print(f"Successfully saved SHAP background to {out_path}")

if __name__ == "__main__":
    create_background()
