"""분위(퀀타일) 그룹 백테스트(FR-BT-060) — 시뮬레이터 선정·엔진 그룹 실행 검증.

핵심 계약:
- select_ranked_targets: G개 그룹은 서로소이면서 합집합이 후보 전체(누락·중복 없음).
- 비율 선정(max_positions_pct): 후보 수 기준 상위 X%(최소 1종목).
- 엔진 quantile 모드: 메인 결과=1그룹(랭킹 최상위 구간), quantileGroups에 그룹별
  요약 지표+자산곡선이 실린다.
"""

import os

import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("polars")
pytest.importorskip("stockstats")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from backtest_engine import BacktestEngine  # noqa: E402
from engine.simulator import select_ranked_targets  # noqa: E402


# ─── select_ranked_targets 단위 검증 ─────────────────────────────────────────

def test_band_partition_disjoint_and_covering():
    """n=23, G=10처럼 나눠떨어지지 않아도 그룹들은 서로소·전체 커버여야 한다."""
    cand = np.arange(23)
    seen = []
    for g in range(1, 11):
        seen.extend(select_ranked_targets(cand, 5, None, [g, 10]).tolist())
    assert sorted(seen) == list(range(23)), "그룹 합집합이 후보 전체와 다름(누락/중복)"


def test_band_first_group_is_top_ranked():
    cand = np.array([7, 3, 9, 1])  # 이미 랭킹 내림차순 정렬된 후보
    top = select_ranked_targets(cand, 2, None, [1, 2])
    assert top.tolist() == [7, 3]
    bottom = select_ranked_targets(cand, 2, None, [2, 2])
    assert bottom.tolist() == [9, 1]


def test_pct_selection_counts():
    cand = np.arange(40)
    assert len(select_ranked_targets(cand, 10, 10.0, None)) == 4   # 40의 10%
    assert len(select_ranked_targets(cand, 10, 1.0, None)) == 1    # 최소 1종목
    # 기본 모드는 기존 상위 K 그대로.
    assert len(select_ranked_targets(cand, 10, None, None)) == 10


# ─── 엔진 통합: 분위 그룹 실행 ────────────────────────────────────────────────

def _write_series(data_dir: str, symbol: str, prices: list[float], dates) -> None:
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": float(p), "high": float(p + 1), "low": float(p - 1),
            "close": float(p), "volume": 5_000_000.0,
        }
        for d, p in zip(dates, prices)
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def _quantile_universe(data_dir: str, dates) -> list[str]:
    """모멘텀 순위가 내내 고정되는 4종목: 상위 절반(A·B)=상승, 하위 절반(C·D)=횡보/하락."""
    _write_series(data_dir, "QG_WIN_A", [100 + 3.0 * i for i in range(len(dates))], dates)
    _write_series(data_dir, "QG_WIN_B", [100 + 2.0 * i for i in range(len(dates))], dates)
    _write_series(data_dir, "QG_FLAT_C", [100.0 for _ in range(len(dates))], dates)
    _write_series(data_dir, "QG_FALL_D", [100 - 0.5 * i for i in range(len(dates))], dates)
    return ["QG_WIN_A", "QG_WIN_B", "QG_FLAT_C", "QG_FALL_D"]


def _quantile_req(symbols: list[str], **extra_risk) -> dict:
    return {
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 10,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "ranking_quantile_groups": 2,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
            **extra_risk,
        },
        "options": {"execution_type": "same_close"},
    }


