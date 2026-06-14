"""
Autonomous post-training evaluation + promotion.

Waits for the retrain orchestrator to finish, then fairly compares the freshly
trained candidate (model/v3_candidate) against the live model (model/v3) on the
SAME adjusted test set, promotes the candidate only if it is clearly better
(with backups), and runs the AI regression suite. Everything is logged.

Run in background after launching the orchestrator:
    cd /Users/eugene/nullalgo/simons && \
      KMP_DUPLICATE_LIB_OK=TRUE OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
      .venv/bin/python scripts/auto_evaluate_and_promote.py
"""
import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pandas as pd

ROOT = Path('/Users/eugene/nullalgo/simons')
LOG = ROOT / 'data' / 'ohlcv' / '.auto_retrain.log'
LIVE = ROOT / 'model' / 'v3'
CAND = ROOT / 'model' / 'v3_candidate'
DATA = ROOT / 'data' / 'training_data_v3.parquet'
PY = str(ROOT / '.venv' / 'bin' / 'python')
REQUIRED = ['transformer_engine.pt', 'xgboost_up.json', 'xgboost_down.json',
            'feature_scaler.joblib', 'model_meta.json']
ENV = {**os.environ, 'KMP_DUPLICATE_LIB_OK': 'TRUE', 'OMP_NUM_THREADS': '1', 'POLARS_MAX_THREADS': '1'}


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [eval] {msg}"
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


def _load_eval_fn():
    spec = importlib.util.spec_from_file_location('eval_model', ROOT / 'scripts' / 'eval_model.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.eval_model


def wait_for_training() -> bool:
    # train_model.py writes model_meta.json LAST (after the transformer + both XGBoost
    # heads), so its appearance is the definitive "training fully complete" signal —
    # far more robust than scanning a shared log for a marker string.
    meta = CAND / 'model_meta.json'
    log("waiting for candidate model_meta.json (final training artifact)...")
    for _ in range(60 * 24):  # up to 24h
        if meta.exists() and all((CAND / f).exists() for f in REQUIRED):
            log("candidate training complete")
            time.sleep(15)  # let any trailing writes flush
            return True
        time.sleep(60)
    log("timeout waiting for training — ABORT")
    return False


def main() -> None:
    if not wait_for_training():
        return
    if not all((CAND / f).exists() for f in REQUIRED):
        log(f"candidate incomplete (training likely failed) — live model untouched, ABORT")
        return

    eval_model = _load_eval_fn()
    live_ts = json.loads((LIVE / 'model_meta.json').read_text()).get('test_start', '2024-07-21')
    cand_ts = json.loads((CAND / 'model_meta.json').read_text()).get('test_start', '2024-07-21')
    test_start = max(live_ts, cand_ts)  # out-of-sample for both
    log(f"evaluating both models on test_start={test_start}")

    df = pd.read_parquet(DATA)
    df['date'] = pd.to_datetime(df['date'])

    live = eval_model(str(LIVE), df, test_start)
    cand = eval_model(str(CAND), df, test_start)
    log(f"LIVE      n={live['n_test']} UP(AP={live['up_ap']:.4f} AUC={live['up_auc']:.4f}) "
        f"DOWN(AP={live['down_ap']:.4f} AUC={live['down_auc']:.4f})")
    log(f"CANDIDATE n={cand['n_test']} UP(AP={cand['up_ap']:.4f} AUC={cand['up_auc']:.4f}) "
        f"DOWN(AP={cand['down_ap']:.4f} AUC={cand['down_auc']:.4f})")

    live_auc = (live['up_auc'] + live['down_auc']) / 2
    cand_auc = (cand['up_auc'] + cand['down_auc']) / 2
    live_ap = (live['up_ap'] + live['down_ap']) / 2
    cand_ap = (cand['up_ap'] + cand['down_ap']) / 2
    log(f"mean AUC: live={live_auc:.4f} cand={cand_auc:.4f} | mean AP: live={live_ap:.4f} cand={cand_ap:.4f}")

    # Promote only on a clear improvement: AUC up by a margin and AP not regressing.
    promote = (cand_auc > live_auc + 0.004) and (cand_ap > live_ap - 0.004)
    if promote:
        ts = time.strftime('%Y%m%d_%H%M%S')
        shutil.copytree(LIVE, ROOT / f'model/v3_pre_promote_{ts}')
        for f in os.listdir(CAND):
            shutil.copy2(CAND / f, LIVE / f)
        log(f"DECISION: PROMOTED candidate → model/v3 (backup model/v3_pre_promote_{ts})")
    else:
        log("DECISION: KEPT live model (candidate not clearly better). Candidate left at model/v3_candidate.")

    # Regression suite (validates whatever now sits at model/v3)
    log("running AI regression tests (test_ai_model_fixes.py)")
    r = subprocess.run([PY, '-m', 'pytest', 'tests/test_ai_model_fixes.py', '-q', '-p', 'no:cacheprovider'],
                       cwd=str(ROOT / 'backend'), env=ENV, capture_output=True, text=True)
    tail = '\n'.join(r.stdout.strip().splitlines()[-3:])
    log(f"regression tests rc={r.returncode}: {tail}")
    log("EVAL_AND_PROMOTE_DONE")


if __name__ == '__main__':
    main()
