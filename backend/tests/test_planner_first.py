"""Planner-first 제어 역전(Phase 5, 2026-07-28) 계약 테스트.

핵심 계약:
- planner가 파스 최선두에서 실행되고(Universe-first), 유니버스 표현의 추출·분류·해석을
  소유한다 — 인터프리터 sectors 필드 누락이 유니버스 해석을 침묵시키던 '보안주' 사고의
  구조적 재발 방지.
- 확정값은 도구 관찰값에서만 채택하고, 적용은 고정 체인과 동일한 결정론 경로 재사용.
- planner ask의 채택은 결정론 게이트가 최종 권한(완성 전략 재질문 금지).
- planner 실패(None)·비활성은 현행 고정 파이프라인 그대로(단독 실패 지점 불가).
- 유니버스 범위 칩(CONCEPT 후보)은 LLM 없이 결정론으로 귀속된다.
"""

from __future__ import annotations

import pytest

import engine.nl_parser as nl_parser
from engine.nl_parser import ParsedStrategy
from strategy_conversation import primary as primary_mod
from strategy_conversation.planner.dag import DagNode
from strategy_conversation.planner.dag_planner import DagPlanResult, ExecutedNode
from strategy_conversation.primary import (
    _apply_planner_first_universe,
    _planner_first_ask,
    _planner_scope_ask,
    run_chip_answer,
)
from strategy_conversation.tools import call as call_tool


# ─── 유니버스 분류·CONCEPT 후보 도구(결정론) ─────────────────────────────────────

@pytest.mark.parametrize("text,expected_type,expected_canonical", [
    ("코스피", "MARKET", "KOSPI"),
    ("대형주", "MARKET", "KOSPI200"),
    ("반도체", "SECTOR", "반도체"),
    ("삼성전자", "SINGLE_STOCK", "005930"),
    ("반도체 ETF", "ETF", None),
    ("보안주", "CONCEPT", None),
])
def test_classify_universe_deterministic(text, expected_type, expected_canonical):
    out = call_tool("classify_universe", text=text)
    assert out.universe_type == expected_type
    assert out.canonical == expected_canonical


def test_concept_candidates_enumerates_catalog_scopes():
    """'보안주'는 카탈로그의 보안주(정보)/보안주(물리)로 범위가 갈린다 — 되묻기 재료."""
    out = call_tool("list_concept_candidates", text="보안주")
    terms = [c["term"] for c in out.candidates]
    assert "보안주(정보)" in terms and "보안주(물리)" in terms
    assert all(c["companies"] > 0 for c in out.candidates)


def test_concept_candidates_empty_for_unknown_term():
    assert call_tool("list_concept_candidates", text="존재하지않는테마xyz").candidates == []


def test_concept_candidates_merge_same_theme_across_catalogs():
    """'퓨리오사ai' 사고 회귀(2026-07-28): 같은 테마가 네이버('퓨리오사AI')·주달
    ('퓨리오사ai') 양쪽에 수록되면 표기 정규화 병합으로 후보 1개여야 한다 — 2개로
    잡히면 동일 라벨을 고르라는 무의미한 범위 되묻기가 나간다. 대표 표기=네이버."""
    out = call_tool("list_concept_candidates", text="퓨리오사ai")
    assert len(out.candidates) == 1
    assert out.candidates[0]["term"] == "퓨리오사AI"


# ─── 관찰값 적용(_apply_planner_first_universe) ─────────────────────────────────

def _executed(nodes_obs):
    executed = {}
    for i, (tool, text, obs) in enumerate(nodes_obs):
        node = DagNode(id=f"n{i}", type="tool", tool=tool, args={"text": text})
        executed[node.id] = ExecutedNode(node, obs)
    return executed


def _plan_result(nodes_obs, outcome="finish", question=None, chips=(), topic=None):
    return DagPlanResult(
        outcome=outcome, question=question, chips=list(chips), sector=None,
        companies=[], nodes=[], topic=topic, executed=_executed(nodes_obs),
    )


