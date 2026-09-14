"""신호 후 N거래일 지연 체결(execution_delay_days) — 엔진 v16.9.0.

next_open의 shift 폭이 1에서 N으로 일반화됐다. 고정할 계약:
  - 지연 N이면 신호 봉의 N번째 거래일 **시가**에 체결한다(기본 1 = 종전 next_open 그대로).
  - 데이터가 먼저 끝나는 종목(상폐)의 강제청산은 지연과 무관하게 그 종목의 마지막 가용 봉에 실린다
    (phase1.close_at_last_available_row가 신호를 N봉 앞에 둔다).
  - 값은 options → risk 순으로 읽고, 1 미만·정수 아님·same_close에 1 초과는 거절한다(Fail Fast).
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backtest_engine import BacktestEngine
from engine import phase1

_FULL = pd.bdate_range("2024-01-02", "2024-02-29")
_SHORT_END = pd.Timestamp("2024-02-15")
_SHORT = pd.bdate_range("2024-01-02", _SHORT_END)   # 2월 15일에 데이터가 끝나는 종목


def _write_parquet(path: Path, dates: pd.DatetimeIndex):
    n = len(dates)
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.0 + i for i in range(n)],
        "volume": [1_000_000] * n,
        "roe_or_gpa": [0.1] * n,
        "pbr": [1.0] * n,
        "per": [10.0] * n,
    })
    df.to_parquet(path)


@pytest.fixture
def data_dir(tmp_path):
    _write_parquet(tmp_path / "AAAAAA.parquet", _FULL)
    _write_parquet(tmp_path / "CCCCCC.parquet", _SHORT)
    return tmp_path


def _req(symbols, options=None, risk_extra=None):
    return {
        "symbols": symbols,
        "universe_id": None,
        "period": "FULL",
        "entry": {"logic": "OR", "conditions": [
            {"id": "price", "type": "signal", "params": {"operator": ">", "value": 0}},
        ]},
        "exit": {"logic": "OR", "conditions": []},
        "risk_params": {"init_cash": 10_000_000.0, "max_positions": 2,
                        "allocation_type": "equal", "skip_risk_management": True,
                        **(risk_extra or {})},
        "options": {"execution_type": "next_open", "fee_rate": 0.0, "slippage_rate": 0.0,
                    "sell_tax_rate": 0.0, **(options or {})},
    }


def _run(data_dir, req):
    return BacktestEngine(data_dir=str(data_dir)).run_backtest(req)


def _first_buy(result, symbol):
    return next(s for s in result["signals"] if s["symbol"] == symbol and s["type"] == "buy")


def test_delay_n_fills_at_nth_bar_open(data_dir):
    """지연 3이면 지연 1보다 정확히 두 거래일 뒤, 그 봉의 시가(100+i)에 체결한다."""
    d1 = _first_buy(_run(data_dir, _req(["AAAAAA"])), "AAAAAA")
    d3 = _first_buy(_run(data_dir, _req(["AAAAAA"], {"execution_delay_days": 3})), "AAAAAA")
    i1 = _FULL.get_loc(pd.Timestamp(d1["date"]))
    i3 = _FULL.get_loc(pd.Timestamp(d3["date"]))
    assert i3 - i1 == 2
    assert d3["price"] == pytest.approx(100.0 + i3)   # 그 봉의 시가


def test_delay_read_from_risk_when_options_lacks_it(data_dir):
    """프론트가 options에 싣지 못해도 risk.execution_delay_days로 같은 결과 — 조용한 소실 방지."""
    via_opt = _first_buy(_run(data_dir, _req(["AAAAAA"], {"execution_delay_days": 3})), "AAAAAA")
    via_risk = _first_buy(_run(data_dir, _req(["AAAAAA"], risk_extra={"execution_delay_days": 3})), "AAAAAA")
    assert via_opt == via_risk


def test_default_delay_is_unchanged_next_open(data_dir):
    """옵션을 안 주면 종전 next_open(지연 1)과 결과가 같다."""
    base = _run(data_dir, _req(["AAAAAA"]))
    one = _run(data_dir, _req(["AAAAAA"], {"execution_delay_days": 1}))
    assert base["signals"] == one["signals"]


@pytest.mark.parametrize("delay", [1, 3])
def test_data_end_forced_exit_lands_on_last_available_bar(data_dir, delay):
    """데이터가 먼저 끝나는 종목의 강제청산은 지연과 무관하게 그 종목의 마지막 봉에 실린다."""
    res = _run(data_dir, _req(["AAAAAA", "CCCCCC"], {"execution_delay_days": delay}))
    sells = [s for s in res["signals"] if s["symbol"] == "CCCCCC" and s["type"] == "sell"]
    assert sells, "expected a forced exit for the symbol whose data ends early"
    assert max(pd.Timestamp(s["date"]) for s in sells) == _SHORT_END


def test_phase1_forced_exit_signal_is_delay_bars_before_last_row():
    n = 10
    entries = np.ones(n, dtype=bool)
    exits = np.zeros(n, dtype=bool)
    reasons = [""] * n
    ctx = {"exec_type": "next_open", "signal_delay": 3, "delisted_symbols": set()}
    phase1.close_at_last_available_row(entries, exits, reasons, "X", ctx)
    assert exits.tolist() == [i == n - 1 - 3 for i in range(n)]
    assert not entries[n - 1 - 3:].any()
    assert reasons[n - 1 - 3]

    # 지연보다 짧은 종목은 손대지 않는다(shift 뒤 창 밖으로 나가는 신호를 만들지 않음).
    short_exits = np.zeros(3, dtype=bool)
    phase1.close_at_last_available_row(np.ones(3, dtype=bool), short_exits, [""] * 3, "X", ctx)
    assert not short_exits.any()


def test_build_context_defaults_signal_delay_to_one():
    ctx = phase1.build_context(
        entry=None, exit_=None, warmup_start_str=None, has_period_filter=False,
        period_start_str=None, end_str="2024-12-31", apply_dividends=True, skip_risk=True,
        skip_pos=False, init_cash=1.0, pos_size_pct=10.0, liquid_limit=10.0,
        exec_type="next_open", delisted_symbols=set(), rank_metric_cols=[],
        tracked_metrics=None, ai_needed=False,
    )
    assert ctx["signal_delay"] == 1


@pytest.mark.parametrize("options,risk,exec_type", [
    ({"execution_delay_days": 0}, {}, "next_open"),
    ({"execution_delay_days": -1}, {}, "next_open"),
    ({"execution_delay_days": 2.5}, {}, "next_open"),
    ({"execution_delay_days": "two"}, {}, "next_open"),
    ({"execution_delay_days": 2}, {}, "same_close"),
    ({}, {"execution_delay_days": 2}, "same_close"),
])
def test_invalid_delay_is_rejected(options, risk, exec_type):
    with pytest.raises(ValueError):
        BacktestEngine._resolve_signal_delay(options, risk, exec_type)


def test_valid_delay_resolution():
    assert BacktestEngine._resolve_signal_delay({}, {}, "next_open") == 1
    assert BacktestEngine._resolve_signal_delay({}, {}, "same_close") == 1
    assert BacktestEngine._resolve_signal_delay({"execution_delay_days": 1}, {}, "same_close") == 1
    assert BacktestEngine._resolve_signal_delay({"execution_delay_days": "4"}, {}, "next_open") == 4
    assert BacktestEngine._resolve_signal_delay({}, {"execution_delay_days": 2}, "next_open") == 2
    # options가 risk보다 우선
    assert BacktestEngine._resolve_signal_delay(
        {"execution_delay_days": 3}, {"execution_delay_days": 2}, "next_open") == 3
