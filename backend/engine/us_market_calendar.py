"""미국 장 운영 달력 — 토스 Open API `/api/v1/market-calendar/US` 정본.

자동매매의 미국 장 시간 판정(engine/virtual_trader._is_us_market_hours)이 쓰는
휴장일·조기 종료일 정보다. 종전에는 "평일 09:30~16:00 ET" 고정 규칙이라
① 공휴일(추수감사절·독립기념일 등)에도 개장으로 보고 ② 조기 종료일(13:00 ET)
오후를 장중으로 봤다. 둘 다 시세 신선도 방어(_fresh_price_map)가 매매를 보류시켜
오체결로 이어지진 않았지만, "왜 안 도는지" 알 수 없는 침묵이었다.

설계:
- **정본은 API가 준 정규장 시각 자체**다. 공휴일 목록을 우리가 관리하지 않는다
  (미국 공휴일은 규칙이 있지만 관측 규칙·조기 종료·임시 휴장(국장일 등)까지
  재현하려면 결국 달력을 베끼게 된다 — 정본을 두 번 적지 않는다).
- 휴장일이면 API가 `regularMarket: null`을 준다 → 그대로 '닫힘'.
- 조기 종료일은 `endTime`이 13:00 ET로 내려온다 → 그대로 반영된다.
- **일 단위 캐시**: 판정은 30초마다 불리지만 달력은 하루에 한 번만 받는다.
- **장애 시 폴백**: 토큰·네트워크 실패면 None을 반환해 호출부가 종전 고정 규칙으로
  진행한다(fail-open). 달력 조회 실패로 자동매매가 조용히 멈추는 편이 더 나쁘다 —
  휴장일 오작동은 시세 신선도 방어가 계속 막는다.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from engine.console_logging import console_logger

logger = console_logger(__name__, "US-CAL")

_BASE_URL = "https://openapi.tossinvest.com"
_REQUEST_TIMEOUT = 5
_ET = ZoneInfo("America/New_York")

# 조회 실패 후 재시도 간격 — 매 30초 루프마다 죽은 API를 두드리지 않는다.
_FAILURE_RETRY_SEC = 600

_lock = threading.Lock()
# 미국 현지 날짜 → (정규장 시작, 종료) | None(휴장). 조회 실패는 캐시하지 않는다.
_cache: dict[str, Optional[tuple[datetime, datetime]]] = {}
_last_failure_at = 0.0


def _provider():
    """시세 provider의 토큰 발급을 재사용한다(자격증명·갱신 로직 단일 정본)."""
    from engine.market_data import market_data_provider

    provider = getattr(market_data_provider, "us_provider", None)
    return provider if provider is not None and provider.is_configured() else None


def _parse_session(day: dict) -> Optional[tuple[datetime, datetime]]:
    """UsMarketDay → (시작, 종료) ET. regularMarket이 null이면 휴장(None)."""
    session = (day or {}).get("regularMarket")
    if not session:
        return None
    try:
        start = datetime.fromisoformat(session["startTime"]).astimezone(_ET)
        end = datetime.fromisoformat(session["endTime"]).astimezone(_ET)
    except (KeyError, TypeError, ValueError):
        return None
    return start, end


def _fetch(date_str: str) -> dict:
    """토스 해외 장 운영 정보 조회(동기). 실패는 예외로 던진다."""
    provider = _provider()
    if provider is None:
        raise RuntimeError("토스 US provider 미구성")
    resp = requests.get(
        f"{_BASE_URL}/api/v1/market-calendar/US",
        params={"date": date_str},
        headers={"Authorization": f"Bearer {provider._get_token()}"},
        timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("result") or {}


def regular_session(now: Optional[datetime] = None) -> Optional[tuple[datetime, datetime]]:
    """오늘(미국 현지)의 정규장 구간 — 휴장이면 None.

    조회 실패 시에도 None을 반환하므로, 호출부는 `calendar_available()`로 '휴장'과
    '모름'을 구분해야 한다(모름이면 고정 규칙 폴백).
    """
    ref = (now.astimezone(_ET) if now is not None else datetime.now(_ET))
    date_str = ref.strftime("%Y-%m-%d")

    global _last_failure_at
    with _lock:
        if date_str in _cache:
            return _cache[date_str]
        # 실패 직후 재시도 억제 — 30초 루프가 죽은 API를 두드리지 않게 한다.
        if _last_failure_at and (ref.timestamp() - _last_failure_at) < _FAILURE_RETRY_SEC:
            return None

    try:
        payload = _fetch(date_str)
    except Exception as exc:  # noqa: BLE001 — 달력 장애가 자동매매를 멈추면 안 된다
        with _lock:
            _last_failure_at = ref.timestamp()
        logger.warning("장 운영 정보 조회 실패(고정 규칙으로 진행): %s", exc)
        return None

    # 응답은 전일/당일/익일 3영업일 — 요청일과 같은 날짜의 항목만 채택한다.
    # (휴장일 조회 시 today가 다음 영업일로 밀려 오는 구현 차이를 흡수한다.)
    session: Optional[tuple[datetime, datetime]] = None
    matched = False
    for key in ("today", "previousBusinessDay", "nextBusinessDay"):
        day = payload.get(key) or {}
        if day.get("date") == date_str:
            session, matched = _parse_session(day), True
            break

    with _lock:
        _last_failure_at = 0.0
        # 오래된 날짜 항목은 버린다(하루 한 건이면 충분).
        _cache.clear()
        _cache[date_str] = session
    if not matched:
        logger.info("%s: 응답에 해당 날짜 없음 — 휴장으로 판정", date_str)
    return session


def calendar_available(now: Optional[datetime] = None) -> bool:
    """이 시점에 달력 판정을 신뢰할 수 있는가(조회 성공분이 캐시에 있는가)."""
    ref = (now.astimezone(_ET) if now is not None else datetime.now(_ET))
    with _lock:
        return ref.strftime("%Y-%m-%d") in _cache


def is_open(now: Optional[datetime] = None) -> Optional[bool]:
    """지금이 미국 정규장인가. 달력을 모르면 None(호출부가 고정 규칙 폴백)."""
    ref = (now.astimezone(_ET) if now is not None else datetime.now(_ET))
    session = regular_session(ref)
    if session is None:
        return False if calendar_available(ref) else None
    start, end = session
    # 종료 시각은 분 단위로 비교한다 — 16:00:30을 장외로 치면 30초 루프가 종료 분의
    # current_close 집행 창(virtual_trader)에 한 번도 닿지 못한다(한국 레인의 분 단위 규칙과 동일).
    return start <= ref and ref.replace(second=0, microsecond=0) <= end


def reset_cache() -> None:
    """테스트·수동 갱신용 — 캐시와 실패 억제 타이머를 비운다."""
    global _last_failure_at
    with _lock:
        _cache.clear()
        _last_failure_at = 0.0
