"""시장지수 시계열 저장소·로더 — `data/index/{KOSPI,KOSDAQ}.parquet`.

왜 따로 두는가
--------------
백테스트 결과의 벤치마크는 지수 추종 ETF(KODEX 200 등) 가격을 종목처럼 읽어 만들지만,
"시장보다 덜 떨어진 종목"처럼 **지수 자체와 종목을 비교하는 조건**은 지수 레벨 시계열이
있어야 한다. 이 모듈이 그 시계열의 유일한 읽기 경로다(쓰기는
`scripts/backfill_index_history.py` — 토스 Open API 2014-07~ + KIS 1996~2014-06 보충).

계약
----
- 파일: `<data 루트>/index/<MARKET>.parquet`, 컬럼 date(Datetime us)·open·high·low·close·
  volume·source. OHLCV 파케이(`data/ohlcv`)의 **형제 디렉터리**라 로더의 data_dir에서
  결정론으로 위치를 구한다(미국 파케이 `ohlcv-us`와 같은 규약).
- 종목 → 지수 매핑은 종목 마스터의 상장 시장(KOSPI/KOSDAQ)이다. ETF는 코스피 상장이
  대부분이라 KOSPI, 미국 종목은 지수가 없어 None(조건이 평가 불가 → fail-closed).
- `attach_index_close`는 종목 프레임에 `index_close` 컬럼을 날짜 조인으로 붙인다.
  지표 엔진(`indicators.py`)은 심볼을 모르므로 이 컬럼이 있을 때만 상대 수익률을 계산한다.
  지수 파일이 없거나 시장을 모르면 null 컬럼을 붙여 조건이 False로 떨어지게 한다(조용히
  0으로 대체하지 않는다 — 결과가 그럴듯하게 틀리는 것보다 거래가 없는 편이 낫다).
- 캐시는 (경로, mtime) 키의 lru — 야간 갱신으로 파일이 바뀌면 자동 무효화된다.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import polars as pl

_logger = logging.getLogger(__name__)

INDEX_DIR_NAME = "index"
INDEX_MARKETS = ("KOSPI", "KOSDAQ")
INDEX_CLOSE_COL = "index_close"
RELATIVE_RETURN_ID = "relative_return"
INDEX_COLUMNS = ("date", "open", "high", "low", "close", "volume", "source")


def index_dir_for(data_dir: str | os.PathLike) -> Path:
    """OHLCV 디렉터리(data/ohlcv)의 형제 `data/index`."""
    return Path(os.path.dirname(os.path.normpath(str(data_dir)))) / INDEX_DIR_NAME


def index_path(market: str, data_dir: str | os.PathLike) -> Path:
    return index_dir_for(data_dir) / f"{market}.parquet"


@lru_cache(maxsize=1)
def _market_by_symbol() -> Dict[str, str]:
    from engine import universe_pit

    out: Dict[str, str] = {}
    for row in universe_pit._load_master():
        market = row.get("market")
        if market in INDEX_MARKETS and row.get("symbol"):
            out[row["symbol"]] = market
    return out


def market_for_symbol(symbol: str) -> Optional[str]:
    """종목의 비교 지수 시장. 마스터에 없는 KRX ETF는 KOSPI, 미국 종목은 None."""
    from engine import universe_pit

    if not symbol:
        return None
    if universe_pit.is_us_symbol(symbol):
        return None
    market = _market_by_symbol().get(symbol)
    if market:
        return market
    if universe_pit.is_etf_symbol(symbol):
        return "KOSPI"
    return None


@lru_cache(maxsize=8)
def _load_cached(path_str: str, _mtime_ns: int) -> pl.DataFrame:
    df = pl.read_parquet(path_str, columns=["date", "close"])
    return (
        df.with_columns(pl.col("date").cast(pl.Datetime("us")))
        .sort("date")
        .rename({"close": INDEX_CLOSE_COL})
    )


def load_index_frame(market: str, data_dir: str | os.PathLike) -> Optional[pl.DataFrame]:
    """지수 (date, index_close) 프레임. 파일이 없으면 None."""
    path = index_path(market, data_dir)
    if not path.exists():
        return None
    return _load_cached(str(path), path.stat().st_mtime_ns)


def uses_relative_return(conditions: Optional[Iterable[Dict[str, Any]]]) -> bool:
    return any((c or {}).get("id") == RELATIVE_RETURN_ID for c in (conditions or []))


def attach_index_close(
    df_pl: pl.DataFrame,
    symbol: str,
    conditions: Optional[List[Dict[str, Any]]],
    data_dir: str | os.PathLike,
) -> pl.DataFrame:
    """상대 수익률 조건이 있을 때만 종목 프레임에 `index_close`를 날짜 조인으로 붙인다.

    조인 후 결측은 전진 충전한다(지수 휴장일과 종목 거래일이 어긋나는 드문 날) — 상장 전
    구간은 종목 프레임에 행이 없으므로 채울 일이 없다.
    """
    if df_pl is None or len(df_pl) == 0 or not uses_relative_return(conditions):
        return df_pl
    if INDEX_CLOSE_COL in df_pl.columns:
        return df_pl

    market = market_for_symbol(symbol)
    index_df = load_index_frame(market, data_dir) if market else None
    if index_df is None:
        _logger.warning(
            "[MARKET-INDEX] %s: 비교 지수 없음(market=%s) — relative_return 조건은 평가되지 않는다",
            symbol, market,
        )
        return df_pl.with_columns(pl.lit(None, dtype=pl.Float64).alias(INDEX_CLOSE_COL))

    date_dtype = df_pl.schema["date"]
    joined = (
        df_pl.with_columns(pl.col("date").cast(pl.Datetime("us")).alias("_join_date"))
        .join(index_df.rename({"date": "_join_date"}), on="_join_date", how="left")
        .drop("_join_date")
        .with_columns(pl.col(INDEX_CLOSE_COL).cast(pl.Float64).fill_null(strategy="forward"))
    )
    # 조인이 date 컬럼 dtype을 바꾸지 않았는지 보존(원본이 Datetime(us)가 아닐 때 대비)
    if joined.schema["date"] != date_dtype:
        joined = joined.with_columns(pl.col("date").cast(date_dtype))
    return joined
