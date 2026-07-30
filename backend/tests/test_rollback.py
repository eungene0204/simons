"""되돌리기 대상 판정(설계 스펙 § 19) — LLM 제안 → 결정론 대조.

여기서 고정하는 계약: **되돌리기는 사용자가 쌓아온 작업을 지우므로 추측으로 실행하지
않는다.** LLM이 지어낸 턴 번호·필드 이름은 임의 보정 없이 되묻기로 강등된다 —
'가장 최근 턴으로 떨어뜨리기' 같은 보정은 사용자가 의도하지 않은 변경을 조용히
사라지게 한다.

원문 해석은 전적으로 LLM이며, 이 모듈의 정규식은 LLM 출력의 JSON 경계에만 걸린다.
"""

from __future__ import annotations

import json

import pytest

from strategy_conversation.conversation import change_log
from strategy_conversation.conversation.rollback import SYSTEM_PROMPT, resolve

EVENTS = [
    {"index": 1, "user_text": "코스피 골든크로스 전략", "changed_fields": []},
    {"index": 2, "user_text": "ETF로 바꿔줘", "changed_fields": ["universe", "max_positions"]},
    {"index": 3, "user_text": "PER 조건 빼줘", "changed_fields": ["fundamental_filters"]},
]


def stub(**payload):
    return lambda system, user: json.dumps(payload, ensure_ascii=False)


def capturing(**payload):
    seen: dict[str, str] = {}

    def _llm(system, user):
        seen["system"] = system
        seen["user"] = user
        return json.dumps(payload, ensure_ascii=False)

    return _llm, seen


# ── 변경 필드 산출 ────────────────────────────────────────────────────────────

def test_changed_field_names_returns_structured_names():
    before = {"max_positions": 10, "universe": ["KOSPI"], "description": "a"}
    after = {"max_positions": 5, "universe": ["KOSPI"], "description": "b"}
    # description은 발화 기록이라 되돌릴 대상이 아니다.
    assert change_log.changed_field_names(before, after) == ["max_positions"]


def test_first_turn_has_no_changed_fields():
    """최초 턴을 '변경'으로 보면 첫 턴으로 되돌리기가 빈 전략을 만든다."""
    assert change_log.changed_field_names(None, {"universe": ["KOSPI"]}) == []


def test_restorable_fields_is_a_closed_list():
    assert change_log.restorable_fields(EVENTS) == [
        "fundamental_filters", "max_positions", "universe",
    ]


# ── 판정 ─────────────────────────────────────────────────────────────────────

def test_turn_scope_resolves_to_that_change():
    decision = resolve("아까 바꾼 거 취소해", EVENTS, stub(
        scope="TURN", turn_index=3, fields=[], ambiguous=False, question=None,
    ))
    assert decision.action == "turn"
    assert decision.turn_index == 3
    assert decision.fields == ["fundamental_filters"]


def test_field_scope_keeps_only_fields_changed_in_that_turn():
    """LLM이 지어낸 필드는 조용히 버린다 — 그 턴에서 바뀌지 않은 것은 되돌릴 게 없다."""
    decision = resolve("유니버스만 되돌려", EVENTS, stub(
        scope="FIELDS", turn_index=2, fields=["universe", "없는필드"], ambiguous=False,
    ))
    assert decision.action == "fields"
    assert decision.fields == ["universe"]


def test_field_scope_with_no_valid_field_falls_back_to_clarify():
    decision = resolve("x", EVENTS, stub(
        scope="FIELDS", turn_index=2, fields=["초기자본"], ambiguous=False,
    ))
    assert decision.action == "clarify"


def test_hallucinated_turn_index_is_not_silently_corrected():
    """가장 최근 턴으로 떨어뜨리면 사용자가 의도하지 않은 변경이 조용히 사라진다."""
    decision = resolve("x", EVENTS, stub(scope="TURN", turn_index=99, ambiguous=False))
    assert decision.action == "clarify"
    assert "99" in decision.reason


def test_ambiguous_flag_becomes_clarify_with_llm_question():
    decision = resolve("되돌려", EVENTS, stub(
        scope="TURN", turn_index=2, ambiguous=True, question="어느 변경을 되돌릴까요?",
    ))
    assert decision.action == "clarify"
    assert decision.question == "어느 변경을 되돌릴까요?"


def test_scope_none_becomes_clarify():
    decision = resolve("x", EVENTS, stub(scope="NONE", turn_index=None, ambiguous=False))
    assert decision.action == "clarify"


@pytest.mark.parametrize("raw", ["설명입니다", "", "{망가진 json"])
def test_unparseable_output_falls_back_to_clarify(raw):
    decision = resolve("x", EVENTS, lambda s, u: raw)
    assert decision.action == "clarify"


def test_no_revertible_history_is_reported_as_unsupported():
    """최초 파스만 있으면 되돌릴 변경이 없다 — LLM을 부르지 않는다."""
    called = []

    def _llm(system, user):
        called.append(1)
        return "{}"

    decision = resolve("되돌려", [EVENTS[0]], _llm)
    assert decision.action == "unsupported"
    assert called == []


def test_llm_unavailable_falls_back_to_clarify_not_guess():
    decision = resolve("되돌려", EVENTS, None)
    assert decision.action == "clarify"


# ── LLM에 전달되는 맥락 ───────────────────────────────────────────────────────

def test_prompt_carries_history_but_not_strategy_values():
    """판정에 필요한 것은 '무엇이 바뀌었나'뿐이다 — 전략 값을 실으면 작은 모델이
    되돌리기가 아니라 전략 해석을 시작한다."""
    llm, seen = capturing(scope="TURN", turn_index=3, ambiguous=False)
    resolve("아까 거 취소", EVENTS, llm)
    assert "ETF로 바꿔줘" in seen["user"]
    assert "universe" in seen["user"]
    assert "[되돌리기 요청]" in seen["user"]
    # 최초 파스는 되돌릴 수 없어 이력에서 빠진다.
    assert "코스피 골든크로스 전략" not in seen["user"]


def test_output_contract_declares_every_field():
    for key in ('"scope"', '"turn_index"', '"fields"', '"ambiguous"', '"question"'):
        assert key in SYSTEM_PROMPT


# ── 필드 라벨 (실측 회귀) ─────────────────────────────────────────────────────
# 이력에 영문 필드명만 보여주면 "손절 바꾼 거 되돌려"가 stop_loss_pct와 연결되지 않아
# 모델이 엉뚱한 턴을 고른다(2026-07-30 실측: 9B가 손절 요청에 재무 조건 턴을 선택,
# 라벨 추가 후 7/7). 라벨을 키로 정해진 문구를 고르는 결정론 매핑이며 원문 해석이 아니다.


def test_summary_carries_user_vocabulary_for_field_names():
    summary = change_log.summarize_for_prompt([
        {"index": 2, "user_text": "손절 -8%로", "changed_fields": ["stop_loss_pct"]},
    ])
    assert "stop_loss_pct" in summary  # 모델이 답에 쓸 이름
    assert "손절" in summary            # 사용자 발화와 잇는 다리


def test_unknown_field_label_is_not_invented():
    assert change_log.label_for("완전히_새로운_필드") == "완전히_새로운_필드"


def test_prompt_rules_cover_no_target_and_field_matching():
    """실측에서 틀렸던 두 경우를 프롬프트가 명시적으로 다룬다."""
    assert "가장 큰 번호" in SYSTEM_PROMPT      # 대상 없는 '되돌려' → 직전 변경
    assert "괄호 안 설명" in SYSTEM_PROMPT      # 라벨 ↔ 사용자 표현 연결