def test_apply_observed_theme_companies(monkeypatch):
    applied = {}

    def _fake_apply(parsed, term):
        applied["term"] = term
        parsed.target_symbols = ["005930", "000660"]
        parsed.sector = None
        return f"'{term}' 관련 상장사 2곳을 대상 종목으로 설정했어요."

    monkeypatch.setattr(nl_parser, "apply_theme_companies", _fake_apply)
    parsed = ParsedStrategy(description="테스트")
    notices: list = []
    result = _plan_result([
        ("classify_universe", "보안주", {"universe_type": "CONCEPT"}),
        ("kg_theme_companies", "보안주",
         {"found": True, "companies": [{"symbol": "005930"}, {"symbol": "000660"}]}),
    ])
    resolved, unresolved = _apply_planner_first_universe(result, parsed, notices)
    assert applied["term"] == "보안주"
    assert resolved == {"보안주"} and unresolved == set()
    assert parsed.target_symbols == ["005930", "000660"]
    assert notices and "보안주" in notices[0]


def test_apply_observed_learned_sector():
    parsed = ParsedStrategy(description="테스트")
    notices: list = []
    result = _plan_result([
        ("ground_term", "이상한테마", {"sector": "반도체"}),
    ])
    resolved, unresolved = _apply_planner_first_universe(result, parsed, notices)
    assert resolved == {"이상한테마"} and unresolved == set()
    assert parsed.sector == "반도체"


def test_non_concept_classification_counts_as_resolved():
    """MARKET/SECTOR/SINGLE_STOCK/ETF 분류는 그 자체로 해석 완료 — 병합 없음."""
    parsed = ParsedStrategy(description="테스트")
    result = _plan_result([
        ("classify_universe", "코스피", {"universe_type": "MARKET", "canonical": "KOSPI"}),
    ])
    resolved, unresolved = _apply_planner_first_universe(result, parsed, [])
    assert resolved == {"코스피"} and unresolved == set()
    assert parsed.sector is None and not parsed.target_symbols


def test_unresolved_concept_stays_for_universe_ask():
    parsed = ParsedStrategy(description="테스트")
    result = _plan_result([
        ("classify_universe", "보안주", {"universe_type": "CONCEPT"}),
        ("kg_theme_companies", "보안주", {"found": False, "companies": []}),
        ("list_concept_candidates", "보안주",
         {"candidates": [{"term": "보안주(정보)", "companies": 50}]}),
    ])
    resolved, unresolved = _apply_planner_first_universe(result, parsed, [])
    assert resolved == set() and unresolved == {"보안주"}


@pytest.mark.parametrize("topic", ["유니버스 범위", "매수조건"])
def test_ambiguous_scope_blocks_silent_theme_application(monkeypatch, topic):
    """실측 사고(2026-07-28): 범위 후보 2개 표현에 kg 테마를 조용히 적용하면서 범위
    질문이 함께 나가 전략과 질문이 모순됐다 — 후보 2개 이상이면 planner ask의 topic과
    무관하게 적용을 차단한다(범위 되묻기는 결정론이 항상 표면화하므로)."""
    def _must_not_apply(parsed, term):
        raise AssertionError("범위 질문 중 테마가 조용히 적용됐다")

    monkeypatch.setattr(nl_parser, "apply_theme_companies", _must_not_apply)
    parsed = ParsedStrategy(description="테스트")
    result = _plan_result(
        [("classify_universe", "보안주", {"universe_type": "CONCEPT"}),
         ("list_concept_candidates", "보안주",
          {"candidates": [{"term": "보안주(정보)", "companies": 50},
                          {"term": "보안주(물리)", "companies": 19}]}),
         ("kg_theme_companies", "보안주",
          {"found": True, "companies": [{"symbol": "012450"}]})],
        outcome="ask", question="범위를 정해 주세요", chips=[], topic=topic,
    )
    resolved, unresolved = _apply_planner_first_universe(result, parsed, [])
    assert resolved == set() and unresolved == {"보안주"}
    assert not parsed.target_symbols


# ─── 범위 모호성 되묻기(_planner_scope_ask — 결정론 소유) ───────────────────────

