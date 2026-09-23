"""F-score(피오트로스키, f_score)·팩터 IC 통계(factorIc) — 엔진 v16.26 회귀.

F-score: 연간 as-of 재무 시계열과 365일 전 값으로 9항목을 세고, 전년 값이 없는 첫해는 NaN(부분 점수 금지).
IC: 리밸런싱일 점수 순위 vs 다음 리밸런싱일까지 수익률 순위의 스피어만 상관 — 유효 기간 2개 미만이면 None.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest_engine import BacktestEngine
from engine.fundamental_fetcher import F_SCORE_COLUMNS, recompute_f_score
from strategy_conversation.registry.indicator_registry import resolve
from strategy_conversation.registry.concept_ontology import natural_ranking_direction


def _two_years(y1: dict, y2: dict) -> pd.DataFrame:
    d1 = pd.bdate_range("2023-01-02", "2023-12-29")
    d2 = pd.bdate_range("2024-01-02", "2024-12-31")
    rows = {"date": list(d1) + list(d2)}
    for col in F_SCORE_COLUMNS[1:]:
        rows[col] = [y1[col]] * len(d1) + [y2[col]] * len(d2)
    return pd.DataFrame(rows)


_GOOD_Y1 = dict(roa=3.0, operating_cf_amount=90.0, net_income=100.0, debt_ratio=60.0, current_ratio=120.0,
                gross_margin=20.0, revenue=1000.0, total_equity=500e8, market_cap=1000.0, close=10000.0)
# 둘째 해: ROA↑·영업CF>순이익·부채비율↓·유동비율↑·주식수 동일·매출총이익률↑·자산회전율↑ → 9점
_GOOD_Y2 = dict(roa=5.0, operating_cf_amount=150.0, net_income=120.0, debt_ratio=50.0, current_ratio=150.0,
                gross_margin=25.0, revenue=1400.0, total_equity=520e8, market_cap=1200.0, close=12000.0)


def test_f_score_counts_nine_when_every_test_passes_and_nan_in_first_year():
    out = recompute_f_score(_two_years(_GOOD_Y1, _GOOD_Y2)).set_index("date")["f_score"]
    assert np.isnan(out.loc["2023-06-01"])                 # 전년 값 없음 → NaN
    assert out.loc["2024-06-03"] == 9.0


def test_f_score_drops_points_for_failed_tests():
    y2 = dict(_GOOD_Y2, roa=-1.0, operating_cf_amount=-5.0, market_cap=1500.0)   # ROA<0·CF<0·ΔROA<0·CF<NI·신주(주식수 25%↑)
    out = recompute_f_score(_two_years(_GOOD_Y1, y2)).set_index("date")["f_score"]
    assert out.loc["2024-06-03"] == 4.0                      # 부채↓·유동비율↑·매출총이익률↑·회전율↑만 남는다


def test_f_score_registry_alias_and_direction():
    assert resolve("피오트로스키").id == "fundamental.f_score"
    assert resolve("F-score").id == "fundamental.f_score"
    assert resolve("알트만").id == "unsupported.quality_score"
    assert natural_ranking_direction("fundamental.f_score") == "top"


# ── 팩터 IC ───────────────────────────────────────────────────────────────────

def _panel(n_days=40, syms=("A", "B", "C", "D", "E", "F", "G", "H", "I", "J"), slope=1.0):
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    rng = np.random.default_rng(1)
    score = pd.DataFrame({s: float(k) for k, s in enumerate(syms)}, index=idx)
    # 점수가 높을수록 매 구간 수익률이 큰 가격 경로(기울기 slope), 약간의 잡음
    px = {}
    for k, s in enumerate(syms):
        rets = slope * 0.01 * k / len(syms) + rng.normal(0, 0.0005, n_days)
        px[s] = 100.0 * np.cumprod(1.0 + rets)
    return score, pd.DataFrame(px, index=idx), idx


def test_factor_ic_is_positive_when_score_predicts_forward_return():
    score, px, idx = _panel()
    rebalance = np.zeros(len(idx), dtype=bool)
    rebalance[::5] = True                                    # 5거래일마다
    out = BacktestEngine._factor_ic_stats(score, px, rebalance)
    assert out is not None and out["periods"] >= 6
    assert out["meanIc"] > 0.8 and out["positiveRate"] == 1.0
    assert out["topBottomSpread"] > 0
    assert out["icir"] is None or out["icir"] > 0


def test_factor_ic_flips_sign_for_inverse_relation_and_none_when_too_few_periods():
    score, px, idx = _panel(slope=-1.0)
    rebalance = np.zeros(len(idx), dtype=bool)
    rebalance[::5] = True
    out = BacktestEngine._factor_ic_stats(score, px, rebalance)
    assert out["meanIc"] < -0.8 and out["topBottomSpread"] < 0
    only_one = np.zeros(len(idx), dtype=bool); only_one[0] = True; only_one[-1] = True
    assert BacktestEngine._factor_ic_stats(score, px, only_one) is None   # 유효 기간 1개
    assert BacktestEngine._factor_ic_stats(None, px, rebalance) is None
