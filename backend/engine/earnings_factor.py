"""실적 서프라이즈 시그널(PEAD) — 랭킹 지표 ``pead``의 계산.

정의
----
종목 i, 거래일 t에서 **가장 최근에 발표된 분기**를 기준으로 두 값을 구한다.

1. **SUE**(표준화된 예상 외 이익) — 그 분기 EPS에서 전년 동기 EPS를 뺀 값을, 직전
   ``SUE_SAMPLE``(8)개 분기의 같은 계산값(YoY 차이) 표준편차로 나눈다.
2. **발표일 초과수익률(CAR)** — 발표일 직전 거래일 종가에서 발표 후 ``POST_DAYS``(2)번째
   거래일 종가까지의 수익률에서, 같은 구간 시장 수익률을 뺀다.

두 값을 각각 횡단면에서 상하위 1% 윈저라이즈 → z-score(`residual_factor.winsorized_zscore`)
한 뒤 평균한 값이 시그널이다. 값이 클수록 '시장이 아직 반영하지 않은 실적 서프라이즈가 큰
종목'이다.

계약
----
- **fail-closed**: 전년 동기 분기가 없거나(결산 변경·상장 초기), YoY 차이 표본이
  ``SUE_SAMPLE``개에 못 미치거나, 표준편차가 0이거나, 발표일 전후 가격이 없으면 NaN이다.
  중립값 0으로 위장하지 않는다(`residual_factor`와 같은 계약).
- **전년 동기는 날짜로 찾는다** — 목록에서 4칸 앞이 아니다. 분기 하나가 비어 있는 종목에서
  인덱스로 세면 2년 전 분기를 전년 동기로 쓰게 된다.
- **발표 전 정보를 쓰지 않는다**: t일의 시그널은 t일까지 발표된 분기만 본다. 발표일 당일이
  거래일이 아니면 직후 거래일을 D로 본다.
- SUE 표본은 YoY 차이 8개이므로 분기 데이터가 최소 12개(3년) 있어야 값이 선다 — 유니버스
  조건('직전 8개 분기 이상의 EPS 데이터')만 충족한 종목은 NaN으로 빠진다.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)

PEAD_ID = "pead"

# 고정 파라미터 — 사용자가 값을 말하지 않는 한 지표 정의의 일부다(노출하지 않는다).
SUE_SAMPLE = 8          # YoY 차이 표준편차의 표본 분기 수
PRE_DAYS = 1            # 발표일 기준 시작 거래일(D-1)
POST_DAYS = 2           # 발표일 기준 종료 거래일(D+2)

# 전년 동기로 인정하는 결산일 간격(개월). 결산기 변경 회사가 11·13개월로 어긋나는 것을
# 허용하되, 2년 전 분기가 전년 동기로 잡히는 것은 막는다.
_YOY_MONTHS_MIN = 11
_YOY_MONTHS_MAX = 13


def _months_between(earlier: pd.Timestamp, later: pd.Timestamp) -> int:
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)


def year_over_year_surprises(quarters: Sequence[dict]) -> List[dict]:
    """분기 목록 → 전년 동기 대비 EPS 차이 목록(결산일 오름차순).

    반환: ``[{"period_end", "announce_date", "surprise"}]``. 전년 동기를 찾지 못한 분기는
    빠진다(목록에서 4칸 앞을 쓰지 않는다 — 모듈 docstring).
    """
    rows = []
    for record in quarters or []:
        period_end = record.get("period_end")
        eps = record.get("eps")
        announced = record.get("announce_date")
        if not period_end or eps is None or not announced:
            continue
        rows.append({
            "period_end": pd.Timestamp(period_end),
            "announce_date": pd.Timestamp(announced),
            "eps": float(eps),
        })
    rows.sort(key=lambda row: row["period_end"])

    by_period = {row["period_end"]: row for row in rows}
    surprises = []
    for row in rows:
        previous = None
        for candidate_end, candidate in by_period.items():
            gap = _months_between(candidate_end, row["period_end"])
            if _YOY_MONTHS_MIN <= gap <= _YOY_MONTHS_MAX:
                previous = candidate
                break
        if previous is None:
            continue
        surprises.append({
            "period_end": row["period_end"],
            "announce_date": row["announce_date"],
            "surprise": row["eps"] - previous["eps"],
        })
    return surprises


def sue_series(quarters: Sequence[dict], sample: int = SUE_SAMPLE) -> List[dict]:
    """각 분기의 SUE — YoY 차이 ÷ 직전 ``sample``개 YoY 차이의 표준편차.

    표본에는 그 분기 자신의 차이가 포함된다(직전 8개 = 자신을 끝으로 하는 8개).
    표본이 모자라거나 표준편차가 0이면 그 분기는 값이 서지 않는다(빠진다).
    """
    surprises = year_over_year_surprises(quarters)
    values = [row["surprise"] for row in surprises]
    out = []
    for position, row in enumerate(surprises):
        if position + 1 < sample:
            continue
        window = values[position + 1 - sample: position + 1]
        deviation = float(np.std(window, ddof=1))
        if not np.isfinite(deviation) or deviation == 0.0:
            continue
        out.append({
            "period_end": row["period_end"],
            "announce_date": row["announce_date"],
            "sue": row["surprise"] / deviation,
        })
    return out


def _position_on_or_after(calendar: pd.DatetimeIndex, day: pd.Timestamp) -> Optional[int]:
    """발표일 이상인 첫 거래일의 위치. 발표일이 달력 끝을 넘으면 None."""
    position = int(calendar.searchsorted(day, side="left"))
    return position if position < len(calendar) else None


def event_excess_return(
    calendar: pd.DatetimeIndex,
    returns: np.ndarray,
    market_returns: np.ndarray,
    announce_date: pd.Timestamp,
    pre_days: int = PRE_DAYS,
    post_days: int = POST_DAYS,
) -> Optional[float]:
    """발표일 전후 초과수익률 — (D-pre → D+post 종목 수익률) − (같은 구간 시장 수익률).

    입력은 일간 수익률이다(지표 공통 재료 `residual_factor.return_materials`). D-1 종가에서
    D+2 종가까지의 수익률은 r[D]·r[D+1]·r[D+2]의 누적이다 — 구간 안에 결측이 하나라도
    있으면 None이다(0으로 채우지 않는다).
    """
    event = _position_on_or_after(calendar, announce_date)
    if event is None:
        return None
    start, end = event - pre_days + 1, event + post_days
    if start < 0 or end >= len(calendar):
        return None

    def _compound(series: np.ndarray) -> Optional[float]:
        window = np.asarray(series[start:end + 1], dtype=np.float64)
        if window.size == 0 or not np.all(np.isfinite(window)):
            return None
        return float(np.prod(1.0 + window) - 1.0)

    stock = _compound(returns)
    market = _compound(market_returns)
    if stock is None or market is None:
        return None
    return stock - market


def symbol_event_rows(
    quarters: Sequence[dict],
    calendar: pd.DatetimeIndex,
    returns: np.ndarray,
    market_returns: np.ndarray,
    *,
    sample: int = SUE_SAMPLE,
    pre_days: int = PRE_DAYS,
    post_days: int = POST_DAYS,
) -> List[dict]:
    """한 종목의 발표 이벤트 목록 — ``[{announce_position, sue, excess_return}]``.

    ``announce_position``은 달력에서 발표일 이상인 첫 거래일의 위치다(편입 지연·제외
    창을 세는 기준점이며, 시그널이 그 날부터 유효해진다).
    """
    rows = []
    for entry in sue_series(quarters, sample=sample):
        position = _position_on_or_after(calendar, entry["announce_date"])
        if position is None:
            continue
        excess = event_excess_return(
            calendar, returns, market_returns, entry["announce_date"],
            pre_days=pre_days, post_days=post_days,
        )
        if excess is None:
            continue
        rows.append({
            "announce_position": position,
            "sue": entry["sue"],
            "excess_return": excess,
        })
    return rows


def _forward_fill_events(
    rows: Sequence[dict], length: int, key: str, *, delay: int, expiry: int
) -> np.ndarray:
    """이벤트 값을 '발표 + delay일'부터 '발표 + expiry일'까지 펼친 시계열.

    구간은 **다음 발표일에서 끊는다** — 새 실적이 나온 뒤에도 옛 분기의 시그널로 편입하는
    것은 PEAD가 아니다. 새 시그널은 자기 delay가 지나야 서므로 그 사이는 NaN이고, 구간
    밖도 NaN이다(편입 자격이 없다는 뜻).
    """
    out = np.full(length, np.nan, dtype=np.float64)
    ordered = sorted(rows, key=lambda item: item["announce_position"])
    for position, row in enumerate(ordered):
        announced = row["announce_position"]
        start = announced + delay
        end = min(announced + expiry, length)
        if position + 1 < len(ordered):
            end = min(end, ordered[position + 1]["announce_position"])
        if start >= length or start >= end:
            continue
        out[start:end] = row[key]
    return out


def event_panels(
    rows_by_symbol: Dict[str, Sequence[dict]],
    calendar: pd.DatetimeIndex,
    *,
    delay: int,
    expiry: int,
) -> Dict[str, pd.DataFrame]:
    """종목별 이벤트 목록 → SUE·초과수익률 패널(거래일 × 종목).

    편입 지연(delay)·제외(expiry)는 거래일 수다 — 자격이 없는 날은 NaN이라 랭킹 후보에서
    빠지고, 그래서 '발표 후 N일이 지난 종목만, M일이 지나면 제외'가 시그널 자체로 표현된다.
    """
    symbols = sorted(rows_by_symbol)
    length = len(calendar)
    panels = {}
    for key in ("sue", "excess_return"):
        data = {
            symbol: _forward_fill_events(
                rows_by_symbol[symbol], length, key, delay=delay, expiry=expiry
            )
            for symbol in symbols
        }
        panels[key] = pd.DataFrame(data, index=calendar, columns=symbols)
    return panels


DEFAULT_ENTRY_DELAY_DAYS = 2      # 발표 후 이만큼 지난 종목만 편입
DEFAULT_EXPIRY_DAYS = 60          # 발표 후 이만큼 지나면 제외


def pead_panel(
    raw_price_df: pd.DataFrame,
    data_dir,
    *,
    entry_delay_days: int = DEFAULT_ENTRY_DELAY_DAYS,
    expiry_days: int = DEFAULT_EXPIRY_DAYS,
) -> Optional[pd.DataFrame]:
    """엔진 랭킹 입력 — raw_price_df와 같은 모양의 시그널 패널(클수록 상위). 불가하면 None.

    `residual_reversal_panel`과 같은 계약이다: 지표 전용 전체 이력에서 계산하고, 마지막에
    백테스트 패널의 달력·종목으로 맞춘다. 분기 실적이 없는 종목, 발표 자격 창 밖의 날은
    NaN이라 후보에서 빠진다.
    """
    from engine.market_index import market_for_symbol
    from engine.residual_factor import return_materials

    symbols = [str(symbol) for symbol in raw_price_df.columns]
    materials = return_materials(data_dir, symbols)
    if materials is None:
        return None
    calendar, returns_by_symbol, market_returns = materials

    rows_by_symbol: Dict[str, List[dict]] = {}
    for symbol in symbols:
        quarters = _load_quarters(symbol)
        series = returns_by_symbol.get(symbol)
        market = market_returns.get(market_for_symbol(symbol) or "")
        if not quarters or series is None or market is None:
            continue
        rows = symbol_event_rows(quarters, calendar, series, market)
        if rows:
            rows_by_symbol[symbol] = rows
    if not rows_by_symbol:
        return None

    panels = event_panels(
        rows_by_symbol, calendar, delay=entry_delay_days, expiry=expiry_days
    )
    signal = pead_signal(panels["sue"], panels["excess_return"])
    aligned = signal.reindex(
        index=pd.DatetimeIndex(raw_price_df.index), columns=raw_price_df.columns
    )
    aligned.index = raw_price_df.index
    # 상장 전·상폐 후 구간은 후보가 아니다(잔차 반전과 같은 처리).
    return aligned.where(raw_price_df.ffill().notna())


def _load_quarters(symbol: str) -> Optional[List[dict]]:
    from engine.quarterly_earnings import load_quarterly_earnings

    return load_quarterly_earnings(symbol)


def pead_signal(sue_panel: pd.DataFrame, excess_panel: pd.DataFrame) -> pd.DataFrame:
    """두 패널 → 시그널: 각각 횡단면 윈저라이즈 z-score 후 평균.

    한쪽만 있는 종목·날은 NaN이다 — 두 값을 평균하라는 요청이므로 한쪽으로 대신하지 않는다.
    """
    from engine.residual_factor import winsorized_zscore

    sue_z = winsorized_zscore(sue_panel)
    excess_z = winsorized_zscore(excess_panel)
    combined = (sue_z + excess_z) / 2.0
    return combined
