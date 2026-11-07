"""연산자만 다른 이동평균 중복 사본은 보류 질문 없이 뺀다(2026-11-07).

사고: "주가가 200일 이동평균선 위에 있는 종목"을 120B가 `>`와 `crosses_above` 두 매수 조건으로
적었고(인용·파라미터 동일), 인용 대조가 후자에 no/moving_average를 답하자 판정 보류로 빠지며
"보류한 조건의 지표와 매수·청산 기준을 다시 알려주시겠어요?"만 남았다(트레이스 4d7e56a49862).
보류 질문이 남는 경우에도 무엇을 보류했는지 옮겨 적는다.
"""
from __future__ import annotations

from strategy_conversation.interpreter import quote_check
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.quote_check import QuoteVerdicts, Verdict
from strategy_conversation.interpreter.required_checks import RequiredChecks
from strategy_conversation.response.output_guard import guard_text

_INPUT = ("코스피·코스닥 AI 관련 기업 중 주가가 200일 이동평균선 위에 있는 종목을 선정해줘. "
          "최근 3개월·6개월 수익률을 기준으로 모멘텀 상위 5개 종목에 동일 비중으로 투자하고, "
          "매월 리밸런싱해줘. 매수가 대비 15% 하락하면 매도하고, 코스피가 200일 이동평균선 "
          "아래로 떨어지면 전량 현금화해줘.")
_QUOTE = "주가가 200일 이동평균선 위에 있는 종목"


def _intent(second_params=None, second_quote=_QUOTE):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": []},
            "entry_conditions": [
                {"factor": "technical.ma_crossover", "operator": ">", "value": None,
                 "parameters": {"short_period": 1, "long_period": 200}, "source_text": _QUOTE},
                {"factor": "technical.ma_crossover", "operator": "crosses_above", "value": None,
                 "parameters": second_params or {"short_period": 1, "long_period": 200},
                 "source_text": second_quote},
            ],
        },
    })


def _verdicts(intent, first="yes", second=("no", "moving_average")):
    a, b = intent.strategy.entry_conditions
    return QuoteVerdicts([(a, Verdict(first, "moving_average")), (b, Verdict(*second))])


def test_operator_duplicate_of_confirmed_copy_is_detected():
    intent = _intent()
    verdicts = _verdicts(intent)
    keep, dup = intent.strategy.entry_conditions
    siblings = intent.strategy.entry_conditions
    assert quote_check.quote_duplicates_confirmed(verdicts, dup, siblings)
    assert not quote_check.quote_duplicates_confirmed(verdicts, keep, siblings)


def test_not_a_duplicate_without_confirmed_copy_or_with_different_parameters():
    # 확인된 사본이 없으면(unclear) 9월 규칙대로 보류한다
    intent = _intent()
    dup = intent.strategy.entry_conditions[1]
    assert not quote_check.quote_duplicates_confirmed(
        _verdicts(intent, first="unclear"), dup, intent.strategy.entry_conditions)
    # 기간이 다르면 다른 조건이다
    intent = _intent(second_params={"short_period": 1, "long_period": 20})
    dup = intent.strategy.entry_conditions[1]
    assert not quote_check.quote_duplicates_confirmed(
        _verdicts(intent), dup, intent.strategy.entry_conditions)
    # 인용이 다르면 다른 조건이다
    intent = _intent(second_quote="200일선을 돌파하면")
    dup = intent.strategy.entry_conditions[1]
    assert not quote_check.quote_duplicates_confirmed(
        _verdicts(intent), dup, intent.strategy.entry_conditions)


def test_duplicate_is_dropped_silently_and_not_held():
    from strategy_conversation import primary

    intent = _intent()
    verdicts = _verdicts(intent)
    checks = RequiredChecks()
    targets = checks.conditions(intent, _INPUT)
    checks.settle(targets, verdicts)
    notices = primary._drop_fabricated_conditions(intent, _INPUT, verdicts)
    assert notices == []
    assert [c.operator for c in intent.strategy.entry_conditions] == [">"]
    assert checks.filter_conditions(intent.strategy) == []
    assert checks.question() is None


def test_held_quote_question_names_the_condition():
    intent = _intent(second_quote="200일선을 돌파하면")
    verdicts = _verdicts(intent)
    checks = RequiredChecks()
    checks.settle(checks.conditions(intent, _INPUT), verdicts)
    held = checks.filter_conditions(intent.strategy)
    question, _suggestions, ask = checks.question(held)
    assert question == ("보류한 매수 조건 — 종가가 200일 이동평균선을 위로 교차하면. 요청 문장과 "
                        "맞는지 확인되지 않아 빼 두었어요. 이 조건도 넣을까요?")
    assert ask["question"] == question
    assert guard_text(question) == question
