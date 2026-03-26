"""
Enhanced Training Data Extraction Pipeline v2.

Extracts 45+ features from OHLCV parquet files for the Hybrid Transformer+XGBoost model.

Feature groups:
  1. Log returns (6): open/high/low/close/volume/OBV
  2. Multi-timeframe momentum (9): RSI-7/14/21, ROC-5/10/20, Williams %R-14, MFI-14, TSI
  3. Trend indicators (8): MACD/signal/hist, ADX, CCI-14, Aroon-up/down, TRIX
  4. Moving average distances (6): dist SMA-10/20/50, dist EMA-10/20/50
  5. Volatility (7): Boll pos, ATR-14 norm, Keltner pos, hist vol 10/20, Garman-Klass, NATR
  6. Volume patterns (5): vol ratio 5/20, OBV slope, AD line norm, VWAP dist
  7. Candle patterns (4): body ratio, upper shadow, lower shadow, range norm
"""

import os
import sys
import json
import glob
import argparse

import numpy as np
import pandas as pd
import polars as pl
from tqdm import tqdm

sys.path.append(os.path.join(os.getcwd(), 'backend'))
from engine.indicators import IndicatorEngine


# ── Feature computation helpers ─────────────────────────────────────────────

def _safe_log_return(series: pd.Series) -> pd.Series:
    """Log return with safe handling of zeros and negatives."""
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


def _mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    mf = tp * volume
    delta = tp.diff()
    pos_mf = (mf * (delta > 0)).rolling(period, min_periods=1).sum()
    neg_mf = (mf * (delta <= 0)).rolling(period, min_periods=1).sum()
    return 100 - 100 / (1 + pos_mf / (neg_mf + 1e-10))


def _tsi(close: pd.Series, r: int = 25, s: int = 13) -> pd.Series:
    diff = close.diff()
    smooth1 = diff.ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    smooth2 = diff.abs().ewm(span=r, adjust=False).mean().ewm(span=s, adjust=False).mean()
    return 100 * smooth1 / (smooth2 + 1e-10)


def _aroon(high: pd.Series, low: pd.Series, period: int = 25) -> tuple:
    aroon_up = high.rolling(period + 1).apply(lambda x: x.argmax(), raw=True) / period * 100
    aroon_down = low.rolling(period + 1).apply(lambda x: x.argmin(), raw=True) / period * 100
    return aroon_up, aroon_down


def _trix(close: pd.Series, period: int = 15) -> pd.Series:
    ema1 = close.ewm(span=period, adjust=False).mean()
    ema2 = ema1.ewm(span=period, adjust=False).mean()
    ema3 = ema2.ewm(span=period, adjust=False).mean()
    return ema3.pct_change() * 100


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _garman_klass_vol(open_: pd.Series, high: pd.Series, low: pd.Series, close: pd.Series,
                      window: int = 20) -> pd.Series:
    log_hl = (np.log(high / (low + 1e-10))) ** 2
    log_co = (np.log(close / (open_ + 1e-10))) ** 2
    gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
    return gk.rolling(window, min_periods=1).mean().apply(np.sqrt)


def _keltner_position(close: pd.Series, high: pd.Series, low: pd.Series,
                      period: int = 20, atr_mult: float = 2.0) -> pd.Series:
    mid = close.ewm(span=period, adjust=False).mean()
    atr = _atr(high, low, close, period)
    upper = mid + atr_mult * atr
    lower = mid - atr_mult * atr
    return (close - lower) / (upper - lower + 1e-10)


