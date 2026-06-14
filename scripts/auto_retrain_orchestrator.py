"""
Autonomous post-resync AI retrain orchestrator.

Chains: wait for KIS adjusted-price resync to finish → rebuild training universe →
extract features from the new adjusted OHLCV → back up the live model → train a
*candidate* model (model/v3_candidate, never overwriting the live model/v3).

Safety: the production model/v3 is left untouched; promotion happens only after a
metric comparison (done separately once this completes). The pre-resync model is
also copied aside. XGBoost/torch OpenMP-segfault and polars-deadlock guards are set.

Run in background:
    cd /Users/eugene/nullalgo/simons && .venv/bin/python scripts/auto_retrain_orchestrator.py
"""
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import polars as pl

ROOT = Path('/Users/eugene/nullalgo/simons')
DONE_FILE = ROOT / 'data' / 'ohlcv' / '.kis_resync_done.json'
LOG = ROOT / 'data' / 'ohlcv' / '.auto_retrain.log'   # gitignored dir
PY = str(ROOT / '.venv' / 'bin' / 'python')

ENV = {**os.environ, 'KMP_DUPLICATE_LIB_OK': 'TRUE', 'OMP_NUM_THREADS': '1', 'POLARS_MAX_THREADS': '1'}


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def wait_for_resync() -> None:
    master = json.loads((ROOT / 'data' / 'stock-master.json').read_text())['stocks']
    target = sum(1 for s in master if s.get('hasOhlcv'))
    log(f"PHASE 0: waiting for resync (target={target})")
    last, stall = -1, 0
    while True:
        n = len(json.loads(DONE_FILE.read_text())) if DONE_FILE.exists() else 0
        if n >= target:
            log(f"resync complete: {n}/{target}")
            return
        stall = stall + 1 if n == last else 0
        last = n
        if stall >= 40:  # ~40 min with no progress → resync likely dead
            if n >= 0.9 * target:
                log(f"resync stalled at {n}/{target} (>=90%), proceeding")
                return
            log(f"resync stalled at {n}/{target} (<90%) — ABORT")
            raise SystemExit(1)
        time.sleep(60)


def build_universe() -> int:
    """top200.txt = top-200 active commons by market cap (close × shares)."""
    log("PHASE 1: building top200 training universe")
    master = json.loads((ROOT / 'data' / 'stock-master.json').read_text())['stocks']
    active = [s for s in master if s.get('hasOhlcv') and not s.get('delistingDate') and s.get('shares')]
    caps = []
    for s in active:
        try:
            c = pl.read_parquet(ROOT / f"data/ohlcv/{s['symbol']}.parquet", columns=['close'])['close']
            if len(c):
                caps.append((s['symbol'], float(c[-1]) * float(s['shares'])))
        except Exception:
            continue
    caps.sort(key=lambda x: -x[1])
    top200 = [sym for sym, _ in caps[:200]]
    (ROOT / 'top200.txt').write_text('\n'.join(top200))
    log(f"top200.txt written ({len(top200)} symbols)")
    return len(top200)


def run(cmd, label) -> int:
    log(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(ROOT), env=ENV)
    log(f"{label} exit={r.returncode}")
    return r.returncode


def main() -> None:
    log("=== auto_retrain_orchestrator START ===")
    wait_for_resync()

    if build_universe() < 50:
        log("universe too small — ABORT")
        raise SystemExit(1)

    # PHASE 2: feature extraction from the new adjusted OHLCV
    log("PHASE 2: extract_training_data.py")
    if run([PY, 'scripts/extract_training_data.py'], 'extract') != 0:
        log("extract FAILED — ABORT")
        raise SystemExit(1)

    # PHASE 3: preserve the current production model
    ts = time.strftime('%Y%m%d_%H%M%S')
    backup = ROOT / f'model/v3_pre_resync_{ts}'
    if (ROOT / 'model/v3').exists():
        shutil.copytree(ROOT / 'model/v3', backup)
        log(f"PHASE 3: backed up model/v3 -> {backup.name}")

    # PHASE 4: train candidate (does NOT overwrite live model/v3)
    candidate = ROOT / 'model/v3_candidate'
    if candidate.exists():
        shutil.rmtree(candidate)
    log("PHASE 4: train_model.py -> model/v3_candidate (~6-8h)")
    rc = run([PY, 'scripts/train_model.py',
              '--data_path', 'data/training_data_v3.parquet',
              '--model_dir', 'model/v3_candidate'], 'train')

    log(f"=== ORCHESTRATOR_DONE train_rc={rc} candidate={candidate} ===")


if __name__ == '__main__':
    main()
