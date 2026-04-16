"""
Shared Feature Engineering Module v3
======================================
Single source of truth for feature computation used by:
  - scripts/extract_training_data.py  (training)
  - backend/ai/ai_engine.py           (inference)

Ensures identical feature values during training and deployment.
"""

import numpy as np
import pandas as pd

# ── Feature list ─────────────────────────────────────────────────────────────

FEATURE_LIST = [
    # Log returns (6)
    'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv',
    # Multi-timeframe momentum (9)
    'rsi_7', 'rsi_14', 'rsi_21', 'roc_5', 'roc_10', 'roc_20',
    'williams_r_14', 'mfi_14', 'tsi',
    # Trend indicators (8)
    'macd', 'macds', 'macdh', 'adx', 'cci_14',
    'aroon_up', 'aroon_down', 'trix_15',
    # MA distances (6)
    'dist_sma_10', 'dist_sma_20', 'dist_sma_50',
    'dist_ema_10', 'dist_ema_20', 'dist_ema_50',
    # Volatility (7)
    'boll_pos', 'atr_14_norm', 'keltner_pos',
    'hist_vol_10', 'hist_vol_20', 'garman_klass', 'natr_14',
    # Volume patterns (5)
    'vol_ratio_5', 'vol_ratio_20', 'obv_slope_10', 'ad_norm', 'vwap_dist',
    # Candle patterns (4)
    'candle_body_ratio', 'candle_upper_shadow', 'candle_lower_shadow', 'candle_range_norm',
]

N_FEATURES = len(FEATURE_LIST)  # 45


# ── Low-level helpers ─────────────────────────────────────────────────────────

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


def _williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    hh = high.rolling(period).max()
    ll = low.rolling(period).min()
    return -100 * (hh - close) / (hh - ll + 1e-10)


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series, period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    mf = tp * volume
    delta = tp.diff()
    pos_mf = (mf * (delta > 0)).rolling(period, min_periods=1).sum()
    neg_mf = (mf * (delta <= 0)).rolling(period, min_periods=1).sum()
    return 100 - 100 / (1 + pos_mf / (neg_mf + 1e-10))


def _tsi(close: pd.Series, r: int = 25, s: int = 13) -> pd.Series:
    diff = close.diff()
    s1 = diff.ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    s2 = diff.abs().ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    return 100 * s1 / (s2 + 1e-10)


def _aroon(high: pd.Series, low: pd.Series, period: int = 25):
    up = high.rolling(period + 1).apply(lambda x: x.argmax(), raw=True) / period * 100
    down = low.rolling(period + 1).apply(lambda x: x.argmin(), raw=True) / period * 100
    return up, down


def _trix(close: pd.Series, period: int = 15) -> pd.Series:
    e1 = close.ewm(span=period, adjust=False).mean()
    e2 = e1.ewm(span=period, adjust=False).mean()
    e3 = e2.ewm(span=period, adjust=False).mean()
    return e3.pct_change() * 100


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _garman_klass_vol(open_: pd.Series, high: pd.Series, low: pd.Series,
                      close: pd.Series, window: int = 20) -> pd.Series:
    """Garman-Klass volatility — uses clipped log to avoid log(0)."""
    eps = 1e-10
    log_hl = (np.log((high + eps) / (low + eps))) ** 2
    log_co = (np.log((close + eps) / (open_ + eps))) ** 2
    gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    return gk.rolling(window, min_periods=1).mean().apply(np.sqrt)


def _keltner_position(close: pd.Series, high: pd.Series, low: pd.Series,
                      period: int = 20, atr_mult: float = 2.0) -> pd.Series:
    mid = close.ewm(span=period, adjust=False).mean()
    atr_val = _atr(high, low, close, period)
    upper = mid + atr_mult * atr_val
    lower = mid - atr_mult * atr_val
    return (close - lower) / (upper - lower + 1e-10)


