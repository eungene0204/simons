"""변경 영향 범위(설계 스펙 § 8·§ 30 `impact`) — 이번 턴이 무엇을 바꿨나.

`changed_fields`(§ 19)는 **값이 달라진 필드**를 답한다. 그것만으로는 답이 안 되는 질문이
하나 있다: **"이번 변경으로 무엇이 쓸 수 없게 됐나."**

유니버스를 ETF로 바꾸면 값이 바뀐 것은 `universe` 하나지만, 그 한 번으로 기존 PER 조건이
적용 불가가 된다. 파생 상태(`DerivedStatus`)는 매 턴 다시 계산되므로 **현재 값만 보면
"원래부터 안 되던 것"과 "방금 안 되게 된 것"이 구분되지 않는다** — 전이를 알려면 직전 턴의
계산 결과와 대조해야 한다.

그래서 이 모듈의 입력은 직전 턴의 `field_states` 에코다(`explicit_fields`·`pending_ask`와
같은 무상태 계약). 상태를 저장하는 것이 아니라, 저장하지 않는 계산값 두 벌을 비교한다.

**사용자에게 새 문구를 만들지 않는다.** ETF에 재무 조건을 쓸 수 없다는 사실은 이미
capability validator가 안내한다 — 여기서 또 알리면 같은 말이 두 번 나간다. 이 산출물은
스펙 § 30의 내부 출력("사용자가 요청하지 않는 한 그대로 노출하지 않는다")이며, 추적·
디버깅과 이후 소비자를 위한 구조화 기록이다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# 파생 상태의 '손이 필요한 정도' — 이 순서로 나빠지면 무효화, 좋아지면 재유효화다.
# APPLICABLE만이 "그대로 쓸 수 있다"이고 나머지는 전부 개입이 필요한 상태다.
_NEEDS_WORK = ("INVALID", "CONFLICTED", "NOT_APPLICABLE")


def _derived(states: Any, slot: str) -> Optional[str]:
    """슬롯의 파생 상태 문자열(없으면 None)."""
    if not isinstance(states, dict):
        return None
    entry = states.get(slot)
    return entry.get("derived") if isinstance(entry, dict) else None


def compute_impact(
    previous_states: Any,
    current_states: Any,
    changed_fields: Optional[Iterable[Any]] = None,
) -> Optional[Dict[str, List[str]]]:
    """이번 턴의 변경 영향. 직전 상태가 없으면(최초 턴) None.

    - affected_fields   : 값이 달라진 필드(= changed_fields, § 19가 이미 산출)
    - invalidated_fields: 쓸 수 있던 칸이 쓸 수 없게 된 슬롯
    - revalidated_fields: 쓸 수 없던 칸이 다시 쓸 수 있게 된 슬롯

    재유효화를 함께 내는 이유: 되돌림이 실제로 일어났다는 증거가 여기에만 남는다.
    파생 상태는 저장하지 않으므로(§ FR-SA-011 ②) "ETF→코스피로 되돌려 PER 조건이
    다시 유효해졌다"는 사실은 두 계산 결과의 차이로만 관측된다.
    """
    if not isinstance(previous_states, dict) or not previous_states:
        return None
    invalidated: List[str] = []
    revalidated: List[str] = []
    for slot in current_states if isinstance(current_states, dict) else {}:
        before, after = _derived(previous_states, slot), _derived(current_states, slot)
        if before is None or after is None or before == after:
            continue
        if before not in _NEEDS_WORK and after in _NEEDS_WORK:
            invalidated.append(slot)
        elif before in _NEEDS_WORK and after not in _NEEDS_WORK:
            revalidated.append(slot)
    affected = [f for f in (changed_fields or ()) if isinstance(f, str)]
    if not (affected or invalidated or revalidated):
        return None
    return {
        "affected_fields": affected,
        "invalidated_fields": invalidated,
        "revalidated_fields": revalidated,
    }
