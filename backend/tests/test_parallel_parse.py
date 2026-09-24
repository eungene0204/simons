"""병렬 파스(2026-09-17) — 원문만 보는 호출(planner-first·조건 구절 나열)을 인터프리터와 동시에.

계약: ① OpenRouter 레인에서는 세 호출이 실제로 겹친다 ② 병렬과 순차의 결과가 같다
③ 요청 컨텍스트(취소 토큰)가 워커 스레드로 건너간다 ④ Ollama 레인·off 설정은 순차 그대로.
"""
from __future__ import annotations

import threading

import pytest

import cancellation
import llm_backend
from strategy_conversation import primary as primary_mod
from strategy_conversation.interpreter import condition_recall
from strategy_conversation.interpreter.models import StrategyIntent

_INPUT = "코스피에서 PER 10 이하이고 ROE 15% 이상인 종목을 매수하는 전략"
_WAIT_S = 5


def _result_with_per_only():
    """1차 해석이 ROE를 빠뜨린 결과 — 조건 누락 대조 패스가 미리 뽑은 구절로 되살려야 한다."""
    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY",
        "strategy": {
            "universe": {"markets": ["KOSPI"]},
            "entry_conditions": [{"factor": "fundamental.per", "operator": "<=", "value": 10,
                                  "source_text": "PER 10 이하"}],
            "backtest": {"period": "5y"},
        },
        "confidence": 0.9,
    })

    class _Result:
        pass

    _Result.intent = intent
    _Result.model_name = "test"
    _Result.prompt_version = "test"
    _Result.repair_attempts = 0
    _Result.latency_ms = 0.0
    _Result.unreflected_numbers = []
    return _Result()


class _Harness:
    """planner-first·인터프리터·recall chat 스텁. rendezvous=True면 서로를 기다린다(겹침 증명)."""

    def __init__(self, rendezvous: bool):
        self.rendezvous = rendezvous
        self.events = {name: threading.Event() for name in ("planner", "interpreter", "phrases")}
        self.saw_others: dict[str, bool] = {}
        self.order: list[str] = []
        self.planner_token = None
        self.chat_inputs: list[tuple[str, str]] = []

    def _meet(self, me: str, others: tuple[str, ...]) -> None:
        self.order.append(me)
        self.events[me].set()
        if self.rendezvous:
            self.saw_others[me] = all(self.events[o].wait(_WAIT_S) for o in others)

    def plan_first(self, user_input):
        self.planner_token = cancellation.current()
        self._meet("planner", ("interpreter",))
        return None

    def chat(self, system, user, **_kw):
        self.chat_inputs.append((system, user))
        if system == condition_recall.build_system_prompt():
            self._meet("phrases", ("interpreter",))
            return '{"phrases": ["PER 10 이하", "ROE 15% 이상"]}'
        return '{"quote": null, "period": null}'

    def interpreter(self):
        harness = self

        class _Interpreter:
            _chat = staticmethod(harness.chat)

            def interpret(self, *_a, **_k):
                harness._meet("interpreter", ("planner", "phrases"))
                return _result_with_per_only()

        return _Interpreter()


@pytest.fixture
def parse_env(monkeypatch):
    monkeypatch.setenv("STRATEGY_CALL_REDUCTION", "off")
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setenv("STRATEGY_CONDITION_RECALL", "on")

    def install(harness: _Harness, *, openrouter: bool = True):
        monkeypatch.setattr(llm_backend, "is_openrouter", lambda: openrouter)
        monkeypatch.setattr(primary_mod, "_plan_first", harness.plan_first)
        monkeypatch.setattr(primary_mod, "_get_interpreter", lambda _cls: harness.interpreter())

    return install


def test_openrouter_lane_runs_planner_interpreter_and_phrases_concurrently(parse_env):
    harness = _Harness(rendezvous=True)
    parse_env(harness)

    result = primary_mod.run_primary_parse(_INPUT)

    # 순차였다면 planner가 인터프리터를 5초 기다리다 포기한다(False).
    assert harness.saw_others == {"planner": True, "interpreter": True, "phrases": True}
    # 미리 뽑은 구절이 실제로 소비됐다 — 1차가 빠뜨린 ROE가 되살아났다.
    assert "roe" in str(result["parsed"].model_dump()).lower()


def test_parallel_and_sequential_parse_produce_identical_results(parse_env, monkeypatch):
    runs = {}
    for mode in ("on", "off"):
        monkeypatch.setenv("STRATEGY_PARALLEL_PARSE", mode)
        harness = _Harness(rendezvous=False)
        parse_env(harness)
        result = primary_mod.run_primary_parse(_INPUT)
        runs[mode] = (
            result["parsed"].model_dump(),
            result["notices"],
            result["clarification_question"],
            sorted(harness.chat_inputs),
        )
    assert runs["on"] == runs["off"]


def test_worker_thread_inherits_request_cancel_token(parse_env):
    harness = _Harness(rendezvous=False)
    parse_env(harness)
    token = cancellation.CancelToken()

    with cancellation.bind(token):
        primary_mod.run_primary_parse(_INPUT)

    # contextvar를 복사하지 않으면 워커는 None을 본다 — '대화 종료'가 planner 호출을 못 끊는다.
    assert harness.planner_token is token


@pytest.mark.parametrize("openrouter, toggle", [(False, "on"), (True, "off")])
def test_ollama_lane_or_off_toggle_keeps_sequential_order(parse_env, monkeypatch, openrouter, toggle):
    monkeypatch.setenv("STRATEGY_PARALLEL_PARSE", toggle)
    harness = _Harness(rendezvous=False)
    parse_env(harness, openrouter=openrouter)

    primary_mod.run_primary_parse(_INPUT)

    assert harness.order == ["planner", "interpreter", "phrases"]
