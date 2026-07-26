"""DAG Planner(Phase 4) 계약 — Action DAG 발행·검증·실행의 결정론 안전 장치.

핵심: DAG 구조 검증(비순환·id 고유·화이트리스트·예산·done 불변·finish 사슬),
동일 호출 1회 실행(관찰 재사용), ask 표면화는 무관찰 턴에만+출력 관문 통과,
확정값은 도구 관찰값에서만 채택. 실패는 전부 None(고정 파이프라인 폴백 신호).
"""

import json

import pytest

import engine.knowledge_graph as kg
import engine.term_grounding as tg
from strategy_conversation.planner.dag import (
    DagContractError,
    parse_dag,
    validate_dag,
)
from strategy_conversation.planner.dag_planner import plan_strategy_dag
from strategy_conversation.planner.dag_shadow import maybe_shadow_plan_dag

_ALLOWED = (
    "kg_resolve_sector", "kg_theme_companies", "ground_term", "resolve_universe",
    "lookup_capabilities", "validate_intent", "compile_strategy",
)


class ScriptedChat:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, system_prompt, user_message, **kwargs):
        # 공유 chat 계약 (system, user, *, max_tokens) — planner가 max_tokens를 넘긴다
        self.calls += 1
        return self.responses.pop(0) if self.responses else ""


def _tool_node(node_id, tool, text="2차전지", deps=()):
    node = {"id": node_id, "type": "tool", "tool": tool, "depends_on": list(deps)}
    if tool not in ("validate_intent", "compile_strategy", "lookup_capabilities"):
        node["args"] = {"text": text}
    return node


def _ask_node(node_id, question, deps=(), chips=(), topic="조건"):
    return {"id": node_id, "type": "ask", "topic": topic, "question": question,
            "chips": list(chips), "depends_on": list(deps)}


def _finish_chain(deps):
    """validate→compile→finish 꼬리(계약이 강제하는 확정 사슬)."""
    return [
        _tool_node("validate", "validate_intent", deps=deps),
        _tool_node("compile", "compile_strategy", deps=["validate"]),
        {"id": "done", "type": "finish", "depends_on": ["compile"]},
    ]


def _dag_json(*nodes):
    return json.dumps({"dag": {"nodes": list(nodes)}}, ensure_ascii=False)


def _validate(nodes, **kwargs):
    kwargs.setdefault("allowed_tools", _ALLOWED)
    kwargs.setdefault("node_budget", 24)
    validate_dag(nodes, **kwargs)


# ── DAG 구조 검증(dag.py — 전부 결정론) ──────────────────────────────────────

def test_cycle_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        _tool_node("a", "kg_resolve_sector", deps=["b"]),
        _tool_node("b", "kg_theme_companies", deps=["a"]),
    ]}})
    with pytest.raises(DagContractError, match="순환"):
        _validate(nodes)


def test_unknown_dependency_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        _tool_node("a", "kg_resolve_sector", deps=["ghost"]),
    ]}})
    with pytest.raises(DagContractError, match="존재하지 않는 의존"):
        _validate(nodes)


def test_duplicate_id_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        _tool_node("a", "kg_resolve_sector"),
        _tool_node("a", "kg_theme_companies"),
    ]}})
    with pytest.raises(DagContractError, match="id 중복"):
        _validate(nodes)


def test_non_whitelisted_tool_rejected():
    nodes = parse_dag({"dag": {"nodes": [_tool_node("a", "run_backtest")]}})
    with pytest.raises(DagContractError, match="화이트리스트"):
        _validate(nodes)


def test_node_budget_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        _tool_node(f"n{i}", "kg_resolve_sector", text=f"표현{i}") for i in range(5)
    ]}})
    with pytest.raises(DagContractError, match="예산"):
        _validate(nodes, node_budget=4)


def test_ask_without_question_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        {"id": "q", "type": "ask", "topic": "청산", "depends_on": []},
    ]}})
    with pytest.raises(DagContractError, match="질문 없음"):
        _validate(nodes)


def test_duplicate_tool_call_rejected():
    nodes = parse_dag({"dag": {"nodes": [
        _tool_node("a", "kg_resolve_sector"),
        _tool_node("b", "kg_resolve_sector"),  # 동일 도구+동일 인자
    ]}})
    with pytest.raises(DagContractError, match="중복"):
        _validate(nodes)


