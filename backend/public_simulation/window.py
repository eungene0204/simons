"""전략 시뮬레이션의 계산 기간 — Asia/Seoul 오늘부터 달력 기준 3년 전까지(순수 함수, 주입 가능한 시각).

정의는 docs/development/strategy-simulation.md §3.2. 한국 휴장일 달력이 저장소에 없으므로 '확정 데이터가
있는 마지막 거래일'은 데이터 자체(dataAsOf)에서 읽고, 지연 여부는 평일 기준으로만 근사한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
# 실제 시작일이 요청 시작일보다 이만큼(일) 넘게 늦으면 '데이터 부족'으로 본다 — 최장 연휴 여유.
START_TOLERANCE_DAYS = 7


class WindowError(Exception):
    """계산 창을 만들 수 없음. code는 사용자 안내 매핑용."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SimulationWindow:
    today: str
    requested_start: str
    requested_end: str
    end_date: str       # 엔진에 보내는 종료일 = min(today, dataAsOf)
    data_as_of: str
    stale: bool

    def to_dict(self) -> Dict[str, Any]:
        """공개 응답 표기(camelCase, 명세 §4.1)."""
        return {
            "today": self.today, "requestedStart": self.requested_start, "requestedEnd": self.requested_end,
            "endDate": self.end_date, "dataAsOf": self.data_as_of, "stale": self.stale,
        }


def seoul_today(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(SEOUL).date()


def three_years_before(day: date) -> date:
    """달력 기준 3년 전 같은 월·일. 그 해에 없는 날짜(2월 29일)는 2월 28일."""
    try:
        return day.replace(year=day.year - 3)
    except ValueError:
        return day.replace(year=day.year - 3, day=28)


def previous_weekday(day: date) -> date:
    """day보다 이른 가장 가까운 평일."""
    prev = day - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def compute_window(now: datetime, data_as_of: date) -> SimulationWindow:
    today = seoul_today(now)
    requested_start = three_years_before(today)
    if data_as_of < requested_start:
        raise WindowError("NO_DATA_IN_WINDOW", "요청 기간에 확정된 데이터가 없습니다.")
    return SimulationWindow(
        today=today.isoformat(),
        requested_start=requested_start.isoformat(),
        requested_end=today.isoformat(),
        end_date=min(today, data_as_of).isoformat(),
        data_as_of=data_as_of.isoformat(),
        # 오늘이 평일이고 장 마감 전이면 직전 평일 데이터가 최신이 정상이다.
        stale=data_as_of < previous_weekday(today),
    )


def actual_period(window: SimulationWindow, actual_start: str, actual_end: str) -> Dict[str, Any]:
    """엔진이 실제 계산한 기간을 요청 기간과 대조한다. 창을 벗어나면 WindowError(미래 데이터 방지)."""
    start = date.fromisoformat(actual_start[:10])
    end = date.fromisoformat(actual_end[:10])
    if start < date.fromisoformat(window.requested_start) or end > date.fromisoformat(window.end_date):
        raise WindowError("WINDOW_VIOLATION", "계산 기간이 요청 기간을 벗어났습니다.")
    limited = (start - date.fromisoformat(window.requested_start)).days > START_TOLERANCE_DAYS
    out: Dict[str, Any] = {
        "requestedStart": window.requested_start,
        "requestedEnd": window.requested_end,
        "actualStart": start.isoformat(),
        "actualEnd": end.isoformat(),
        "dataAsOf": window.data_as_of,
        "stale": window.stale,
        "limited": limited,
    }
    if limited:
        out["limitReason"] = "DATA_STARTS_LATER"
    return out