def _ad_line(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    clv = ((close - low) - (high - close)) / (high - low + 1e-10)
    return (clv * volume).cumsum()


# ── Main feature list (used by inference too) ───────────────────────────────

FEATURE_LIST_V2 = [
    # Log returns (6)
    'ret_open', 'ret_high', 'ret_low', 'ret_close', 'ret_volume', 'ret_obv',
    # Multi-timeframe momentum (9)
    'rsi_7', 'rsi_14', 'rsi_21',
    'roc_5', 'roc_10', 'roc_20',
    'williams_r_14', 'mfi_14', 'tsi',
    # Trend (8)
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

assert len(FEATURE_LIST_V2) == 45


# ── Feature engineering per symbol ──────────────────────────────────────────

def engineer_features(pdf: pd.DataFrame) -> pd.DataFrame:
    """Compute all 45 features from a raw OHLCV DataFrame (must have open/high/low/close/volume)."""

    o, h, l, c, v = pdf['open'], pdf['high'], pdf['low'], pdf['close'], pdf['volume']

    # --- Log returns ---
    for col in ['open', 'high', 'low', 'close']:
        pdf[f'ret_{col}'] = _safe_log_return(pdf[col])
    pdf['ret_volume'] = _safe_log_return(v)

    # OBV
    close_diff = c.diff()
    direction = (close_diff > 0).astype(int) - (close_diff < 0).astype(int)
    direction.iloc[0] = 0
    pdf['obv'] = (direction * v).cumsum()
    pdf['ret_obv'] = _safe_log_return(pdf['obv'].replace(0, np.nan).ffill())

    # --- Momentum ---
    pdf['rsi_7'] = _rsi(c, 7)
    pdf['rsi_14'] = _rsi(c, 14)
    pdf['rsi_21'] = _rsi(c, 21)
    pdf['roc_5'] = _roc(c, 5)
    pdf['roc_10'] = _roc(c, 10)
    pdf['roc_20'] = _roc(c, 20)
    pdf['williams_r_14'] = _williams_r(h, l, c, 14)
    pdf['mfi_14'] = _mfi(h, l, c, v, 14)
    pdf['tsi'] = _tsi(c)

    # --- Trend (MACD, ADX, CCI via stockstats + custom) ---
    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    pdf['macd'] = ema12 - ema26
    pdf['macds'] = pdf['macd'].ewm(span=9, adjust=False).mean()
    pdf['macdh'] = pdf['macd'] - pdf['macds']

    # ADX
    plus_dm = h.diff().clip(lower=0)
    minus_dm = (-l.diff()).clip(lower=0)
    atr14 = _atr(h, l, c, 14)
    plus_di = 100 * (plus_dm.rolling(14, min_periods=1).mean() / (atr14 + 1e-10))
    minus_di = 100 * (minus_dm.rolling(14, min_periods=1).mean() / (atr14 + 1e-10))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10))
    pdf['adx'] = dx.rolling(14, min_periods=1).mean()

    # CCI
    tp = (h + l + c) / 3
    sma_tp = tp.rolling(14, min_periods=1).mean()
    mad = tp.rolling(14, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    pdf['cci_14'] = (tp - sma_tp) / (0.015 * mad + 1e-10)

    # Aroon
    pdf['aroon_up'], pdf['aroon_down'] = _aroon(h, l, 25)

    # TRIX
    pdf['trix_15'] = _trix(c, 15)

    # --- MA distances ---
    for p in [10, 20, 50]:
        sma = c.rolling(p, min_periods=1).mean()
        ema = c.ewm(span=p, adjust=False).mean()
        pdf[f'dist_sma_{p}'] = c / sma - 1
        pdf[f'dist_ema_{p}'] = c / ema - 1

    # --- Volatility ---
    # Bollinger position
    sma20 = c.rolling(20, min_periods=1).mean()
    std20 = c.rolling(20, min_periods=1).std()
    boll_ub = sma20 + 2 * std20
    boll_lb = sma20 - 2 * std20
    pdf['boll_pos'] = (c - boll_lb) / (boll_ub - boll_lb + 1e-10)

    # ATR normalized
    pdf['atr_14_norm'] = atr14 / (c + 1e-10)

    # Keltner channel position
    pdf['keltner_pos'] = _keltner_position(c, h, l, 20, 2.0)

    # Historical volatility
    log_ret = np.log(c / c.shift(1))
    pdf['hist_vol_10'] = log_ret.rolling(10, min_periods=1).std() * np.sqrt(252)
    pdf['hist_vol_20'] = log_ret.rolling(20, min_periods=1).std() * np.sqrt(252)

    # Garman-Klass
    pdf['garman_klass'] = _garman_klass_vol(o, h, l, c, 20)

    # NATR (Normalized ATR)
    pdf['natr_14'] = atr14 / (c + 1e-10) * 100

    # --- Volume patterns ---
    vol_ma5 = v.rolling(5, min_periods=1).mean()
    vol_ma20 = v.rolling(20, min_periods=1).mean()
    pdf['vol_ratio_5'] = v / (vol_ma5 + 1e-10)
    pdf['vol_ratio_20'] = v / (vol_ma20 + 1e-10)

    obv = pdf['obv']
    pdf['obv_slope_10'] = (obv - obv.shift(10)) / (obv.shift(10).abs() + 1e-10)

    ad = _ad_line(h, l, c, v)
    ad_range = ad.rolling(20, min_periods=1).max() - ad.rolling(20, min_periods=1).min()
    pdf['ad_norm'] = (ad - ad.rolling(20, min_periods=1).min()) / (ad_range + 1e-10)

    # VWAP distance (cumulative within each day isn't meaningful for daily, use rolling)
    vwap_20 = (c * v).rolling(20, min_periods=1).sum() / (v.rolling(20, min_periods=1).sum() + 1e-10)
    pdf['vwap_dist'] = c / vwap_20 - 1

    # --- Candle patterns ---
    body = (c - o).abs()
    full_range = h - l + 1e-10
    pdf['candle_body_ratio'] = body / full_range
    pdf['candle_upper_shadow'] = (h - pd.concat([c, o], axis=1).max(axis=1)) / full_range
    pdf['candle_lower_shadow'] = (pd.concat([c, o], axis=1).min(axis=1) - l) / full_range

    # Range normalized by 20-day avg range
    avg_range = full_range.rolling(20, min_periods=1).mean()
    pdf['candle_range_norm'] = full_range / (avg_range + 1e-10)

    return pdf


# ── Main extraction ─────────────────────────────────────────────────────────

def extract_training_data(ohlcv_dir: str, output_file: str, lookback_window: int = 60,
                          symbols=None, buy_threshold: float = 0.07,
                          sell_threshold: float = 0.07, horizon: int = 10):
    """Extract OHLCV data, compute 45 features, create targets, and save to parquet."""

    if not symbols:
        if os.path.exists('top200.txt'):
            with open('top200.txt', 'r') as f:
                content = f.read().strip()
                if content.startswith('[') and content.endswith(']'):
                    symbols = json.loads(content)
                else:
                    symbols = [line.strip() for line in content.split('\n') if line.strip()]
        else:
            symbols = [os.path.basename(f).replace('.parquet', '')
                       for f in glob.glob(os.path.join(ohlcv_dir, '*.parquet'))]

    all_data = []
    print(f"Extracting data for {len(symbols)} symbols...")
    print(f"Features: {len(FEATURE_LIST_V2)}")
    print(f"Targets: Buy>={buy_threshold*100:.0f}%, Sell<=-{sell_threshold*100:.0f}%, Horizon={horizon}d")

    for symbol in tqdm(symbols):
        try:
            file_path = os.path.join(ohlcv_dir, f"{symbol}.parquet")
            if not os.path.exists(file_path):
                continue

            df_pl = pl.read_parquet(file_path)
            pdf = df_pl.to_pandas()
            pdf.columns = [c.lower() for c in pdf.columns]
            pdf = pdf.sort_values('date').reset_index(drop=True)
            pdf['symbol'] = symbol

            # Minimum data requirement
            if len(pdf) < lookback_window + horizon + 50:
                continue

            # Feature engineering
            pdf = engineer_features(pdf)

            # Targets
            pdf[f'fwd_return_{horizon}'] = pdf['close'].shift(-horizon) / pdf['close'] - 1

            # Rolling max/min for binary targets
            future_max = pdf['close'].rolling(window=horizon).max().shift(-horizon)
            future_min = pdf['close'].rolling(window=horizon).min().shift(-horizon)
            pdf['target_up'] = ((future_max / pdf['close'] - 1) >= buy_threshold).astype(int)
            pdf['target_down'] = ((future_min / pdf['close'] - 1) <= -sell_threshold).astype(int)

            # Backward compat
            pdf['target_7pct_10d'] = pdf['target_up']
            pdf['target_drop_7pct_10d'] = pdf['target_down']

            # Clean
            pdf[FEATURE_LIST_V2] = pdf[FEATURE_LIST_V2].replace([np.inf, -np.inf], np.nan)
            pdf = pdf.dropna(subset=FEATURE_LIST_V2 + [f'fwd_return_{horizon}', 'target_up', 'target_down'])

            if len(pdf) > lookback_window:
                all_data.append(pdf)

        except Exception as e:
            print(f"Error processing {symbol}: {e}")

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        final_df.to_parquet(output_file)
        print(f"Saved {len(final_df):,} bars from {len(all_data)} symbols to {output_file}")
        print(f"Date range: {final_df['date'].min()} ~ {final_df['date'].max()}")
        print(f"Target up rate: {final_df['target_up'].mean():.2%}")
        print(f"Target down rate: {final_df['target_down'].mean():.2%}")
    else:
        print("No data extracted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ohlcv_dir", default="/Users/eugene/nullalgo/simons/data/ohlcv")
    parser.add_argument("--output_file", default="/Users/eugene/nullalgo/simons/data/training_data_raw_v2.parquet")
    parser.add_argument("--buy_threshold", type=float, default=0.07)
    parser.add_argument("--sell_threshold", type=float, default=0.07)
    parser.add_argument("--horizon", type=int, default=10)
    args = parser.parse_args()

    extract_training_data(args.ohlcv_dir, args.output_file,
                          buy_threshold=args.buy_threshold,
                          sell_threshold=args.sell_threshold,
                          horizon=args.horizon)
