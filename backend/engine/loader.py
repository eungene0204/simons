import os
import polars as pl
import pandas as pd
import numpy as np
from datetime import datetime

class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir

    def load_symbol_data(self, symbol: str) -> pl.DataFrame:
        file_path = os.path.join(self.data_dir, f"{symbol}.parquet")
        
        # --- Auto-Download Logic ---
        if not os.path.exists(file_path):
            print(f"[INFO] Data for {symbol} missing. Attempting automatic download...")
            from .data_fetcher import fetch_and_enrich
            success = fetch_and_enrich(symbol, self.data_dir)
            if not success:
                # Fallback for specific environment check (existing logic)
                abs_fallback = f"/Users/eugene/nullalgo/simons/data/ohlcv/{symbol}.parquet"
                if os.path.exists(abs_fallback):
                    file_path = abs_fallback
                else:
                    raise FileNotFoundError(f"Data for {symbol} not found and download failed.")
        # ----------------------------
        
        return pl.read_parquet(file_path)

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
            
        # 2. Robust Price Sanitization
        # Replace non-positive or non-finite values with NaN
        for col in ['open', 'high', 'low', 'close']:
            if col in pdf.columns:
                pdf.loc[pdf[col] <= 0, col] = np.nan
                pdf.loc[~np.isfinite(pdf[col]), col] = np.nan
                # Fill missing prices with previous ones, then next ones as fallback
                pdf[col] = pdf[col].ffill().bfill()
            
        pdf.set_index('date', inplace=True)
        pdf.index = pd.to_datetime(pdf.index)
        return pdf

    def check_liquidity(self, pdf: pd.DataFrame, target_amount: float, limit_pct: float) -> np.ndarray:
        """Check if trading volume is enough to cover the target amount."""
        data_len = len(pdf)
        vol_val = (pdf['close'] * pdf['volume']).values
        liquidity_ok = np.ones(data_len, dtype=bool)
        
        if limit_pct > 0:
            liquidity_ok = np.zeros(data_len, dtype=bool)
            for i in range(1, data_len):
                # Yesterday's trading value * limit_pct
                liquidity_ok[i] = vol_val[i-1] * (limit_pct / 100.0) >= target_amount
                
        return liquidity_ok
