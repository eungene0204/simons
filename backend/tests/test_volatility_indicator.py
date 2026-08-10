"""변동성 지표 지원 승격(엔진 v13.1) 회귀 테스트.

배경: '변동성이 낮은 종목에 투자하는 전략'이 미지원 개념이라 빈 빌더로 흘렀다
(2026-08-10). 표준편차는 OHLCV로 계산 가능하지만 엔진 지표·랭킹 배선이 없어
레지스트리에 UNSUPPORTED로 등록돼 있었다. 이 파일은 승격된 배선 전체를 고정한다:
① IndicatorEngine/SignalEngine의 volatility 조건(연환산 %, KRX 실측 √246),
② ranking_metric='volatility'의 방향 계약(기본 bottom — 무언의 top이면 고변동성
선정으로 전략이 뒤집힌다), ③ 레지스트리/온톨로지/컴파일러의 canonical 매핑,
④ 미지원 안내 채널의 표현-제외 술어(반영됐는데 "미지원" 안내가 나가는 모순 방지).
"""

import numpy as np
import polars as pl
import pytest

from engine.indicators import IndicatorEngine
from engine.result_handler import KRX_TRADING_DAYS_PER_YEAR
from engine.signals import SignalEngine


def _ohlcv(close: np.ndarray) -> pl.DataFrame:
    n = len(close)
    dates = pl.date_range(
        pl.date(2024, 1, 1),
        pl.date(2024, 1, 1) + pl.duration(days=n - 1),
        interval="1d",
        eager=True,
    )
    return pl.DataFrame({
        "date": dates,
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.full(n, 1_000_000.0),
    })


def _series(daily_std: float, n: int = 200, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 10000 * np.cumprod(1 + rng.normal(0, daily_std, n))


_COND = {
    "id": "volatility",
    "params": {"period": 60, "operator": "<=", "value": 30, "signalType": "buy"},
}


def test_indicator_engine_computes_annualized_volatility_column():
    df = _ohlcv(_series(0.005))
    out = IndicatorEngine.calculate(df, [_COND])
    assert "volatility_60" in out.columns
    vol = out["volatility_60"].to_list()
    # 롤링 창(60) 이전은 NaN — 0 동률로 위장하면 안 된다.
    assert vol[59] is None or (isinstance(vol[59], float) and np.isnan(vol[59]))
    # 일 0.5% std → 연환산 ≈ 0.5% × √246 ≈ 7.8% 부근(합성 표본 오차 허용).
    assert vol[-1] == pytest.approx(0.5 * np.sqrt(KRX_TRADING_DAYS_PER_YEAR), rel=0.35)


def test_low_volatility_fires_and_high_volatility_does_not():
    engine = SignalEngine()
    low = IndicatorEngine.calculate(_ohlcv(_series(0.005)), [_COND])
    sig_low, reasons = engine.generate_signals(low, {"conditions": [_COND]})
    assert sig_low.sum() > 0
    assert not sig_low[:60].any()  # NaN 워밍업 구간은 신호 금지
    assert "변동성" in next(r for r in reasons if r)

    high = IndicatorEngine.calculate(_ohlcv(_series(0.04)), [_COND])
    sig_high, _ = engine.generate_signals(high, {"conditions": [_COND]})
    assert sig_high.sum() == 0


def test_condition_description_mentions_annualized_percent():
    desc = SignalEngine().get_condition_description(_COND)
    assert "변동성" in desc and "60일" in desc and "30" in desc and "이하" in desc


def test_tech_signal_to_condition_maps_volatility():
    from engine.nl_parser import TechnicalSignal
    from engine.strategy_converter import _tech_signal_to_condition

    cond = _tech_signal_to_condition(TechnicalSignal(
        indicator="volatility", signal_type="buy", period=60, operator="<=", value=25,
    ))
    assert cond["id"] == "volatility"
    assert cond["params"]["period"] == 60
    assert cond["params"]["operator"] == "<="
    assert cond["params"]["value"] == 25


def test_registry_promotion_and_aliases():
    from strategy_conversation.registry.indicator_registry import REGISTRY, resolve

    assert REGISTRY["technical.volatility"].supported == "SUPPORTED"
    assert REGISTRY["ranking.volatility"].supported == "SUPPORTED"
    assert "unsupported.volatility" not in REGISTRY
    assert resolve("변동성").id == "technical.volatility"
    assert resolve("volatility").id == "technical.volatility"
    assert resolve("저변동성").id == "ranking.volatility"


def test_natural_direction_is_bottom():
    from strategy_conversation.registry.concept_ontology import natural_ranking_direction

    assert natural_ranking_direction("ranking.volatility") == "bottom"


# ─── 컴파일 계약 ────────────────────────────────────────────────────────────────

def _ranking_intent(metric: str, direction=None, lookback_days=None):
    from strategy_conversation.interpreter.models import StrategyIntent

    ranking = {"metric": metric}
    if direction is not None:
        ranking["direction"] = direction
    if lookback_days is not None:
        ranking["lookback_days"] = lookback_days
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            "entry_conditions": [], "exit_conditions": [],
            "ranking": [ranking],
            "portfolio": {"selection_count": 20, "rebalance_frequency": "monthly"},
            "risk_management": {}, "backtest": {},
        },
    })


