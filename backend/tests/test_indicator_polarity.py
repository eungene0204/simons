"""지표 자연 방향(polarity) — 선언 무결성 + 랭킹 방향 기본값 교정.

배경: 랭킹 방향의 부호 지식이 엔진 표현식 한 줄(backtest_engine의 합성 랭킹
`1.0 - pbr_rank` / `roe_rank`)에만 존재했고, `RankingSpec.direction`은 default="top"
이라 **LLM이 방향을 말하지 않은 것**과 사용자가 높은 순을 지정한 것이 구별되지 않았다.
그 결과 'PER 기준 20종목'처럼 방향이 빠진 요청이 조용히 top으로 떨어져 저평가 전략이
'가장 비싼 종목 선정'으로 뒤집혔다. 온톨로지 polarity가 그 지식의 정본이다.
"""

import pytest

from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry.concept_ontology import (
    HIGHER_BETTER,
    LOWER_BETTER,
    POLARITY_NONE,
    get_ontology,
    natural_ranking_direction,
    polarity_of,
)
from strategy_conversation.registry.indicator_registry import _SPECS
from strategy_conversation.validation.pipeline import run_validation


def _ranking_intent(metric: str, direction=None, **overrides):
    ranking = {"metric": metric}
    if direction is not None:
        ranking["direction"] = direction
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": []},
        "entry_conditions": [], "exit_conditions": [],
        "ranking": [ranking],
        "portfolio": {"selection_count": 20, "rebalance_frequency": "monthly"},
        "risk_management": {}, "backtest": {},
    }
    strategy.update(overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy,
    })


def _compile(metric: str, direction=None):
    validated, report = run_validation(_ranking_intent(metric, direction))
    assert report.is_valid, report.errors
    return compile_strategy(validated, report, "랭킹 전략")


# ─── 선언 무결성 ────────────────────────────────────────────────────────────────

def test_every_supported_leaf_declares_polarity():
    """지원 잎은 전수 명시 — 침묵은 '선언 누락'과 '방향 없음'을 구별할 수 없게 만든다."""
    ontology = get_ontology()
    for spec in _SPECS:
        if spec.supported == "UNSUPPORTED":
            continue
        assert spec.id in ontology.polarity, f"polarity 미선언: {spec.id}"


def test_polarity_values_and_no_ghost_keys():
    ontology = get_ontology()
    for leaf, value in ontology.polarity.items():
        assert value in (LOWER_BETTER, HIGHER_BETTER, POLARITY_NONE)
        assert any(s.id == leaf for s in _SPECS), f"Registry에 없는 유령 키: {leaf}"
    assert list(ontology.issues) == []


def test_valuation_is_lower_better_profitability_is_higher():
    """가치 지표는 낮을수록, 수익성·성장은 높을수록 선호 — 합성 시 부호의 정본."""
    for metric in ("fundamental.per", "fundamental.pbr", "fundamental.debt_ratio"):
        assert polarity_of(metric) == LOWER_BETTER
    for metric in ("fundamental.roe_or_gpa", "fundamental.operating_margin",
                   "fundamental.revenue_growth", "ranking.return"):
        assert polarity_of(metric) == HIGHER_BETTER


def test_ambiguous_metrics_declared_none_not_forced():
    """선호 방향이 없는 지표는 억지로 방향을 만들지 않는다 — 틀린 방향이 더 나쁘다.

    시가총액(대형/소형은 선호지 우열 아님), 배당성향(높으면 배당↑ 재투자↓),
    투자·재무활동 현금흐름(성장기업은 음수가 정상), 오실레이터(과매도 매수 vs
    과매수 추종이 정반대).
    """
    for metric in ("fundamental.market_cap", "fundamental.payout_rate",
                   "fundamental.investing_cf_amount", "fundamental.financing_cf_amount",
                   "technical.rsi", "technical.ma_crossover"):
        assert polarity_of(metric) == POLARITY_NONE
        assert natural_ranking_direction(metric) is None


# ─── 랭킹 방향 기본값 교정 ──────────────────────────────────────────────────────

def test_unspecified_direction_uses_natural_direction():
    """방향 미지정 'PER 기준 20종목' → bottom(낮은 순). 종전엔 조용히 top이었다."""
    parsed = _compile("fundamental.per")
    assert parsed.ranking_metric == "per"
    assert parsed.ranking_direction == "bottom"


def test_unspecified_direction_higher_better_stays_default():
    """높을수록 선호 지표는 top이 자연 방향 — top은 엔진 기본값이라 저장하지 않는다
    (방향 미지정 기존 전략의 strategy_id 불변 계약 유지)."""
    parsed = _compile("fundamental.operating_margin")
    assert parsed.ranking_metric == "operating_margin"
    assert parsed.ranking_direction is None


def test_explicit_direction_wins_over_polarity():
    """사용자가 방향을 말했으면 그대로 — 자연 방향이 덮어쓰지 않는다.

    'PER 높은 순'을 일부러 원하는 연구도 가능하다. polarity는 침묵을 채우는 것이지
    사용자 판정을 재심하는 장치가 아니다.
    """
    assert _compile("fundamental.per", direction="top").ranking_direction is None
    assert _compile("fundamental.operating_margin", direction="bottom").ranking_direction == "bottom"


def test_polarity_none_metric_keeps_previous_behavior():
    """자연 방향이 없는 지표(시가총액)는 종전대로 방향 미저장 — 억지 방향 금지."""
    parsed = _compile("fundamental.market_cap")
    assert parsed.ranking_metric == "market_cap"
    assert parsed.ranking_direction is None


def test_direction_default_is_none_not_top():
    """모델 기본값이 None이어야 '미언급'을 감지할 수 있다(물질화 기본값 둔갑 방지)."""
    intent = _ranking_intent("fundamental.per")
    assert intent.strategy.ranking[0].direction is None


# ─── 프롬프트 계약 ──────────────────────────────────────────────────────────────

def test_prompt_annotates_polarity_and_direction_rule():
    from strategy_conversation.interpreter.prompts import PROMPT_VERSION, build_system_prompt

    assert PROMPT_VERSION >= "3.2"
    prompt = build_system_prompt()
    assert "[낮을수록 선호]" in prompt and "[높을수록 선호]" in prompt
    assert "direction은 사용자가 정렬 방향을 말했을 때만" in prompt
    # 방향 없는 지표에는 병기하지 않는다(어휘 비대 방지)
    rsi_line = next(l for l in prompt.splitlines() if l.startswith("- technical.rsi "))
    assert "선호]" not in rsi_line
