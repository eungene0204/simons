"""
Fair head-to-head evaluation of two AI signal models on the SAME test set.

Loads a model via the production AIEngine (so inference parity is guaranteed — same
scaler, transformer backbone, XGBoost up/down heads) and scores every test-period
window, then reports UP/DOWN average-precision and ROC-AUC. Each model uses its own
fitted scaler (correct), and both are scored on the same adjusted test data, so the
comparison answers "which model serves us better on the data we now trust."

Usage:
    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 \
      python scripts/eval_model.py model/v3 --data data/training_data_v3.parquet --test_start 2024-07-21
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from ai.feature_engineering import FEATURE_LIST, N_FEATURES  # noqa: E402


def eval_model(model_dir: str, df: pd.DataFrame, test_start: str, lookback: int = 60) -> dict:
    from ai.ai_engine import AIEngine
    eng = AIEngine(model_dir=model_dir)
    ts = pd.Timestamp(test_start)

    up_p, up_y, dn_p, dn_y = [], [], [], []
    for _sym, g in df.groupby('symbol'):
        g = g.sort_values('date').reset_index(drop=True)
        if len(g) <= lookback:
            continue
        feats = g[FEATURE_LIST].to_numpy(dtype=np.float32)
        scaled = np.ascontiguousarray(eng.scaler.transform(feats).astype(np.float32))
        n_windows = len(g) - lookback + 1
        s0, s1 = scaled.strides
        windows = as_strided(scaled, shape=(n_windows, lookback, N_FEATURES), strides=(s0, s0, s1))

        emb = eng._infer_windows(windows)
        up, dn = eng._xgb_predict(emb)

        end_idx = np.arange(lookback - 1, len(g))          # date index each window predicts
        dates = pd.to_datetime(g['date'].to_numpy()[end_idx])
        tu = g['target_up'].to_numpy()[end_idx]
        td = g['target_down'].to_numpy()[end_idx]
        mask = (dates >= ts) & ~np.isnan(tu) & ~np.isnan(td)
        if mask.any():
            up_p.append(up[mask]); up_y.append(tu[mask])
            dn_p.append(dn[mask]); dn_y.append(td[mask])

    up_p, up_y = np.concatenate(up_p), np.concatenate(up_y)
    dn_p, dn_y = np.concatenate(dn_p), np.concatenate(dn_y)
    return {
        "model_dir": model_dir,
        "n_test": int(len(up_y)),
        "up_ap": float(average_precision_score(up_y, up_p)),
        "up_auc": float(roc_auc_score(up_y, up_p)),
        "up_rate": float(up_y.mean()),
        "down_ap": float(average_precision_score(dn_y, dn_p)),
        "down_auc": float(roc_auc_score(dn_y, dn_p)),
        "down_rate": float(dn_y.mean()),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('model_dir')
    ap.add_argument('--data', default='data/training_data_v3.parquet')
    ap.add_argument('--test_start', default='2024-07-21')
    args = ap.parse_args()

    df = pd.read_parquet(args.data)
    df['date'] = pd.to_datetime(df['date'])
    m = eval_model(args.model_dir, df, args.test_start)
    print(f"[eval] {m['model_dir']}  n={m['n_test']}")
    print(f"  UP   AP={m['up_ap']:.4f}  AUC={m['up_auc']:.4f}  (base rate {m['up_rate']:.3f})")
    print(f"  DOWN AP={m['down_ap']:.4f}  AUC={m['down_auc']:.4f}  (base rate {m['down_rate']:.3f})")


if __name__ == '__main__':
    main()