def _compile(metric: str, direction=None):
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.validation.pipeline import run_validation

    # 산정 기간은 명시한다 — 미지정이면 되묻기(NEEDS_CLARIFICATION)가 정상 동작이라
    # 컴파일까지 가지 않는다(test_volatility_ranking_asks_lookback_when_unspecified).
    validated, report = run_validation(_ranking_intent(metric, direction, lookback_days=60))
    assert report.is_valid, report.errors
    return compile_strategy(validated, report, "변동성 랭킹 전략")


def test_compile_volatility_ranking_defaults_to_bottom():
    parsed = _compile("ranking.volatility")
    assert parsed.ranking_metric == "volatility"
    assert parsed.ranking_direction == "bottom"


def test_compile_volatility_ranking_explicit_top_is_stored():
    """엔진 기본 방향이 bottom이므로 명시적 top을 None으로 접으면 뒤집힌다."""
    parsed = _compile("ranking.volatility", direction="top")
    assert parsed.ranking_direction == "top"


def test_compile_return_ranking_direction_unchanged():
    """모멘텀 랭킹의 방향 저장 규칙(기본 top=None 저장)은 종전과 동일해야 한다(해시 불변)."""
    parsed = _compile("return")
    assert parsed.ranking_metric == "return"
    assert parsed.ranking_direction is None


def test_compile_volatility_threshold_condition():
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.pipeline import run_validation

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            "entry_conditions": [{
                "factor": "변동성", "operator": "<=", "value": 30,
                "source_text": "변동성 30% 이하",
            }],
            "exit_conditions": [], "ranking": [],
            "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
            "risk_management": {}, "backtest": {},
        },
    })
    validated, report = run_validation(intent)
    assert report.is_valid, report.errors
    assert not report.unsupported_features
    parsed = compile_strategy(validated, report, "변동성 30% 이하 종목")
    assert [(s.indicator, s.operator, s.value) for s in parsed.entry_signals] == [
        ("volatility", "<=", 30.0)
    ]


def test_volatility_panel_excludes_backfilled_new_listings():
    """[회귀] 2022-07-01 실측(v13.2) — 상장 21일째 종목이 '120거래일 변동성 하위 7%'로
    매수됐다. 원인: 엔진 price_df의 bfill이 상장 전 구간을 첫 가격으로 평평하게 채워
    수익률 0 → 변동성이 0으로 위장. 패널 계산은 bfill 전 원시 가격을 받아 관측치
    lookback개 미만이면 NaN(후보 배제)이어야 한다."""
    import pandas as pd

    from engine.indicators import annualized_volatility_panel

    n, lookback = 200, 120
    idx = pd.RangeIndex(n)
    rng = np.random.default_rng(1)
    old = pd.Series(10000 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=idx)
    # 신규 상장: 마지막 21일만 데이터 존재(그 전은 NaN — 엔진 raw_price_df 형태)
    newly = pd.Series(np.nan, index=idx)
    newly.iloc[-21:] = 5000 * np.cumprod(1 + rng.normal(0, 0.001, 21))
    raw = pd.DataFrame({"OLD": old, "NEW": newly})

    vol = annualized_volatility_panel(raw, lookback)
    assert np.isfinite(vol["OLD"].iloc[-1])
    # 관측치 21개뿐인 신규 상장 종목은 120일 변동성이 정의되지 않는다.
    assert np.isnan(vol["NEW"].iloc[-1])

    # 오염 경로 재현: bfill된 패널을 넘기면 신규 상장이 '초저변동'으로 위장된다 —
    # 엔진이 raw를 넘겨야 하는 이유(이 단언이 깨지면 bfill 위장 자체가 사라진 것).
    contaminated = annualized_volatility_panel(raw.ffill().bfill(), lookback)
    assert contaminated["NEW"].iloc[-1] < vol["OLD"].iloc[-1]