def test_scope_ask_surfaces_even_when_planner_drifts_to_condition_ask():
    """'미용기기' 사고 유형(2026-07-28): planner가 유니버스 ask를 계획하지 않아도
    후보 2개 이상 관찰이 있으면 결정론이 범위 질문을 확정한다(고정 템플릿+후보 칩)."""
    result = _plan_result(
        [("list_concept_candidates", "보안주",
          {"candidates": [{"term": "보안주(정보)", "companies": 50},
                          {"term": "보안주(물리)", "companies": 19}]})],
        outcome="ask", question="어떤 조건에서 매수할까요?", chips=["PER 15 이하"],
        topic="매수조건",
    )
    scope = _planner_scope_ask(result, {"보안주"})
    assert scope is not None
    question, chips, terms = scope
    assert "보안주" in question and "범위" in question
    assert chips == ["보안주(정보)", "보안주(물리)"]
    assert terms == {"보안주"}


def test_scope_ask_reuses_planner_universe_question_and_observed_chips():
    """planner가 유니버스 ask를 냈으면 질문 문구는 재사용하되 칩은 항상 관찰된
    카탈로그 후보 표기다(9B 칩 지어내기 드리프트 차단)."""
    result = _plan_result(
        [("list_concept_candidates", "보안주",
          {"candidates": [{"term": "보안주(정보)", "companies": 50},
                          {"term": "보안주(물리)", "companies": 19}]})],
        outcome="ask", question="'보안주'는 범위가 넓어요. 어느 쪽인가요?",
        chips=["방산/군수 관련 기업 (한화에어로스페이스 등)"], topic="유니버스 범위",
    )
    scope = _planner_scope_ask(result, {"보안주"})
    assert scope is not None
    question, chips, _terms = scope
    assert question == "'보안주'는 범위가 넓어요. 어느 쪽인가요?"
    assert chips == ["보안주(정보)", "보안주(물리)"]


def test_scope_ask_none_without_ambiguous_candidates():
    """후보 1개 이하 표현은 범위 되묻기 대상이 아니다 — term-in 체인 소관."""
    result = _plan_result(
        [("list_concept_candidates", "미용기기",
          {"candidates": [{"term": "미용기기", "companies": 19}]})],
        outcome="ask", question="어떤 조건에서 매수할까요?", chips=[], topic="매수조건",
    )
    assert _planner_scope_ask(result, {"미용기기"}) is None


# ─── planner ask 채택 판정(_planner_first_ask — 결정론 게이트가 최종 권한) ───────

def test_universe_topic_ask_is_owned_by_scope_logic():
    """유니버스 topic ask는 조건 ask 채택 경로에서 다루지 않는다 — 범위 되묻기는
    _planner_scope_ask(결정론)가 소유한다."""
    result = _plan_result([], outcome="ask", question="어느 범위인가요?",
                          chips=["보안주(정보)", "보안주(물리)"], topic="유니버스")
    assert _planner_first_ask(result, ParsedStrategy(description="테스트")) is None


def test_condition_ask_dropped_when_gate_says_complete(monkeypatch):
    result = _plan_result([], outcome="ask", question="어떤 조건에서 매수할까요?",
                          chips=["PER 15 이하 시 매수"], topic="매수조건")
    parsed = ParsedStrategy(description="테스트")
    monkeypatch.setattr(nl_parser, "detect_incomplete_backtest_conditions",
                        lambda p, u="": (None, None))
    assert _planner_first_ask(result, parsed) is None
    monkeypatch.setattr(nl_parser, "detect_incomplete_backtest_conditions",
                        lambda p, u="": ("어떤 조건에서 매수할까요?", []))
    assert _planner_first_ask(result, parsed) is not None


def test_finish_outcome_yields_no_ask():
    result = _plan_result([], outcome="finish")
    assert _planner_first_ask(result, ParsedStrategy(description="t")) is None


# ─── run_primary_parse 통합 — planner 최선두 실행·실패 폴백 ─────────────────────

