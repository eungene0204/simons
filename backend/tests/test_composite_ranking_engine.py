"""복합 순위 합산 랭킹(FR-BT-063, 엔진 v13.4) — 점수 패널·엔진 통합 검증.

핵심 계약:
- 구성 지표마다 전 지표가 정의된 종목 풀 안에서 백분위 순위(방향 기준 좋은 쪽이 높게)를
  매겨 동일 가중 평균한다 → 순위 합산이 가장 낮은 종목이 최상위(같은 정렬).
- 어느 한 지표라도 없는 종목은 후보 제외(valid=False, 점수 0).
- 구성 지표 컬럼이 유니버스 전체에 없으면 경고로 드러낸다(조용한 0거래 금지).
- 엔진 통합: 'composite'+ranking_components로 실제 매수 종목이 합산 상위와 일치.
"""

import os

import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("polars")
pytest.importorskip("stockstats")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from backtest_engine import (  # noqa: E402
    BacktestEngine,
    _composite_ranking_components,
    _composite_ranking_label,
)


# ─── 점수 패널 단위 검증 ──────────────────────────────────────────────────────

def _fund_values(idx, syms, per_row: dict) -> dict:
    """{col: {sym: Series}} — 날짜 전 구간 상수 값."""
    return {
        col: {s: pd.Series(v, index=idx) for s, v in by_sym.items()}
        for col, by_sym in per_row.items()
    }


def test_composite_panel_equals_rank_sum_order():
    """ROE 높은 순 + PER 낮은 순 합산: 순위 합이 낮은 종목이 높은 점수를 받는다."""
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    syms = ["A", "B", "C", "D"]
    # ROE(높을수록 좋음): A=20 B=15 C=10 D=5  → 순위 A1 B2 C3 D4
    # PER(낮을수록 좋음): A=30 B=5  C=10 D=8  → 순위 B1 D2 C3 A4
    # 합산: A=5 B=3 C=6 D=6 → B > A > (C = D)
    values = _fund_values(idx, syms, {
        "roe_or_gpa": {"A": 20, "B": 15, "C": 10, "D": 5},
        "per": {"A": 30, "B": 5, "C": 10, "D": 8},
    })
    price = pd.DataFrame(100.0, index=idx, columns=syms)
    comps = [
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "per", "direction": "bottom"},
    ]
    rank_df, valid, missing = BacktestEngine._composite_rank_panel(
        comps, price, values, idx, syms, "same_close",
    )
    assert missing == []
    row = rank_df.iloc[-1]
    assert row["B"] > row["A"] > row["C"]
    assert row["C"] == pytest.approx(row["D"])
    assert bool(valid.iloc[-1].all())


def test_composite_panel_excludes_symbol_missing_any_component():
    """한 지표라도 NaN인 종목은 후보 제외(valid=False, 점수 0) — 중립값 위장 금지."""
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    syms = ["A", "B", "C"]
    values = _fund_values(idx, syms, {
        "roe_or_gpa": {"A": 20, "B": 15, "C": 10},
        "per": {"A": 30, "B": 5, "C": np.nan},
    })
    price = pd.DataFrame(100.0, index=idx, columns=syms)
    comps = [
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "per", "direction": "bottom"},
    ]
    rank_df, valid, _ = BacktestEngine._composite_rank_panel(
        comps, price, values, idx, syms, "same_close",
    )
    assert not bool(valid.iloc[-1]["C"])
    assert rank_df.iloc[-1]["C"] == 0.0
    # 남은 두 종목의 백분위는 서로만 비교된다(C 제외 풀).
    assert bool(valid.iloc[-1]["A"]) and bool(valid.iloc[-1]["B"])


def test_composite_panel_reports_missing_component_column():
    """구성 지표 컬럼이 유니버스 전체에 없으면 라벨을 돌려 호출부가 경고로 드러낸다."""
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    syms = ["A", "B"]
    values = _fund_values(idx, syms, {"roe_or_gpa": {"A": 20, "B": 15}})
    price = pd.DataFrame(100.0, index=idx, columns=syms)
    comps = [
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "pcr", "direction": "bottom"},
    ]
    rank_df, valid, missing = BacktestEngine._composite_rank_panel(
        comps, price, values, idx, syms, "same_close",
    )
    assert rank_df is None and valid is None
    assert missing == ["PCR"]


