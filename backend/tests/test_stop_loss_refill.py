"""손절 종목 대체 편입 — 엔진 v16.12 (2026-09-17 사용자 결정).

랭킹 회전(선정=진입) 전략에서 손절로 청산된 종목은 그 리밸런싱 기간의 목표 집합에 그대로
남아 **다음 거래일에 다시 매수**됐다(실측: 60거래일 수익률 상위 5종목·월간·손절 -15%,
아티스트컴퍼니 2024-01 손절→재매수 3회). 목표 집합이 '목표가 채워질 때까지 빈 슬롯을
메우는' 계약이라 손절로 빈 자리를 같은 종목으로 다시 채운 것이다.

결정: 손절 종목은 그 기간 목표에서 빠지고, 빈자리는 그 리밸런싱일 랭킹의 다음 순위가
채운다(보유·이미 빠진 종목 제외). 남은 후보가 없으면 다음 리밸런싱까지 현금. 다음
리밸런싱일엔 손절 종목도 다시 정상 후보다.
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

_DATES = pd.date_range(start="2024-01-01", periods=75, freq="D")   # 1/1 ~ 3/15
_CRASH_DAY = "2024-02-06"
_REFILL_TEMPLATE = "손절 종목 대체 편입 (리밸런싱일 순위 {0}위)"


def _write(data_dir: str, symbol: str, daily_return: float, crash_day: str | None = None) -> None:
    """일정 수익률 추세 종목. crash_day엔 장중 저가만 종가의 70%로 찍힌다(종가 추세는 유지)
    — 손절은 장중 저가로 감지되므로 그날 손절이 나고, 종가 순위는 계속 최상위로 남는다."""
    closes = 100.0 * np.cumprod(np.full(len(_DATES), 1.0 + daily_return))
    rows = []
    for d, c in zip(_DATES, closes):
        day = d.strftime("%Y-%m-%d")
        low = c * (0.7 if day == crash_day else 0.99)
        rows.append({"date": day, "open": float(c), "high": float(c) * 1.01, "low": float(low),
                     "close": float(c), "volume": 5_000_000.0})
    pl.from_dicts(rows).write_parquet(f"{data_dir}/{symbol}.parquet")


def _run(prefix: str, specs, *, max_positions: int, execution_type: str = "same_close", **risk):
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(data_dir, exist_ok=True)
    symbols = []
    for name, ret, crash in specs:
        sym = f"{prefix}_{name}"
        _write(data_dir, sym, ret, crash)
        symbols.append(sym)
    engine = BacktestEngine(data_dir=data_dir)
    result = engine.run_backtest({
        "symbols": symbols,
        "entry": {"conditions": []},
        "exit": {"conditions": []},
        "risk": {
            "position_size_pct": 100,
            "max_positions": max_positions,
            "ranking_metric": "return",
            "ranking_lookback_days": 5,
            "rebalancing_period": "monthly",
            "stop_loss_pct": 10,
            "liquidity_multiplier": 0,
            **risk,
        },
        "options": {"execution_type": execution_type},
    })
    assert not result.get("error"), result.get("error")
    return result


def _trades(result, symbol: str, side: str):
    return [s for s in result["signals"] if s["symbol"] == symbol and s["type"] == side]


def _dates(result, symbol: str, side: str):
    return [s["date"] for s in _trades(result, symbol, side)]


_SPECS = [("A", 0.03, _CRASH_DAY), ("B", 0.02, None), ("C", 0.01, None), ("D", 0.005, None)]


def test_stopped_stock_not_rebought_and_next_rank_fills_same_close():
    result = _run("SLR", _SPECS, max_positions=2)

    a_sells = _trades(result, "SLR_A", "sell")
    assert a_sells and a_sells[0]["date"] == _CRASH_DAY, [s["date"] for s in a_sells]
    assert "손절매 실행" in a_sells[0]["condition"], a_sells[0]["condition"]

    # 손절 뒤 같은 기간(2월)에는 다시 사지 않는다 — 종전엔 다음 거래일(2/7)에 재매수됐다.
    a_buys = _dates(result, "SLR_A", "buy")
    assert not [d for d in a_buys if _CRASH_DAY < d < "2024-03-01"], a_buys

    # 빈자리는 리밸런싱일(2/1) 랭킹의 다음 순위(3위 C)가 채운다 — 손절 체결일에(same_close).
    c_buys = _trades(result, "SLR_C", "buy")
    assert c_buys and c_buys[0]["date"] == _CRASH_DAY, [b["date"] for b in c_buys]
    assert c_buys[0]["conditionParts"] == [{"t": _REFILL_TEMPLATE, "a": [3]}], c_buys[0]
    assert c_buys[0]["condition"] == "손절 종목 대체 편입 (리밸런싱일 순위 3위)"
    # 4위 D는 자리가 없어 사지 않는다.
    assert not _dates(result, "SLR_D", "buy")


def test_stopped_stock_is_eligible_again_on_next_rebalance():
    result = _run("SLE", _SPECS, max_positions=2)
    a_buys = _dates(result, "SLE_A", "buy")
    assert "2024-03-01" in a_buys, a_buys
    # 3월 리밸런싱일 재편입은 정상 랭킹 사유다(대체 편입 사유가 아니다).
    march = [b for b in _trades(result, "SLE_A", "buy") if b["date"] == "2024-03-01"][0]
    assert "수익률 상위" in march["condition"], march["condition"]
    # 대체 편입된 C는 3월 목표(상위 2 = A·B)에서 빠져 편출된다.
    assert "2024-03-01" in _dates(result, "SLE_C", "sell")


def test_no_remaining_candidate_leaves_slot_in_cash():
    specs = [("A", 0.03, _CRASH_DAY), ("B", 0.02, None)]
    result = _run("SLN", specs, max_positions=2)
    assert _dates(result, "SLN_A", "sell")[0] == _CRASH_DAY
    a_buys = _dates(result, "SLN_A", "buy")
    assert not [d for d in a_buys if _CRASH_DAY < d < "2024-03-01"], a_buys
    assert "2024-03-01" in a_buys, a_buys
    # B는 계속 보유(편출·재매수 없음) — 빈자리는 현금으로 남는다.
    assert _dates(result, "SLN_B", "buy") == ["2024-02-01"]


def test_next_open_stop_exits_next_day_and_refill_buys_same_open():
    result = _run("SLO", _SPECS, max_positions=2, execution_type="next_open")
    # 손절 감지(2/6 장중) → 다음 거래일 시가 청산, 같은 시가에 다음 순위 편입.
    a_sells = _dates(result, "SLO_A", "sell")
    assert a_sells and a_sells[0] == "2024-02-07", a_sells
    a_buys = _dates(result, "SLO_A", "buy")
    assert not [d for d in a_buys if "2024-02-07" <= d < "2024-03-01"], a_buys
    c_buys = _trades(result, "SLO_C", "buy")
    assert c_buys and c_buys[0]["date"] == "2024-02-07", [b["date"] for b in c_buys]
    assert c_buys[0]["conditionParts"] == [{"t": _REFILL_TEMPLATE, "a": [3]}]


def test_refill_skips_stock_already_stopped_this_period():
    """대체 편입 종목도 손절되면 그 종목까지 건너뛰고 다음 순위로 간다."""
    specs = [("A", 0.03, _CRASH_DAY), ("B", 0.02, None), ("C", 0.01, "2024-02-09"),
             ("D", 0.005, None)]
    result = _run("SLS", specs, max_positions=2)
    assert _dates(result, "SLS_C", "sell")[0] == "2024-02-09"
    d_buys = _trades(result, "SLS_D", "buy")
    assert d_buys and d_buys[0]["date"] == "2024-02-09", [b["date"] for b in d_buys]
    assert d_buys[0]["conditionParts"] == [{"t": _REFILL_TEMPLATE, "a": [4]}]
    for sym in ("SLS_A", "SLS_C"):
        assert not [d for d in _dates(result, sym, "buy") if "2024-02-06" < d < "2024-03-01"], sym


def test_quantile_band_refill_stays_in_band_and_reports_global_rank():
    """분위 그룹은 자기 구간 안에서만 대체한다(다음 그룹 종목을 끌어오지 않음). 사유의 순위는
    구간 안 순번이 아니라 리밸런싱일 후보 전체 기준이다."""
    from engine.simulator import Simulator
    from engine import trade_reason as tr

    idx = pd.bdate_range("2024-01-02", periods=30)
    syms = list("ABCDEF")
    price = pd.DataFrame(100.0, index=idx, columns=syms)
    low = price * 0.99
    low.loc[idx[5], "E"] = 50.0          # 2그룹(D·E·F) 보유 종목 E가 장중 급락 → 손절
    ents = pd.DataFrame(True, index=idx, columns=syms)
    exts = pd.DataFrame(False, index=idx, columns=syms)
    rank = pd.DataFrame([[6, 5, 4, 3, 2, 1]] * len(idx), index=idx, columns=syms, dtype=float)
    sim = Simulator()
    pf = sim.run(
        price, price, ents, exts,
        {"max_positions": 2, "rebalancing_period": "monthly", "stop_loss_pct": 10,
         "ranking_band": [2, 2], "ranking_group_cap": 2, "allocation_type": "equal", "init_cash": 1e7},
        {"execution_type": "same_close"},
        rank_df=rank, high_df=price * 1.01, low_df=low, available_df=ents,
    )
    orders = pf.orders.records_readable
    buys = orders[orders["Side"] == "Buy"]
    jan = buys[buys["Timestamp"] < pd.Timestamp("2024-02-01")]
    assert set(jan["Column"]) == {"D", "E", "F"}, jan
    refill_day = idx[5].strftime("%Y-%m-%d")
    assert list(sim.entry_reason_overrides) == ["F"], sim.entry_reason_overrides
    assert tr.text(sim.entry_reason_overrides["F"][refill_day]) == "손절 종목 대체 편입 (리밸런싱일 순위 6위)"
    # 1월 중 E 재매수 없음, 2월 리밸런싱일에 다시 후보.
    e_buys = list(buys[buys["Column"] == "E"]["Timestamp"])
    assert e_buys == [idx[0], pd.Timestamp("2024-02-01")], e_buys
