"""상대강도(수익률 순위) 랭킹 백테스트 검증.

핵심: 진입 신호 없이 ranking_metric="return"만으로 전 종목을 후보로 만들고,
N일 수익률 상위 max_positions 종목만 선정/보유하는지 확인한다.
vectorbt/polars/stockstats가 있는 환경에서만 실행(없으면 skip).
"""

import os

import pytest

pytest.importorskip("vectorbt")
pytest.importorskip("polars")
pytest.importorskip("stockstats")

import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

from backtest_engine import BacktestEngine  # noqa: E402


def _write_series(data_dir: str, symbol: str, prices: list[float], dates) -> None:
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": float(p),
            "high": float(p + 1),
            "low": float(p - 1),
            "close": float(p),
            "volume": 5_000_000.0,
        }
        for d, p in zip(dates, prices)
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def test_return_ranking_selects_only_top_k_by_momentum():
    """4종목 중 최근 수익률 상위 2종목(WIN_A/WIN_B)만 매수되고, 하락/횡보주는 매수되지 않는다."""
    dates = pd.date_range(start="2024-01-01", periods=40, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # 상승주: 꾸준히 오름 → 높은 N일 수익률. 횡보/하락주: 낮은 수익률.
    _write_series(data_dir, "RANK_WIN_A", [100 + 3 * i for i in range(40)], dates)
    _write_series(data_dir, "RANK_WIN_B", [100 + 2 * i for i in range(40)], dates)
    _write_series(data_dir, "RANK_FLAT_C", [100.0 for _ in range(40)], dates)
    _write_series(data_dir, "RANK_FALL_D", [100 - 1 * i for i in range(40)], dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RANK_WIN_A", "RANK_WIN_B", "RANK_FLAT_C", "RANK_FALL_D"],
        "entry": {"conditions": []},          # 진입 신호 없음 — 선정 자체가 진입
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)

    buy_symbols = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}

    # 상위 수익률 종목만 매수, 횡보/하락주는 절대 매수되지 않음.
    assert buy_symbols <= {"RANK_WIN_A", "RANK_WIN_B"}, f"하위 종목이 매수됨: {buy_symbols}"
    assert "RANK_WIN_A" in buy_symbols, "최상위 수익률 종목이 매수되지 않음"
    assert "RANK_FALL_D" not in buy_symbols
    assert "RANK_FLAT_C" not in buy_symbols


def test_monthly_rebalancing_rotates_dropouts():
    """월간 리밸런싱: 다음 달 순위에서 빠진 종목은 매도되고, 새로 오른 종목이 편입된다."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")  # Jan~Apr
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    # STEADY: 내내 상승 → 항상 상위.
    _write_series(data_dir, "RB_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    # EARLY: 1월 급등 후 2월부터 급락 → 2월초 상위, 3월초 탈락.
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RB_EARLY", early, dates)
    # LATE: 1월 횡보, 2월부터 급등 → 2월초 탈락, 3월초 편입.
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RB_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RB_STEADY", "RB_EARLY", "RB_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    # SL/TP 없음 → vbt 네이티브 from_orders(목표비중) 경로로 처리됨.
    result = engine.run_backtest(req)
    buys = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    sells = {s["symbol"] for s in result["signals"] if s["type"] == "sell"}

    # 세 종목 모두 어느 시점엔가 보유됨 → 리밸런싱 재선정이 작동.
    assert {"RB_STEADY", "RB_EARLY", "RB_LATE"} <= buys, f"재선정 누락: {buys}"
    # 급락해 순위에서 빠진 EARLY는 리밸런싱으로 매도됨(SL 없음 → 매도는 리밸런싱이 유일).
    assert "RB_EARLY" in sells, f"탈락 종목이 매도되지 않음: {sells}"


def test_monthly_rebalancing_with_stoploss_uses_signal_path():
    """리밸런싱 + 봉중간 SL이 섞이면 from_signals 커스텀 루프(reconstitution)로 라우팅된다.

    SL을 발동 안 하게 느슨히(-90%) 둬도 회전/재선정은 동일하게 동작해야 한다.
    """
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)

    _write_series(data_dir, "RBS_STEADY", [100 + 1.0 * i for i in range(100)], dates)
    early = [100 + 3.0 * i for i in range(31)]
    early += [early[-1] - 3.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBS_EARLY", early, dates)
    late = [100.0 for _ in range(31)] + [100 + 4.0 * (i + 1) for i in range(69)]
    _write_series(data_dir, "RBS_LATE", late, dates)

    engine = BacktestEngine(data_dir=data_dir)
    req = {
        "symbols": ["RBS_STEADY", "RBS_EARLY", "RBS_LATE"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 50,
            "max_positions": 2,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "stop_loss_pct": 90,   # 발동 안 함 → from_signals 경로만 강제
            "liquidity_multiplier": 0,
        },
        "options": {"execution_type": "same_close"},
    }

    result = engine.run_backtest(req)
    buys = {s["symbol"] for s in result["signals"] if s["type"] == "buy"}
    sells = {s["symbol"] for s in result["signals"] if s["type"] == "sell"}

    assert {"RBS_STEADY", "RBS_EARLY", "RBS_LATE"} <= buys, f"재선정 누락: {buys}"
    assert "RBS_EARLY" in sells, f"탈락 종목이 매도되지 않음: {sells}"
