"""
AIEngine v3 — Inference engine for Hybrid Transformer + XGBoost.

Changes from v2:
  - Uses shared feature_engineering module (training/inference parity)
  - Supports v3 model: DualHeadModel embeddings, no scale_pos_weight
  - Thresholds loaded from model_meta.json (calibrated on val set)
  - No embedding augmentation (removed norm/mean/std/max/min)
  - Backward-compatible with v2 model directory structure
"""

import os
import json
import threading
import logging
import random
import concurrent.futures
import warnings

import torch
import xgboost as xgb
import pandas as pd
import numpy as np
import joblib
from numpy.lib.stride_tricks import as_strided

from ai.models import HybridAIModel
from ai.feature_engineering import engineer_features, FEATURE_LIST, N_FEATURES

seed = 42
torch.manual_seed(seed)
np.random.seed(seed)
random.seed(seed)

logger = logging.getLogger(__name__)


class AIEngine:
    def __init__(self, model_dir: str | None = None):
        if model_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            # Prefer v3, fall back to v2
            v3 = os.path.join(base, 'model', 'v3')
            v2 = os.path.join(base, 'model', 'v2')
            model_dir = v3 if os.path.exists(os.path.join(v3, 'model_meta.json')) else v2

        self.model_dir  = model_dir
        self.model_lock = threading.Lock()
        self._score_cache: dict = {}

        # Determinism
        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            self.device = torch.device('cuda')
        elif torch.backends.mps.is_available():
            self.device = torch.device('mps')
        else:
            self.device = torch.device('cpu')

        # Load metadata
        meta_path = os.path.join(model_dir, 'model_meta.json')
        with open(meta_path, 'r') as f:
            self.meta = json.load(f)

        self.model_version  = self.meta.get('version', 3)
        self.lookback       = self.meta.get('lookback', 60)
        self.buy_threshold  = self.meta.get('buy_threshold', 0.5)
        self.sell_threshold = self.meta.get('sell_threshold', 0.5)

        # Backward-compat aliases
        self.ts_features     = FEATURE_LIST
        self.use_separate_xgb = True

        # Load scaler
        scaler_path = os.path.join(model_dir, 'feature_scaler.joblib')
        if not os.path.exists(scaler_path):
            raise FileNotFoundError(f"Scaler not found: {scaler_path}")
        self.scaler = joblib.load(scaler_path)

        # Validate scaler dimension
        expected = getattr(self.scaler, 'n_features_in_', None)
        if isinstance(expected, int) and expected != N_FEATURES:
            raise ValueError(f"Scaler expects {expected} features, but FEATURE_LIST has {N_FEATURES}")

        # Transformer dimensions
        d_model       = self.meta.get('d_model', 256)
        nhead         = self.meta.get('nhead', 4)
        num_layers    = self.meta.get('num_layers', 7)
        dim_ff        = self.meta.get('dim_feedforward', 1024)
        dropout       = self.meta.get('dropout', 0.2)
        stoch_depth   = self.meta.get('stochastic_depth', 0.1)

        self.transformer = HybridAIModel(
            input_dim=N_FEATURES,
            d_model=d_model,
            nhead=nhead,
            num_layers=num_layers,
            dim_feedforward=dim_ff,
            dropout=dropout,
            stochastic_depth=stoch_depth,
        ).to(self.device)

        model_path = os.path.join(model_dir, 'transformer_engine.pt')
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Transformer not found: {model_path}")
        self.transformer.load_state_dict(
            torch.load(model_path, map_location=self.device, weights_only=True)
        )
        self.transformer.eval()

        # XGBoost models
        up_path   = os.path.join(model_dir, 'xgboost_up.json')
        down_path = os.path.join(model_dir, 'xgboost_down.json')

        if not os.path.exists(up_path):
            raise FileNotFoundError(f"XGBoost UP not found: {up_path}")
        if not os.path.exists(down_path):
            raise FileNotFoundError(f"XGBoost DOWN not found: {down_path}")

        self.xgb_up   = xgb.XGBClassifier()
        self.xgb_down = xgb.XGBClassifier()
        self.xgb_up.load_model(up_path)
        self.xgb_down.load_model(down_path)

        logger.info(f"AIEngine v{self.model_version} initialized — "
                    f"Device={self.device}, Features={N_FEATURES}, Lookback={self.lookback}, "
                    f"buy_thr={self.buy_threshold:.4f}, sell_thr={self.sell_threshold:.4f}, "
                    f"ModelDir={model_dir}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _preprocess_for_ai(self, df: pd.DataFrame):
        """Feature engineering + scaling + sliding windows. No lock needed."""
        n = len(df)
        if n <= self.lookback:
            return None

        pdf = df.copy()
        pdf.columns = [c.lower() for c in pdf.columns]
        pdf = engineer_features(pdf)

        pdf[FEATURE_LIST] = pdf[FEATURE_LIST].ffill().fillna(0)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            scaled = np.ascontiguousarray(
                self.scaler.transform(pdf[FEATURE_LIST].values).astype(np.float32)
            )

        n_windows = n - self.lookback + 1
        s0, s1 = scaled.strides
        windows = as_strided(
            scaled,
            shape=(n_windows, self.lookback, N_FEATURES),
            strides=(s0, s0, s1),
        )
        return scaled, n, windows, n_windows

    def _infer_windows(self, windows: np.ndarray) -> np.ndarray:
        """Transformer forward pass. Caller must hold model_lock."""
        batch_size = 4096
        parts = []
        with torch.inference_mode():
            for i in range(0, len(windows), batch_size):
                batch = torch.from_numpy(
                    np.ascontiguousarray(windows[i:i + batch_size])
                ).to(self.device)
                parts.append(self.transformer(batch).cpu().numpy())
        return np.concatenate(parts, axis=0)

    def _xgb_predict(self, embeddings: np.ndarray):
        """XGBoost predict → (sig_probs, drop_probs)."""
        try:
            sig_probs  = self.xgb_up.predict_proba(embeddings)[:, 1]
        except Exception:
            sig_probs  = self.xgb_up.predict(embeddings).astype(float)
        try:
            drop_probs = self.xgb_down.predict_proba(embeddings)[:, 1]
        except Exception:
            drop_probs = self.xgb_down.predict(embeddings).astype(float)
        return sig_probs, drop_probs

    # ── Public API ────────────────────────────────────────────────────────────

    def predict_signals(self, df: pd.DataFrame) -> tuple:
        """Single-symbol inference. Returns (ai_probs, ai_drop_probs)."""
        result = self.predict_signals_batch({'_single': df})
        return result['_single']

    def predict_signals_batch(self, dfs: dict) -> dict:
        """
        Batch inference for multiple symbols.

        Args:
            dfs: {symbol: pd.DataFrame} — OHLCV data

        Returns:
            {symbol: (ai_probs, ai_drop_probs)}
            Each array has length == len(df), padded with zeros for the first
            (lookback-1) bars that have no complete window.
        """
        def _cache_key(sym: str, df: pd.DataFrame) -> tuple:
            idx = df.index
            return (sym, str(idx[-1]) if len(idx) else '', len(df))

        # Cache check
        results: dict = {}
        uncached: dict = {}
        for sym, df in dfs.items():
            key = _cache_key(sym, df)
            if key in self._score_cache:
                results[sym] = self._score_cache[key]
            else:
                uncached[sym] = df

        if uncached:
            logger.info(f"[AI-Batch] Cache hit={len(results)}, miss={len(uncached)}")

        # Phase 1: parallel preprocessing (no lock)
        def _prep(item):
            sym, df = item
            try:
                return sym, self._preprocess_for_ai(df)
            except Exception as e:
                logger.warning(f"[AI-Batch] {sym} preprocess failed: {e}")
                return sym, None

        with concurrent.futures.ThreadPoolExecutor() as ex:
            prep = dict(ex.map(_prep, uncached.items()))

        valid = {s: d for s, d in prep.items() if d is not None}
        sym_order = list(valid.keys())

        # Phase 2: Transformer + XGBoost (single lock)
        if sym_order:
            with self.model_lock:
                windows_list = []
                sym_meta = {}
                for sym in sym_order:
                    _, n, windows, n_windows = valid[sym]
                    windows_list.append(np.ascontiguousarray(windows))
                    sym_meta[sym] = (n_windows, n)

                all_windows   = np.concatenate(windows_list, axis=0)
                logger.info(f"[AI-Batch] Transformer: {len(all_windows)} windows ({len(sym_order)} symbols)")
                all_embeddings = self._infer_windows(all_windows)
                all_sig, all_drop = self._xgb_predict(all_embeddings)

                offset = 0
                for sym in sym_order:
                    n_windows, n = sym_meta[sym]
                    sig  = all_sig[offset:offset + n_windows]
                    drop = all_drop[offset:offset + n_windows]
                    offset += n_windows

                    probs      = np.zeros(n)
                    probs_drop = np.zeros(n)
                    probs[self.lookback - 1:]      = sig
                    probs_drop[self.lookback - 1:] = drop

                    scored = (probs, probs_drop)
                    results[sym] = scored
                    self._score_cache[_cache_key(sym, uncached[sym])] = scored

        # Fill missing symbols
        for sym, df in dfs.items():
            if sym not in results:
                n = len(df)
                results[sym] = (np.zeros(n), np.zeros(n))

        return results


if __name__ == '__main__':
    engine = AIEngine()
    dates = pd.date_range('2024-01-01', periods=100)
    df = pd.DataFrame({
        'open':   np.random.rand(100) * 1000 + 500,
        'high':   np.random.rand(100) * 1000 + 600,
        'low':    np.random.rand(100) * 1000 + 400,
        'close':  np.random.rand(100) * 1000 + 500,
        'volume': np.random.rand(100) * 100000 + 10000,
    }, index=dates)
    probs, probs_drop = engine.predict_signals(df)
    print(f"Predictions: {len(probs)} steps. "
          f"Up>thr: {(probs >= engine.buy_threshold).sum()}, "
          f"Down>thr: {(probs_drop >= engine.sell_threshold).sum()}")
