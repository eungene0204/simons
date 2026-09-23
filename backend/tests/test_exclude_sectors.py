"""업종 제외 필터(exclude_sectors, 엔진 v16.24) 배선 회귀.

배경(2026-09-23): 국내 퀀트 플랫폼이 기본 필터로 두는 '금융주 제외'·'지주사 제외'를 엔진이
받을 자리가 없었다(sector는 포함 필터뿐). 묶음 통칭 '금융'은 은행·증권·보험·금융지주 넷이다.

고정하는 것: ① 묶음 통칭 펴기(SECTOR_GROUP_ALIASES) ② 심볼 제외(미상 종목은 남긴다)
③ 해석 레인(스키마·검증·컴파일·디컴파일·정본 DSL·엔진 요청·해시) ④ 미해석 표현은 미지원 안내.
"""

from __future__ import annotations

import pytest

from engine.nl_parser import ParsedStrategy
from engine.strategy_converter import compute_strategy_id, to_backtest_request, to_canonical_strategy_dsl
from engine.universe_pit import exclude_by_sector, expand_legacy_sector, normalize_sector_value
from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation

_FIN = ("은행", "증권", "보험", "금융지주")


def _intent(universe: dict, **overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": [], "symbols": [], **universe},
        "entry_conditions": [{"factor": "fundamental.per", "operator": "<=", "value": 10,
                              "source_text": "PER 10 이하"}],
        "exit_conditions": [],
        "ranking": [],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9, "strategy": strategy,
    })


# ── ① 묶음 통칭 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("term", ["금융", "금융주", "금융업", "금융 섹터"])
def test_financial_group_alias_expands_to_four_sectors(term):
    assert expand_legacy_sector(term) == _FIN


@pytest.mark.parametrize("term", ["지주사", "지주회사", "홀딩스", "지주"])
def test_holding_company_aliases(term):
    assert expand_legacy_sector(term) == ("지주회사",)


def test_group_alias_also_works_as_inclusion_filter_value():
    assert normalize_sector_value(["금융"]) == list(_FIN)


# ── ② 심볼 제외 ────────────────────────────────────────────────────────────────

@pytest.fixture
def sector_map(monkeypatch):
    mapping = {"A": "은행", "B": "반도체", "C": "지주회사", "D": "보험"}
    monkeypatch.setattr("engine.universe_pit._load_sector_map", lambda: mapping)
    return mapping


def test_exclude_by_sector_removes_group_and_keeps_unknown(sector_map):
    kept, n = exclude_by_sector(["A", "B", "C", "D", "Z"], ["금융주"])
    assert kept == ["B", "C", "Z"] and n == 2          # Z=업종 미상 → 남긴다
    kept, n = exclude_by_sector(["A", "B", "C", "D"], ["금융", "지주사"])
    assert kept == ["B"] and n == 3
    assert exclude_by_sector(["A", "B"], []) == (["A", "B"], 0)


# ── ③ 해석 레인 관통 ────────────────────────────────────────────────────────────

def test_exclusion_compiles_round_trips_and_reaches_request():
    validated, report = run_validation(_intent({"exclude_sectors": ["금융주", "지주사"]}))
    assert validated.strategy.universe.exclude_sectors == [*_FIN, "지주회사"]
    parsed = compile_strategy(validated, report, "PER 10 이하, 금융주·지주사 제외")
    assert parsed.exclude_sectors == [*_FIN, "지주회사"]
    assert parsed.sector is None                         # 포함 필터와 독립
    spec = decompile_strategy(parsed)
    assert spec.universe.exclude_sectors == [*_FIN, "지주회사"]
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["exclude_sectors"] == [*_FIN, "지주회사"]
    canonical = to_canonical_strategy_dsl(parsed)
    assert canonical["exclude_sectors"] == sorted([*_FIN, "지주회사"])


def test_exclusion_changes_strategy_id_and_absence_keeps_it():
    validated, report = run_validation(_intent({}))
    base = compile_strategy(validated, report, "x")
    validated2, report2 = run_validation(_intent({"exclude_sectors": ["금융"]}))
    excl = compile_strategy(validated2, report2, "x")
    assert compute_strategy_id(base) != compute_strategy_id(excl)
    assert "exclude_sectors" not in to_canonical_strategy_dsl(base)
    assert to_backtest_request(base, resolve_symbols=False)["exclude_sectors"] is None


def test_parsed_strategy_normalizes_raw_exclusions():
    p = ParsedStrategy(description="x", exclude_sectors=["금융", "은행", "없는업종"])
    assert p.exclude_sectors == list(_FIN)
    assert ParsedStrategy(description="x", exclude_sectors=[]).exclude_sectors is None


def test_target_symbols_mode_drops_exclusion_from_request():
    p = ParsedStrategy(description="x", target_symbols=["005930"], exclude_sectors=["금융"])
    assert to_backtest_request(p, resolve_symbols=False)["exclude_sectors"] is None


# ── ④ 미해석·비적용 시장은 미지원 안내 ─────────────────────────────────────────

def test_unresolved_or_etf_exclusion_is_reported_not_dropped_silently():
    validated, report = run_validation(_intent({"exclude_sectors": ["금융", "우주여행업"]}))
    assert validated.strategy.universe.exclude_sectors == list(_FIN)
    assert any("우주여행업" in u for u in report.unsupported_features)
    assert report.errors == []                            # 제외 하나가 안 풀려도 오류는 아니다(미지원 안내만)
    validated, report = run_validation(_intent({"markets": ["ETF"], "exclude_sectors": ["금융"]}))
    assert validated.strategy.universe.exclude_sectors == []
    assert any("금융" in u for u in report.unsupported_features)
