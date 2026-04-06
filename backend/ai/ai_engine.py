"""
AIEngine v2 — Inference engine for Hybrid Transformer + XGBoost.

Supports both v1 (single XGBoost head) and v2 (separate up/down XGBoost models).
Auto-detects model version from model_meta.json.
"""

import torch
import xgboost as xgb
import pandas as pd
import numpy as np
import polars as pl
import joblib
import os
import json
import threading
import logging
import random
import concurrent.futures
import warnings
from numpy.lib.stride_tricks import as_strided

from ai.models import HybridAIModel

seed = 42
torch.manual_seed(seed)
np.random.seed(seed)
random.seed(seed)

logger = logging.getLogger(__name__)


# ── Feature engineering (matches extract_training_data.py v2) ────────────────

def _safe_log_return(series: pd.Series) -> pd.Series:
    pct = series.pct_change()
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.log1p(pct)


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=1).mean()
    rs = gain / (loss + 1e-10)
    return 100 - 100 / (1 + rs)


def _roc(close: pd.Series, period: int) -> pd.Series:
    return close.pct_change(period)


def _williams_r(high, low, close, period=14):
    hh = high.rolling(period).max()
    ll = low.rolling(period).min()
    return -100 * (hh - close) / (hh - ll + 1e-10)


def _mfi(high, low, close, volume, period=14):
    tp = (high + low + close) / 3
    mf = tp * volume
    delta = tp.diff()
    pos_mf = (mf * (delta > 0)).rolling(period, min_periods=1).sum()
    neg_mf = (mf * (delta <= 0)).rolling(period, min_periods=1).sum()
    return 100 - 100 / (1 + pos_mf / (neg_mf + 1e-10))


def _tsi(close, r=25, s=13):
    diff = close.diff()
    s1 = diff.ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    s2 = diff.abs().ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    return 100 * s1 / (s2 + 1e-10)


def _aroon(high, low, period=25):
    up = high.rolling(period + 1).apply(lambda x: x.argmax(), raw=True) / period * 100
    down = low.rolling(period + 1).apply(lambda x: x.argmin(), raw=True) / period * 100
    return up, down


def _trix(close, period=15):
    e1 = close.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return e3.pct_change() * 100


def _atr(high, low, close, period=14):
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _garman_klass_vol(open_, high, low, close, window=20):
    log_hl = (np.log(high.clip(lower=1e-10) / (low + 1e-10))) ** 2
    log_co = (np.log(close.clip(lower=1e-10) / (open_ + 1e-10))) ** 2
    gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    return gk.rolling(window, min_periods=1).mean().apply(np.sqrt)


def _keltner_position(close, high, low, period=20, atr_mult=2.0):
    mid = close.ewm(span=period, adjust=False).mean()
    atr_val = _atr(high, low, close, period)
    upper = mid + atr_mult * atr_val
    lower = mid - atr_mult * atr_val
    return (close - lower) / (upper - lower + 1e-10)


def _ad_line(high, low, close, volume):
    clv = ((close - low) - (high - close)) / (high - low + 1e-10)
    return (clv * volume).cumsum()


# V2 feature list (45 features)
FEATURES_V2 = [
    'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv',
    'rsi_7', 'rsi_14', 'rsi_21', 'roc_5', 'roc_10', 'roc_20',
    'williams_r_14', 'mfi_14', 'tsi',
    'macd', 'macds', 'macdh', 'adx', 'cci_14',
    'aroon_up', 'aroon_down', 'trix_15',
    'dist_sma_10', 'dist_sma_20', 'dist_sma_50',
    'dist_ema_10', 'dist_ema_20', 'dist_ema_50',
    'boll_pos', 'atr_14_norm', 'keltner_pos',
    'hist_vol_10', 'hist_vol_20', 'garman_klass', 'natr_14',
    'vol_ratio_5', 'vol_ratio_20', 'obv_slope_10', 'ad_norm', 'vwap_dist',
    'candle_body_ratio', 'candle_upper_shadow', 'candle_lower_shadow', 'candle_range_norm',
]

# V1 feature list (17 features) — for backward compatibility
FEATURES_V1 = [
    'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv',
    'rsi_14', 'macd', 'macds', 'macdh', 'kdjk', 'kdjd', 'cci_14', 'adx',
    'dist_sma_20', 'dist_ema_20', 'boll_pos'
]


