"""매크로 시계열 저장소·로더(엔진 v16.31) — `data/macro/<series>.parquet`.

시장 국면 필터가 KOSPI·KOSDAQ 지수만 보던 것을 금리·환율·변동성 지수 등으로 넓힌다. 파일은
야간 동기화(`backend/scripts/sync_macro_series.py`, scripts/sync_data.py가 부른다)가 만들고, 로컬은
프로덕션 사본을 pull 한다(parquet 정본=프로덕션 — `scripts/mirror_data.py --macro`).

스키마: date(Datetime us)·value(float)·source(str). 월간 시계열(연준 기준금리·한국 국고채 등)은 동기화가
관측일을 그 달 **말일**로 옮겨 싣고 엔진이 거래일에 ffill 한다 — 그 달이 끝나기 전에 그 달 값을 쓰지 않는다.

시리즈 정본(MACRO_SERIES): id → 라벨·출처·단위. 사용자가 말한 표현('환율', 'VIX', '미국 10년물')은
대화 레인의 별칭 표(MACRO_ALIASES)가 정본 id로 옮긴다 — 애매한 표현('금리')은 되묻는다.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

MACRO_DIR_NAME = "macro"

# (라벨(한국어), 출처, 코드, 단위, 빈도, 영어 라벨)
MACRO_SERIES: Dict[str, Dict[str, str]] = {
    "vix":        {"label": "VIX(변동성 지수)", "source": "yfinance", "code": "^VIX", "unit": "pt", "freq": "daily", "label_en": "VIX"},
    "usdkrw":     {"label": "원/달러 환율", "source": "yfinance", "code": "KRW=X", "unit": "원", "freq": "daily", "label_en": "USD/KRW"},
    "usdjpy":     {"label": "엔/달러 환율", "source": "yfinance", "code": "JPY=X", "unit": "엔", "freq": "daily", "label_en": "USD/JPY"},
    "dxy":        {"label": "달러 인덱스", "source": "yfinance", "code": "DX-Y.NYB", "unit": "pt", "freq": "daily", "label_en": "Dollar index"},
    "us10y":      {"label": "미국 10년물 국채 금리", "source": "yfinance", "code": "^TNX", "unit": "%", "freq": "daily", "label_en": "US 10Y yield"},
    "us2y":       {"label": "미국 2년물 국채 금리", "source": "fred", "code": "DGS2", "unit": "%", "freq": "daily", "label_en": "US 2Y yield"},
    "us3m":       {"label": "미국 3개월물 국채 금리", "source": "yfinance", "code": "^IRX", "unit": "%", "freq": "daily", "label_en": "US 3M yield"},
    "us_spread":  {"label": "미국 장단기 금리차(10년−2년)", "source": "fred", "code": "T10Y2Y", "unit": "%p", "freq": "daily", "label_en": "US 10Y−2Y spread"},
    "fed_funds":  {"label": "미국 기준금리(연준)", "source": "fred", "code": "FEDFUNDS", "unit": "%", "freq": "monthly", "label_en": "Fed funds rate"},
    "kr10y":      {"label": "한국 국고채 10년 금리(월간)", "source": "fred", "code": "IRLTLT01KRM156N", "unit": "%", "freq": "monthly", "label_en": "Korea 10Y yield"},
    "kr3m":       {"label": "한국 CD 3개월 금리(월간)", "source": "fred", "code": "IR3TIB01KRM156N", "unit": "%", "freq": "monthly", "label_en": "Korea 3M CD rate"},
    "gold":       {"label": "금 선물", "source": "yfinance", "code": "GC=F", "unit": "$", "freq": "daily", "label_en": "Gold futures"},
    "wti":        {"label": "WTI 원유 선물", "source": "yfinance", "code": "CL=F", "unit": "$", "freq": "daily", "label_en": "WTI crude"},
}

# 표기 변형 → 정본 id(대화 레인 별칭 표 — 표기 정규화이지 의미 해석이 아니다). 애매한 낱말('금리')은 없다.
MACRO_ALIASES: Dict[str, str] = {
    "vix": "vix", "변동성지수": "vix", "공포지수": "vix", "vix지수": "vix",
    "usdkrw": "usdkrw", "usd/krw": "usdkrw", "원달러": "usdkrw", "원/달러": "usdkrw", "달러원": "usdkrw",
    "원달러환율": "usdkrw", "환율": "usdkrw", "달러환율": "usdkrw", "krw": "usdkrw",
    "usdjpy": "usdjpy", "엔달러": "usdjpy", "엔/달러": "usdjpy", "엔화": "usdjpy", "엔화환율": "usdjpy",
    "dxy": "dxy", "달러인덱스": "dxy", "달러지수": "dxy", "dollarindex": "dxy",
    "us10y": "us10y", "미국10년물": "us10y", "미국10년물금리": "us10y", "미국국채10년": "us10y", "미국10년": "us10y",
    "10년물": "us10y", "tnx": "us10y",
    "us2y": "us2y", "미국2년물": "us2y", "미국2년물금리": "us2y", "미국국채2년": "us2y",
    "us3m": "us3m", "미국3개월물": "us3m", "미국단기금리": "us3m",
    "us_spread": "us_spread", "장단기금리차": "us_spread", "금리차": "us_spread", "수익률곡선": "us_spread",
    "장단기스프레드": "us_spread", "10y2y": "us_spread",
    "fed_funds": "fed_funds", "연준기준금리": "fed_funds", "미국기준금리": "fed_funds", "fedfunds": "fed_funds",
    "연방기금금리": "fed_funds", "fed": "fed_funds",
    "kr10y": "kr10y", "한국국고채10년": "kr10y", "국고채10년": "kr10y", "한국10년물": "kr10y", "국고채": "kr10y",
    "kr3m": "kr3m", "cd금리": "kr3m", "한국cd금리": "kr3m", "한국단기금리": "kr3m", "cd3개월": "kr3m",
    "gold": "gold", "금": "gold", "금값": "gold", "금선물": "gold",
    "wti": "wti", "원유": "wti", "유가": "wti", "국제유가": "wti", "wti원유": "wti",
}

# 되묻기 선택지 — 애매한 표현('금리')에 시스템이 고르라고 보여 주는 정본 id 묶음.
RATE_SERIES = ("us10y", "us2y", "fed_funds", "kr10y", "kr3m", "us_spread")


def macro_dir_for(data_dir: str | os.PathLike) -> Path:
    """OHLCV 데이터 루트(data/ohlcv)의 형제 디렉터리 data/macro."""
    return Path(data_dir).resolve().parent / MACRO_DIR_NAME


def macro_path(series: str, data_dir: str | os.PathLike) -> Path:
    return macro_dir_for(data_dir) / f"{series}.parquet"


def normalize_series(value) -> Optional[str]:
    if value is None:
        return None
    def _fold(text: str) -> str:
        return text.strip().lower().replace(" ", "").replace("_", "").replace("-", "").replace("/", "")

    key = _fold(str(value))
    if key in MACRO_SERIES:
        return key
    for alias, sid in MACRO_ALIASES.items():
        if key == _fold(alias):
            return sid
    return MACRO_ALIASES.get(key)


@lru_cache(maxsize=32)
def _load_cached(path_str: str, _mtime_ns: int) -> pd.Series:
    df = pd.read_parquet(path_str, columns=["date", "value"])
    s = pd.Series(df["value"].astype(float).values, index=pd.DatetimeIndex(pd.to_datetime(df["date"])))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.dropna()


def load_macro_series(series: str, data_dir: str | os.PathLike) -> Optional[pd.Series]:
    """(date → value) 시리즈. 파일이 없으면 None. (경로, mtime) 캐시 — 야간 갱신으로 자동 무효화."""
    path = macro_path(series, data_dir)
    if not path.exists():
        return None
    return _load_cached(str(path), path.stat().st_mtime_ns)


def series_label(series: str, english: bool = False) -> str:
    spec = MACRO_SERIES.get(series)
    if spec is None:
        return series
    return spec["label_en"] if english else spec["label"]
