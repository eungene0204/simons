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
from collections import OrderedDict

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
        # Bounded LRU cache (keyed per symbol) — prevents unbounded memory growth
        # in a long-running server that scores many symbols over many requests.
        self._score_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
        self._cache_max = 8192
        # Max windows processed per transformer/XGBoost flush — bounds peak
        # memory during full-universe batches (streamed, not all at once).
        self._window_budget = 8192

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

        # Transformer dimensions. These must match the trained checkpoint;
        # defaults mirror the shipped v3 model so an incomplete meta degrades
        # safely instead of silently building a mismatched network (which would
        # otherwise surface only as a cryptic load_state_dict shape error).
        shape_keys = ('d_model', 'nhead', 'num_layers', 'dim_feedforward')
        missing = [k for k in shape_keys if k not in self.meta]
        if missing:
            logger.warning("model_meta.json missing architecture keys %s — "
                           "falling back to shipped v3 defaults (128/8/3); "
                           "checkpoint load will fail if the real values differ.", missing)
        d_model       = self.meta.get('d_model', 128)
        nhead         = self.meta.get('nhead', 8)
        num_layers    = self.meta.get('num_layers', 3)
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

    def _cache_put(self, key: tuple, value: tuple):
        """Insert into the bounded LRU score cache, evicting the oldest if full."""
        self._score_cache[key] = value
        self._score_cache.move_to_end(key)
        while len(self._score_cache) > self._cache_max:
            self._score_cache.popitem(last=False)

    def _preprocess_for_ai(self, df: pd.DataFrame):
        """Feature engineering + scaling + sliding windows. No lock needed."""
        n = len(df)
        if n <= self.lookback:
            return None

        pdf = df.copy()
        pdf.columns = [c.lower() for c in pdf.columns]
        pdf = engineer_features(pdf)

        pdf[FEATURE_LIST] = pdf[FEATURE_LIST].ffill().fillna(0)
        feature_frame = pdf[FEATURE_LIST].copy()

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            scaled = np.ascontiguousarray(
                self.scaler.transform(feature_frame).astype(np.float32)
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
        legacy_head = getattr(self, "xgb_head", None)
        if legacy_head is not None:
            try:
                preds = legacy_head.predict_proba(embeddings)
                return preds[:, 0], preds[:, 1]
            except Exception:
                pass
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
            # Include a content fingerprint, not just (sym, last_index, len):
            # the single-symbol path always passes sym='_single', so two
            # different frames with the same length and last index would
            # otherwise collide and return the wrong cached scores.
            idx = df.index
            last_idx = str(idx[-1]) if len(idx) else ''
            close_col = next((c for c in df.columns if c.lower() == 'close'), None)
            n = len(df)
            if close_col is not None and n:
                col = df[close_col]
                fp = (float(col.iloc[0]), float(col.iloc[n // 2]), float(col.iloc[-1]))
            else:
                fp = (0.0, 0.0, 0.0)
            return (sym, last_idx, n) + fp

        # Cache check
        results: dict = {}
        uncached: dict = {}
        for sym, df in dfs.items():
            key = _cache_key(sym, df)
            if key in self._score_cache:
                self._score_cache.move_to_end(key)
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

        # Phase 2: Transformer + XGBoost (single lock).
        # Stream symbols through the model in bounded chunks rather than
        # materializing every window of every symbol at once — a full-universe
        # batch would otherwise allocate tens of GB before inference starts.
        if sym_order:
            with self.model_lock:
                window_budget = self._window_budget

                def _flush(buf_windows, buf_meta):
                    batch = np.concatenate(buf_windows, axis=0)
                    emb = self._infer_windows(batch)
                    sig_all, drop_all = self._xgb_predict(emb)
                    off = 0
                    for sym, n_windows, n in buf_meta:
                        sig  = sig_all[off:off + n_windows]
                        drop = drop_all[off:off + n_windows]
                        off += n_windows

                        probs      = np.zeros(n)
                        probs_drop = np.zeros(n)
                        probs[self.lookback - 1:]      = sig
                        probs_drop[self.lookback - 1:] = drop

                        scored = (probs, probs_drop)
                        results[sym] = scored
                        self._cache_put(_cache_key(sym, uncached[sym]), scored)

                buf_windows: list = []
                buf_meta: list = []
                buf_count = 0
                for sym in sym_order:
                    _, n, windows, n_windows = valid[sym]
                    buf_windows.append(np.ascontiguousarray(windows))
                    buf_meta.append((sym, n_windows, n))
                    buf_count += n_windows
                    if buf_count >= window_budget:
                        logger.info(f"[AI-Batch] Transformer flush: {buf_count} windows ({len(buf_meta)} symbols)")
                        _flush(buf_windows, buf_meta)
                        buf_windows, buf_meta, buf_count = [], [], 0
                if buf_windows:
                    logger.info(f"[AI-Batch] Transformer flush: {buf_count} windows ({len(buf_meta)} symbols)")
                    _flush(buf_windows, buf_meta)

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
