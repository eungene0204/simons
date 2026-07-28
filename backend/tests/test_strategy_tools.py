"""Tool 레이어(Phase 1) 계약 — 카탈로그 등록·입출력 형식 검증·기존 서비스 위임.

Planner → Tool/Engine → Responder 전환의 도구 경계가 동작을 바꾸지 않고(기존 서비스
위임) 계약 위반(미등록 이름·형식 불일치)만 ToolError로 거르는지 확인한다.
"""

import pytest

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.tools import ToolError, call, get_tool, list_tools


def _intent(**strategy_overrides) -> StrategyIntent:
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": []},
        "entry_conditions": [
            {"factor": "fundamental.per", "operator": "<=", "value": 10,
             "source_text": "PER 10 이하"}
        ],
        "exit_conditions": [],
        "ranking": [],
        "portfolio": {"selection_count": 20, "rebalance_frequency": "monthly"},
        "risk_management": {"stop_loss": 8},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9,
        "strategy": strategy,
    })


# ── 카탈로그 등록 ─────────────────────────────────────────────────────────────

def test_catalog_registers_all_tools():
    names = {spec.name for spec in list_tools()}
    assert names == {
        "kg_resolve_sector", "kg_theme_companies", "ground_term",
        "resolve_universe", "lookup_capabilities", "validate_intent",
        "compile_strategy", "classify_universe", "list_concept_candidates",
    }


def test_only_ground_term_is_nondeterministic():
    nondeterministic = {s.name for s in list_tools() if not s.deterministic}
    assert nondeterministic == {"ground_term"}


def test_unknown_tool_raises():
    with pytest.raises(ToolError):
        get_tool("없는도구")


def test_input_format_violation_raises():
    with pytest.raises(ToolError):
        call("resolve_universe", sectors="반도체")  # list여야 한다


# ── 개별 도구 위임 ────────────────────────────────────────────────────────────

def test_lookup_capabilities_mirrors_registry():
    from strategy_conversation.registry.capability_registry import SUPPORTED_MARKETS

    out = call("lookup_capabilities")
    assert out.markets == list(SUPPORTED_MARKETS)
    assert out.max_positions_range == [1, 100]


def test_resolve_universe_delegates_to_resolver():
    out = call("resolve_universe", sectors=["반도체"], symbols=["삼성전자", "도저히없는종목123"])
    assert out.sector_value == "반도체"
    assert out.unresolved_sectors == []
    assert out.symbol_codes == ["005930"]
    assert out.unresolved_symbols == ["도저히없는종목123"]


def test_kg_resolve_sector_delegates(monkeypatch):
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "resolve_sector_from_text", lambda text: "반도체")
    assert call("kg_resolve_sector", text="HBM 관련주").sector == "반도체"


def test_kg_theme_companies_not_found(monkeypatch):
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: None)
    out = call("kg_theme_companies", text="미지의테마")
    assert out.found is False and out.companies == []


def test_kg_theme_companies_delegates(monkeypatch):
    import engine.knowledge_graph as kg

    monkeypatch.setattr(kg, "theme_backtest_companies", lambda text: {
        "term": "HBM", "companies": [{"symbol": "005930", "name": "삼성전자"}],
        "first_known_date": "2024-01-02",
    })
    out = call("kg_theme_companies", text="HBM 관련주")
    assert out.found is True
    assert out.term == "HBM"
    assert out.companies[0]["symbol"] == "005930"


def test_ground_term_requires_chat_injection():
    with pytest.raises(ToolError):
        call("ground_term", text="소부장")


def test_ground_term_delegates(monkeypatch):
    import engine.term_grounding as tg

    monkeypatch.setattr(tg, "resolve_sector", lambda text, chat, **kw: "에너지/원자력")
    out = call("ground_term", text="SMR 관련주", chat=lambda s, u: "")
    assert out.sector == "에너지/원자력"


# ── 검증·컴파일 파이프라인 위임 ───────────────────────────────────────────────

def test_validate_then_compile_via_tools():
    validation = call("validate_intent", intent=_intent())
    assert validation.report.is_valid

    compiled = call("compile_strategy", intent=validation.intent,
                    report=validation.report, user_input="PER 10 이하 저평가 전략",
                    partial=not validation.report.is_valid)
    assert compiled.dropped == []
    filters = compiled.parsed.fundamental_filters
    assert any(f.metric == "per" and f.value == 10 for f in filters)


def test_compile_partial_reports_dropped():
    # 임계값 없는 조건은 부분 컴파일에서 제외 목록으로 보고된다(조용한 소실 금지)
    intent = _intent(entry_conditions=[
        {"factor": "fundamental.per", "operator": "<=", "value": None,
         "source_text": "PER 낮은"}
    ])
    validation = call("validate_intent", intent=intent)
    assert not validation.report.is_valid

    compiled = call("compile_strategy", intent=validation.intent,
                    report=validation.report, user_input="PER 낮은 종목",
                    partial=True)
    assert compiled.dropped  # 제외 조건이 정직하게 보고된다
