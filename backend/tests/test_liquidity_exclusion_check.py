"""유동성 제외 대조(2026-10-07 예시 18·23) — '거래가 너무 없는 종목은 제외'가 미지원 안내로 나가던 사고."""

import json

from strategy_conversation.interpreter import liquidity_exclusion_check as liq
from strategy_conversation.interpreter.models import StrategyIntent

_TEXT_23 = ("KOSPI에서 PBR 1배 이하이면서 부채비율이 100% 이하인 종목을 중심으로 포트폴리오를 만들고 싶습니다. "
            "거래가 너무 없는 종목은 제외하고 매월 조건을 다시 점검해 주세요. 최대 12종목, 동일 비중, 손절 -12%로 운영하고 싶습니다.")
_TEXT_18 = ("KOSPI에서 PBR 1.2배 이하이면서 최근 20일 평균 거래대금이 30억 원 이상인 종목만 대상으로 보고 싶습니다. "
            "너무 거래가 없는 종목은 제외하고 싶고, 그 안에서 20일 신고가 돌파가 나오면 진입하는 방식으로 구성해 주세요.")


def _intent(entry, unsupported):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "strategy": {"universe": {"markets": ["KOSPI"]}, "entry_conditions": entry},
        "unsupported_features": unsupported,
    })


def _chat(kind):
    calls = []

    def chat(system, user, max_tokens=None):
        calls.append(user)
        return json.dumps({"items": [{"kind": kind}]})
    chat.calls = calls
    return chat


def _run(intent, text, chat):
    targets = liq.features_to_check(intent, text)
    return liq.apply_verdicts(intent, liq.check_features(text, targets, chat))


def test_valueless_liquidity_exclusion_becomes_trading_value_question():
    intent = _intent([{"factor": "fundamental.pbr", "operator": "<=", "value": 1,
                       "source_text": "PBR 1배 이하"}],
                     ["거래가 너무 없는 종목은 제외"])
    moved = _run(intent, _TEXT_23, _chat("liquidity"))
    assert moved == ["거래가 너무 없는 종목은 제외"]
    assert intent.unsupported_features == []
    added = intent.strategy.entry_conditions[-1]
    assert (added.factor, added.operator, added.value, added.value_source) == (
        "fundamental.trading_value", ">=", None, "MISSING")
    assert added.source_text == "거래가 너무 없는 종목은 제외"


def test_liquidity_restatement_of_existing_amount_only_drops_report():
    intent = _intent([{"factor": "fundamental.trading_value", "operator": ">=", "value": 30,
                       "parameters": {"period": 20},
                       "source_text": "최근 20일 평균 거래대금이 30억 원 이상"}],
                     ["너무 거래가 없는 종목은 제외하고 싶고"])
    _run(intent, _TEXT_18, _chat("liquidity"))
    assert intent.unsupported_features == []
    assert [c.value for c in intent.strategy.entry_conditions] == [30]


def test_other_or_failed_verdict_keeps_report():
    for chat in (_chat("other"), _chat("unclear"), lambda *a, **k: "not json"):
        intent = _intent([], ["거래가 너무 없는 종목은 제외"])
        _run(intent, _TEXT_23, chat)
        assert intent.unsupported_features == ["거래가 너무 없는 종목은 제외"]
        assert intent.strategy.entry_conditions == []


def test_reports_absent_from_input_are_not_asked():
    intent = _intent([], ["유동성 낮은 종목 제외"])
    chat = _chat("liquidity")
    assert liq.features_to_check(intent, _TEXT_23) == []
    _run(intent, _TEXT_23, chat)
    assert chat.calls == []
    assert intent.unsupported_features == ["유동성 낮은 종목 제외"]
