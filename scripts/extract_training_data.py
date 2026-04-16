"""
Training Data Extraction Pipeline v3
======================================
Key changes from v2:
  - Uses shared backend/ai/feature_engineering.py (train/inference parity)
  - Triple-barrier labeling: UP / FLAT / DOWN (3-class)
    * UP   = max(fwd_close[1..h]) / close - 1 >= upper_barrier first
    * DOWN = min(fwd_close[1..h]) / close - 1 <= -lower_barrier first
    * FLAT = neither (include timeout barrier)
  - Purge + embargo: removes overlap rows at split boundaries
  - Extended to 2026 data
"""

import os
import sys
import glob
import json
import argparse

import numpy as np
import pandas as pd
import polars as pl
from tqdm import tqdm

# Import shared feature engineering
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend'))
from ai.feature_engineering import engineer_features, FEATURE_LIST

# Backward compat alias
FEATURE_LIST_V2 = FEATURE_LIST


# ── Triple-barrier labeling ───────────────────────────────────────────────────

def triple_barrier_labels(
    close: pd.Series,
    upper: float = 0.07,
    lower: float = 0.05,
    horizon: int = 10,
) -> pd.DataFrame:
    """
    Triple-barrier labeling for each bar.

    Barriers:
      - Upper: +upper (e.g. +7%) → label = 1 (UP)
      - Lower: -lower (e.g. -5%) → label = -1 (DOWN)
      - Timeout: horizon bars elapsed without touching either → label = 0 (FLAT)

    Returns DataFrame with columns:
      - label:       -1 / 0 / 1
      - target_up:   1 if label == 1
      - target_down: 1 if label == -1
      - fwd_return:  close[t+horizon] / close[t] - 1 (point return, not barrier)
    """
    n = len(close)
    prices = close.values
    labels = np.zeros(n, dtype=np.int8)
    fwd_returns = np.full(n, np.nan)

    for i in range(n - 1):
        end = min(i + horizon, n - 1)
        entry = prices[i]
        if entry <= 0:
            continue

        hit = 0
        for j in range(i + 1, end + 1):
            ret = prices[j] / entry - 1
            if ret >= upper:
                hit = 1
                break
            if ret <= -lower:
                hit = -1
                break

        labels[i] = hit
        if end < n:
            fwd_returns[i] = prices[end] / entry - 1

    result = pd.DataFrame({
        'label':       labels,
        'target_up':   (labels == 1).astype(np.int8),
        'target_down': (labels == -1).astype(np.int8),
        'fwd_return':  fwd_returns,
    }, index=close.index)

    # Last `horizon` bars have no valid label
    result.iloc[-horizon:] = np.nan

    return result


# ── Main extraction ───────────────────────────────────────────────────────────

def extract_training_data(
    ohlcv_dir: str,
    output_file: str,
    symbols=None,
    upper_barrier: float = 0.07,
    lower_barrier: float = 0.05,
    horizon: int = 10,
    min_bars: int = 200,
):
    """Extract OHLCV → 45 features + triple-barrier labels → parquet."""

    if not symbols:
        if os.path.exists('top200.txt'):
            with open('top200.txt', 'r') as f:
                content = f.read().strip()
                if content.startswith('['):
                    symbols = json.loads(content)
                else:
                    symbols = [l.strip() for l in content.split('\n') if l.strip()]
        else:
            symbols = [
                os.path.basename(f).replace('.parquet', '')
                for f in glob.glob(os.path.join(ohlcv_dir, '*.parquet'))
            ]

    print(f"Extracting data for {len(symbols)} symbols...")
    print(f"Features: {len(FEATURE_LIST)}")
    print(f"Labels: UP>={upper_barrier*100:.0f}%, DOWN<=-{lower_barrier*100:.0f}%, horizon={horizon}d")

    all_data = []
    skipped = 0

    for symbol in tqdm(symbols):
        try:
            fpath = os.path.join(ohlcv_dir, f'{symbol}.parquet')
            if not os.path.exists(fpath):
                skipped += 1
                continue

            df_pl = pl.read_parquet(fpath)
            pdf = df_pl.to_pandas()
            pdf.columns = [c.lower() for c in pdf.columns]
            pdf = pdf.sort_values('date').reset_index(drop=True)
            pdf['symbol'] = symbol

            if len(pdf) < min_bars + horizon:
                skipped += 1
                continue

            # Feature engineering (shared module)
            pdf = engineer_features(pdf)

            # Triple-barrier labels
            lbl = triple_barrier_labels(
                pdf['close'], upper=upper_barrier, lower=lower_barrier, horizon=horizon
            )
            pdf['label']       = lbl['label']
            pdf['target_up']   = lbl['target_up']
            pdf['target_down'] = lbl['target_down']
            pdf['fwd_return']  = lbl['fwd_return']

            # Fill features
            pdf[FEATURE_LIST] = pdf[FEATURE_LIST].ffill().fillna(0)

            # Drop rows with missing labels or features
            pdf = pdf.dropna(subset=['label', 'target_up', 'target_down', 'fwd_return'])

            if len(pdf) > 0:
                all_data.append(pdf[['symbol', 'date'] + FEATURE_LIST + ['label', 'target_up', 'target_down', 'fwd_return']])

        except Exception as e:
            print(f"  Error {symbol}: {e}")
            skipped += 1

    if not all_data:
        print("No data extracted.")
        return

    final_df = pd.concat(all_data, ignore_index=True)
    final_df['date'] = pd.to_datetime(final_df['date'])
    final_df = final_df.sort_values(['date', 'symbol']).reset_index(drop=True)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    final_df.to_parquet(output_file, index=False)

    print(f"\nSaved {len(final_df):,} bars from {len(all_data)} symbols → {output_file}")
    print(f"Skipped: {skipped} symbols")
    print(f"Date range: {final_df['date'].min().date()} ~ {final_df['date'].max().date()}")
    up_rate   = final_df['target_up'].mean()
    down_rate = final_df['target_down'].mean()
    flat_rate = 1 - up_rate - down_rate
    print(f"Label distribution — UP: {up_rate:.2%}, DOWN: {down_rate:.2%}, FLAT: {flat_rate:.2%}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ohlcv_dir',       default='/Users/eugene/nullalgo/simons/data/ohlcv')
    parser.add_argument('--output_file',     default='/Users/eugene/nullalgo/simons/data/training_data_v3.parquet')
    parser.add_argument('--upper_barrier',   type=float, default=0.07)
    parser.add_argument('--lower_barrier',   type=float, default=0.05)
    parser.add_argument('--horizon',         type=int,   default=10)
    parser.add_argument('--min_bars',        type=int,   default=200)
    args = parser.parse_args()

    extract_training_data(
        args.ohlcv_dir,
        args.output_file,
        upper_barrier=args.upper_barrier,
        lower_barrier=args.lower_barrier,
        horizon=args.horizon,
        min_bars=args.min_bars,
    )
