"""NCAV(ncav_ratio)·분기 성장률 6종 — 엔진 v16.27 회귀(수집 파서·파생·런타임·등록)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine import quarterly_earnings as qe
from engine.data_resolver import DataResolver
from engine.fundamental_fetcher import (
    _compute_derived_annual_metrics, compute_ncav, parse_dart_ncav_inputs, recompute_ncav_ratio,
)
from strategy_conversation.registry.indicator_registry import resolve
from strategy_conversation.registry.concept_ontology import natural_ranking_direction


def _bs(account_id, amount, sj="BS"):
    return {"sj_div": sj, "account_id": account_id, "account_nm": account_id, "account_detail": "-",
            "thstrm_amount": str(amount)}


def test_ncav_inputs_parse_and_derive():
    rows = [_bs("ifrs-full_CurrentAssets", 5_000), _bs("ifrs-full_Liabilities", 3_000),
            _bs("ifrs-full_Equity", 4_000)]
    assert parse_dart_ncav_inputs(rows) == {"current_assets": 5000.0, "total_liabilities": 3000.0}
    assert compute_ncav(5000, 3000) == 2000.0 and compute_ncav(None, 3000) is None
    recs = _compute_derived_annual_metrics([{"year_end": "2024-12-31", "current_assets": 5000.0,
                                             "total_liabilities": 3000.0}])
    assert recs[0]["ncav"] == 2000.0


def test_ncav_ratio_is_market_cap_over_ncav_and_nan_when_ncav_nonpositive():
    df = pd.DataFrame({"market_cap": [100.0, 100.0, 100.0], "ncav": [200e8, -5e8, np.nan]})
    out = recompute_ncav_ratio(df)["ncav_ratio"].tolist()
    assert out[0] == pytest.approx(50.0) and np.isnan(out[1]) and np.isnan(out[2])


def test_quarterly_income_rows_and_q4_derivation(monkeypatch):
    """분기 3개 + 연간 1개 응답에서 EPS와 손익 3항목을 받고 4분기는 연간 − 3분기 누적."""
    def rows(eps, eps_cum, rev, rev_cum, rcept="20240515000000"):
        return [
            {"sj_div": "IS", "account_id": "ifrs-full_BasicEarningsLossPerShare", "account_detail": "-",
             "thstrm_amount": str(eps), "thstrm_add_amount": str(eps_cum), "rcept_no": rcept},
            {"sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_detail": "-",
             "thstrm_amount": str(rev), "thstrm_add_amount": str(rev_cum), "rcept_no": rcept},
            {"sj_div": "IS", "account_id": "dart_OperatingIncomeLoss", "account_detail": "-",
             "thstrm_amount": str(rev // 10), "thstrm_add_amount": str(rev_cum // 10), "rcept_no": rcept},
        ]
    responses = {"11013": rows(100, 100, 1000, 1000), "11012": rows(110, 210, 1100, 2100),
                 "11014": rows(120, 330, 1200, 3300), "11011": rows(500, 500, 5000, 5000, "20250320000000")}
    monkeypatch.setattr(qe, "_fetch_report_rows", lambda c, y, code, fs: responses.get(code))
    monkeypatch.setattr(qe, "_BASIC_EPS_ACCOUNT_IDS", {"ifrs-full_BasicEarningsLossPerShare"}, raising=False)
    got = qe._collect_year("X", 2024, "CFS")
    assert got[1]["income"] == {"revenue": 1000.0, "operating_income": 100.0}
    assert got[4]["eps"] == pytest.approx(170.0)
    assert got[4]["income"] == {"revenue": 1700.0, "operating_income": 170.0}


def test_quarterly_growth_events_qoq_and_yoy_match_by_date_and_skip_nonpositive_base():
    recs = [
        {"period_end": "2023-03-31", "announce_date": "2023-05-15", "revenue": 100.0},
        {"period_end": "2023-06-30", "announce_date": "2023-08-14", "revenue": 120.0},
        {"period_end": "2023-12-31", "announce_date": "2024-03-20", "revenue": 150.0},   # 3분기 없음
        {"period_end": "2024-03-31", "announce_date": "2024-05-15", "revenue": 130.0},
        {"period_end": "2024-06-30", "announce_date": "2024-08-14", "revenue": -10.0},
        {"period_end": "2024-09-30", "announce_date": "2024-11-14", "revenue": 50.0},
    ]
    qoq = dict((d.strftime("%Y-%m-%d"), v) for d, v in qe.quarterly_growth_events(recs, "revenue", "qoq"))
    assert qoq["2023-08-14"] == pytest.approx(20.0)
    assert "2024-03-20" not in qoq                     # 직전 분기(9월) 없음 → 위치가 아니라 날짜로 판단
    assert qoq["2024-05-15"] == pytest.approx(130 / 150 * 100 - 100)
    assert "2024-11-14" not in qoq                     # 기준 분기 적자
    yoy = dict((d.strftime("%Y-%m-%d"), v) for d, v in qe.quarterly_growth_events(recs, "revenue", "yoy"))
    assert yoy["2024-05-15"] == pytest.approx(30.0) and "2023-08-14" not in yoy
    ser = qe.quarterly_growth_series(recs, "revenue", "qoq", pd.bdate_range("2023-08-10", "2023-08-16"))
    assert np.isnan(ser.iloc[0]) and ser.iloc[-1] == pytest.approx(20.0)   # 발표일부터 as-of


def test_resolver_computes_quarterly_growth_from_cache(monkeypatch):
    recs = [{"period_end": "2024-03-31", "announce_date": "2024-05-15", "net_income": 100.0},
            {"period_end": "2024-06-30", "announce_date": "2024-08-14", "net_income": 150.0}]
    monkeypatch.setattr("engine.quarterly_earnings.load_quarterly_earnings", lambda s: recs)
    df = pl.DataFrame({"date": pd.bdate_range("2024-08-12", periods=5), "close": [100.0] * 5})
    out, logs = DataResolver().resolve("TEST", df, {"conditions": [
        {"type": "fundamental", "id": "net_income_growth_qoq", "params": {"operator": ">=", "value": 10}}]}, None)
    assert out["net_income_growth_qoq"].to_numpy()[-1] == pytest.approx(50.0)


def test_registry_aliases_and_directions():
    assert resolve("순유동자산").id == "fundamental.ncav_ratio"
    assert natural_ranking_direction("fundamental.ncav_ratio") == "bottom"
    assert resolve("분기 매출 성장률").id == "fundamental.revenue_growth_yoy"
    assert resolve("net_income_growth_qoq").id == "fundamental.net_income_growth_qoq"
    assert natural_ranking_direction("fundamental.revenue_growth_qoq") == "top"
