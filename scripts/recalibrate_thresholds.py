"""
Recalibrate the live model's buy/sell thresholds in model_meta.json.

The shipped thresholds are written at train time by train_model.calibrate_threshold.
A prior version returned a fixed 0.5 fallback whenever the val precision target was
unreachable — and for the heavily regularized DOWN head, whose scores compress into
~[0.35, 0.38], 0.5 sits *above the max score*, so `ai_drop_model` never fired.

This script recomputes both thresholds with the corrected, fire-rate-floored
calibrator, scoring the val window exactly the way production inference does
(AIEngine: same scaler + transformer + XGBoost up/down heads, full-series sliding
windows masked to the val date range). It backs up model_meta.json and rewrites the
two threshold fields in place; nothing else in the model changes.

    KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
      .venv/bin/python scripts/recalibrate_thresholds.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import as_strided

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from ai.feature_engineering import FEATURE_LIST, N_FEATURES  # noqa: E402

MODEL_DIR = ROOT / 'model' / 'v3'
DATA = ROOT / 'data' / 'training_data_v3.parquet'
LOOKBACK = 60


def _load_calibrate_threshold():
    spec = importlib.util.spec_from_file_location('train_model', ROOT / 'scripts' / 'train_model.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.calibrate_threshold


def _score_range(eng, df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp):
    """Score every window whose predicted date falls in [start, end), the way the
    live engine does. Returns (up_prob, up_y, down_prob, down_y)."""
    up_p, up_y, dn_p, dn_y = [], [], [], []
    for _sym, g in df.groupby('symbol'):
        g = g.sort_values('date').reset_index(drop=True)
        if len(g) <= LOOKBACK:
            continue
        feats = g[FEATURE_LIST].to_numpy(dtype=np.float32)
        scaled = np.ascontiguousarray(eng.scaler.transform(feats).astype(np.float32))
        nw = len(g) - LOOKBACK + 1
        s0, s1 = scaled.strides
        windows = as_strided(scaled, shape=(nw, LOOKBACK, N_FEATURES), strides=(s0, s0, s1))
        emb = eng._infer_windows(windows)
        up, dn = eng._xgb_predict(emb)
        end_idx = np.arange(LOOKBACK - 1, len(g))
        dates = pd.to_datetime(g['date'].to_numpy()[end_idx])
        tu = g['target_up'].to_numpy()[end_idx]
        td = g['target_down'].to_numpy()[end_idx]
        mask = (dates >= start) & (dates < end) & ~np.isnan(tu) & ~np.isnan(td)
        if mask.any():
            up_p.append(up[mask]); up_y.append(tu[mask])
            dn_p.append(dn[mask]); dn_y.append(td[mask])
    return (np.concatenate(up_p), np.concatenate(up_y),
            np.concatenate(dn_p), np.concatenate(dn_y))


def main() -> None:
    from ai.ai_engine import AIEngine

    meta_path = MODEL_DIR / 'model_meta.json'
    meta = json.loads(meta_path.read_text())

    # Reconstruct the train-time val window from meta (same embargoed split).
    val_str = meta.get('val_range', '2023-01-21 ~ 2024-07-01')
    val_start_s, val_end_s = [s.strip() for s in val_str.split('~')]
    val_start, val_end = pd.Timestamp(val_start_s), pd.Timestamp(val_end_s)

    calibrate_threshold = _load_calibrate_threshold()
    eng = AIEngine(model_dir=str(MODEL_DIR))

    df = pd.read_parquet(DATA)
    df['date'] = pd.to_datetime(df['date'])

    print(f"[recalib] scoring val window {val_start.date()} ~ {val_end.date()} ...", flush=True)
    up_p, up_y, dn_p, dn_y = _score_range(eng, df, val_start, val_end)
    print(f"[recalib] val windows: up={len(up_y)} down={len(dn_y)} "
          f"(up_rate={up_y.mean():.3f} down_rate={dn_y.mean():.3f})")
    print(f"[recalib] score range — UP [{up_p.min():.3f},{up_p.max():.3f}] "
          f"DOWN [{dn_p.min():.3f},{dn_p.max():.3f}]")

    new_buy = calibrate_threshold(up_y, up_p, target_precision=0.55)
    new_sell = calibrate_threshold(dn_y, dn_p, target_precision=0.55)
    old_buy = float(meta.get('buy_threshold', 0.5))
    old_sell = float(meta.get('sell_threshold', 0.5))

    buy_fire = float((up_p >= new_buy).mean())
    sell_fire = float((dn_p >= new_sell).mean())
    print(f"[recalib] buy_threshold : {old_buy:.4f} -> {new_buy:.4f}  (fires {buy_fire*100:.1f}% of val bars)")
    print(f"[recalib] sell_threshold: {old_sell:.4f} -> {new_sell:.4f}  (fires {sell_fire*100:.1f}% of val bars)")

    backup = MODEL_DIR / f"model_meta.pre_recalib_{time.strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(meta_path, backup)
    meta['buy_threshold'] = new_buy
    meta['sell_threshold'] = new_sell
    meta_path.write_text(json.dumps(meta, indent=4))
    print(f"[recalib] updated {meta_path} (backup {backup.name})")


if __name__ == '__main__':
    main()
