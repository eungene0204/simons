"""Only quoted structured verdicts may correct role, EMA, and holding meaning."""
import json

import pytest

from strategy_conversation import primary
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.semantic_reconciliation import reconcile_semantic_fields


def _intent(quote, **fields):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "technical.ma_crossover", "operator": "crosses_above",
                              "parameters": {"short_period": 5, "long_period": 20},
                              "source_text": quote, **fields}]}})


def test_kr_numeric_normalization_does_not_reinterpret_quote_words():
    intent = _intent("20일 EMA를 이탈하면 청산", operator="crosses_below")
    condition = intent.strategy.entry_conditions[0]
    primary._fill_deterministic_condition_params(intent, semantic_authority=True)
    assert intent.strategy.entry_conditions == [condition]
    assert intent.strategy.exit_conditions == []
    assert condition.factor == "technical.ma_crossover"


def test_confirmed_ema_and_role_are_applied_in_one_batch():
    quote = "20일 EMA를 이탈하면 청산"
    intent = _intent(quote, operator="crosses_below")
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        return json.dumps({"items": [{"id": "c:0", "quote": quote, "status": "corrected",
            "requested_role": "exit", "factor": "technical.ema", "parameters": {
                "short_period": None, "long_period": {"number_text": "20", "count": 20, "unit": "day"}}}]})
    reconcile_semantic_fields(intent, quote, chat)
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions[0].factor == "technical.ema"
    assert intent.strategy.exit_conditions[0].parameters == {"short_period": None, "long_period": 20}
    assert len(calls) == 1


def _ema_exit_intent(quote, *, role="exit"):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        role + "_conditions": [{"factor": "technical.ema", "operator": "crosses_below",
                                "parameters": {"short_period": 5, "long_period": 20},
                                "source_text": quote}]}})


def _flip_reply(quote, role):
    return json.dumps({"items": [{"id": "c:0", "quote": quote, "status": "corrected",
        "requested_role": role, "factor": "technical.ma_crossover", "parameters": {
            "short_period": {"number_text": "5", "count": 5, "unit": "day"},
            "long_period": {"number_text": "20", "count": 20, "unit": "day"}}}]})


def test_reconciliation_cannot_turn_an_ema_condition_into_ma_crossover():
    """2026-10-23 사고(속설 #22): 메인 인터프리터가 매도를 technical.ema(5/20, crosses_below)로 맞게 냈는데
    보정 LLM이 같은 문장에서 8턴 중 6턴 technical.ma_crossover로 '교정'해 EMA 매도가 SMA로 바뀌었다
    (결과 -40.53% ↔ -5.21%). 1차 출력이 EMA면 보정이 ma_crossover로 되돌리지 못한다."""
    quote = "5일 EMA가 20일 EMA 아래로 내려오면 매도"
    intent = _ema_exit_intent(quote)
    reconcile_semantic_fields(intent, quote, lambda *a, **k: _flip_reply(quote, "exit"))
    condition = intent.strategy.exit_conditions[0]
    assert condition.factor == "technical.ema"
    assert condition.operator == "crosses_below"
    assert condition.parameters == {"short_period": 5, "long_period": 20}


def test_ema_guard_keeps_role_correction_from_the_same_reply():
    quote = "5일 EMA가 20일 EMA 아래로 내려오면 매도"
    intent = _ema_exit_intent(quote, role="entry")
    reconcile_semantic_fields(intent, quote, lambda *a, **k: _flip_reply(quote, "exit"))
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions[0].factor == "technical.ema"


def test_prompt_example_condition_correction_shape_is_the_parsed_shape():
    """2026-10-21 사고: 예시에 조건 보정 모양이 없어 LLM이 role+중첩 condition으로 답했고,
    파서가 읽는 requested_role·factor·parameters가 없어 매도 칸 이동이 무산 → 청산 조건 보류·소실.
    프롬프트 예시의 조건 보정 항목이 그대로 파서에 받아들여져야 한다."""
    from strategy_conversation.interpreter.semantic_reconciliation import _SYSTEM

    example = json.loads(_SYSTEM.split("JSON만: ", 1)[1])
    item = next(i for i in example["items"] if i["id"].startswith("c:") and i["status"] == "corrected")
    quote = "60일선 아래로 내려가면 매도"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "technical.ma_crossover", "operator": "crosses_below",
                              "parameters": {"short_period": 1, "long_period": 60},
                              "source_text": quote}]}})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps(
        {"items": [{**item, "id": "c:0", "quote": quote}]}))
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions[0].factor == "technical.ma_crossover"
    assert intent.strategy.exit_conditions[0].parameters == {"short_period": 1, "long_period": 60}


