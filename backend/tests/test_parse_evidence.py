import json

from strategy_conversation.interpreter import condition_recall, parse_evidence
from strategy_conversation.interpreter.models import StrategyIntent


def test_one_call_recovers_condition_and_period_without_overwriting():
    text = "코스피 PER 10 이하 ROE 15 이상 최근 3년"
    calls = []
    def chat(*args, **kwargs):
        calls.append(args)
        return json.dumps({"conditions": {"phrases": ["PER 10 이하", "ROE 15 이상"]},
                           "backtest": {"quote": "최근 3년", "period": "3y"},
                           "universe": {"terms": ["코스피"]}})
    evidence = parse_evidence.extract_evidence(text, chat)
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {
        "entry_conditions": [{"factor": "fundamental.per", "value": 10,
                              "operator": "<=", "source_text": "PER 10 이하"}]}})
    recovered = condition_recall.recover_missing_conditions(intent, text, chat, evidence.phrases)
    assert recovered == ["fundamental.roe_or_gpa"]
    assert condition_recall.recover_backtest_period(intent, text, evidence.period_chat(chat)) == "3y"
    assert condition_recall.recover_backtest_period(intent, text, evidence.period_chat(chat)) is None
    assert len(calls) == 1
    assert intent.strategy.entry_conditions[-1].value is None


def test_null_period_is_a_valid_result_not_a_second_call():
    def chat(*args, **kwargs):
        return '{"conditions":{"phrases":[]},"backtest":{"quote":null,"period":null}}'
    evidence = parse_evidence.extract_evidence("코스피", chat)
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {}})
    def unexpected(*args, **kwargs):
        raise AssertionError("unexpected second call")
    assert condition_recall.recover_backtest_period(intent, "코스피", evidence.period_chat(unexpected)) is None


def test_invalid_section_falls_back_without_discarding_other_evidence():
    evidence = parse_evidence.extract_evidence("최근 3년", lambda *a, **k:
        '{"conditions":{"phrases":[]},"backtest":{"period":"3y"},"universe":{"terms":["invented"]}}')
    assert evidence.phrases == []
    assert evidence.period is None
    assert evidence.universe_terms is None
    calls = []
    def fallback(*args, **kwargs):
        calls.append(args)
        return '{"period":"3y","quote":"최근 3년"}'
    intent = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": {}})
    assert condition_recall.recover_backtest_period(intent, "최근 3년", evidence.period_chat(fallback)) == "3y"
    assert len(calls) == 1


def test_primary_parse_reduces_four_calls_to_two_with_same_strategy(monkeypatch):
    import llm_backend
    from strategy_conversation import primary
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter
    from strategy_conversation.runtime.planner_gate import settle_plain_markets

    monkeypatch.setattr(llm_backend, "is_openrouter", lambda: False)
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_CONDITION_RECALL", "on")
    text = "코스피에서 PER 10 이하 종목을 매수"
    payload = {"intent": "CREATE_STRATEGY", "strategy": {
        "universe": {"markets": ["KOSPI"]}, "entry_conditions": [
            {"factor": "fundamental.per", "operator": "<=", "value": 10, "source_text": "PER 10 이하"}]}}
    outputs, counts = [], []
    for mode in ("off", "on"):
        monkeypatch.setenv("STRATEGY_CALL_REDUCTION", mode)
        calls = []
        def chat(system, user, **kwargs):
            calls.append(system)
            if system == parse_evidence.build_system_prompt():
                return json.dumps({"conditions": {"phrases": ["PER 10 이하"]},
                                   "backtest": {"quote": None, "period": None},
                                   "universe": {"terms": ["코스피"]}})
            if system == condition_recall.build_system_prompt():
                return '{"phrases":["PER 10 이하"]}'
            if system == condition_recall.build_period_system_prompt():
                return '{"quote":null,"period":null}'
            return json.dumps(payload)
        def plan(user):
            calls.append("planner")
            return settle_plain_markets(StrategyIntent.model_validate(payload),
                                        parse_evidence.ParseEvidence(universe_terms=["코스피"]))
        monkeypatch.setattr(primary, "_plan_first", plan)
        interpreter = StrategyInterpreter(chat_fn=chat, model="stub")
        monkeypatch.setattr(primary, "_get_interpreter", lambda cls: interpreter)
        result = primary.run_primary_parse(text)
        outputs.append((result["parsed"].model_dump(), result["clarification_question"], result["notices"]))
        counts.append(len(calls))
    assert outputs[0] == outputs[1]
    assert counts == [4, 2]


def test_complex_planning_overlaps_interpretation_after_evidence(monkeypatch):
    import threading
    import cancellation
    import llm_backend
    from strategy_conversation import primary
    from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterResult

    planned = threading.Event()
    saw = []
    monkeypatch.setattr(llm_backend, "is_openrouter", lambda: True)
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_CONDITION_RECALL", "on")
    monkeypatch.setenv("STRATEGY_PARALLEL_PARSE", "on")
    monkeypatch.setenv("STRATEGY_CALL_REDUCTION", "on")
    def plan(user):
        saw.append(cancellation.current())
        planned.set()
        return None
    class Interpreter:
        def _chat(self, system, user, **kwargs):
            return '{"conditions":{"phrases":[]},"backtest":{"period":null,"quote":null},"universe":{"terms":["보안주"]}}'
        def interpret(self, *args, **kwargs):
            assert planned.wait(3), "complex planning waited for the main interpreter"
            return InterpreterResult(StrategyIntent.model_validate({"intent":"CREATE_STRATEGY", "strategy":{
                "universe":{"markets":["KOSPI"]}}}), "{}", 0, 0, "stub")
    monkeypatch.setattr(primary, "_get_interpreter", lambda cls: Interpreter())
    monkeypatch.setattr(primary, "_plan_first", plan)
    token = cancellation.CancelToken()
    with cancellation.bind(token):
        assert primary.run_primary_parse("보안주") is not None
    assert saw == [token]