def test_finish_requires_compile_and_validate_chain():
    bare_finish = parse_dag({"dag": {"nodes": [
        {"id": "done", "type": "finish", "depends_on": []},
    ]}})
    with pytest.raises(DagContractError, match="compile_strategy에 의존하지 않음"):
        _validate(bare_finish)

    compile_only = parse_dag({"dag": {"nodes": [
        _tool_node("compile", "compile_strategy"),
        {"id": "done", "type": "finish", "depends_on": ["compile"]},
    ]}})
    with pytest.raises(DagContractError, match="validate_intent에 의존하지 않음"):
        _validate(compile_only)

    _validate(parse_dag({"dag": {"nodes": _finish_chain(deps=[])}}))  # 정상 사슬


def test_done_immutability():
    original = parse_dag({"dag": {"nodes": [_tool_node("a", "kg_resolve_sector")]}})
    snapshot = {"a": original[0].immutable_snapshot()}

    changed = parse_dag({"dag": {"nodes": [
        _tool_node("a", "kg_resolve_sector", text="다른표현"),
    ]}})
    with pytest.raises(DagContractError, match="done 노드 변경"):
        _validate(changed, done_snapshots=snapshot)

    # 누락은 위반이 아니다 — done은 러너 보유 이력이라 재발행 생략 허용(러너가 병합)
    _validate(parse_dag({"dag": {"nodes": [_tool_node("b", "kg_theme_companies")]}}),
              done_snapshots=snapshot)

    # 의존 재배선은 허용(내용 불변) — 새 노드 추가와 함께 deps만 바뀐 재발행
    rewired = parse_dag({"dag": {"nodes": [
        _tool_node("seed", "kg_theme_companies"),
        _tool_node("a", "kg_resolve_sector", deps=["seed"]),
    ]}})
    _validate(rewired, done_snapshots=snapshot)


# ── Planner 루프(dag_planner.py) ─────────────────────────────────────────────

def _resolution_dag(question="모멘텀을 어떤 기간 수익률로 계산할까요?"):
    """해석 tool 2종 → ask → validate/compile/finish 사슬의 표준 DAG."""
    return _dag_json(
        _tool_node("t1", "kg_resolve_sector"),
        _tool_node("t2", "kg_theme_companies"),
        _ask_node("ask1", question, deps=["t1", "t2"],
                  chips=["1개월", "3개월", "6개월"]),
        *_finish_chain(deps=["ask1"]),
    )


def test_ask_surfaced_after_observation_turn(monkeypatch):
    """턴1: 도구 실행(관찰) → 턴2: 무관찰 재발행 → ask 표면화. 도구는 1회만 실행,
    sector는 LLM 주장이 아니라 도구 관찰값에서 채택된다."""
    calls = {"kg": 0}

    def fake_resolve(text):
        calls["kg"] += 1
        return "화학"

    monkeypatch.setattr(kg, "resolve_sector_from_text", fake_resolve)
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    chat = ScriptedChat([_resolution_dag(), _resolution_dag()])

    result = plan_strategy_dag("2차전지 관련주로 모멘텀 전략", chat)
    assert result is not None and result.outcome == "ask"
    assert result.question == "모멘텀을 어떤 기간 수익률로 계산할까요?"
    assert result.chips == ["1개월", "3개월", "6개월"]
    assert result.sector == "화학"
    assert chat.calls == 2
    assert calls["kg"] == 1  # 재발행 시 관찰 재사용 — 재실행 없음


def test_ground_term_epilogue_requeries_theme(monkeypatch):
    """ground_term 학습 성공 후 테마 재조회는 LLM 턴 없는 결정론 에필로그다."""
    monkeypatch.setattr(tg, "resolve_sector", lambda text, chat, **kw: "반도체")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "미지테마", "companies": [{"symbol": "005930", "name": "삼성전자"}],
        "first_known_date": None,
    })
    dag = _dag_json(
        _tool_node("g", "ground_term", text="미지테마"),
        _ask_node("ask1", "손절 기준을 정할까요?", deps=["g"]),
        *_finish_chain(deps=["ask1"]),
    )
    chat = ScriptedChat([dag, dag])
    result = plan_strategy_dag("미지테마 전략 만들어줘", chat)
    assert result is not None and result.outcome == "ask"
    assert result.sector == "반도체"
    assert result.companies[0]["symbol"] == "005930"
    assert len(result.auto_steps) == 1
    assert result.auto_steps[0]["tool"] == "kg_theme_companies"
    assert chat.calls == 2


