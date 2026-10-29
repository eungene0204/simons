"""종목 자체 N일 하락 기준값 해석 회귀 테스트(2026-10-30 속설 #32 녹화, nemotron-3.5-super-vl).

배경: "최근 20일 동안 20% 이상 하락한 KOSPI 종목"은 시장 대비 초과수익률 < -20 + 연속 하락(문장에 없는 조건)으로,
"최근 20일 수익률이 -20% 이하"는 수익률 낮은 순 랭킹(기준값 소실)으로 해석됐다. 엔진에서 정확히 표현하는 자리는
technical.roc(N일 전 대비 변화율 %) <= -X다(사용자 결정). 원인은 어휘에서 roc에 설명이 없고 시장 대비
초과수익률에만 'N거래일 수익률' 설명이 있던 것 — 어휘 설명으로 고친다. 같은 문장의 원출력은 같은 문장의 원출력은 strategy 괄호가
일찍 닫혀 portfolio(hold_period_days=20)가 최상위로 밀려 버려졌다 — 형식 정규화로 되돌린다.
"""

import json

from strategy_conversation.interpreter.models import StrategyIntent


# 실측 원출력(요약): entry_conditions 뒤에서 strategy가 닫히고 나머지 칸이 최상위에 남았다.
_EARLY_CLOSED = {
    "intent": "CREATE_STRATEGY",
    "strategy": {
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "technical.roc", "operator": "<=", "value": -20, "unit": "percent",
                              "parameters": {"period": 20}, "source_text": "최근 20일 동안 20% 이상 하락한"}],
    },
    "exit_conditions": [],
    "entry_logic": "AND",
    "ranking": [],
    "portfolio": {"hold_period_days": 20},
}


def test_strategy_fields_pushed_to_top_level_are_restored():
    intent = StrategyIntent.model_validate(_EARLY_CLOSED)

    assert intent.strategy.portfolio.hold_period_days == 20
    assert intent.strategy.entry_conditions[0].factor == "technical.roc"


def test_top_level_field_does_not_override_strategy_field():
    data = {**_EARLY_CLOSED, "strategy": {**_EARLY_CLOSED["strategy"], "portfolio": {"hold_period_days": 5}}}

    intent = StrategyIntent.model_validate(data)

    assert intent.strategy.portfolio.hold_period_days == 5


def test_vocabulary_separates_own_return_from_market_relative_return():
    """roc에 설명이 없고 relative_return에만 'N거래일 수익률' 설명이 있어 하락 기준값이 시장 대비 칸으로 갔다."""
    from strategy_conversation.interpreter.prompts import build_system_prompt

    lines = build_system_prompt().splitlines()
    roc = next(line for line in lines if line.startswith("- technical.roc "))
    relative = next(line for line in lines if line.startswith("- technical.relative_return "))
    assert "종목 자체의 N거래일 수익률" in roc
    assert "비교 없는 종목 자체 수익률 기준은 technical.roc" in relative


# 수정 턴 실측: "데드크로스 나오면 팔아"의 인용을 "…팔어"로 오기해 패치 전체가 거부됐다.
_TYPO_PATCH = {
    "intent": "MODIFY_STRATEGY", "strategy": None,
    "patches": [{"op": "replace", "path": "/exit_conditions/0",
                 "value": {"factor": "concept.dead_cross", "source_text": "데드크로스 나오면 팔어"},
                 "source_text": "데드크로스 나오면 팔어"}],
}


def test_ungrounded_patch_quote_is_a_format_violation():
    from strategy_conversation.interpreter.output_repair import ungrounded_quote_error, ungrounded_quote_fields

    fields = ungrounded_quote_fields(StrategyIntent.model_validate(_TYPO_PATCH), "데드크로스 나오면 팔아")

    assert [path for path, _ in fields] == ["patches[0].source_text", "patches[0].value.source_text"]
    assert "'데드크로스 나오면 팔어'는 입력 문장에 없는 표기" in ungrounded_quote_error(fields)


def test_grounded_quotes_ignore_spacing():
    from strategy_conversation.interpreter.output_repair import ungrounded_quote_fields

    intent = StrategyIntent.model_validate(_EARLY_CLOSED)

    assert ungrounded_quote_fields(intent, "최근 20일 동안 20%이상 하락한 KOSPI 종목을 매수") == []


def test_ungrounded_quote_triggers_one_regeneration():
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    fixed = json.loads(json.dumps(_TYPO_PATCH, ensure_ascii=False).replace("팔어", "팔아"))
    replies = [json.dumps(_TYPO_PATCH, ensure_ascii=False), json.dumps(fixed, ensure_ascii=False)]
    calls = []

    def chat(system, user, **_kw):
        calls.append(user)
        return replies[len(calls) - 1]

    interpreter = StrategyInterpreter(chat_fn=chat, model="stub")
    result = interpreter.interpret("데드크로스 나오면 팔아", draft={"entry_conditions": [], "exit_conditions": []})

    assert len(calls) == 2 and "입력 문장에 없는 표기" in calls[1]
    assert result.intent.patches[0].source_text == "데드크로스 나오면 팔아"
