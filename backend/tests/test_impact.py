"""변경 영향 범위(설계 스펙 § 8·§ 30 `impact`) 계약.

파생 상태는 저장되지 않으므로 현재 값만으로는 "원래부터 안 되던 것"과 "방금 안 되게 된
것"이 구분되지 않는다. 전이는 직전 턴 계산 결과와의 대조로만 관측된다.
"""

from __future__ import annotations

from strategy_conversation.conversation.impact import compute_impact


def _states(**slots) -> dict:
    return {slot: {"value": "CONFIRMED", "derived": derived}
            for slot, derived in slots.items()}


def test_first_turn_has_no_impact():
    """직전 상태가 없으면 비교할 것이 없다 — 최초 파스는 무영향이다."""
    assert compute_impact(None, _states(매수_조건="APPLICABLE"), []) is None
    assert compute_impact({}, _states(매수_조건="APPLICABLE"), []) is None


def test_universe_change_invalidates_dependent_conditions():
    """[스펙 § 8.1] 유니버스가 바뀌면 그에 기대던 조건이 쓸 수 없게 된다.

    값이 바뀐 것은 universe 하나지만 영향은 매수 조건까지 번진다 — 그 사실은
    changed_fields만으로는 드러나지 않는다.
    """
    impact = compute_impact(
        _states(유니버스="APPLICABLE", 매수_조건="APPLICABLE"),
        _states(유니버스="APPLICABLE", 매수_조건="NOT_APPLICABLE"),
        ["universe"],
    )
    assert impact["affected_fields"] == ["universe"]
    assert impact["invalidated_fields"] == ["매수_조건"]
    assert impact["revalidated_fields"] == []


def test_reverting_the_universe_shows_revalidation():
    """되돌림이 실제로 일어났다는 증거는 여기에만 남는다 — 파생 상태는 저장되지 않는다."""
    impact = compute_impact(
        _states(매수_조건="NOT_APPLICABLE"),
        _states(매수_조건="APPLICABLE"),
        ["universe"],
    )
    assert impact["invalidated_fields"] == []
    assert impact["revalidated_fields"] == ["매수_조건"]


def test_steady_state_inapplicability_is_not_an_impact():
    """계속 쓸 수 없던 칸은 이번 턴의 영향이 아니다 — 전이만 센다."""
    assert compute_impact(
        _states(매수_조건="NOT_APPLICABLE"),
        _states(매수_조건="NOT_APPLICABLE"),
        [],
    ) is None


def test_conflict_and_invalid_count_as_needing_work():
    """모순·미지원도 '쓸 수 없게 됨'이다 — 해당 없음만 무효화인 것이 아니다."""
    for after in ("INVALID", "CONFLICTED"):
        impact = compute_impact(
            _states(매수_조건="APPLICABLE"), _states(매수_조건=after), [])
        assert impact["invalidated_fields"] == ["매수_조건"], after


def test_malformed_echo_is_ignored():
    """프론트 에코는 신뢰 경계 밖이다 — 깨진 입력이 추적을 깨뜨리지 않는다."""
    assert compute_impact("not-a-dict", _states(매수_조건="APPLICABLE"), []) is None
    assert compute_impact(_states(매수_조건="APPLICABLE"), None, []) is None