def test_omitted_done_nodes_merged_from_runner_copy(monkeypatch):
    """9B가 턴2에서 done 노드 재발행을 생략해도 러너 보유 사본이 병합되어 ask가
    표면화된다 — 생략을 위반으로 보면 planner가 전량 폴백되던 실측 문제의 계약."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    turn2_asks_only = _dag_json(
        _ask_node("ask1", "모멘텀을 어떤 기간 수익률로 계산할까요?",
                  deps=["t1", "t2"], chips=["1개월", "3개월"]),
        *_finish_chain(deps=["ask1"]),
    )
    chat = ScriptedChat([_resolution_dag(), turn2_asks_only])
    result = plan_strategy_dag("2차전지 관련주로 모멘텀 전략", chat)
    assert result is not None and result.outcome == "ask"
    assert result.question == "모멘텀을 어떤 기간 수익률로 계산할까요?"
    assert result.sector == "화학"  # 생략된 done 노드의 관찰이 유지된다
    assert chat.calls == 2


def test_forbidden_question_guard_falls_back(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    dag = _resolution_dag(question="이 전략 사용을 권장합니다.")
    assert plan_strategy_dag("2차전지 전략", ScriptedChat([dag, dag])) is None


def test_invalid_json_falls_back():
    assert plan_strategy_dag("전략 만들어줘", ScriptedChat(["글쎄요"])) is None


def test_truncated_trailing_brace_repaired(monkeypatch):
    """마지막 닫는 중괄호가 빠진 출력은 결정론 괄호 보정으로 복구한다(9B 실측 결함).
    짝이 어긋난 출력은 보정하지 않는다."""
    from strategy_conversation.planner.dag_planner import _extract_json

    truncated = _resolution_dag()[:-1]  # 최상위 '}' 하나 절단
    data = _extract_json(truncated)
    assert data is not None and "dag" in data
    assert _extract_json('{"dag": {"nodes": [}') is None  # 교차 닫힘은 보정 불가


def test_contract_violation_falls_back():
    dag = _dag_json(_tool_node("a", "run_backtest"))
    assert plan_strategy_dag("전략 만들어줘", ScriptedChat([dag])) is None


def test_done_mutation_falls_back(monkeypatch):
    """턴2 재발행에서 done 노드의 args를 바꾸면 계약 위반 폴백이다."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    turn1 = _resolution_dag()
    turn2 = _dag_json(
        _tool_node("t1", "kg_resolve_sector", text="바뀐표현"),
        _tool_node("t2", "kg_theme_companies"),
        _ask_node("ask1", "질문?", deps=["t1", "t2"]),
        *_finish_chain(deps=["ask1"]),
    )
    assert plan_strategy_dag("2차전지 전략", ScriptedChat([turn1, turn2])) is None


def test_stalled_identical_emission_falls_back():
    """실행 가능 도구도 ready ask도 없는 동일 발행 반복은 무진전 폴백이다
    (validate/compile은 이 단계에서 실행하지 않는 이연 도구)."""
    dag = _dag_json(*_finish_chain(deps=[]))
    chat = ScriptedChat([dag, dag])
    assert plan_strategy_dag("전략 만들어줘", chat) is None
    assert chat.calls == 2


def test_turn_budget_exhausted(monkeypatch):
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    chat = ScriptedChat([_resolution_dag()])
    assert plan_strategy_dag("2차전지 전략", chat, max_turns=1) is None


def test_blank_input_falls_back():
    assert plan_strategy_dag("  ", ScriptedChat([])) is None


# ── Primary 모드(Phase 4 승격 — 되묻기 질문·칩을 planner가 담당) ───────────────

def test_config_accepts_dag_primary_mode(monkeypatch):
    from strategy_conversation import config

    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    assert config.dag_planner_mode() == "primary"
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "이상한값")
    assert config.dag_planner_mode() == "off"


