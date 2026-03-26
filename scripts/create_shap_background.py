"""Create SHAP background dataset for XAI explanations. Works with v1 and v2 models."""

import os
import sys
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
from ai.ai_engine import AIEngine, _engineer_features_v2, _engineer_features_v1


def create_background(model_dir=None):
    print("Initializing AIEngine...")
    engine = AIEngine(model_dir=model_dir)

    # Try loading processed training data
    processed_path = os.path.join(engine.model_dir, 'training_data_processed.parquet')
    if not os.path.exists(processed_path):
        processed_path = "model/training_data_processed.parquet"

    print(f"Loading training data from {processed_path}...")
    df = pd.read_parquet(processed_path)

    df['date'] = pd.to_datetime(df['date'])
    # Use validation period data for representative background
    val_df = df[(df['date'].dt.year >= 2022) & (df['date'].dt.year <= 2023)].copy()
    if val_df.empty:
        val_df = df[df['date'].dt.year == 2023].copy()

    symbols = val_df['symbol'].unique()
    n_sample = min(30, len(symbols))
    sampled_symbols = np.random.choice(symbols, n_sample, replace=False)

    background_windows = []
    features_to_use = engine.ts_features

    print(f"Generating windows from {n_sample} symbols...")
    for sym in sampled_symbols:
        sym_df = val_df[val_df['symbol'] == sym].sort_values('date').copy()
        sym_df.columns = [c.lower() for c in sym_df.columns]

        if len(sym_df) < engine.lookback:
            continue

        # Feature engineering
        if engine.model_version >= 2:
            sym_df = _engineer_features_v2(sym_df)
        else:
            sym_df = _engineer_features_v1(sym_df)

        sym_df[features_to_use] = sym_df[features_to_use].replace(
            [np.inf, -np.inf], np.nan
        ).ffill().fillna(0)
        scaled_data = engine.scaler.transform(sym_df[features_to_use].values).astype(np.float32)
        scaled_data = np.ascontiguousarray(scaled_data)

        n_windows = len(scaled_data) - engine.lookback + 1
        if n_windows <= 0:
            continue

        s0, s1 = scaled_data.strides
        windows_arr = as_strided(
            scaled_data,
            shape=(n_windows, engine.lookback, len(features_to_use)),
            strides=(s0, s0, s1),
        )

        idx = np.random.choice(len(windows_arr), min(10, len(windows_arr)), replace=False)
        background_windows.append(np.array(windows_arr[idx]))

    if not background_windows:
        print("No windows generated.")
        return

    background_windows = np.concatenate(background_windows, axis=0)

    # Keep 100-200 samples for fast KernelSHAP
    target_size = min(200, len(background_windows))
    if len(background_windows) > target_size:
        idx = np.random.choice(len(background_windows), target_size, replace=False)
        background_windows = background_windows[idx]

    print(f"Background shape: {background_windows.shape}")

    out_path = os.path.join(engine.model_dir, 'shap_background.npy')
    np.save(out_path, background_windows)
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_dir", default=None)
    args = parser.parse_args()
    create_background(args.model_dir)
