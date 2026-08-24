"""미국 종목 일봉 서빙 (data/ohlcv-us).

백테스트 엔진 로더(data/ohlcv)와는 분리되어 있다 — 미국 데이터는 아직 엔진에
미배선이므로, 차트/시세 표시 경로(GET /stock/{symbol}/ohlcv)만 이 모듈로 폴백한다.
"""
import os
import re

import numpy as np
import polars as pl

_US_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ohlcv-us")

# 티커가 파일 경로에 들어가므로 형식을 엄격히 제한한다 (경로 조작 방지)
_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def load_us_ohlcv(symbol: str, limit: int = 1260, data_dir: str | None = None):
    """미국 파케이에서 한국 경로와 동일 형태의 {candles, lastClose, sigma}를 만든다.

    파일이 없거나 티커 형식이 아니면 None. 미국 주가는 정수가 아니므로 가격을
    float로 유지한다(한국 경로처럼 int 절삭하면 저가주 차트가 계단형으로 뭉개짐).
    """
    if not _US_SYMBOL_RE.fullmatch(symbol):
        return None
    path = os.path.join(data_dir or _US_DATA_DIR, f"{symbol}.parquet")
    if not os.path.exists(path):
        return None

    df = pl.read_parquet(path, columns=["date", "open", "high", "low", "close", "volume"])
    df = df.drop_nulls(subset=["close"])
    if df.is_empty():
        return None
    df_tail = df.tail(limit)

    candles = []
    for row in df_tail.iter_rows(named=True):
        date_val = row["date"]
        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
        close_px = round(float(row["close"]), 4)

        def px(value: float | None) -> float:
            return round(float(value), 4) if value is not None else close_px

        volume = row["volume"]
        candles.append({
            "date": date_str,
            "open": px(row["open"]),
            "high": px(row["high"]),
            "low": px(row["low"]),
            "close": close_px,
            "volume": int(volume) if volume is not None and np.isfinite(volume) else 0,
        })

    last_close = candles[-1]["close"]

    # 30일 연율화 변동성 (한국 경로 get_stock_ohlcv와 동일 산식)
    closes = df.tail(32)["close"].to_numpy().astype(float)
    if len(closes) >= 2:
        returns = np.diff(closes) / closes[:-1]
        sigma = float(np.std(returns) * np.sqrt(252))
    else:
        sigma = 0.3

    return {"candles": candles, "lastClose": last_close, "sigma": sigma}