def _engineer_features_v2(pdf: pd.DataFrame) -> pd.DataFrame:
    """Compute all 45 v2 features from OHLCV DataFrame."""
    o, h, l, c, v = pdf['open'], pdf['high'], pdf['low'], pdf['close'], pdf['volume']

    # Log returns
    for col in ['open', 'high', 'low', 'close']:
        pdf[f'ret_{col}'] = _safe_log_return(pdf[col])
    pdf['ret_volume'] = _safe_log_return(v)

    close_diff = c.diff()
    direction = (close_diff > 0).astype(int) - (close_diff < 0).astype(int)
    direction.iloc[0] = 0
    pdf['obv'] = (direction * v).cumsum()
    pdf['ret_obv'] = _safe_log_return(pdf['obv'].replace(0, np.nan).ffill())

    # Momentum
    pdf['rsi_7'] = _rsi(c, 7)
    pdf['rsi_14'] = _rsi(c, 14)
    pdf['rsi_21'] = _rsi(c, 21)
    pdf['roc_5'] = _roc(c, 5)
    pdf['roc_10'] = _roc(c, 10)
    pdf['roc_20'] = _roc(c, 20)
    pdf['williams_r_14'] = _williams_r(h, l, c, 14)
    pdf['mfi_14'] = _mfi(h, l, c, v, 14)
    pdf['tsi'] = _tsi(c)

    # Trend
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    pdf['macd'] = ema12 - ema26
    pdf['macds'] = pdf['macd'].ewm(span=9, adjust=False).mean()
    pdf['macdh'] = pdf['macd'] - pdf['macds']

    plus_dm = h.diff().clip(lower=0)
    minus_dm = (-l.diff()).clip(lower=0)
    atr14 = _atr(h, l, c, 14)
    plus_di = 100 * (plus_dm.rolling(14, min_periods=1).mean() / (atr14 + 1e-10))
    minus_di = 100 * (minus_dm.rolling(14, min_periods=1).mean() / (atr14 + 1e-10))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    pdf['adx'] = dx.rolling(14, min_periods=1).mean()

    tp = (h + l + c) / 3
    sma_tp = tp.rolling(14, min_periods=1).mean()
    mad = tp.rolling(14, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    pdf['cci_14'] = (tp - sma_tp) / (0.015 * mad + 1e-10)

    pdf['aroon_up'], pdf['aroon_down'] = _aroon(h, l, 25)
    pdf['trix_15'] = _trix(c, 15)

    # MA distances
    for p in [10, 20, 50]:
        sma = c.rolling(p, min_periods=1).mean()
        ema = c.ewm(span=p, adjust=False).mean()
        pdf[f'dist_sma_{p}'] = c / sma - 1
        pdf[f'dist_ema_{p}'] = c / ema - 1

    # Volatility
    sma20 = c.rolling(20, min_periods=1).mean()
    std20 = c.rolling(20, min_periods=1).std()
    boll_ub = sma20 + 2 * std20
    boll_lb = sma20 - 2 * std20
    pdf['boll_pos'] = (c - boll_lb) / (boll_ub - boll_lb + 1e-10)
    pdf['atr_14_norm'] = atr14 / (c + 1e-10)
    pdf['keltner_pos'] = _keltner_position(c, h, l, 20, 2.0)

    log_ret = np.log(c.clip(lower=1e-10) / c.shift(1).clip(lower=1e-10))
    pdf['hist_vol_10'] = log_ret.rolling(10, min_periods=1).std() * np.sqrt(252)
    pdf['hist_vol_20'] = log_ret.rolling(20, min_periods=1).std() * np.sqrt(252)
    pdf['garman_klass'] = _garman_klass_vol(o, h, l, c, 20)
    pdf['natr_14'] = atr14 / (c + 1e-10) * 100

    # Volume patterns
    vol_ma5 = v.rolling(5, min_periods=1).mean()
    vol_ma20 = v.rolling(20, min_periods=1).mean()
    pdf['vol_ratio_5'] = v / (vol_ma5 + 1e-10)
    pdf['vol_ratio_20'] = v / (vol_ma20 + 1e-10)

    obv = pdf['obv']
    pdf['obv_slope_10'] = (obv - obv.shift(10)) / (obv.shift(10).abs() + 1e-10)

    ad = _ad_line(h, l, c, v)
    ad_range = ad.rolling(20, min_periods=1).max() - ad.rolling(20, min_periods=1).min()
    pdf['ad_norm'] = (ad - ad.rolling(20, min_periods=1).min()) / (ad_range + 1e-10)

    vwap_20 = (c * v).rolling(20, min_periods=1).sum() / (v.rolling(20, min_periods=1).sum() + 1e-10)
    pdf['vwap_dist'] = c / vwap_20 - 1

    # Candle patterns
    body = (c - o).abs()
    full_range = h - l + 1e-10
    pdf['candle_body_ratio'] = body / full_range
    pdf['candle_upper_shadow'] = (h - pd.concat([c, o], axis=1).max(axis=1)) / full_range
    pdf['candle_lower_shadow'] = (pd.concat([c, o], axis=1).min(axis=1) - l) / full_range
    avg_range = full_range.rolling(20, min_periods=1).mean()
    pdf['candle_range_norm'] = full_range / (avg_range + 1e-10)

    return pdf


def _engineer_features_v1(pdf: pd.DataFrame) -> pd.DataFrame:
    """V1 feature engineering (backward compat) using stockstats + IndicatorEngine."""
    from engine.indicators import IndicatorEngine

    if not any(c.startswith('rsi') for c in pdf.columns):
        from stockstats import StockDataFrame
        sdf = StockDataFrame.retype(pdf.copy())
        pdf['rsi_14'] = sdf['rsi_14']

    indicator_reqs = [
        {'id': 'ema', 'params': {'period': 20}},
        {'id': 'macd', 'params': {}},
        {'id': 'stochastic', 'params': {}},
        {'id': 'cci', 'params': {'period': 14}},
        {'id': 'adx', 'params': {}},
        {'id': 'bollinger_bands', 'params': {'period': 20}},
        {'id': 'volume_spike', 'params': {'period': 20}},
    ]
    pdf = IndicatorEngine.calculate(pl.from_pandas(pdf), indicator_reqs).to_pandas()

    with np.errstate(invalid='ignore', divide='ignore'):
        for col in ['open', 'high', 'low', 'close']:
            pdf[f'ret_{col}'] = np.log1p(pdf[col].pct_change())
        pdf['ret_volume'] = np.log1p(pdf['volume'].pct_change())
        pdf['ret_obv'] = np.log1p(pdf['obv'].pct_change())

    pdf['dist_sma_20'] = pdf['close'] / pdf['close_20_sma'] - 1
    pdf['dist_ema_20'] = pdf['close'] / pdf['close_20_ema'] - 1
    pdf['boll_pos'] = (pdf['close'] - pdf['boll_lb']) / (pdf['boll_ub'] - pdf['boll_lb'] + 1e-8)

    return pdf


# ── Embedding augmentation ──────────────────────────────────────────────────

def _augment_embeddings(emb: np.ndarray) -> np.ndarray:
    """Add statistical summary features to embeddings (must match training)."""
    norm = np.linalg.norm(emb, axis=1, keepdims=True)
    mean = emb.mean(axis=1, keepdims=True)
    std = emb.std(axis=1, keepdims=True)
    mx = emb.max(axis=1, keepdims=True)
    mn = emb.min(axis=1, keepdims=True)
    return np.hstack([emb, norm, mean, std, mx, mn])


# ── AIEngine ────────────────────────────────────────────────────────────────

class AIEngine:
    def __init__(self, model_dir=None):
        if model_dir is None:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_dir = os.path.join(base, 'model', 'v2')

        self.model_dir = model_dir
        self.model_lock = threading.Lock()
        self._score_cache: dict = {}

        torch.manual_seed(seed)
        np.random.seed(seed)
        random.seed(seed)

        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")

        # Load metadata
        meta_path = os.path.join(model_dir, 'model_meta.json')
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                self.meta = json.load(f)
        else:
            self.meta = {"buy_threshold": 0.07, "sell_threshold": 0.07, "lookback": 60}

        self.model_version = self.meta.get('version', 2)

        # Load scaler
        scaler_path = os.path.join(model_dir, 'feature_scaler.joblib')
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
        else:
            raise FileNotFoundError(f"Scaler not found at {scaler_path}")

        # Always use v2 features
        self.ts_features = FEATURES_V2

        self.lookback = self.meta.get('lookback', 60)

        # Load Transformer
        ts_features_count = len(self.ts_features)
        d_model = self.meta.get('d_model', 128)
        nhead = self.meta.get('nhead', 8)
        num_layers = self.meta.get('num_layers', 6)
        dim_feedforward = self.meta.get('dim_feedforward', 512)
        dropout = self.meta.get('dropout', 0.1)
        stochastic_depth = self.meta.get('stochastic_depth', 0.1)

        self.transformer = HybridAIModel(
            input_dim=ts_features_count,
            d_model=d_model,
            nhead=nhead,
            num_layers=num_layers,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            stochastic_depth=stochastic_depth,
        ).to(self.device)

        model_path = os.path.join(model_dir, 'transformer_engine.pt')
        if os.path.exists(model_path):
            self.transformer.load_state_dict(torch.load(model_path, map_location=self.device))
            self.transformer.eval()
        else:
            raise FileNotFoundError(f"Transformer model not found at {model_path}")

        # Load XGBoost v2 separate up/down models
        self.use_separate_xgb = True

        up_path = os.path.join(model_dir, 'xgboost_up.json')
        down_path = os.path.join(model_dir, 'xgboost_down.json')

        self.xgb_up = xgb.XGBClassifier()
        if os.path.exists(up_path):
            self.xgb_up.load_model(up_path)
        else:
            raise FileNotFoundError(f"XGBoost UP model not found at {up_path}")

        self.xgb_down = xgb.XGBClassifier()
        if os.path.exists(down_path):
            self.xgb_down.load_model(down_path)
        else:
            raise FileNotFoundError(f"XGBoost DOWN model not found at {down_path}")

        # Validate scaler
        expected_features = getattr(self.scaler, 'n_features_in_', None)
        actual_features = len(self.ts_features)
        if isinstance(expected_features, int) and expected_features != actual_features:
            raise ValueError(
                f"Scaler expects {expected_features} features but ts_features has {actual_features}."
            )

        logger.info(f"AIEngine v{self.model_version} initialized. Device={self.device}, "
                     f"Features={len(self.ts_features)}, Lookback={self.lookback}, "
                     f"SeparateXGB={self.use_separate_xgb}")

    # ── Internal helpers ────────────────────────────────────────────────────

    def _preprocess_for_ai(self, df: pd.DataFrame):
        """Feature engineering + scaling + sliding window creation (no lock needed)."""
        data_len = len(df)
        if data_len <= self.lookback:
            return None

        pdf = df.copy()
        pdf.columns = [c.lower() for c in pdf.columns]

        pdf = _engineer_features_v2(pdf)

        features = self.ts_features
        pdf[features] = pdf[features].replace([np.inf, -np.inf], np.nan).ffill().fillna(0)

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            scaled_data = np.ascontiguousarray(
                self.scaler.transform(pdf[features]).astype(np.float32)
            )

        n_windows = data_len - self.lookback + 1
        s0, s1 = scaled_data.strides
        windows_arr = as_strided(
            scaled_data,
            shape=(n_windows, self.lookback, len(features)),
            strides=(s0, s0, s1),
        )
        return scaled_data, data_len, windows_arr, n_windows

    def _infer_windows(self, windows_arr: np.ndarray, n_windows: int) -> np.ndarray:
        """Transformer forward pass (caller must hold model_lock)."""
        batch_size = 4096
        parts = []
        with torch.inference_mode():
            for i in range(0, n_windows, batch_size):
                batch = torch.from_numpy(
                    np.ascontiguousarray(windows_arr[i:i + batch_size])
                ).to(self.device)
                parts.append(self.transformer(batch).cpu().numpy())
        return np.concatenate(parts, axis=0)

    def _xgb_predict(self, embeddings: np.ndarray):
        """XGBoost v2 prediction → (signal_probs, drop_probs)."""
        emb_aug = _augment_embeddings(embeddings)
        legacy_head = getattr(self, "xgb_head", None)

        if legacy_head is not None:
            try:
                probs = legacy_head.predict_proba(emb_aug)
                probs = np.asarray(probs, dtype=float)
                if probs.ndim == 2 and probs.shape[1] >= 2:
                    return probs[:, 0], probs[:, 1]
                if probs.ndim == 1:
                    return probs.astype(float), np.zeros(len(probs), dtype=float)
            except Exception:
                pass

        try:
            sig_probs = self.xgb_up.predict_proba(emb_aug)[:, 1]
        except Exception:
            sig_probs = self.xgb_up.predict(emb_aug).astype(float)
        try:
            drop_probs = self.xgb_down.predict_proba(emb_aug)[:, 1]
        except Exception:
            drop_probs = self.xgb_down.predict(emb_aug).astype(float)
        return sig_probs, drop_probs

    # ── Single symbol inference (backward compat) ───────────────────────────

    def predict_signals(self, df: pd.DataFrame) -> tuple:
        """Single symbol AI inference."""
        result = self.predict_signals_batch({"_single": df})
        return result["_single"]

    # ── Batch inference (core optimization) ─────────────────────────────────

    def predict_signals_batch(self, dfs: dict) -> dict:
        """Batch inference for multiple symbols with single lock acquisition.

        Args:
            dfs: {symbol: pd.DataFrame} — OHLCV+indicator data

        Returns:
            {symbol: (ai_probs, ai_drop_probs)}
        """
        # Cache hit check
        def _cache_key(sym: str, df: pd.DataFrame) -> tuple:
            idx = df.index
            return (sym, str(idx[-1]) if len(idx) else "", len(df))

        results: dict = {}
        uncached_dfs: dict = {}
        for sym, df in dfs.items():
            key = _cache_key(sym, df)
            if key in self._score_cache:
                results[sym] = self._score_cache[key]
            else:
                uncached_dfs[sym] = df

        if uncached_dfs:
            logger.info(f"[AI-Batch] Cache hit={len(results)}, miss={len(uncached_dfs)}")

        # Phase 1: Parallel preprocessing (no lock)
        def _prep(item):
            sym, df = item
            try:
                return sym, self._preprocess_for_ai(df)
            except Exception as e:
                logger.warning(f"[AI-Batch] {sym} preprocessing failed: {e}")
                return sym, None

        with concurrent.futures.ThreadPoolExecutor() as ex:
            prep_results = dict(ex.map(_prep, uncached_dfs.items()))

        valid = {sym: data for sym, data in prep_results.items() if data is not None}
        sym_order = list(valid.keys())

        # Phase 2: Transformer + XGBoost (single lock)
        if sym_order:
            with self.model_lock:
                windows_list = []
                sym_meta = {}
                for sym in sym_order:
                    _, data_len, windows_arr, n_windows = valid[sym]
                    windows_list.append(np.ascontiguousarray(windows_arr))
                    sym_meta[sym] = (n_windows, data_len)

                all_windows = np.concatenate(windows_list, axis=0)
                logger.info(f"[AI-Batch] Transformer: {len(all_windows)} windows ({len(sym_order)} symbols)")
                all_embeddings = self._infer_windows(all_windows, len(all_windows))

                all_sig, all_drop = self._xgb_predict(all_embeddings)

                offset = 0
                for sym in sym_order:
                    n_windows, data_len = sym_meta[sym]
                    sig = all_sig[offset:offset + n_windows]
                    drop = all_drop[offset:offset + n_windows]
                    offset += n_windows

                    probs = np.zeros(data_len)
                    probs_drop = np.zeros(data_len)
                    probs[self.lookback - 1:] = sig
                    probs_drop[self.lookback - 1:] = drop
                    scored = (probs, probs_drop)
                    results[sym] = scored
                    key = _cache_key(sym, uncached_dfs[sym])
                    self._score_cache[key] = scored

        # Fill missing with zeros
        for sym, df in dfs.items():
            if sym not in results:
                n = len(df)
                results[sym] = (np.zeros(n), np.zeros(n))

        return results


if __name__ == "__main__":
    engine = AIEngine()
    dates = pd.date_range('2024-01-01', periods=100)
    df = pd.DataFrame({
        'open': np.random.rand(100) * 1000 + 500,
        'high': np.random.rand(100) * 1000 + 600,
        'low': np.random.rand(100) * 1000 + 400,
        'close': np.random.rand(100) * 1000 + 500,
        'volume': np.random.rand(100) * 100000 + 10000,
    }, index=dates)
    probs, probs_drop = engine.predict_signals(df)
    print(f"Predictions: {len(probs)} steps. Up: {probs[-5:]}, Drop: {probs_drop[-5:]}")