def test_number_text_with_unit_suffix_is_read_as_its_count():
    """트레이스 05527d9d7abb(2026-10-21) 원응답: number_text="60일" — 단위가 붙은 옮겨 적기를
    float 실패로 버려 청산 조건이 보류됐다. 앞쪽 숫자 표기가 count와 같으면 받아들인다."""
    quote = "60일선 아래로 내려가면 매도"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [
            {"factor": "technical.ma_crossover", "operator": ">", "parameters": {
                "short_period": 1, "long_period": 60}, "source_text": "종가가 60일선 위 유지되는 동안 보유하고"},
            {"factor": "technical.ma_crossover", "operator": "crosses_below", "parameters": {
                "short_period": 1, "long_period": 60}, "source_text": quote}]}})
    utterance = "코스닥에서 종가가 60일선 위 유지되는 동안 보유하고, 60일선 아래로 내려가면 매도해 주세요. 최근 3년"
    reply = {"items": [
        {"id": "c:0", "quote": "종가가 60일선 위 유지되는 동안 보유하고", "status": "unchanged"},
        {"id": "c:1", "quote": quote, "status": "corrected", "requested_role": "exit",
         "factor": "technical.ma_crossover", "parameters": {"short_period": None, "long_period": {
             "number_text": "60일", "count": 60, "unit": "day"}}}]}
    reconcile_semantic_fields(intent, utterance, lambda *a, **k: json.dumps(reply, ensure_ascii=False))
    assert [c.operator for c in intent.strategy.entry_conditions] == [">"]
    assert intent.strategy.exit_conditions[0].operator == "crosses_below"
    assert intent.strategy.exit_conditions[0].parameters == {"short_period": 1, "long_period": 60}


def test_number_text_digits_must_still_match_count():
    quote = "60일선 아래로 내려가면 매도"
    intent = _intent(quote, operator="crosses_below")
    before = intent.model_dump()
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "c:0", "quote": quote, "status": "corrected", "requested_role": "exit",
        "parameters": {"long_period": {"number_text": "60일", "count": 20, "unit": "day"}}}]}))
    assert intent.model_dump() == before


@pytest.mark.parametrize("reply", ["bad json", '{"items":[]}', '{"items":[{"id":"wrong"}]}'])
def test_missing_verdict_never_invokes_lexical_ema_or_role_fallback(reply):
    quote = "20일 EMA를 이탈하면 청산"
    intent = _intent(quote, operator="crosses_below")
    before = intent.model_dump()
    reconcile_semantic_fields(intent, quote, lambda *a, **k: reply)
    primary._fill_deterministic_condition_params(intent, semantic_authority=True)
    assert intent.model_dump() == before


def test_unquoted_period_is_not_written_into_the_condition():
    quote = "20일 이동평균선 위면 매수"
    intent = _intent(quote)
    before = intent.model_dump()
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "c:0", "quote": quote, "status": "corrected", "parameters": {
            "long_period": {"number_text": "60", "count": 60, "unit": "day"}}}]}))
    assert intent.model_dump() == before


def test_unsupported_holding_label_requires_llm_kind_and_quantity():
    quote = "한 달 보유"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {},
                                          "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "max_hold",
        "number_text": "한", "count": 1, "unit": "month"}]}))
    assert intent.strategy.portfolio.hold_period_days == 21
    assert intent.unsupported_features == []


def test_existing_holding_value_is_not_overwritten_by_reported_label():
    quote = "한 달 보유"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "portfolio": {"hold_period_days": 10}}, "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "max_hold",
        "number_text": "한", "count": 1, "unit": "month"}]}))
    assert intent.strategy.portfolio.hold_period_days == 10
    assert intent.unsupported_features == [quote]


def test_risk_report_is_reconciled_only_with_a_quoted_percent_verdict():
    quote = "손절 -7%"
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {},
                                          "unsupported_features": [quote]})
    reconcile_semantic_fields(intent, quote, lambda *a, **k: json.dumps({"items": [{
        "id": "f:0", "quote": quote, "status": "corrected", "kind": "stop_loss",
        "number_text": "-7", "count": 7, "unit": "percent"}]}))
    assert intent.strategy.risk_management.stop_loss == 7
    assert intent.unsupported_features == []


def _crossover_intent(quote):
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "technical.ma_crossover", "operator": ">",
                              "parameters": {"short_period": 1, "long_period": 20},
                              "source_text": quote}]}})


def _period_correction(quote):
    return {"id": "c:0", "quote": quote, "status": "corrected", "requested_role": "entry",
            "factor": "technical.ma_crossover",
            "parameters": {"short_period": {"number_text": "5일", "count": 5, "unit": "day"},
                           "long_period": {"number_text": "20일", "count": 20, "unit": "day"}}}


