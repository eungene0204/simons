import pandas as pd
import numpy as np
import os
from backend.ai.ai_engine import AIEngine
from numpy.lib.stride_tricks import as_strided

def create_background():
    print("Initializing AIEngine to load Scaler...")
    try:
        # Use the NEW expanded model
        engine = AIEngine(model_dir="model/expanded_features")
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
            
        # 1. Feature Engineering (Expanded 17 features)
        from backend.engine.indicators import IndicatorEngine
        indicator_reqs = [
            {'id': 'ema', 'params': {'period': 20}},
            {'id': 'macd', 'params': {}},
            {'id': 'stochastic', 'params': {}},
            {'id': 'cci', 'params': {'period': 14}},
            {'id': 'adx', 'params': {}},
            {'id': 'bollinger_bands', 'params': {'period': 20}},
            {'id': 'volume_spike', 'params': {'period': 20}}
        ]
        import polars as pl
        sym_df_pl = IndicatorEngine.calculate(pl.from_pandas(sym_df), indicator_reqs)
        sym_df = sym_df_pl.to_pandas()

        # Price/Volume Log Returns
        for col in ['open', 'high', 'low', 'close']:
            sym_df[f'ret_{col}'] = np.log1p(sym_df[col].pct_change())
        sym_df['ret_volume'] = np.log1p(sym_df['volume'].pct_change())
        sym_df['ret_obv'] = np.log1p(sym_df['obv'].pct_change())

        # Stationary Technical Features
        sym_df['dist_sma_20'] = sym_df['close'] / sym_df['close_20_sma'] - 1
        sym_df['dist_ema_20'] = sym_df['close'] / sym_df['close_20_ema'] - 1
        sym_df['boll_pos'] = (sym_df['close'] - sym_df['boll_lb']) / (sym_df['boll_ub'] - sym_df['boll_lb'] + 1e-8)
        
        features_to_use = engine.ts_features
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
    
    out_path = "model/expanded_features/shap_background.npy"
    np.save(out_path, background_windows)
    print(f"Successfully saved SHAP background to {out_path}")

if __name__ == "__main__":
    create_background()
