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
        if not os.path.exists(file_path):
            # Fallback for specific environment
            abs_fallback = f"/Users/eugene/nullalgo/simons/data/ohlcv/{symbol}.parquet"
            if os.path.exists(abs_fallback):
                file_path = abs_fallback
            else:
                raise FileNotFoundError(f"Data for {symbol} not found in {self.data_dir}")
        
        return pl.read_parquet(file_path)

    def preprocess_data(self, df_pl: pl.DataFrame) -> pd.DataFrame:
        """OHLCV basic alignment and adjusting prices if needed."""
        pdf = df_pl.to_pandas()
        pdf['raw_close_ref'] = pdf['close']
        
        if 'adj_close' in pdf.columns:
            factor = pdf['adj_close'] / pdf['close']
            pdf['open'] *= factor
            pdf['high'] *= factor
            pdf['low'] *= factor
            pdf['close'] = pdf['adj_close']
            
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
