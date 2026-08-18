"""복합 순위 합산(FR-BT-063) — 대화 레인(검증→컴파일→디컴파일→엔진 요청) 계약.

- 랭킹 항목 2개 이상 = 복합 순위 합산 → ranking_metric='composite' + ranking_components.
- 방향 미지정은 지표의 자연 방향(PER=bottom, ROE=top)으로 채운다.
- 미지원 랭킹 항목은 검증기가 **제거**하고 내부 식별자를 미지원 보고에 담지 않는다
  (2026-08-17 'composite_score' → 수익률 랭킹 둔갑 + 내부명 노출 사고 회귀).
- 컴파일러는 등록되지 않은 랭킹 지표를 'return'으로 바꿔치지 않는다.
- 디컴파일 왕복: composite → RankingSpec N개 → 재컴파일 시 동일 구성.
- 가격 산출 구성 지표(수익률)의 산정 기간은 자리와 무관하게 되묻는다.
"""

import pytest

from engine.nl_parser import ParsedStrategy
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial, compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _intent(ranking, **overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": [], "symbols": []},
        "entry_conditions": [],
        "exit_conditions": [],
        "ranking": ranking,
        "portfolio": {"selection_percent": 10, "rebalance_frequency": "monthly"},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9,
        "strategy": strategy,
    })


_FOUR = [
    {"metric": "fundamental.roe_or_gpa", "direction": "top", "source_text": "roe 내림차순"},
    {"metric": "fundamental.current_ratio", "direction": "top", "source_text": "유동비율 내림차순"},
    {"metric": "fundamental.per", "direction": "bottom", "source_text": "per 오름차순"},
    {"metric": "fundamental.pcr", "direction": "bottom", "source_text": "pcr 오름차순"},
]


def test_multi_ranking_compiles_to_composite():
    validated, report = run_validation(_intent(_FOUR))
    assert report.is_valid, report.errors
    parsed = compile_strategy(validated, report, "roe 내림차순, 유동비율 내림차순, per 오름차순, pcr 오름차순 순위 합산 상위 10%")
    assert parsed.ranking_metric == "composite"
    assert [(c.metric, c.direction) for c in parsed.ranking_components] == [
        ("roe_or_gpa", "top"), ("current_ratio", "top"), ("per", "bottom"), ("pcr", "bottom"),
    ]
    assert parsed.max_positions_pct == 10.0
    # 사용자가 말하지 않은 것은 생기지 않는다 — 조건도, 분위 그룹도.
    assert parsed.fundamental_filters == []
    assert parsed.ranking_quantile_groups is None


def test_composite_fills_natural_direction_when_unspecified():
    validated, report = run_validation(_intent([
        {"metric": "fundamental.roe_or_gpa"}, {"metric": "fundamental.per"},
    ]))
    parsed = compile_strategy(validated, report, "ROE와 PER 순위 합산")
    assert parsed.ranking_metric == "composite"
    assert {c.metric: c.direction for c in parsed.ranking_components} == {
        "roe_or_gpa": "top", "per": "bottom",
    }


def test_composite_flows_to_engine_risk_params_and_hash():
    validated, report = run_validation(_intent(_FOUR))
    parsed = compile_strategy(validated, report, None)
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["ranking_metric"] == "composite"
    assert [c["metric"] for c in req["risk"]["ranking_components"]] == [
        "roe_or_gpa", "current_ratio", "per", "pcr",
    ]
    canonical = to_canonical_strategy_dsl(parsed)
    assert canonical["ranking_metric"] == "composite"
    assert len(canonical["ranking_components"]) == 4
    # 단일 랭킹 전략엔 이 키가 없다(기존 strategy_id 불변).
    v1, r1 = run_validation(_intent([{"metric": "fundamental.per", "direction": "bottom"}]))
    p1 = compile_strategy(v1, r1, None)
    assert "ranking_components" not in to_canonical_strategy_dsl(p1)


