"""랭킹 lookback 패널이 창 이전(워밍업) 가격을 쓴다 — 엔진 v16.12.

종목 데이터는 지표 워밍업을 위해 창 시작 전부터 읽지만, 랭킹 패널(N거래일 수익률·변동성·
초과수익률·복합·후보 우선순위)은 창으로 잘린 종가로 계산돼 창의 첫 lookback 거래일 동안
순위가 비어 있었다 — 전략이 그동안 현금으로 앉아 있었다(2026-09-17 실측: 60거래일 수익률
상위 5종목·월간, 2023-09-18 시작 → 첫 매수 2024-01-02). SRS는 "시작일 이전 데이터를
미리 불러와 지표를 보장한다"고 적고 있었다.

지켜야 할 가드(v13.3): 관측이 lookback개 미만인 종목(창 안에서 상장·워밍업 중 상장)은
여전히 lookback 봉이 쌓일 때까지 순위가 없다.
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

_DATES = pd.bdate_range("2023-06-01", "2024-03-29")
_START = "2023-10-02"
_END = "2024-03-29"


def _data_dir() -> str:
    d = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(d, exist_ok=True)
    return d


def _write(symbol: str, daily_return: float, first_day: str | None = None) -> None:
    closes = 100.0 * np.cumprod(np.full(len(_DATES), 1.0 + daily_return))
    rows = [
        {"date": d.strftime("%Y-%m-%d"), "open": float(c), "high": float(c) * 1.01,
         "low": float(c) * 0.99, "close": float(c), "volume": 5_000_000.0}
        for d, c in zip(_DATES, closes)
        if first_day is None or d.strftime("%Y-%m-%d") >= first_day
    ]
    pl.from_dicts(rows).write_parquet(f"{_data_dir()}/{symbol}.parquet")


def _run(symbols, execution_type="same_close", **risk):
    engine = BacktestEngine(data_dir=_data_dir())
    result = engine.run_backtest({
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {"max_positions": 1, "position_size_pct": 100, "ranking_metric": "return",
                 "ranking_lookback_days": 60, "rebalancing_period": "monthly",
                 "liquidity_multiplier": 0, **risk},
        "options": {"execution_type": execution_type},
        "startDate": _START,
        "endDate": _END,
    })
    assert not result.get("error"), result.get("error")
    return result


def _buys(result):
    return [(s["date"], s["symbol"]) for s in result["signals"] if s["type"] == "buy"]


_COMPOSITE = [{"metric": "return", "direction": "top"}, {"metric": "volatility", "direction": "bottom"}]


@pytest.mark.parametrize("risk", [
    {"ranking_metric": "return"},
    {"ranking_metric": "volatility"},
    {"ranking_metric": "composite", "ranking_components": _COMPOSITE},
], ids=["return", "volatility", "composite"])
def test_ranking_uses_warmup_prices_on_first_window_day(risk):
    _write("RWU_UP", 0.004)
    _write("RWU_FLAT", 0.0)
    _write("RWU_DOWN", -0.003)
    # 변동성·복합 분기는 어느 종목을 고르는지가 아니라 창 첫날 순위가 정의되는지만 본다.
    result = _run(["RWU_UP", "RWU_FLAT", "RWU_DOWN"], **risk)
    buys = _buys(result)
    assert buys, "매수 없음"
    # 창 첫 거래일(=첫 리밸런싱일)에 이미 순위가 있다 — 종전엔 60거래일 뒤 첫 리밸런싱(2024-01-02).
    assert buys[0][0] == _START, buys


# ── next_open 창 첫날(v16.12, 사용자 결정) ────────────────────────────────────
# 규약: 창 중간 리밸런싱일 i의 편입은 "i-N 거래일 종가까지의 정보(순위·유동성·시총·신호)로 정하고
# i일 시가에 체결"이다(N=execution_delay_days, 기본 1). 창 첫날(=첫 리밸런싱일)도 똑같이 창 직전
# N번째 거래일 정보로 정해 첫날 시가에 체결한다. 종전엔 shift가 창 안에서만 일어나 첫날 후보가 비어
# 첫 주기 전체가 현금이었다(2026-09-17 실측: 2023-09-18 시작 → 첫 매수 2023-10-04).

def _run_live_liquidity(symbols, **risk):
    """유동성 게이트를 실제로 켠다(기본 10%) — 첫날 유동성도 창 직전 거래대금으로 판정돼야 한다."""
    params = {"liquidity_limit_pct": 10}
    params.update(risk)
    engine = BacktestEngine(data_dir=_data_dir())
    result = engine.run_backtest({
        "symbols": symbols,
        "entry": params.pop("entry", {"conditions": []}),
        "exit": {"conditions": []},
        "risk": {"max_positions": 1, "position_size_pct": 100, "rebalancing_period": "monthly",
                 **params},
        "options": {"execution_type": "next_open"},
        "startDate": _START,
        "endDate": _END,
    })
    assert not result.get("error"), result.get("error")
    return result


@pytest.mark.parametrize("delay", [1, 2])
def test_next_open_first_window_day_fills_like_mid_window_rebalance(delay):
    _write("RWN_UP", 0.004)
    _write("RWN_FLAT", 0.0)
    result = _run_live_liquidity(["RWN_UP", "RWN_FLAT"], ranking_metric="return",
                                 ranking_lookback_days=60, execution_delay_days=delay)
    buys = _buys(result)
    # 창 첫날(10/2, 첫 리밸런싱일) 시가에 체결 — 순위는 창 직전 N번째 거래일 종가 기준.
    assert buys and buys[0] == (_START, "RWN_UP"), buys


def test_next_open_first_window_day_fundamental_ranking():
    """재무 지표 랭킹도 창 첫날에 창 직전 거래일 값으로 선정한다."""
    for sym, pbr in (("RWF_CHEAP", 0.5), ("RWF_RICH", 3.0)):
        rows = [
            {"date": d.strftime("%Y-%m-%d"), "open": 100.0, "high": 101.0, "low": 99.0,
             "close": 100.0, "volume": 5_000_000.0, "pbr": pbr}
            for d in _DATES
        ]
        pl.from_dicts(rows).write_parquet(f"{_data_dir()}/{sym}.parquet")
    result = _run_live_liquidity(["RWF_CHEAP", "RWF_RICH"], ranking_metric="pbr",
                                 ranking_direction="bottom")
    buys = _buys(result)
    assert buys and buys[0] == (_START, "RWF_CHEAP"), buys


def test_next_open_entry_signal_first_day_uses_pre_window_signal():
    """매수 조건 전략: 창 직전 거래일의 신호로 창 첫날 시가에 체결(창 중간과 같은 1일 지연).
    창 첫날 상장한 종목은 전일 신호·전일 거래대금이 없어 첫날엔 살 수 없다(상장 전 선정 금지)."""
    _write("RWS_OLD", 0.001)
    _write("RWS_NEW", 0.002, first_day=_START)
    entry = {"conditions": [{"id": "price", "params": {"value": 0, "operator": ">"}}]}
    result = _run_live_liquidity(["RWS_OLD", "RWS_NEW"], entry=entry, max_positions=2,
                                 rebalancing_period="none", position_size_pct=50)
    buys = _buys(result)
    old = [d for d, s in buys if s == "RWS_OLD"]
    new = [d for d, s in buys if s == "RWS_NEW"]
    assert old and old[0] == _START, buys
    assert new and new[0] > _START, buys
    # 첫날 매수의 사유는 창 직전 신호 봉의 조건 서술이다(폴백 문구가 아니다).
    first = [s for s in result["signals"] if s["type"] == "buy" and s["symbol"] == "RWS_OLD"][0]
    assert "현재가" in first["condition"], first["condition"]


def test_stock_listed_inside_window_still_waits_for_lookback_bars():
    """창 안에서 상장한 급등주는 상장 후 60봉이 쌓이기 전엔 후보가 아니다(v13.3 가드 유지)."""
    _write("RWL_OLD", 0.001)
    _write("RWL_NEW", 0.02, first_day="2023-11-01")   # 최고 수익률이지만 창 안 신규 상장
    result = _run(["RWL_OLD", "RWL_NEW"])
    buys = _buys(result)
    assert buys[0] == (_START, "RWL_OLD"), buys
    new_buys = [d for d, s in buys if s == "RWL_NEW"]
    # 상장(11/1) 후 60거래일 ≈ 2024-01-24 — 그 뒤 첫 리밸런싱은 2024-02-01.
    assert new_buys and min(new_buys) >= "2024-02-01", buys


def test_stock_listed_during_warmup_without_enough_history_waits():
    """워밍업 구간 중 상장해 창 시작 시점 관측이 lookback 미만인 종목도 후보가 아니다."""
    _write("RWW_OLD", 0.001)
    _write("RWW_NEW", 0.02, first_day="2023-09-01")   # 창 시작(10/2)에 21거래일뿐
    result = _run(["RWW_OLD", "RWW_NEW"])
    buys = _buys(result)
    assert buys[0] == (_START, "RWW_OLD"), buys
    new_buys = [d for d, s in buys if s == "RWW_NEW"]
    # 9/1 상장 + 60거래일 ≈ 2023-11-24 → 다음 리밸런싱 2023-12-01.
    assert new_buys and min(new_buys) == "2023-12-01", buys
