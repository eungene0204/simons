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


def test_single_concept_candidate_triggers_theme_requery_epilogue(monkeypatch):
    """후보 1개는 범위가 갈리지 않는다 — 그 정본 표기의 테마 조회는 판단이 아니라
    절차라 LLM 턴 없이 결정론 에필로그로 실행된다(2026-08-02 감사 #3 #4: 9B가 관찰된
    카탈로그 후보 60곳을 두고 매수 질문으로 건너뛰어 시드 앵커 2곳이 적용됐다)."""
    monkeypatch.setattr(kg, "catalog_theme_candidates",
                        lambda text: [{"term": "전력저장장치(ESS)", "companies": 2}])
    queried = []

    def fake_theme(text):
        queried.append(text)
        return {"term": text,
                "companies": [{"symbol": "006400", "name": "삼성SDI"},
                              {"symbol": "373220", "name": "LG에너지솔루션"}],
                "first_known_date": None}

    monkeypatch.setattr(kg, "theme_backtest_companies", fake_theme)
    dag = _dag_json(
        _tool_node("cand", "list_concept_candidates", text="ESS"),
        _ask_node("ask1", "어떤 조건에서 매수할까요?", deps=["cand"]),
        *_finish_chain(deps=["ask1"]),
    )
    chat = ScriptedChat([dag, dag])
    result = plan_strategy_dag("ESS 관련주로 전략 만들어줘", chat)
    assert result is not None and result.outcome == "ask"
    assert queried == ["전력저장장치(ESS)"], "후보 정본 표기로 결정론 재조회해야 한다"
    assert len(result.auto_steps) == 1
    assert result.companies and result.companies[0]["symbol"] == "006400"


def test_multiple_concept_candidates_do_not_auto_requery(monkeypatch):
    """후보 2개 이상은 범위 질문 대상이다 — 자동 조회(조용한 확정)는 금지."""
    monkeypatch.setattr(kg, "catalog_theme_candidates",
                        lambda text: [{"term": "보안(물리)", "companies": 10},
                                      {"term": "보안(정보)", "companies": 12}])
    queried = []
    monkeypatch.setattr(kg, "theme_backtest_companies",
                        lambda text: queried.append(text) or None)
    dag = _dag_json(
        _tool_node("cand", "list_concept_candidates", text="보안"),
        _ask_node("ask1", "어느 범위로 할까요?", deps=["cand"], topic="유니버스"),
        *_finish_chain(deps=["ask1"]),
    )
    result = plan_strategy_dag("보안주 전략", ScriptedChat([dag, dag]))
    assert result is not None and result.outcome == "ask"
    assert queried == []
    assert result.auto_steps == []


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


