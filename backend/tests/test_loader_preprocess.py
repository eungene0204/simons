import os
import sys

import polars as pl

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from engine.loader import DataLoader


def test_preprocess_data_handles_integer_price_columns_with_nan_sanitization():
    loader = DataLoader("unused")
    df = pl.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "open": [100, 0],
            "high": [110, 120],
            "low": [90, 95],
            "close": [105, 115],
            "volume": [1000, 2000],
        }
    )

    pdf = loader.preprocess_data(df)

    assert pdf["open"].dtype.kind == "f"
    assert float(pdf["open"].iloc[1]) == 100.0