def _intent_dict(**overrides):
    data = {
        "intent": "CREATE_STRATEGY",
        "status": "NEEDS_CLARIFICATION",
        "strategy": {
            "name": None,
            "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [],
                         "symbols": [], "etf_theme": None},
            "entry_conditions": [], "exit_conditions": [], "ranking": [],
            "portfolio": {"selection_count": None, "weighting": None,
                          "rebalance_frequency": None, "hold_period_days": None},
            "risk_management": {"stop_loss": None, "take_profit": None,
                                "trailing_stop": None, "max_mdd_limit": None},
            "backtest": {"period": None, "start_date": None, "end_date": None,
                         "execution_timing": None, "initial_capital": None,
                         "fee_rate": None, "slippage_rate": None},
        },
        "patches": [], "missing_fields": [], "unsupported_features": [],
        "assumptions": [], "clarification_questions": [], "confidence": 0.9,
    }
    data.update(overrides)
    return data


class _StubInterpreter:
    def __init__(self, intent_data):
        from strategy_conversation.interpreter.llm_strategy_interpreter import (
            InterpreterResult,
        )
        from strategy_conversation.interpreter.models import StrategyIntent

        self._result = InterpreterResult(
            intent=StrategyIntent.model_validate(intent_data),
            raw_output="{}", repair_attempts=0, latency_ms=1.0, model_name="stub",
        )

    def interpret(self, user_input, draft=None):
        return self._result