def test_composite_decompile_roundtrip():
    validated, report = run_validation(_intent(_FOUR))
    parsed = compile_strategy(validated, report, None)
    spec = decompile_strategy(parsed)
    assert [r.metric for r in spec.ranking] == [
        "fundamental.roe_or_gpa", "fundamental.current_ratio", "fundamental.per", "fundamental.pcr",
    ]
    v2, r2 = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0))
    p2 = compile_strategy(v2, r2, None)
    assert p2.ranking_metric == "composite"
    assert [(c.metric, c.direction) for c in p2.ranking_components] == \
        [(c.metric, c.direction) for c in parsed.ranking_components]


def test_single_ranking_decompile_uses_ranking_namespace_for_volatility():
    """'volatility'는 fundamental.*이 아니라 ranking.volatility로 왕복해야 한다."""
    parsed = ParsedStrategy(
        description="변동성 낮은 상위 10종목", universe=["KOSPI"],
        ranking_metric="volatility", ranking_direction="bottom", ranking_lookback_days=60,
    )
    spec = decompile_strategy(parsed)
    assert spec.ranking[0].metric == "ranking.volatility"


def test_unsupported_ranking_metric_is_removed_and_not_leaked():
    """LLM이 지어낸 랭킹 지표('composite_score')는 제거되고, 내부명이 미지원 보고에
    담기지 않으며, 컴파일러가 수익률 랭킹으로 바꿔치지 않는다."""
    validated, report = run_validation(_intent([
        {"metric": "composite_score", "direction": "bottom", "quantile_groups": 10},
    ]))
    assert validated.strategy.ranking == []
    assert "composite_score" not in report.unsupported_features
    assert not any("composite_score" in e for e in report.errors)
    parsed, _dropped, _pending = compile_partial(validated, report, "")
    assert parsed.ranking_metric is None, "미지원 랭킹이 수익률 랭킹으로 둔갑"
    assert parsed.ranking_quantile_groups is None


def test_unsupported_ranking_reports_user_expression_when_available():
    validated, report = run_validation(_intent([
        {"metric": "composite_score", "source_text": "순위를 합산하여"},
    ]))
    assert report.unsupported_features == ["순위를 합산하여"]


def test_composite_with_price_component_asks_lookback_at_any_index():
    """수익률 구성 지표가 두 번째 자리에 있어도 산정 기간을 묻는다(조용한 60일 확정 금지)."""
    validated, report = run_validation(_intent([
        {"metric": "fundamental.per", "direction": "bottom"},
        {"metric": "return"},
    ]))
    fields = [q.field for q in report.clarification_questions]
    assert "strategy.ranking[1].lookback_days" in fields, fields


def test_composite_price_component_inherits_strategy_lookback():
    """되묻기 칩 답은 전략 공통 ranking_lookback_days로 결속된다 — 디컴파일이 그 값을
    구성 지표에 이어받아 재컴파일에서 산정 기간을 다시 묻지 않는다."""
    parsed = ParsedStrategy(
        description="PER 낮은 순 + 수익률 순위 합산", universe=["KOSPI"],
        ranking_metric="composite", ranking_lookback_days=20,
        ranking_components=[
            {"metric": "per", "direction": "bottom"},
            {"metric": "return", "direction": "top"},
        ],
    )
    spec = decompile_strategy(parsed)
    assert spec.ranking[1].metric == "ranking.return"
    assert spec.ranking[1].lookback_days == 20


def test_parsed_strategy_composite_requires_two_components():
    with pytest.raises(ValueError):
        ParsedStrategy(
            description="x", universe=["KOSPI"], ranking_metric="composite",
            ranking_components=[{"metric": "per", "direction": "bottom"}],
        )
    # 단일 랭킹으로 바뀌면 남은 구성 지표는 비운다.
    p = ParsedStrategy(
        description="x", universe=["KOSPI"], ranking_metric="per",
        ranking_components=[
            {"metric": "per", "direction": "bottom"}, {"metric": "pbr", "direction": "bottom"},
        ],
    )
    assert p.ranking_components is None