def test_progress_extends_turn_budget(monkeypatch):
    """진전(새 관찰)이 있으면 예산을 hard_cap(turns+2)까지 연장한다(2026-08-02 감사 #3 #4).

    CONCEPT 유니버스는 classify → candidates → ask로 LLM 3턴이 필요한데 예산 2에서
    항상 소진돼, 관찰된 카탈로그 테마(60곳)가 버려지고 폴백 레인이 시드 앵커(2곳)를
    적용하는 조용한 범위 축소가 났다. max_turns=1이어도 턴1이 도구를 실행했으면
    턴2에서 ask가 표면화된다."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    chat = ScriptedChat([_resolution_dag(), _resolution_dag()])
    result = plan_strategy_dag("2차전지 전략", chat, max_turns=1)
    assert result is not None and result.outcome == "ask"
    assert chat.calls == 2


def test_turn_budget_exhausted(monkeypatch):
    """연장은 무한이 아니다 — 매 턴 새 도구로 진전해도 hard_cap(turns+2)에서 멈춘다."""
    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "화학")
    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)

    def _growing_dag(n):
        nodes = [_tool_node(f"t{i}", "kg_resolve_sector", text=f"표현{i}")
                 for i in range(1, n + 1)]
        return _dag_json(*nodes)

    # 턴마다 새 도구 노드를 하나씩 늘려 계속 진전시킨다 — ask 없이 hard_cap 도달
    chat = ScriptedChat([_growing_dag(1), _growing_dag(2), _growing_dag(3), _growing_dag(4)])
    assert plan_strategy_dag("2차전지 전략", chat, max_turns=1) is None
    assert chat.calls == 3  # turns=1 + 연장 2 = hard_cap 3


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


def test_filled_slot_ask_skipped_surfaces_next_empty_slot():
    """filled_slots에 있는 슬롯의 ask는 결정론 가드가 건너뛰고 다음 빈 슬롯 ask를
    표면화한다 — 프롬프트 지시를 어기고 풀 골격(ask_entry부터)을 재발행하는 9B
    드리프트로 매수 조건을 재질문하던 2026-07-29 사고의 회귀. topic 표기의 공백
    차이(매수조건 ↔ 매수 조건)는 정규화로 흡수한다."""
    dag = _dag_json(
        _ask_node("ask_entry", "어떤 조건에서 매수할까요?",
                  chips=["부채비율 200% 이하, ROE 5% 이상", "PER 15 배 이하"],
                  topic="매수조건"),
        _ask_node("ask_exit", "어떤 조건에서 매도할까요?", deps=["ask_entry"],
                  topic="매도조건"),
        _ask_node("ask_positions", "최대 몇 종목을 보유할까요?", deps=["ask_exit"],
                  chips=["최대 5종목", "최대 10종목"], topic="최대보유"),
        *_finish_chain(deps=["ask_positions"]),
    )
    result = plan_strategy_dag(
        "부채비율 200% 이하, ROE 5% 이상", ScriptedChat([dag]),
        state_summary={"filled_slots": ["유니버스", "매수 조건", "매도 조건", "리스크 관리"]},
    )
    assert result is not None and result.outcome == "ask"
    assert result.topic == "최대보유"
    assert result.question == "최대 몇 종목을 보유할까요?"
    assert result.chips == ["최대 5종목", "최대 10종목"]


def test_all_asks_filled_falls_back_without_reask():
    """발행된 ask가 전부 채워진 슬롯이면 어떤 재질문도 표면화하지 않는다 —
    무진전 폴백(None)으로 강등되고 레인의 기존 질문 유지 계약이 이어받는다."""
    dag = _dag_json(
        _ask_node("ask_entry", "어떤 조건에서 매수할까요?", topic="매수 조건"),
        _ask_node("ask_exit", "어떤 조건에서 매도할까요?", deps=["ask_entry"],
                  topic="매도조건"),
        *_finish_chain(deps=["ask_exit"]),
    )
    chat = ScriptedChat([dag, dag])
    result = plan_strategy_dag(
        "손절 10%로 바꿔줘", chat,
        state_summary={"filled_slots": ["매수 조건", "매도 조건"]},
    )
    assert result is None
    assert chat.calls == 2


def test_primary_clarification_helper_contract(monkeypatch):
    """_dag_planner_clarification — ask면 (질문, 칩, topic), 그 외(None·finish·예외)는 None."""
    import strategy_conversation.planner.dag_planner as dag_mod
    import strategy_conversation.planner.shadow as shadow_mod
    from strategy_conversation.planner.dag_planner import DagPlanResult
    from strategy_conversation.primary import _dag_planner_clarification

    monkeypatch.setattr(shadow_mod, "_default_chat", lambda: (lambda *a, **k: ""))

    def _plan_returns(result):
        monkeypatch.setattr(dag_mod, "plan_strategy_dag", lambda *a, **kw: result)

    ask = DagPlanResult("ask", "리밸런싱 주기는 어떻게 할까요?", ["매월", "분기마다"],
                        None, [], [], topic="리밸런싱")
    _plan_returns(ask)
    assert _dag_planner_clarification("반도체 etf 전략", object()) == (
        "리밸런싱 주기는 어떻게 할까요?", ["매월", "분기마다"], "리밸런싱")

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
    # provenance를 함께 넘긴다 — 유니버스는 사용자가 말한 설정이라야 '채워짐'이다.
    summary = _dag_state_summary(parsed, ["universe"])
    assert summary["universe"] == ["ETF"]
    assert summary["etf_theme"] == "반도체"
    assert summary["entry_signal_types"] == ["ma_crossover"]
    assert "exit_signal_types" not in summary  # 빈 필드는 요약에 넣지 않는다
    assert "유니버스" in summary["filled_slots"] and "매수 조건" in summary["filled_slots"]
    assert "매도 조건" not in summary["filled_slots"]


def test_dag_state_summary_does_not_count_materialized_defaults_as_filled():
    """[회귀 2026-07-29] ParsedStrategy는 유니버스·최대 보유·기간·초기 자본에 기본값을
    물질화한다 — 값만 보면 **빈 전략조차 4/8 완료**로 보여 planner가 그 슬롯을 영영
    묻지 않는다. 판정은 provenance(explicit_fields)를 함께 봐야 한다."""
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.primary import _dag_state_summary

    empty = ParsedStrategy(description="빈 전략")
    # 기본값은 실제로 채워져 있다(값 존재 ≠ 사용자 언급).
    assert empty.universe and empty.max_positions and empty.backtest_period
    assert _dag_state_summary(empty, [])["filled_slots"] == []
    # 사용자가 말한 설정만 채워짐으로 올라온다.
    assert _dag_state_summary(empty, ["universe", "초기 자본"])["filled_slots"] == ["유니버스"]


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


# ── Action 메타데이터·상태(설계 스펙 § 12.1·12.2) ──────────────────────────────
# 계약: ① 도구 효과는 정적 사실이라 LLM이 이번 턴에 다시 정하지 않는다
#       ② 무효화된 노드는 삭제하지 않고 INVALIDATED로 남긴다(이력 추적)
#       ③ 정상 선행 실행이 무효화로 잡히지 않는다

from strategy_conversation.planner.dag import (  # noqa: E402
    NodeStatus,
    invalidated_by_state_change,
    node_statuses,
    parse_dag,
    ready_nodes,
    tool_effects,
)


def _dag(*nodes):
    return parse_dag({"dag": {"nodes": list(nodes)}})


def test_tool_effects_are_filled_deterministically_not_by_llm():
    """LLM이 엉뚱한 효과를 실어 보내도 도구의 정적 사실이 이긴다."""
    nodes = _dag({
        "id": "t1", "type": "tool", "tool": "kg_theme_companies",
        "produces": ["엉뚱한필드"], "invalidated_by": [],
    })
    assert nodes[0].produces == ["universe.symbols"]
    assert "universe.type" in nodes[0].invalidated_by


def test_unknown_tool_keeps_llm_declared_meta_without_inventing():
    nodes = _dag({"id": "a1", "type": "ask", "question": "?", "produces": ["x"]})
    assert nodes[0].produces == ["x"]
    assert nodes[0].invalidated_by == []


def test_meta_format_violation_is_a_contract_error():
    import pytest as _pytest

    with _pytest.raises(Exception):
        _dag({"id": "a1", "type": "ask", "question": "?", "requires": "문자열"})


def test_completed_node_is_invalidated_when_its_premise_changes():
    nodes = _dag(
        {"id": "t1", "type": "tool", "tool": "kg_theme_companies"},
        {"id": "a1", "type": "ask", "question": "?", "depends_on": ["t1"]},
    )
    invalid = invalidated_by_state_change(nodes, {"universe.type"}, {"t1"})
    # 완료된 조회가 무효가 되고, 그 관찰에 기대던 질문도 함께 무효다.
    assert invalid == {"t1", "a1"}


def test_pending_node_is_not_invalidated_by_its_own_dependency():
    """정상 선행 실행이 무효화로 잡히면 DAG가 시작조차 못 한다."""
    nodes = _dag(
        {"id": "t0", "type": "tool", "tool": "classify_universe"},
        {"id": "t1", "type": "tool", "tool": "kg_theme_companies", "depends_on": ["t0"]},
    )
    # classify_universe가 universe.type을 만들었지만 t1은 아직 실행 전이다.
    assert invalidated_by_state_change(nodes, {"universe.type"}, {"t0"}) == set()


def test_nodes_without_declared_invalidation_are_never_invalidated():
    nodes = _dag({"id": "a1", "type": "ask", "question": "?"})
    assert invalidated_by_state_change(nodes, {"universe.type"}, {"a1"}) == set()


def test_statuses_name_why_a_node_will_not_run():
    nodes = _dag(
        {"id": "t1", "type": "tool", "tool": "kg_theme_companies"},
        {"id": "t2", "type": "tool", "tool": "lookup_capabilities"},
        {"id": "a1", "type": "ask", "question": "?", "depends_on": ["t1"]},
        {"id": "a2", "type": "ask", "question": "?", "depends_on": ["t2"]},
    )
    statuses = node_statuses(nodes, done_ids={"t2"}, invalidated_ids={"t1"})
    assert statuses["t1"] is NodeStatus.INVALIDATED   # 삭제하지 않고 남긴다
    assert statuses["a1"] is NodeStatus.BLOCKED       # 영영 오지 않을 의존
    assert statuses["t2"] is NodeStatus.COMPLETED
    assert statuses["a2"] is NodeStatus.READY


def test_invalidated_nodes_are_excluded_from_ready():
    nodes = _dag(
        {"id": "t1", "type": "tool", "tool": "kg_theme_companies"},
        {"id": "a1", "type": "ask", "question": "?", "depends_on": ["t1"]},
    )
    assert [n.id for n in ready_nodes(nodes, set())] == ["t1"]
    assert ready_nodes(nodes, set(), excluded_ids={"t1"}) == []
