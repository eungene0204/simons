"""
Preprocessing Pipeline v2.

Reads raw training data, applies RobustScaler to all 45 features,
and saves the processed parquet + scaler for inference.
"""

import os
import argparse

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler
import joblib

# Import feature list from extraction script
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_training_data import FEATURE_LIST_V2


def preprocess_for_training(input_file: str, output_dir: str):
    """Scale features with RobustScaler and save processed data."""

    print(f"Loading raw data from {input_file}...")
    df = pd.read_parquet(input_file)
    print(f"Loaded {len(df):,} rows")

    # Verify all features exist
    missing = [f for f in FEATURE_LIST_V2 if f not in df.columns]
    if missing:
        raise ValueError(f"Missing features in data: {missing}")

    # Sanitize Inf/NaN
    print("Sanitizing data (Inf/NaN)...")
    df[FEATURE_LIST_V2] = df[FEATURE_LIST_V2].replace([np.inf, -np.inf], np.nan)
    df[FEATURE_LIST_V2] = df[FEATURE_LIST_V2].ffill().bfill().fillna(0)

    # Clip extreme outliers (> 10 std from median) per feature before scaling
    print("Clipping extreme outliers...")
    for feat in FEATURE_LIST_V2:
        median = df[feat].median()
        std = df[feat].std()
        if std > 0:
            lower = median - 10 * std
            upper = median + 10 * std
            df[feat] = df[feat].clip(lower=lower, upper=upper)

    # Scale
    print(f"Scaling {len(FEATURE_LIST_V2)} features with RobustScaler...")
    scaler = RobustScaler()
    df[FEATURE_LIST_V2] = scaler.fit_transform(df[FEATURE_LIST_V2])

    # Save
    os.makedirs(output_dir, exist_ok=True)
    joblib.dump(scaler, os.path.join(output_dir, 'feature_scaler.joblib'))

    processed_file = os.path.join(output_dir, 'training_data_processed.parquet')
    df.to_parquet(processed_file)

    print(f"Preprocessing complete.")
    print(f"  Processed data: {processed_file}")
    print(f"  Scaler: {os.path.join(output_dir, 'feature_scaler.joblib')}")
    print(f"  Features: {len(FEATURE_LIST_V2)}")
    print(f"  Total samples: {len(df):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", default="/Users/eugene/nullalgo/simons/data/training_data_raw_v2.parquet")
    parser.add_argument("--output_dir", default="/Users/eugene/nullalgo/simons/model/v2")
    args = parser.parse_args()

    preprocess_for_training(args.input_file, args.output_dir)