def test_volatility_ranking_asks_lookback_when_unspecified():
    """산정 기간을 말하지 않으면 묻는다(2026-08-10 사용자 요청) — 기본 60일을 조용히
    확정하지 않는다. 기간을 말했으면 묻지 않는다."""
    from strategy_conversation.validation.completeness_validator import validate_completeness

    _missing, questions = validate_completeness(_ranking_intent("ranking.volatility"))
    lookback_qs = [q for q in questions if q.field == "strategy.ranking[0].lookback_days"]
    assert len(lookback_qs) == 1
    assert lookback_qs[0].recommended_value == 60

    intent = _ranking_intent("ranking.volatility")
    intent.strategy.ranking[0].lookback_days = 120
    _missing2, questions2 = validate_completeness(intent)
    assert not [q for q in questions2 if q.field == "strategy.ranking[0].lookback_days"]

    # 모멘텀('return') 랭킹은 기존 계약(60일 물질화) 그대로 — 묻지 않는다.
    _missing3, questions3 = validate_completeness(_ranking_intent("return"))
    assert not [q for q in questions3 if "lookback" in q.field]


def test_volatility_lookback_chip_echo_binds_deterministically():
    """칩 정본 표기('변동성 산정 기간 120일')는 _apply_prompt_overrides가 결정적으로
    ranking_lookback_days에 자리 배정한다(칩=값 결속 계약)."""
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    base = ParsedStrategy(
        description="변동성 낮은 종목", universe=["KOSPI"], ranking_metric="volatility",
    )
    after = _apply_prompt_overrides(
        base, "변동성 산정 기간 120일",
        skip_signal_validation=True, preserve_universe=True,
    )
    assert after.ranking_lookback_days == 120
    assert after.ranking_metric == "volatility"  # 다른 필드는 건드리지 않는다


def test_percentile_condition_moves_to_selection_percent():
    """백분위 드리프트 백스톱(2026-08-10): LLM이 '변동성 하위 10%만 편입'의 10을
    portfolio.selection_percent가 아니라 랭킹 조건 value(unit percentile)로 실으면,
    조건 이동·소거 때 편입 규모가 조용히 사라진다 — 검증기가 자리만 옮겨야 한다."""
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.pipeline import run_validation

    def intent_with_percentile_condition(unit, selection_count=None):
        return StrategyIntent.model_validate({
            "intent": "CREATE_STRATEGY", "confidence": 0.9,
            "strategy": {
                "universe": {"markets": ["KOSPI"], "sectors": []},
                "entry_conditions": [{
                    "factor": "ranking.volatility", "operator": "<=", "value": 20,
                    "unit": unit, "source_text": "변동성이 가장 낮은 상위 20%",
                }],
                "exit_conditions": [], "ranking": [],
                "portfolio": {"selection_count": selection_count,
                              "rebalance_frequency": "monthly"},
                "risk_management": {}, "backtest": {},
            },
        })

    validated, report = run_validation(intent_with_percentile_condition("percentile"))
    # 산정 기간 미지정이라 되묻기(NEEDS_CLARIFICATION)는 정상 — 오류만 없으면 된다.
    assert not report.errors, report.errors
    assert validated.strategy.ranking[0].metric == "ranking.volatility"
    assert validated.strategy.portfolio.selection_percent == 20.0

    # 사용자가 이미 종목 수를 말했으면 덮지 않는다.
    validated2, _ = run_validation(intent_with_percentile_condition("percentile", selection_count=5))
    assert validated2.strategy.portfolio.selection_percent is None
    assert validated2.strategy.portfolio.selection_count == 5

    # unit 없는 맨 값은 연환산 % 임계값과 구별 불가 — 옮기지 않는다.
    validated3, _ = run_validation(intent_with_percentile_condition(None))
    assert validated3.strategy.portfolio.selection_percent is None


def test_unsupported_notice_suppressed_when_expressed():
    """변동성이 전략에 반영됐으면 '미지원' 안내가 함께 나가면 모순이다(표현-제외 술어)."""
    from engine.nl_parser import (
        ParsedStrategy,
        _mentioned_unsupported_concepts,
        concepts_expressed_in_strategy,
    )

    # 큐 자체는 남아 있어야 한다 — 결정적 추출기는 변동성을 표현하지 못하므로
    # 규칙 기반 레인이 자신을 불신하고 LLM에 위임하는 신호다(pcr와 동형).
    assert "volatility" in _mentioned_unsupported_concepts("변동성이 낮은 종목에 투자")

    ranked = ParsedStrategy(
        description="변동성 낮은 종목", universe=["KOSPI"], ranking_metric="volatility",
    )
    assert "volatility" in concepts_expressed_in_strategy(ranked, "변동성이 낮은 종목")

    filtered = ParsedStrategy.model_validate({
        "description": "변동성 30% 이하", "universe": ["KOSPI"],
        "entry_signals": [{
            "indicator": "volatility", "signal_type": "buy",
            "period": 60, "operator": "<=", "value": 30,
        }],
    })
    assert "volatility" in concepts_expressed_in_strategy(filtered, "변동성 30% 이하")

    plain = ParsedStrategy(description="RSI 전략", universe=["KOSPI"])
    assert "volatility" not in concepts_expressed_in_strategy(plain, "변동성 낮게")