def test_state_summary_rendered_to_llm(monkeypatch):
    """이미 결정된 전략 State가 LLM 상태 제시에 포함된다 — 재질문 방지 근거."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    seen_messages = []

    def capturing_chat(system_prompt, user_message, **kwargs):
        seen_messages.append(user_message)
        return _resolution_dag()

    result = plan_strategy_dag(
        "반도체 etf 투자 전략", capturing_chat,
        state_summary={"universe": ["ETF"], "etf_theme": "반도체"},
    )
    assert result is not None and result.outcome == "ask"
    assert all("이미 결정된 전략 State" in m for m in seen_messages)
    assert all("반도체" in m for m in seen_messages)


def test_primary_clarification_helper_contract(monkeypatch):
    """_dag_planner_clarification — ask면 (질문, 칩), 그 외(None·finish·예외)는 None."""
    import strategy_conversation.planner.dag_planner as dag_mod
    import strategy_conversation.planner.shadow as shadow_mod
    from strategy_conversation.planner.dag_planner import DagPlanResult
    from strategy_conversation.primary import _dag_planner_clarification

    monkeypatch.setattr(shadow_mod, "_default_chat", lambda: (lambda *a, **k: ""))

    def _plan_returns(result):
        monkeypatch.setattr(dag_mod, "plan_strategy_dag", lambda *a, **kw: result)

    ask = DagPlanResult("ask", "리밸런싱 주기는 어떻게 할까요?", ["매월", "분기마다"],
                        None, [], [])
    _plan_returns(ask)
    assert _dag_planner_clarification("반도체 etf 전략", object()) == (
        "리밸런싱 주기는 어떻게 할까요?", ["매월", "분기마다"])

    _plan_returns(None)
    assert _dag_planner_clarification("반도체 etf 전략", object()) is None

    _plan_returns(DagPlanResult("finish", None, [], None, [], []))
    assert _dag_planner_clarification("반도체 etf 전략", object()) is None

    def _raises(*a, **kw):
        raise RuntimeError("planner 장애")

    monkeypatch.setattr(dag_mod, "plan_strategy_dag", _raises)
    assert _dag_planner_clarification("반도체 etf 전략", object()) is None


def test_dag_state_summary_from_parsed():
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import _dag_state_summary

    parsed = ParsedStrategy(
        description="요약 테스트", universe=["ETF"], etf_theme="반도체",
        entry_signals=[{"indicator": "ma_crossover", "signal_type": "buy",
                        "short_period": 5, "long_period": 20}],
    )
    summary = _dag_state_summary(parsed)
    assert summary["universe"] == ["ETF"]
    assert summary["etf_theme"] == "반도체"
    assert summary["entry_signal_types"] == ["ma_crossover"]
    assert "exit_signal_types" not in summary  # 빈 필드는 요약에 넣지 않는다
    assert "유니버스" in summary["filled_slots"] and "매수 조건" in summary["filled_slots"]
    assert "매도 조건" not in summary["filled_slots"]


def test_dag_state_summary_ranking_fills_entry_slot():
    """랭킹(ranking_metric)은 매수 조건 슬롯 충족이다 — 결정론 filled_slots가 정본.
    9B 추론에 맡기면 '최근 3개월 수익률 상위 매수' 후 매수 조건을 재질문한다(사고 회귀)."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import _dag_state_summary

    parsed = ParsedStrategy(
        description="랭킹 요약", universe=["ETF"], etf_theme="반도체",
        ranking_metric="return", ranking_lookback_days=90,
    )
    summary = _dag_state_summary(parsed)
    assert summary["ranking_metric"] == "return"
    assert "매수 조건" in summary["filled_slots"]


# ── Shadow 모드 ───────────────────────────────────────────────────────────────

def test_dag_shadow_off_is_noop(monkeypatch):
    monkeypatch.delenv("STRATEGY_DAG_PLANNER_MODE", raising=False)
    assert maybe_shadow_plan_dag("2차전지 전략 만들어줘") is None


def test_dag_shadow_runs_and_logs(monkeypatch, tmp_path):
    log_path = tmp_path / "dag_planner_shadow.jsonl"
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "shadow")
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_SHADOW_LOG", str(log_path))
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    chat = ScriptedChat([_resolution_dag(), _resolution_dag()])

    thread = maybe_shadow_plan_dag("2차전지 관련주로 모멘텀 전략", chat_fn=chat)
    assert thread is not None
    thread.join(timeout=10)

    record = json.loads(log_path.read_text().strip())
    assert record["outcome"] == "ask"
    assert record["sector"] == "화학"
    assert record["node_count"] == 6
    assert record["llm_turns"] == 2
    assert record["error"] is None
    assert "latency_ms" in record