def test_correction_survives_truncation_after_invented_ids():
    """2026-11-10: 맞는 교정 뒤에 없는 id를 지어내다 토큰 한도에 잘려 교정 전체가 버려졌다(예시 13)."""
    quote = "5일선이 20일선 위에 있는"
    intent = _crossover_intent(quote)
    head = json.dumps({"items": [_period_correction(quote)]}, ensure_ascii=False)[:-2]
    truncated = head + ', {"id": "f:0", "quote": "최대 보유 종목은 8개", "status": "corr'
    reconcile_semantic_fields(intent, quote, lambda *a, **k: truncated)
    assert intent.strategy.entry_conditions[0].parameters["short_period"] == 5


def test_invented_ids_in_a_complete_reply_are_ignored():
    quote = "5일선이 20일선 위에 있는"
    intent = _crossover_intent(quote)
    reply = json.dumps({"items": [_period_correction(quote),
                                  {"id": "f:9", "quote": "없는 항목", "status": "corrected", "kind": "restated"}]},
                       ensure_ascii=False)
    reconcile_semantic_fields(intent, quote, lambda *a, **k: reply)
    assert intent.strategy.entry_conditions[0].parameters["short_period"] == 5


def test_truncated_reply_missing_a_subject_changes_nothing():
    quote = "5일선이 20일선 위에 있는"
    intent = _crossover_intent(quote)
    reconcile_semantic_fields(intent, quote, lambda *a, **k: '{"items": [{"id": "c:0", "quo')
    assert intent.strategy.entry_conditions[0].parameters["short_period"] == 1


def _feature_intent(feature, quote):
    intent = _crossover_intent(quote)
    intent.unsupported_features = [feature]
    return intent


def test_restated_summary_is_removed_from_unsupported_report():
    """2026-11-10: 뒤에서 구체 조건으로 풀어 쓴 '재무가 튼튼한 종목'에 거짓 미지원 안내가 나갔다(예시 19)."""
    quote, feature = "5일선이 20일선 위에 있는", "재무가 튼튼한 종목"
    intent = _feature_intent(feature, quote)
    seen = []

    def chat(system, user, **_):
        seen.append(json.loads(user))
        return json.dumps({"items": [{"id": "c:0", "quote": quote, "status": "unchanged"},
                                     {"id": "f:0", "quote": feature, "status": "corrected", "kind": "restated"}]},
                          ensure_ascii=False)

    reconcile_semantic_fields(intent, f"{feature} 중 {quote} 종목", chat)
    assert intent.unsupported_features == []
    assert seen[0]["reflected_conditions"] == [quote]


def test_unsupported_feature_stays_unless_judged_restated():
    quote, feature = "5일선이 20일선 위에 있는", "뉴스가 좋은 종목"
    intent = _feature_intent(feature, quote)
    reply = json.dumps({"items": [{"id": "c:0", "quote": quote, "status": "unchanged"},
                                  {"id": "f:0", "quote": feature, "status": "unchanged"}]}, ensure_ascii=False)
    reconcile_semantic_fields(intent, f"{feature} 중 {quote} 종목", lambda *a, **k: reply)
    assert intent.unsupported_features == [feature]


def _rsi_both_in_entry():
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {"entry_conditions": [
        {"factor": "technical.rsi", "operator": "crosses_above", "value": 30, "source_text": "RSI가 30 이하로 떨어졌다가 반등"},
        {"factor": "technical.rsi", "operator": ">=", "value": 70, "source_text": "RSI가 70 이상이면 매도"},
    ]}})


def test_sell_condition_left_in_entry_is_moved_by_role_verdict():
    """2026-11-10: 재생성본이 매도 칸 사본을 지워 매도 조건이 사라졌다(예시 46)."""
    intent = _rsi_both_in_entry()
    utterance = "RSI가 30 이하로 떨어졌다가 반등하면 매수, RSI가 70 이상이면 매도"
    reply = json.dumps({"items": [
        {"id": "c:0", "quote": "RSI가 30 이하로 떨어졌다가 반등", "status": "unchanged"},
        {"id": "c:1", "quote": "RSI가 70 이상이면 매도", "status": "corrected", "requested_role": "exit",
         "parameters": {"short_period": {"number_text": "70", "count": 70, "unit": "day"}}},
    ]}, ensure_ascii=False)
    reconcile_semantic_fields(intent, utterance, lambda *a, **k: reply)
    assert [(c.operator, c.value) for c in intent.strategy.entry_conditions] == [("crosses_above", 30)]
    moved = intent.strategy.exit_conditions[0]
    assert (moved.operator, moved.value) == (">=", 70)
    assert "short_period" not in moved.parameters


def test_same_factor_entries_stay_without_role_verdict():
    intent = _rsi_both_in_entry()
    utterance = "RSI가 30 이하로 떨어졌다가 반등하고 RSI가 70 이상이면 매도"
    calls = []

    def chat(*a, **k):
        calls.append(1)
        raise RuntimeError("lane down")

    reconcile_semantic_fields(intent, utterance, chat)
    assert len(intent.strategy.entry_conditions) == 2 and intent.strategy.exit_conditions == []
    assert calls == [1]
