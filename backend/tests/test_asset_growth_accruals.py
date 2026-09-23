"""자산성장률(asset_growth)·발생액 비율(accruals_ratio) — 엔진 v16.25 런타임 계산·등록 회귀.

재료(자본총계·부채비율·순이익·영업현금흐름)가 parquet에 이미 있어 백필 없이 data_resolver가 계산한다
(FCF 수익률 v16.15와 같은 패턴). 둘 다 낮을수록 선호(자산성장·발생액 이상현상).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine.data_resolver import DataResolver
from engine.fundamental_fetcher import compute_total_assets, recompute_accruals_ratio, recompute_asset_growth
from engine.signals import FUNDAMENTAL_LABELS
from strategy_conversation.registry.indicator_registry import resolve
from strategy_conversation.registry.concept_ontology import natural_ranking_direction


def _annual_frame():
    """2년치 일봉: 첫해 총자산 1,000억(자본 800억·부채비율 25%), 둘째 해 1,200억(자본 1,000억·20%)."""
    d1 = pd.bdate_range("2023-01-02", "2023-12-29")
    d2 = pd.bdate_range("2024-01-02", "2024-12-31")
    df = pd.DataFrame({
        "date": list(d1) + list(d2),
        "total_equity": [800e8] * len(d1) + [1000e8] * len(d2),
        "debt_ratio": [25.0] * len(d1) + [20.0] * len(d2),
        "net_income": [100.0] * len(d1) + [150.0] * len(d2),           # 억원
        "operating_cf_amount": [80.0] * len(d1) + [60.0] * len(d2),    # 억원
    })
    return df


def test_total_assets_and_accruals_definition():
    df = _annual_frame()
    total = compute_total_assets(df)
    assert total.iloc[0] == pytest.approx(1000e8) and total.iloc[-1] == pytest.approx(1200e8)
    out = recompute_accruals_ratio(df)
    assert out["accruals_ratio"].iloc[0] == pytest.approx((100 - 80) * 1e8 / 1000e8 * 100)   # 2%
    assert out["accruals_ratio"].iloc[-1] == pytest.approx((150 - 60) * 1e8 / 1200e8 * 100)  # 7.5%


def test_asset_growth_is_year_over_year_of_asof_series():
    out = recompute_asset_growth(_annual_frame())
    g = out.set_index("date")["asset_growth"]
    assert np.isnan(g.loc["2023-06-01"])                       # 1년 전 값 없음
    assert g.loc["2024-06-03"] == pytest.approx(20.0)         # 1,200 ÷ 1,000 − 1
    assert g.loc["2024-01-02"] == pytest.approx(20.0)


def test_resolver_computes_both_when_requested_as_conditions():
    df_pl = pl.from_pandas(_annual_frame().assign(close=100.0))
    entry = {"conditions": [
        {"type": "fundamental", "id": "asset_growth", "params": {"operator": "<=", "value": 30}},
        {"type": "fundamental", "id": "accruals_ratio", "params": {"operator": "<=", "value": 5}},
    ]}
    out, logs = DataResolver().resolve("TEST", df_pl, entry, None)
    assert {"asset_growth", "accruals_ratio"} <= set(out.columns)
    assert out["accruals_ratio"].to_numpy()[-1] == pytest.approx(7.5)
    assert not any(l.get("level") == "WARN" and "미해결" in l.get("message", "") for l in logs)


def test_registry_aliases_labels_and_polarity():
    assert resolve("자산성장률").id == "fundamental.asset_growth"
    assert resolve("발생액").id == "fundamental.accruals_ratio"
    assert natural_ranking_direction("fundamental.asset_growth") == "bottom"
    assert natural_ranking_direction("fundamental.accruals_ratio") == "bottom"
    assert FUNDAMENTAL_LABELS["asset_growth"] == "자산성장률"
    assert FUNDAMENTAL_LABELS["accruals_ratio"] == "발생액 비율"