def test_composite_panel_next_open_shifts_one_day():
    """next_open은 전일 값 기준(look-ahead 방지) — 첫날 점수 0·valid False."""
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    syms = ["A", "B"]
    values = _fund_values(idx, syms, {
        "roe_or_gpa": {"A": 20, "B": 15}, "per": {"A": 30, "B": 5},
    })
    price = pd.DataFrame(100.0, index=idx, columns=syms)
    comps = [
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "per", "direction": "bottom"},
    ]
    rank_df, valid, _ = BacktestEngine._composite_rank_panel(
        comps, price, values, idx, syms, "next_open",
    )
    assert not bool(valid.iloc[0].any())
    assert float(rank_df.iloc[0].sum()) == 0.0
    assert bool(valid.iloc[1].all())


def test_composite_components_gate_requires_two_and_mode():
    assert _composite_ranking_components({"ranking_metric": "per"}) == []
    assert _composite_ranking_components({
        "ranking_metric": "composite",
        "ranking_components": [{"metric": "per", "direction": "bottom"}],
    }) == []
    comps = [
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "per", "direction": "bottom"},
    ]
    assert _composite_ranking_components({
        "ranking_metric": "composite", "ranking_components": comps,
    }) == comps


def test_composite_label_is_human_readable():
    label = _composite_ranking_label([
        {"metric": "roe_or_gpa", "direction": "top"},
        {"metric": "per", "direction": "bottom"},
        {"metric": "return", "direction": "top", "lookback_days": 20},
    ])
    assert label == "복합 순위(ROE 높은·PER 낮은·최근 20거래일 수익률 높은)"


# ─── 엔진 통합 ────────────────────────────────────────────────────────────────

def _write_series(data_dir: str, symbol: str, dates, roe: float, per: float) -> None:
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
            "volume": 5_000_000.0,
            "roe_or_gpa": roe, "per": per,
        }
        for d in dates
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def test_engine_composite_ranking_buys_rank_sum_top():
    """ROE 높은 순+PER 낮은 순 합산 상위 1종목만 편입 — 한 지표만 좋은 종목은 뽑히지 않는다."""
    dates = pd.date_range(start="2024-01-01", periods=60, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    # 순위 합산: BAL(2+2=4) < ROE_ONLY(1+4=5) = PER_ONLY(4+1=5) < WEAK(3+3=6)
    _write_series(data_dir, "CR_BAL", dates, roe=15.0, per=8.0)
    _write_series(data_dir, "CR_ROE_ONLY", dates, roe=20.0, per=30.0)
    _write_series(data_dir, "CR_PER_ONLY", dates, roe=5.0, per=5.0)
    _write_series(data_dir, "CR_WEAK", dates, roe=10.0, per=10.0)
    symbols = ["CR_BAL", "CR_ROE_ONLY", "CR_PER_ONLY", "CR_WEAK"]

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest({
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 100,
            "max_positions": 1,
            "ranking_metric": "composite",
            "ranking_components": [
                {"metric": "roe_or_gpa", "direction": "top"},
                {"metric": "per", "direction": "bottom"},
            ],
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    })
    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols == {"CR_BAL"}, f"합산 상위가 아닌 종목이 매수됨: {buy_symbols}"
    conditions = [s["condition"] for s in result["signals"] if s["type"] == "buy"]
    assert all("복합 순위(ROE 높은·PER 낮은) 상위" in c and "%" in c for c in conditions), conditions


def test_engine_composite_missing_component_warns_not_silent():
    """구성 지표 컬럼(pcr)이 유니버스 전체에 없으면 경고가 실린다."""
    dates = pd.date_range(start="2024-01-01", periods=30, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    _write_series(data_dir, "CR_M1", dates, roe=15.0, per=8.0)
    _write_series(data_dir, "CR_M2", dates, roe=20.0, per=30.0)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest({
        "symbols": ["CR_M1", "CR_M2"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 100,
            "max_positions": 1,
            "ranking_metric": "composite",
            "ranking_components": [
                {"metric": "roe_or_gpa", "direction": "top"},
                {"metric": "pcr", "direction": "bottom"},
            ],
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    })
    assert any("복합 순위 구성 지표" in w for w in result.get("warnings", [])), result.get("warnings")
