"""조건이 아닌 슬롯(포트폴리오·리스크·청산) 되묻기의 칩·결속 회귀.

[회귀 2026-07-31 결속 소실 사고] 인터프리터는 이 슬롯들에도 recommended_value를 냈지만
`_build_clarification`의 칩 생성이 **조건 임계값 질문에만** 있어서 전부 버려졌다. 칩이
0개면 `_pending_ask_payload`가 None을 내므로, 포트폴리오·리스크·청산 질문은 구조적으로
영원히 결속되지 않았다(실측: 고정 파이프라인 경로 결속 0/7턴). 결속이 없으면 다음 턴의
사용자 답변은 "어느 질문의 답인지" 근거를 잃고 일반 의도 분류 레인으로 떨어진다.

이 테스트가 지키는 계약 둘:
1. 슬롯 질문의 추천값이 칩으로 나온다.
2. **그 칩은 실제로 값에 결속된다** — 결속되지 않는 칩은 발행 시점에 탈락해 사용자에게
   보이지도 않으므로(칩=값 결속 계약), 문구를 지어내면 수정 자체가 무효가 된다.
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy
from strategy_conversation.interpreter.models import (
    ClarificationQuestion,
    StrategyIntent,
    ValidationReport,
)
from strategy_conversation.primary import (
    _bind_chips,
    _build_clarification,
    _pending_ask_payload,
    _SLOT_CHIP_BUILDERS,
)


def _clarify(field: str, recommended):
    report = ValidationReport(
        status="NEEDS_CLARIFICATION",
        clarification_questions=[ClarificationQuestion(
            field=field, question="질문", recommended_value=recommended,
            recommendation_reason="이유",
        )],
    )
    return _build_clarification(report, StrategyIntent(intent="CREATE_STRATEGY"))


def _base_strategy() -> ParsedStrategy:
    return ParsedStrategy(
        description="테스트", universe=["KOSPI"],
        entry_signals=[{"indicator": "rsi", "signal_type": "buy",
                        "operator": "<=", "value": 30}],
    )


@pytest.mark.parametrize("field,recommended", [
    ("strategy.portfolio.selection_count", 10),
    ("strategy.portfolio.rebalance_frequency", "monthly"),
    ("strategy.portfolio.hold_period_days", 30),
    ("strategy.risk_management.stop_loss", 8),
    ("strategy.risk_management.take_profit", 25),
    ("strategy.risk_management.trailing_stop", 12),
    ("strategy.exit_conditions", "monthly"),
    ("strategy.ranking[0].lookback_days", 60),
])
def test_slot_question_produces_chips(field, recommended):
    _question, chips, topic = _clarify(field, recommended)
    assert chips, f"{field}: 추천값이 있는데 칩이 없다 — 결속 불가"
    assert topic, f"{field}: topic이 없으면 확정 판정(_confirm_target)이 필드를 못 찾는다"


@pytest.mark.parametrize("field", sorted(_SLOT_CHIP_BUILDERS))
def test_every_slot_chip_actually_binds(field):
    """지어낸 문구 금지 — 모든 칩이 값 결속 또는 확정 결속을 통과해야 한다."""
    topic, build = _SLOT_CHIP_BUILDERS[field]
    chips = build(None)
    assert chips, f"{field}: 추천값이 없어도 대안 칩은 나와야 한다"
    bound, bindings, confirms = _bind_chips(chips, _base_strategy(), topic)
    unbound = [c for c in chips if c not in bindings and c not in confirms]
    assert not unbound, f"{field}: 결속되지 않는 칩 — 발행돼도 사용자에게 보이지 않는다: {unbound}"


def test_recommended_value_leads_the_options():
    """추천값이 맨 앞 — 화면의 첫 선택지가 우리가 권한 값이어야 한다."""
    _q, chips, _t = _clarify("strategy.risk_management.stop_loss", 12)
    assert chips[0] == "손절 -12%"


def test_slot_chips_yield_a_bound_pending_ask():
    """칩 → pending_ask 결속까지 실제로 이어진다(이 사슬이 끊겨 있던 것이 사고 원인)."""
    _q, chips, topic = _clarify("strategy.risk_management.stop_loss", 8)
    ask = _pending_ask_payload("손절 기준은?", chips, topic, _base_strategy())
    assert ask is not None, "결속이 없으면 다음 턴 답변을 이 질문에 귀속할 수 없다"
    assert ask["chip_bindings"]["손절 -8%"] == {"stop_loss_pct": 8.0}


def test_only_one_slot_supplies_chips_per_turn():
    """pending_ask 하나에 topic 하나 — 여러 슬롯 칩을 섞으면 확정 판정이 엉뚱한 필드를 본다."""
    report = ValidationReport(
        status="NEEDS_CLARIFICATION",
        clarification_questions=[
            ClarificationQuestion(field="strategy.portfolio.selection_count",
                                  question="몇 종목?", recommended_value=10,
                                  recommendation_reason="r"),
            ClarificationQuestion(field="strategy.risk_management.stop_loss",
                                  question="손절?", recommended_value=8,
                                  recommendation_reason="r"),
        ],
    )
    question, chips, topic = _build_clarification(
        report, StrategyIntent(intent="CREATE_STRATEGY"))
    assert topic == "최대 보유"
    assert all(c.startswith("최대 ") for c in chips), chips
    # 두 질문 모두 문구로는 남는다 — 칩만 한 슬롯 것이다.
    assert "몇 종목?" in question and "손절?" in question


def test_unbindable_planner_chips_fall_back_to_slot_sot():
    """[회귀 2026-08-01] planner 칩이 전부 결속 불가여도 정본 칩으로 발행된다.

    Trace 실측(`gate=chip_binding_failed 칩=0/3`)에서 planner가 낸 매도 칩 3개가 전부
    엔진이 표현할 수 없어 탈락했다. 칩 개수만 보면 "칩이 있으니 괜찮다"로 지나가지만
    결과는 칩 0개와 똑같다 — pending_ask가 없어 다음 턴 답변의 귀속 근거가 사라진다.
    """
    from strategy_conversation.primary import _bound_ask_with_slot_fallback

    # 실측에서 "표현할 수 없어 노출 제외"로 탈락한 문구들.
    junk = ["거래량 급감(전일 대비 1/2 이하) 시 매도", "심리도 악화 시 매도"]
    ask, used = _bound_ask_with_slot_fallback(
        "어떤 조건에서 매도할까요?", junk, "매도 조건", _base_strategy())
    assert ask is not None, "결속 불가 칩만 있으면 슬롯 정본으로 되살려야 한다"
    assert ask["chips"] and all(c not in junk for c in ask["chips"])
    assert used != junk


def test_planner_chips_are_always_replaced_by_slot_sot():
    """[2026-08-02 사용자 결정] planner 칩은 결속 가능해도 노출하지 않는다.

    모든 옵션 칩은 하드코딩 정본이어야 지원을 확신할 수 있다 — 결속 게이트만으로는
    부족하다('거래량 급증(전일 대비 3배) 시 매수'가 부분 결속으로 통과해 노출된 사고).
    """
    from engine import strategy_slots
    from strategy_conversation.primary import _bound_ask_with_slot_fallback

    ask, used = _bound_ask_with_slot_fallback(
        "어떤 조건에서 매도할까요?", ["20일 보유 후 청산"], "매도 조건", _base_strategy())
    assert ask is not None
    canonical = strategy_slots.suggestions_for_topic("매도 조건")
    assert used == canonical
    assert set(ask["chips"]) <= set(canonical)


def test_etf_universe_gets_no_fundamental_chips():
    """ETF 유니버스의 매수 조건 정본 칩에는 재무 칩(PER·ROE)이 없다.

    ETF는 개별 기업 재무제표 지표를 조건으로 쓸 수 없다(universe_capabilities) —
    결속 검사는 유니버스 호환성을 보지 않으므로(PER 칩도 ETF 전략에 결속된다)
    정본 선별 단계에서 제외해야 한다.
    """
    from engine import strategy_slots

    stock_chips = strategy_slots.suggestions_for_topic("매수 조건", universe=["KOSPI"])
    etf_chips = strategy_slots.suggestions_for_topic("매수 조건", universe=["ETF"])
    assert "PER 10 이하" in stock_chips and "ROE 15% 이상" in stock_chips
    assert "PER 10 이하" not in etf_chips and "ROE 15% 이상" not in etf_chips
    assert etf_chips, "재무 칩 제외 후에도 기술 지표 칩은 남아야 한다"


def test_slot_sot_supplies_chips_for_a_chipless_planner_ask():
    """[회귀 2026-08-01] planner가 칩 없는 ask를 내는 턴이 있다.

    Trace 실측에서 같은 질문("어떤 조건에서 매도할까요?")이 어떤 턴엔 칩 3개, 어떤 턴엔
    0개로 나왔다 — LLM 출력 편차다. 칩이 0개면 pending_ask가 발행되지 않아 그 답이
    다음 턴에 귀속 근거를 잃는다. 그 공백은 슬롯 정본에서 메운다(어휘 복제 금지).
    """
    from engine import strategy_slots

    chips = strategy_slots.suggestions_for_topic("매도조건")
    assert chips, "planner topic이 슬롯에 매칭되면 정본 칩이 나와야 한다"
    # 정본 칩이 실제로 결속돼야 보완이 의미가 있다.
    ask = _pending_ask_payload("어떤 조건에서 매도할까요?", chips, "매도 조건",
                               _base_strategy())
    assert ask is not None and ask["chips"]


def test_unknown_topic_supplies_nothing():
    """모르는 topic에 아무 칩이나 붙이지 않는다 — 엉뚱한 슬롯의 답으로 귀속된다."""
    from engine import strategy_slots

    assert strategy_slots.suggestions_for_topic("듣도보도못한주제") == []
    assert strategy_slots.suggestions_for_topic(None) == []


def test_condition_chips_are_untouched():
    """조건 임계값 칩(기존 동작)은 슬롯 칩 추가의 영향을 받지 않는다."""
    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "fundamental.per", "operator": "<="}],
    })
    report = ValidationReport(
        status="NEEDS_CLARIFICATION",
        clarification_questions=[ClarificationQuestion(
            field="strategy.entry_conditions[0].value", question="PER 기준값은?",
            recommended_value=10, recommendation_reason="r")],
    )
    _question, chips, topic = _build_clarification(report, intent)
    assert chips == ["PER 10배 이하"]
    assert topic is None, "조건 칩은 슬롯이 아니다 — topic이 붙으면 확정 판정이 오작동한다"
