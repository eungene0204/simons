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
from typing import Any, Dict, Optional

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

# 참조 시계열(사용자 조건으로 노출하지 않는 것) — 결과 지표의 기준값으로만 쓴다.
# CPI는 해당 월이 끝나고 2주쯤 뒤에 공표되므로 **매매 조건(매크로 필터)으로 쓰면 미래 참조**다.
# 실질 수익률 환산은 사후 표시라 그 문제가 없어 MACRO_SERIES와 분리해 둔다.
REFERENCE_SERIES: Dict[str, Dict[str, str]] = {
    # 한국 CPI: FRED의 OECD 계열(KORCPIALLMINMEI 등)은 2023-11에 중단됐다(2026-09-23 실측).
    # 월별이 끊긴 자료로 최근 구간을 메우면 실질 수익률이 조용히 과대평가된다 — 대신 연간이지만
    # 계속 갱신되는 세계은행 지수를 쓰고, 덮지 못한 구간은 결과에 그대로 고지한다.
    "kr_cpi": {"label": "한국 소비자물가지수", "source": "worldbank", "code": "KR/FP.CPI.TOTL",
               "unit": "pt", "freq": "annual", "label_en": "Korea CPI"},
    "us_cpi": {"label": "미국 소비자물가지수", "source": "fred", "code": "CPIAUCSL",
               "unit": "pt", "freq": "monthly", "label_en": "US CPI"},
}

# 파일로 존재할 수 있는 모든 시리즈(필터용 + 참조용) — 동기화 스크립트·라벨 조회가 본다.
ALL_SERIES: Dict[str, Dict[str, str]] = {**MACRO_SERIES, **REFERENCE_SERIES}


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
    spec = ALL_SERIES.get(series)
    if spec is None:
        return series
    return spec["label_en"] if english else spec["label"]


# ── 무위험수익률·물가 (결과 지표의 기준값) ────────────────────────────────────
# 지역별 단기 금리 시리즈. 샤프·소르티노의 무위험수익률을 0으로 두면 금리가 높았던
# 구간(2000년대 초 CD 4~5%)의 위험조정 성과가 실제보다 좋게 나온다 — 백테스트 창의
# 실제 단기금리 평균을 쓴다(v16.33).
SHORT_RATE_SERIES: Dict[str, str] = {"kr": "kr3m", "us": "us3m"}

# 지역별 소비자물가지수 — 실질(인플레이션 조정) 수익률의 기준.
CPI_SERIES: Dict[str, str] = {"kr": "kr_cpi", "us": "us_cpi"}


def _align_to_window(series: pd.Series, index) -> pd.Series:
    """월간·일간이 섞인 시리즈를 백테스트 창의 거래일 축에 ffill 정렬한다(창 밖 값은 버린다)."""
    idx = pd.DatetimeIndex(pd.to_datetime(index)).normalize()
    if series is None or series.empty or len(idx) == 0:
        return pd.Series(dtype=float)
    merged = series.reindex(series.index.union(idx)).ffill()
    return merged.reindex(idx).dropna()


def average_short_rate(region: str, index, data_dir: str | os.PathLike) -> Optional[Dict[str, Any]]:
    """백테스트 창의 연 무위험수익률(소수)과 근거.

    반환 {'rate': 0.0325, 'series': 'kr3m', 'label': '한국 CD 3개월 금리(월간)', 'coverage': 0.98}.
    자료가 없으면 None — 호출 측은 0으로 떨어뜨린다(계산을 막지 않는다).
    """
    sid = SHORT_RATE_SERIES.get(str(region or "kr").lower())
    if sid is None:
        return None
    series = load_macro_series(sid, data_dir)
    if series is None:
        return None
    aligned = _align_to_window(series, index)
    if aligned.empty:
        return None
    return {
        "rate": float(aligned.mean()) / 100.0,
        "series": sid,
        "label": series_label(sid),
        "label_en": series_label(sid, english=True),
        "coverage": float(len(aligned)) / float(len(pd.Index(index))),
    }


def inflation_over_window(region: str, index, data_dir: str | os.PathLike) -> Optional[Dict[str, Any]]:
    """백테스트 창의 누적 물가상승률(소수)과 연율 — 실질(인플레이션 조정) 수익률의 기준.

    반환 {'total': 0.21, 'annual': 0.024, 'series': 'kr_cpi', 'from': .., 'to': ..,
          'windowTo': .., 'covered': False}.
    **ffill한 꼬리로 기간을 늘리지 않는다**: 물가 자료가 창 끝보다 이르면 마지막 실측 관측일까지만
    환산하고 그 사실을 함께 싣는다(한국 CPI는 연간이라 늘 몇 달이 남는다). 자료가 없으면 None.
    """
    sid = CPI_SERIES.get(str(region or "kr").lower())
    if sid is None:
        return None
    series = load_macro_series(sid, data_dir)
    if series is None or series.empty:
        return None
    idx = pd.DatetimeIndex(pd.to_datetime(index)).normalize()
    if len(idx) == 0:
        return None
    w_start, w_end = idx[0], idx[-1]
    at_or_before_start = series[series.index <= w_start]
    base_date = at_or_before_start.index[-1] if len(at_or_before_start) else None
    if base_date is None:
        after = series[series.index >= w_start]
        base_date = after.index[0] if len(after) else None
    at_or_before_end = series[series.index <= w_end]
    last_date = at_or_before_end.index[-1] if len(at_or_before_end) else None
    if base_date is None or last_date is None or last_date <= base_date:
        return None
    base, last = float(series.loc[base_date]), float(series.loc[last_date])
    days = (last_date - base_date).days
    if base <= 0 or days <= 0:
        return None
    years = days / 365.25
    return {
        "total": last / base - 1.0,
        "annual": (last / base) ** (1.0 / years) - 1.0 if years > 0 else None,
        "series": sid,
        "label": series_label(sid),
        "label_en": series_label(sid, english=True),
        "from": base_date.strftime("%Y-%m-%d"),
        "to": last_date.strftime("%Y-%m-%d"),
        "windowTo": w_end.strftime("%Y-%m-%d"),
        # 창 끝까지 물가 자료가 닿았는지(연간 자료는 대개 False) — 실질 수익률 표기의 단서다.
        "covered": bool((w_end - last_date).days <= 45),
    }