def _ad_line(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    clv = ((close - low) - (high - close)) / (high - low + 1e-10)
    return (clv * volume).cumsum()


# ── Main feature engineering ──────────────────────────────────────────────────

def engineer_features(pdf: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all 45 features from an OHLCV DataFrame.

    Input columns (case-insensitive, normalized before call):
        date, open, high, low, close, volume

    Returns the same DataFrame with feature columns added.
    All infinite values are replaced with NaN (caller should ffill/fillna).
    """
    pdf = pdf.copy()
    pdf.columns = [c.lower() for c in pdf.columns]

    o = pdf['open']
    h = pdf['high']
    l = pdf['low']
    c = pdf['close']
    v = pdf['volume']

    # ── Log returns ──────────────────────────────────────────────────────────
    for col in ['open', 'high', 'low', 'close']:
        pdf[f'ret_{col}'] = _safe_log_return(pdf[col])
    pdf['ret_volume'] = _safe_log_return(v)

    close_diff = c.diff()
    direction = (close_diff > 0).astype(int) - (close_diff < 0).astype(int)
    direction.iloc[0] = 0
    obv = (direction * v).cumsum()
    pdf['obv'] = obv
    pdf['ret_obv'] = _safe_log_return(obv.replace(0, np.nan).ffill())

    # ── Momentum ─────────────────────────────────────────────────────────────
    pdf['rsi_7']  = _rsi(c, 7)
    pdf['rsi_14'] = _rsi(c, 14)
    pdf['rsi_21'] = _rsi(c, 21)
    pdf['roc_5']  = _roc(c, 5)
    pdf['roc_10'] = _roc(c, 10)
    pdf['roc_20'] = _roc(c, 20)
    pdf['williams_r_14'] = _williams_r(h, l, c, 14)
    pdf['mfi_14'] = _mfi(h, l, c, v, 14)
    pdf['tsi']    = _tsi(c)

    # ── Trend ────────────────────────────────────────────────────────────────
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    pdf['macd']  = ema12 - ema26
    pdf['macds'] = pdf['macd'].ewm(span=9, adjust=False).mean()
    pdf['macdh'] = pdf['macd'] - pdf['macds']

    atr14 = _atr(h, l, c, 14)
    plus_dm  = h.diff().clip(lower=0)
    minus_dm = (-l.diff()).clip(lower=0)
    plus_di  = 100 * (plus_dm.rolling(14, min_periods=1).mean()  / (atr14 + 1e-10))
    minus_di = 100 * (minus_dm.rolling(14, min_periods=1).mean() / (atr14 + 1e-10))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    pdf['adx'] = dx.rolling(14, min_periods=1).mean()

    tp = (h + l + c) / 3
    sma_tp = tp.rolling(14, min_periods=1).mean()
    mad = tp.rolling(14, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    pdf['cci_14'] = (tp - sma_tp) / (0.015 * mad + 1e-10)

    pdf['aroon_up'], pdf['aroon_down'] = _aroon(h, l, 25)
    pdf['trix_15'] = _trix(c, 15)

    # ── MA distances ─────────────────────────────────────────────────────────
    for p in [10, 20, 50]:
        sma = c.rolling(p, min_periods=1).mean()
        ema = c.ewm(span=p, adjust=False).mean()
        pdf[f'dist_sma_{p}'] = c / (sma + 1e-10) - 1
        pdf[f'dist_ema_{p}'] = c / (ema + 1e-10) - 1

    # ── Volatility ───────────────────────────────────────────────────────────
    sma20  = c.rolling(20, min_periods=1).mean()
    std20  = c.rolling(20, min_periods=1).std()
    boll_ub = sma20 + 2 * std20
    boll_lb = sma20 - 2 * std20
    pdf['boll_pos']    = (c - boll_lb) / (boll_ub - boll_lb + 1e-10)
    pdf['atr_14_norm'] = atr14 / (c + 1e-10)
    pdf['keltner_pos'] = _keltner_position(c, h, l, 20, 2.0)

    # Historical volatility — use clipped log to match inference exactly
    log_ret = np.log((c + 1e-10) / (c.shift(1) + 1e-10))
    pdf['hist_vol_10'] = log_ret.rolling(10, min_periods=1).std() * np.sqrt(252)
    pdf['hist_vol_20'] = log_ret.rolling(20, min_periods=1).std() * np.sqrt(252)

    pdf['garman_klass'] = _garman_klass_vol(o, h, l, c, 20)
    pdf['natr_14']      = atr14 / (c + 1e-10) * 100

    # ── Volume patterns ──────────────────────────────────────────────────────
    vol_ma5  = v.rolling(5,  min_periods=1).mean()
    vol_ma20 = v.rolling(20, min_periods=1).mean()
    pdf['vol_ratio_5']  = v / (vol_ma5  + 1e-10)
    pdf['vol_ratio_20'] = v / (vol_ma20 + 1e-10)

    pdf['obv_slope_10'] = (obv - obv.shift(10)) / (obv.shift(10).abs() + 1e-10)

    ad = _ad_line(h, l, c, v)
    ad_min   = ad.rolling(20, min_periods=1).min()
    ad_range = ad.rolling(20, min_periods=1).max() - ad_min
    pdf['ad_norm'] = (ad - ad_min) / (ad_range + 1e-10)

    vwap_20    = (c * v).rolling(20, min_periods=1).sum() / (v.rolling(20, min_periods=1).sum() + 1e-10)
    pdf['vwap_dist'] = c / (vwap_20 + 1e-10) - 1

    # ── Candle patterns ──────────────────────────────────────────────────────
    body       = (c - o).abs()
    full_range = h - l + 1e-10
    pdf['candle_body_ratio']    = body / full_range
    pdf['candle_upper_shadow']  = (h - pd.concat([c, o], axis=1).max(axis=1)) / full_range
    pdf['candle_lower_shadow']  = (pd.concat([c, o], axis=1).min(axis=1) - l) / full_range
    avg_range = full_range.rolling(20, min_periods=1).mean()
    pdf['candle_range_norm']    = full_range / (avg_range + 1e-10)

    # Replace inf values
    pdf[FEATURE_LIST] = pdf[FEATURE_LIST].replace([np.inf, -np.inf], np.nan)

    return pdf