def test_quantile_mode_main_result_is_group_one():
    """메인 결과는 1그룹(랭킹 최상위 구간) — 하위 그룹 종목은 메인에서 매수되지 않는다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _quantile_universe(data_dir, dates)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_quantile_req(symbols))

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols, "메인(1그룹) 매수 기록이 없음"
    assert buy_symbols <= {"QG_WIN_A", "QG_WIN_B"}, (
        f"하위 분위 종목이 메인 결과에 매수됨: {buy_symbols}"
    )


def test_quantile_mode_returns_group_summaries():
    """quantileGroups에 그룹별 요약 지표·자산곡선이 실리고, 상위 그룹 수익률이
    하위 그룹(횡보/하락 구성)보다 높다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _quantile_universe(data_dir, dates)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_quantile_req(symbols))

    qg = result.get("quantileGroups")
    assert qg, "quantileGroups가 결과에 없음"
    groups = qg["groups"]
    assert [g["group"] for g in groups] == [1, 2]
    assert qg["groupCount"] == 2
    for g in groups:
        assert g["equity"], f"{g['group']}그룹 자산곡선이 비어 있음"
        assert len(g["equity"]) == len(g["dates"])
        assert g["pctRange"] == [(g["group"] - 1) * 50, g["group"] * 50]
        assert "그룹" in g["label"]
    assert groups[0]["totalReturn"] > groups[1]["totalReturn"], (
        f"상승 종목 그룹이 하락 종목 그룹보다 수익률이 낮음: {groups}"
    )
    # 그룹 비교 계산 기준(순수 리밸런싱) 고지 경고.
    assert any("분위 그룹 비교" in w for w in result.get("warnings", []))


def test_quantile_mode_without_rebalancing_skips_groups_with_warning():
    """정기 리밸런싱이 없으면 그룹 비교를 조용히 빼지 않고 경고로 드러낸다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _quantile_universe(data_dir, dates)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_quantile_req(symbols, rebalancing_period="none"))

    assert not result.get("quantileGroups")
    assert any("정기 리밸런싱" in w for w in result.get("warnings", []))


def test_pct_selection_holds_half_universe():
    """상위 50% 비율 선정: 4종목 중 상위 2종목만 편입된다(개수 max_positions 무시)."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    _write_series(data_dir, "PS_WIN_A", [100 + 3.0 * i for i in range(100)], dates)
    _write_series(data_dir, "PS_WIN_B", [100 + 2.0 * i for i in range(100)], dates)
    _write_series(data_dir, "PS_FLAT_C", [100.0 for _ in range(100)], dates)
    _write_series(data_dir, "PS_FALL_D", [100 - 0.5 * i for i in range(100)], dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["PS_WIN_A", "PS_WIN_B", "PS_FLAT_C", "PS_FALL_D"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 1,          # 비율이 있으면 개수는 무시되어야 한다
            "max_positions_pct": 50.0,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }
    result = engine.run_backtest(req)
    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols == {"PS_WIN_A", "PS_WIN_B"}, (
        f"상위 50% 선정이 개수 상한/하위 종목과 어긋남: {buy_symbols}"
    )


# ─── 그룹당 보유 상한 (FR-BT-060b) ───────────────────────────────────────────

def test_band_cap_limits_each_group():
    """band_cap은 각 그룹 구간에서 랭킹 상위 N종목만 남긴다(모든 그룹 동일 적용)."""
    cand = np.arange(8)  # 이미 랭킹 내림차순
    top = select_ranked_targets(cand, 99, None, [1, 2], band_cap=2)
    assert top.tolist() == [0, 1]
    bottom = select_ranked_targets(cand, 99, None, [2, 2], band_cap=2)
    assert bottom.tolist() == [4, 5]
    # cap 없으면 구간 전체(기존 동작 불변).
    assert select_ranked_targets(cand, 99, None, [2, 2]).tolist() == [4, 5, 6, 7]


def test_quantile_group_cap_limits_main_portfolio():
    """그룹당 1종목 상한이면 메인(1그룹)은 랭킹 최상위 1종목만 보유한다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = _quantile_universe(data_dir, dates)

    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest(_quantile_req(symbols, ranking_group_cap=1))

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    assert buy_symbols == {"QG_WIN_A"}, (
        f"그룹당 1종목 상한인데 메인이 최상위 1종목만 사지 않음: {buy_symbols}"
    )
    qg = result.get("quantileGroups")
    assert qg and qg["groupCap"] == 1
