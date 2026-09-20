"""FCF 수익률·연속 배당 연수 지표 신설(엔진 v16.15, 2026-09-20) 배선 회귀.

사고: 배당·FCF Yield 전략에서 "잉여현금흐름수익률(FCF Yield)"이 미지원(→ FCF 마진 근사)으로,
"최근 3년 연속 배당"이 미지원 안내로만 남았다. 재료(잉여현금흐름 raw·일별 시가총액·ex-date별
주당배당)는 parquet에 이미 있었으므로 지표를 만들어 반영한다.
"""
import numpy as np
import pandas as pd
import polars as pl

from engine.fundamental_fetcher import recompute_fcf_yield
from engine.nl_parser import FundamentalFilter
from engine.signals import FUNDAMENTAL_LABELS
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry.concept_ontology import ontology_prompt_sections
from strategy_conversation.registry.indicator_registry import REGISTRY, resolve
from strategy_conversation.validation.pipeline import run_validation


def test_recompute_fcf_yield_definition_and_guards():
    """FCF 수익률(%) = fcf(원) ÷ (market_cap 억원 × 1e8) × 100. 시총 비양수·결측은 null, 음의 FCF는 음수."""
    df = pd.DataFrame({
        "market_cap": [1000.0, 1000.0, 0.0, np.nan, 2000.0],
        "fcf": [5e9, -2e9, 5e9, 5e9, np.nan],
    })
    out = recompute_fcf_yield(df)
    assert out["fcf_yield"].iloc[0] == 5.0
    assert out["fcf_yield"].iloc[1] == -2.0
    assert np.isnan(out["fcf_yield"].iloc[2]) and np.isnan(out["fcf_yield"].iloc[3])
    assert np.isnan(out["fcf_yield"].iloc[4])
    # 컬럼이 없으면 no-op
    assert "fcf_yield" not in recompute_fcf_yield(pd.DataFrame({"close": [1.0]})).columns


def test_data_resolver_computes_both_metrics_from_existing_columns():
    """parquet에 새 컬럼이 없어도(백필 전) 기존 컬럼(fcf·market_cap·dividends·date)에서 런타임 계산한다."""
    from engine.data_resolver import DataResolver

    idx = pd.date_range("2021-01-04", "2023-06-30", freq="B")
    div = np.zeros(len(idx))
    for d in ("2021-12-29", "2022-12-28"):
        div[idx.get_loc(pd.Timestamp(d))] = 100.0
    df_pl = pl.DataFrame({
        "date": idx.to_pydatetime().tolist(),
        "close": np.full(len(idx), 50000.0),
        "market_cap": np.full(len(idx), 1000.0),
        "fcf": np.full(len(idx), 5e9),
        "dividends": div,
    })
    resolver = DataResolver()
    missing = {"fcf_yield", "dividend_streak_years"}
    df_pl = resolver._resolve_computable_ratios("000000", df_pl, missing)
    df_pl = resolver._resolve_dividend_metrics("000000", df_pl, missing)
    assert missing == set()
    assert df_pl["fcf_yield"][0] == 5.0
    last = df_pl.filter(pl.col("date") == pl.lit(pd.Timestamp("2023-06-30")))
    assert last["dividend_streak_years"][0] == 2.0


def test_registry_ontology_and_engine_vocabulary_include_new_metrics():
    for factor_id, engine_key in (
        ("fundamental.fcf_yield", "fcf_yield"),
        ("fundamental.dividend_streak_years", "dividend_streak_years"),
    ):
        spec = REGISTRY[factor_id]
        assert spec.supported != "UNSUPPORTED" and not spec.data_pending
        assert spec.engine_binding == ("fundamental_filter", engine_key)
        assert engine_key in FUNDAMENTAL_LABELS
        FundamentalFilter(metric=engine_key, operator=">=", value=1.0)  # 엔진 스키마가 받는다
    rendered = "\n".join(ontology_prompt_sections())
    assert "fundamental.fcf_yield" in rendered and "fundamental.dividend_streak_years" in rendered
    assert "unsupported.fcf_yield" not in rendered
    # 사용자 표기 별칭 → 정본
    assert resolve("연속 배당").id == "fundamental.dividend_streak_years"
    assert resolve("연속 배당 연수").id == "fundamental.dividend_streak_years"
    assert resolve("FCF Yield").id == "fundamental.fcf_yield"
    assert resolve("잉여현금흐름수익률").id == "fundamental.fcf_yield"
    # 마진·증가율은 그대로 각자 지표
    assert resolve("잉여현금흐름마진").id == "fundamental.fcf_margin"
    assert resolve("잉여현금흐름증가율").id == "fundamental.fcf_growth"


def test_conditions_on_new_metrics_validate_and_compile():
    from strategy_conversation.compiler.strategy_compiler import compile_strategy

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": []},
            "entry_conditions": [
                {"factor": "fundamental.dividend_streak_years", "operator": ">=", "value": 3,
                 "source_text": "최근 3년 연속 배당을 지급한"},
                {"factor": "fundamental.fcf_yield", "operator": ">=", "value": 5,
                 "source_text": "잉여현금흐름수익률(FCF Yield)이 5% 이상"},
            ],
            "exit_conditions": [],
            "ranking": [{"metric": "fundamental.fcf_yield", "direction": "top"}],
            "portfolio": {"selection_count": 30, "rebalance_frequency": "quarterly"},
            "risk_management": {},
            "backtest": {"period": "3y"},
        },
    })
    validated, report = run_validation(intent)
    assert report.unsupported_features == [] and report.preparing_features == []
    assert [c.factor for c in validated.strategy.entry_conditions] == [
        "fundamental.dividend_streak_years", "fundamental.fcf_yield",
    ]
    parsed = compile_strategy(validated, report, "최근 3년 연속 배당을 지급한 FCF Yield 5% 이상 상위 30")
    assert {(f.metric, f.operator, f.value) for f in parsed.fundamental_filters} == {
        ("dividend_streak_years", ">=", 3.0), ("fcf_yield", ">=", 5.0),
    }
    assert parsed.ranking_metric == "fcf_yield"
