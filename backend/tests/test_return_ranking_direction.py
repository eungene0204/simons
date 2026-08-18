"""수익률(모멘텀) 랭킹의 방향(direction) 존중 — 엔진 v16.2.

'최근 N일 수익률 오름차순(bottom)' 요청은 대화 계층(프롬프트 규칙 → 컴파일러 →
스키마 → 변환기)까지는 `ranking_direction="bottom"`으로 전달되는데, 엔진의 return
분기만 그 값을 읽지 않아 **정반대(수익률 높은 순)** 로 실행됐다 — 변동성·재무·복합
분기는 모두 direction을 읽는다. 매수 사유도 방향과 무관하게 "상위"로 찍혀 결과 화면
만으로는 뒤집힌 것을 알 수 없었다.
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


def _write_trend(data_dir: str, symbol: str, dates, daily_return: float) -> None:
    """일정한 일수익률로 움직이는 종목 — 랭킹 순서가 결정론적으로 정해진다."""
    closes = 100.0 * np.cumprod(np.full(len(dates), 1.0 + daily_return))
    rows = [
        {
            "date": d.strftime("%Y-%m-%d"),
            "open": float(c), "high": float(c) * 1.01, "low": float(c) * 0.99, "close": float(c),
            "volume": 5_000_000.0,
        }
        for d, c in zip(dates, closes)
    ]
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def _run(direction):
    dates = pd.date_range(start="2024-01-01", periods=80, freq="D")
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    _write_trend(data_dir, "RD_UP", dates, 0.01)     # 최근 수익률 최상위
    _write_trend(data_dir, "RD_FLAT", dates, 0.0)
    _write_trend(data_dir, "RD_DOWN", dates, -0.01)  # 최근 수익률 최하위
    risk = {
        "position_size_pct": 100,
        "max_positions": 1,
        "ranking_metric": "return",
        "ranking_lookback_days": 20,
        "rebalancing_period": "monthly",
        "liquidity_multiplier": 0,
    }
    if direction is not None:
        risk["ranking_direction"] = direction
    engine = BacktestEngine(data_dir=data_dir)
    return engine.run_backtest({
        "symbols": ["RD_UP", "RD_FLAT", "RD_DOWN"],
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": risk,
        "options": {"execution_type": "same_close"},
    })


def _buys(result):
    return [s for s in result["signals"] if s["type"] == "buy"]


def test_return_ranking_default_top_buys_highest_return():
    """방향 미지정(기본 top)은 종전과 같이 수익률 최상위 종목을 산다(결과 불변)."""
    buys = _buys(_run(None))
    assert buys, "매수 없음"
    assert {b["symbol"] for b in buys} == {"RD_UP"}, buys
    assert all("수익률 상위" in b["condition"] for b in buys), [b["condition"] for b in buys]


def test_return_ranking_bottom_buys_lowest_return():
    """'수익률 오름차순(bottom)'은 수익률 최하위 종목을 산다 — 종전엔 조용히 top으로 실행됐다."""
    buys = _buys(_run("bottom"))
    assert buys, "매수 없음"
    assert {b["symbol"] for b in buys} == {"RD_DOWN"}, buys
    # 매수 사유도 방향을 드러낸다 — 결과 화면에서 뒤집힘을 알아볼 수 있어야 한다.
    assert all("수익률 하위" in b["condition"] for b in buys), [b["condition"] for b in buys]