def test_planner_first_universe_ask_wins_over_condition_question(monkeypatch):
    """'보안주' 사고 재현 계약: 인터프리터가 sectors를 비워도 planner-first가 유니버스를
    소유해 CONCEPT 범위 질문이 조건 질문보다 먼저 나간다."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(primary_mod, "_interpreter_singleton",
                        _StubInterpreter(_intent_dict()))
    plan = _plan_result(
        [("classify_universe", "보안주", {"universe_type": "CONCEPT"}),
         ("kg_theme_companies", "보안주", {"found": False, "companies": []}),
         ("list_concept_candidates", "보안주",
          {"candidates": [{"term": "보안주(정보)", "companies": 50},
                          {"term": "보안주(물리)", "companies": 19}]})],
        outcome="ask", question="'보안주'는 범위가 넓어요. 어느 쪽을 대상으로 할까요?",
        chips=["보안주(정보)", "보안주(물리)"], topic="유니버스",
    )
    import strategy_conversation.planner.dag_planner as dp
    monkeypatch.setattr(dp, "plan_strategy_dag",
                        lambda user_input, chat_fn, **kw: plan)
    result = primary_mod.run_primary_parse("보안주 관련 투자 전략")
    assert result is not None
    assert result["clarification_question"] == plan.question
    assert result["clarification_suggestions"] == ["보안주(정보)", "보안주(물리)"]
    assert result["clarification_priority"] == "dag_planner"
    assert result["pending_ask"] == {
        "topic": "유니버스", "question": plan.question,
        "chips": ["보안주(정보)", "보안주(물리)"],
    }


def test_planner_drift_leaves_unresolved_term_to_chain(monkeypatch):
    """'미용기기' 사고 회귀(2026-07-28): planner가 후보 1개 표현을 해석하지 않고 조건
    ask로 드리프트 — 그 표현은 term-in 체인으로 흘러 해석돼야 한다(무조건 제외 금지).
    체인 해석 후 미지원 안내는 지워지고 planner 조건 ask는 유지된다."""
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.delenv("STRATEGY_PLANNER_MODE", raising=False)
    monkeypatch.setattr(primary_mod, "_interpreter_singleton", _StubInterpreter(
        _intent_dict(strategy={
            **_intent_dict()["strategy"],
            "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": ["미용기기"],
                         "symbols": [], "etf_theme": None},
        })
    ))
    applied = {}

    def _fake_apply(parsed, term):
        applied["term"] = term
        parsed.target_symbols = ["149980", "214150"]
        parsed.sector = None
        return f"'{term}' 관련으로 확인된 상장사 2곳을 대상 종목으로 설정했어요."

    monkeypatch.setattr(nl_parser, "apply_theme_companies", _fake_apply)
    plan = _plan_result(
        [("classify_universe", "미용기기", {"universe_type": "CONCEPT"}),
         ("list_concept_candidates", "미용기기",
          {"candidates": [{"term": "미용기기", "companies": 19}]})],
        outcome="ask", question="어떤 조건에서 매수할까요?",
        chips=["PER 20 이하 및 ROE 10% 이상 재무 건전성 기준"], topic="매수조건",
    )
    import strategy_conversation.planner.dag_planner as dp
    monkeypatch.setattr(dp, "plan_strategy_dag",
                        lambda user_input, chat_fn, **kw: plan)
    result = primary_mod.run_primary_parse("미용기기 관련주 투자 전략을 만들자")
    assert result is not None
    # 체인이 표현을 해석했다 — planner가 못 푼 표현이 증발하지 않는다
    assert applied["term"] == "미용기기"
    assert result["parsed"].target_symbols == ["149980", "214150"]
    # 해석된 표현의 미지원 안내는 없다(모순 방지)
    assert not any("미용기기" in n and "지원되지 않아" in n for n in result["notices"])
    # planner 조건 ask는 유지된다(게이트가 공백 인정)
    assert result["clarification_question"] == "어떤 조건에서 매수할까요?"


def test_planner_first_failure_falls_back_to_current_pipeline(monkeypatch):
    monkeypatch.setenv("STRATEGY_DAG_PLANNER_MODE", "primary")
    monkeypatch.setattr(primary_mod, "_interpreter_singleton",
                        _StubInterpreter(_intent_dict()))
    import strategy_conversation.planner.dag_planner as dp

    def _boom(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(dp, "plan_strategy_dag", _boom)
    result = primary_mod.run_primary_parse("PER 낮은 종목 전략")
    # planner 장애가 파스를 깨지 않는다 — 현행 검증 질문(진입 조건)이 그대로 나간다
    assert result is not None
    assert result["clarification_question"] is not None


def test_planner_first_disabled_by_default(monkeypatch):
    monkeypatch.delenv("STRATEGY_DAG_PLANNER_MODE", raising=False)
    monkeypatch.setattr(primary_mod, "_interpreter_singleton",
                        _StubInterpreter(_intent_dict()))
    import strategy_conversation.planner.dag_planner as dp

    def _fail(*args, **kwargs):
        raise AssertionError("off 모드에서 planner-first가 호출됐다")

    monkeypatch.setattr(dp, "plan_strategy_dag", _fail)
    assert primary_mod.run_primary_parse("PER 낮은 종목 전략") is not None


# ─── 유니버스 범위 칩 결정론 귀속(run_chip_answer) ───────────────────────────────

def _universe_pending_ask():
    # topic은 실측 드리프트 표기('유니버스 범위')로 둔다 — 포함 판정 계약 검증 겸용
    return {"topic": "유니버스 범위",
            "question": "'보안주'는 범위가 넓어요. 어느 쪽을 대상으로 할까요?",
            "chips": ["보안주(정보)", "보안주(물리)"]}


def test_universe_chip_applies_theme_deterministically(monkeypatch):
    monkeypatch.delenv("STRATEGY_DAG_PLANNER_MODE", raising=False)

    def _fake_apply(parsed, term):
        parsed.target_symbols = ["012345"]
        parsed.sector = None
        return f"'{term}' 관련 상장사 1곳을 대상 종목으로 설정했어요."

    monkeypatch.setattr(nl_parser, "apply_theme_companies", _fake_apply)
    prev = ParsedStrategy(description="보안주 전략").model_dump()
    result = run_chip_answer("보안주(정보)", prev, _universe_pending_ask())
    assert result is not None
    assert result["parsed"].target_symbols == ["012345"]
    assert result["interpreter"]["mode"] == "primary_chip_answer"
    assert result["notices"] and "보안주(정보)" in result["notices"][0]


def test_universe_chip_without_catalog_match_falls_through(monkeypatch):
    """칩과 정확히 일치했지만 카탈로그 정합이 깨진 경우 — 수정 인터프리터 폴백(None)."""
    monkeypatch.setattr(nl_parser, "apply_theme_companies", lambda p, t: None)
    prev = ParsedStrategy(description="보안주 전략").model_dump()
    assert run_chip_answer("보안주(물리)", prev, _universe_pending_ask()) is None
