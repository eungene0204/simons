"""영속 Artifact 상태 — 비싼 도구 산출물의 유효성 기록(2026-07-30 하이브리드 상태 모델).

세 상태 종류 중 이것만 **상태를 저장한다.** 파생 런타임 상태(`DerivedStatus`)를 저장하지
않는 이유가 여기서는 뒤집히기 때문이다:

  · 파생 상태는 전략을 보면 **공짜로 다시 계산된다**(0.12ms). 저장하면 판정이 두 곳에서
    갈라질 뿐 얻는 것이 없다.
  · Artifact는 다시 만들려면 지식그래프 조회·외부 검색·네트워크가 필요하다. "이게 아직
    맞나"를 알기 위해 다시 만들 수는 없으므로, **무엇을 근거로 만들었는지**(source_key)를
    남겨 두고 근거가 바뀌었는지만 대조한다.

그래서 여기 저장되는 것은 산출물의 값이 아니라 **근거와 상태**다. 값 자체는 이미
ParsedStrategy에 있다(`target_symbols`).

`planner/dag.py`의 `invalidated_by`와 같은 의존 관계를 쓰지만 수명이 다르다 — 저쪽은
파스 1회 안에서 살고, 이쪽은 턴을 넘는다. `NodeStatus`(작업을 실행했나)와 `ArtifactStatus`
(그 결과가 아직 유효한가)를 같은 이름으로 섞지 않는 이유이기도 하다.

**대조의 한계**: STALE 판정은 "사용자가 요구한 테마"와 "산출물이 만들어진 테마"가 각각
저장돼 있을 때만 가능하다. 정본 업종('반도체')은 `parsed.sector`에 남아 대조가 성립하지만,
미지 테마('쿠팡 관련주')는 `sector` 검증을 통과하지 못해 요청이 어디에도 남지 않는다 —
그 경우 대조할 상대가 없으므로 `basis_verified=False`로 표시한다. 미지 테마의 신선도는
수정 레인의 테마 교체 체인(`replace_theme_universe` — 교체 시 종목을 비우고 재조회)이
소유하며, 이 모듈은 그 사실을 관측만 한다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional


class ArtifactStatus(str, Enum):
    """저장된 도구 산출물의 유효성."""

    # 만들어진 근거가 그대로다.
    VALID = "VALID"
    # 근거가 바뀌었다 — 값은 남아 있지만 지금 State와 맞지 않는다. 재조회 대상이다.
    STALE = "STALE"
    # 근거 자체가 사라졌다(테마를 지웠다). 재조회로 되살릴 대상이 아니다.
    INVALIDATED = "INVALIDATED"
    # 조회를 시도했으나 실패했다(검색 소진 등). 같은 근거로 재시도해도 같은 결과다.
    FAILED = "FAILED"


# 지금 턴을 넘겨 사는 산출물은 하나다 — 테마 조회가 채운 종목 목록.
# 값은 parsed.target_symbols, 근거는 parsed.theme_universe(정본 테마 표기)에 있다.
THEME_SYMBOLS = "universe.symbols"
_PRODUCED_BY = {THEME_SYMBOLS: "kg_theme_companies"}


def _normalize(term: Any) -> str:
    """테마 표기 비교용 정규화(공백·대소문자 무시). 의미 판단이 아니라 표기 정규화다."""
    return str(term or "").replace(" ", "").lower()


def _requested_terms(parsed: Any) -> list:
    """사용자가 이번 State에서 요구하는 유니버스 표현(정규화)."""
    sector = getattr(parsed, "sector", None)
    if sector is None:
        return []
    terms = [sector] if isinstance(sector, str) else list(sector)
    return [_normalize(t) for t in terms if t]


def evaluate_artifacts(parsed: Any, previous: Any = None) -> Optional[Dict[str, dict]]:
    """저장된 산출물의 현재 유효성을 판정한다(재조회 없이 근거 대조만).

    previous: 직전 턴의 기록(프론트 에코). 값이 아니라 근거와 상태만 들어 있다.
    반환 None = 추적할 산출물이 없다(테마 유래 종목이 아예 없는 전략).

    **재조회를 여기서 하지 않는다** — 판정과 실행을 섞으면 표시용 호출이 네트워크를
    타게 되고, 실패가 파스를 깬다. 재조회는 수정 레인의 테마 교체 체인이 소유한다.
    """
    theme = getattr(parsed, "theme_universe", None)
    symbols = getattr(parsed, "target_symbols", None) or []
    prior = (previous or {}).get(THEME_SYMBOLS) if isinstance(previous, dict) else None

    if not theme:
        # 테마 유래 종목이 없다. 직전에 테마 산출물이 있었다면 근거가 사라진 것이다 —
        # 사용자가 직접 지정한 종목으로 바뀐 경우가 여기다.
        if isinstance(prior, dict) and prior.get("source_key"):
            return {THEME_SYMBOLS: {**prior, "status": ArtifactStatus.INVALIDATED.value}}
        return None

    requested = _requested_terms(parsed)
    if not symbols:
        # 테마는 있는데 종목이 없다 — 조회가 결과를 내지 못했다(검색 소진 테마 등).
        status = ArtifactStatus.FAILED
    elif requested and _normalize(theme) not in requested:
        # 사용자가 요구하는 테마가 바뀌었는데 종목은 이전 테마 것이다.
        # 재조회 없이 대조만으로 알 수 있는 유일한 이유이며, 이것이 이 모듈의 존재 이유다.
        status = ArtifactStatus.STALE
    else:
        status = ArtifactStatus.VALID

    return {THEME_SYMBOLS: {
        "status": status.value,
        "produced_by": _PRODUCED_BY[THEME_SYMBOLS],
        "source_key": theme,
        "symbol_count": len(symbols),
        # 대조가 실제로 이뤄졌는가. 미지 테마('쿠팡 관련주')는 요청이 parsed.sector에
        # 남지 않아(정본 업종만 통과) 대조할 상대가 없다 — 그때 VALID는 "확인했다"가
        # 아니라 "반증이 없다"는 뜻이다. 그 차이를 이름으로 드러내지 않으면 검증되지
        # 않은 산출물이 검증된 것처럼 보인다.
        "basis_verified": bool(requested),
    }}
