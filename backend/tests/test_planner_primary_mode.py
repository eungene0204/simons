"""planner primary 모드(Phase 3 승격) — 미해석 업종·테마 구간의 planner 담당 계약.

핵심: planner 결과의 결정론 적용(섹터 병합·상장사 반영·되묻기 칩), 실패(None)·예외 시
표현 단위 고정 체인 폴백(planner는 단독 실패 지점 불가), config 모드 인식.
"""

import json

import pytest

import strategy_conversation.primary as primary_mod
from strategy_conversation.planner import mini_planner as planner_mod
from strategy_conversation.planner import shadow as shadow_mod
from strategy_conversation.planner.mini_planner import PlannerResult
from strategy_conversation.primary import _resolve_sector_terms_planner_primary


@pytest.fixture
def parsed():
    from engine.nl_parser import ParsedStrategy

    return ParsedStrategy(description="planner-primary-test")


@pytest.fixture
def no_llm(monkeypatch):
    """planner의 실제 LLM 호출 차단 — 테스트는 결과 소비 계약만 검증한다."""
    monkeypatch.setattr(shadow_mod, "_default_chat", lambda: (lambda *a, **k: ""))


def _plan_returns(monkeypatch, result):
    monkeypatch.setattr(planner_mod, "plan_universe_resolution",
                        lambda term, chat_fn, **kw: result)


def _theme_apply_misses(monkeypatch):
    import engine.nl_parser as nl_parser

    monkeypatch.setattr(nl_parser, "apply_theme_companies", lambda parsed, term: None)


def test_config_accepts_primary_mode(monkeypatch):
    from strategy_conversation import config

    monkeypatch.setenv("STRATEGY_PLANNER_MODE", "primary")
    assert config.planner_mode() == "primary"


def test_resolved_sector_merged(parsed, no_llm, monkeypatch):
    _theme_apply_misses(monkeypatch)
    _plan_returns(monkeypatch, PlannerResult("resolved", "반도체", [], None, [], 5))
    notices: list = []
    question, chips = _resolve_sector_terms_planner_primary(parsed, ["미지테마"], notices)
    assert question is None and chips is None
    assert parsed.sector == "반도체"
    assert any("반도체" in n for n in notices)


def test_resolved_companies_applied(parsed, no_llm, monkeypatch):
    _theme_apply_misses(monkeypatch)
    _plan_returns(monkeypatch, PlannerResult(
        "resolved", None, [{"symbol": "005930", "name": "삼성전자"}], None, [], 5))
    notices: list = []
    question, _ = _resolve_sector_terms_planner_primary(parsed, ["미지테마"], notices)
    assert question is None
    assert "005930" in parsed.target_symbols


def test_clarify_returns_question_with_chips(parsed, no_llm, monkeypatch):
    from engine.nl_parser import SECTOR_REASK_SUGGESTIONS

    _plan_returns(monkeypatch, PlannerResult(
        "clarify", None, [], "어떤 업종을 말씀하신 건가요?", [], 5))
    notices: list = []
    question, chips = _resolve_sector_terms_planner_primary(parsed, ["미지테마"], notices)
    assert question == "어떤 업종을 말씀하신 건가요?"
    assert chips == list(SECTOR_REASK_SUGGESTIONS)
    assert parsed.sector is None


def test_planner_none_falls_back_to_fixed_chain(parsed, no_llm, monkeypatch):
    _plan_returns(monkeypatch, None)
    called = {}

    def fake_fixed(parsed_arg, terms, notices_arg, on_stage=None):
        called["terms"] = terms
        return "고정 체인 질문", ["칩"]

    monkeypatch.setattr(primary_mod, "_resolve_sector_terms_term_in", fake_fixed)
    notices: list = []
    question, chips = _resolve_sector_terms_planner_primary(parsed, ["미지테마"], notices)
    assert called["terms"] == ["미지테마"]
    assert question == "고정 체인 질문" and chips == ["칩"]


def test_planner_exception_falls_back(parsed, no_llm, monkeypatch):
    def boom(term, chat_fn, **kw):
        raise RuntimeError("planner down")

    monkeypatch.setattr(planner_mod, "plan_universe_resolution", boom)
    called = {}
    monkeypatch.setattr(
        primary_mod, "_resolve_sector_terms_term_in",
        lambda p, terms, n, on_stage=None: (called.setdefault("terms", terms) and None,
                                            None))
    notices: list = []
    _resolve_sector_terms_planner_primary(parsed, ["미지테마"], notices)
    assert called["terms"] == ["미지테마"]
