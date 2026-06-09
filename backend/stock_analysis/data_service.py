"""
StockDataService — 종목의 가격/거래량/재무 기초 데이터 수집(단일 책임: 데이터 수집).

1차 소스는 로컬 OHLCV parquet(`data/ohlcv/{symbol}.parquet`)로, 종가/등락률/거래량과
per/pbr/roe/부채비율을 포함한다. 데이터가 없는 항목은 환각으로 채우지 않고
`missing` 목록에 기록한다(분석/추천 단계에서 '데이터 없음'으로 처리).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

from .symbol_resolver import StockRef, resolve_by_symbol

logger = logging.getLogger(__name__)

_OHLCV_DIR = Path(__file__).resolve().parents[2] / "data" / "ohlcv"


@dataclass
class StockData:
    symbol: str
    name: str
    sector: Optional[str] = None
    ohlcv: Optional[pd.DataFrame] = None
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    per: Optional[float] = None
    pbr: Optional[float] = None
    roe: Optional[float] = None
    debt_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    as_of: Optional[str] = None
    missing: list[str] = field(default_factory=list)

    @property
    def has_price(self) -> bool:
        return self.current_price is not None


def _last_valid(series: pd.Series) -> Optional[float]:
    cleaned = series.dropna()
    if cleaned.empty:
        return None
    try:
        return float(cleaned.iloc[-1])
    except (TypeError, ValueError):
        return None


class StockDataService:
    """단일 책임: 원천 데이터 수집. 분석/판정은 하지 않는다."""

    def __init__(self, ohlcv_dir: Path = _OHLCV_DIR) -> None:
        self._ohlcv_dir = ohlcv_dir

    def load(self, ref: StockRef | str) -> StockData:
        if isinstance(ref, str):
            resolved = resolve_by_symbol(ref)
            ref = resolved or StockRef(symbol=ref, name=ref)

        data = StockData(symbol=ref.symbol, name=ref.name, sector=ref.sector)

        if getattr(ref, "overseas", False):
            # 국내 parquet가 없는 해외 종목 — 전 항목 데이터 없음.
            data.missing = ["현재가", "등락률", "거래량", "PER", "PBR", "ROE", "부채비율", "시가총액", "OHLCV"]
            return data

        path = self._ohlcv_dir / f"{ref.symbol}.parquet"
        if not path.exists():
            data.missing = ["현재가", "등락률", "거래량", "PER", "PBR", "ROE", "부채비율", "시가총액", "OHLCV"]
            return data

        try:
            df = pd.read_parquet(path)
        except Exception:
            logger.exception("OHLCV parquet 읽기 실패: %s", path)
            data.missing = ["OHLCV"]
            return data

        if df.empty:
            data.missing = ["현재가", "등락률", "거래량", "OHLCV"]
            return data

        data.ohlcv = df
        last = df.iloc[-1]
        data.current_price = _last_valid(df["close"]) if "close" in df else None
        data.change_pct = float(last["change"]) if "change" in df and pd.notna(last.get("change")) else None
        data.volume = float(last["volume"]) if "volume" in df and pd.notna(last.get("volume")) else None
        data.per = _last_valid(df["per"]) if "per" in df else None
        data.pbr = _last_valid(df["pbr"]) if "pbr" in df else None
        data.roe = _last_valid(df["roe_or_gpa"]) if "roe_or_gpa" in df else None
        data.debt_ratio = _last_valid(df["debt_ratio"]) if "debt_ratio" in df else None
        if "date" in df and pd.notna(last.get("date")):
            data.as_of = pd.Timestamp(last["date"]).strftime("%Y-%m-%d")
        # parquet sector가 비면 korea-stocks.json sector 유지.
        if not data.sector and "sector" in df and pd.notna(last.get("sector")):
            data.sector = str(last["sector"])

        # 누락 항목 기록(환각 금지).
        for label, value in (
            ("현재가", data.current_price),
            ("등락률", data.change_pct),
            ("거래량", data.volume),
            ("PER", data.per),
            ("PBR", data.pbr),
            ("ROE", data.roe),
            ("부채비율", data.debt_ratio),
        ):
            if value is None:
                data.missing.append(label)
        # 시가총액은 1차 소스에 없음 — 항상 데이터 없음.
        data.missing.append("시가총액")
        return data
