import os
import polars as pl
import pandas as pd
import numpy as np

class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._cache: dict[str, pl.DataFrame] = {}

    def load_symbol_data(self, symbol: str) -> pl.DataFrame:
        # Return cached data if available (avoids repeated parquet I/O during optimization)
        if symbol in self._cache:
            return self._cache[symbol]

        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")

        if not os.path.exists(file_path):
            return None

        df = pl.read_parquet(file_path)
        self._cache[symbol] = df
        return df

    def clear_cache(self):
        """Clear the in-memory data cache."""
        self._cache.clear()

    def preprocess_data(self, df_pl: pl.DataFrame) -> pd.DataFrame:
        """OHLCV basic alignment and adjusting prices if needed."""
        pdf = df_pl.to_pandas()

        # 1. Handle Adjustment
        if 'adj_close' in pdf.columns:
            factor = pdf['adj_close'] / pdf['close']
            pdf['open'] *= factor
            pdf['high'] *= factor
            pdf['low'] *= factor
            pdf['close'] = pdf['adj_close']

        # 2. Robust Price Sanitization (vectorized across all price columns at once)
        price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in pdf.columns]
        if price_cols:
            vals = pdf[price_cols].values  # single numpy view
            vals[(vals <= 0) | ~np.isfinite(vals)] = np.nan
            # ffill + bfill via pandas (operates on contiguous block)
            pdf[price_cols] = pd.DataFrame(vals, columns=price_cols, index=pdf.index).ffill().bfill()

        pdf.set_index('date', inplace=True)
        pdf.index = pd.to_datetime(pdf.index)
        return pdf

    def check_liquidity(self, pdf: pd.DataFrame, target_amount: float, limit_pct: float) -> np.ndarray:
        """Check if trading volume is enough to cover the target amount."""
        data_len = len(pdf)
        if limit_pct <= 0:
            return np.ones(data_len, dtype=bool)

        vol_val = (pdf['close'] * pdf['volume']).values
        liquidity_ok = np.zeros(data_len, dtype=bool)
        # 전일 거래대금 * limit_pct% >= target_amount (벡터화)
        liquidity_ok[1:] = vol_val[:-1] * (limit_pct / 100.0) >= target_amount
        return liquidity_ok
