import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), "backend"))

from engine.result_handler import ResultHandler


class _MeanValue:
    def __init__(self, value):
        self._value = value

    def mean(self):
        return self._value


class _TradesView:
    def __init__(self, pnl_mean, count):
        self.pnl = _MeanValue(pnl_mean)
        self._count = count

    def __len__(self):
        return self._count


class _Trades:
    def __init__(
        self,
        exit_types=None,
        exit_idxs=None,
        entry_idxs=None,
        entry_timestamps=None,
        exit_timestamps=None,
    ):
        exit_types = exit_types or [1, 1]
        exit_idxs = exit_idxs or [1, 2]
        entry_idxs = entry_idxs or [0, 1]
        entry_timestamps = entry_timestamps or ["2024-01-02", "2024-01-03"]
        exit_timestamps = exit_timestamps or ["2024-01-03", "2024-01-04"]
        self.records = pd.DataFrame(
            {
                "pnl": [1_578_907.98, -206_767.98],
                "return": [0.12, -0.10],
                "exit_type": exit_types,
                "exit_idx": exit_idxs,
                "entry_idx": entry_idxs,
            }
        )
        self.records_readable = pd.DataFrame(
            {
                "Column": ["005930", "005930"],
                "Column Idx": [0, 0],
                "Entry Timestamp": pd.to_datetime(entry_timestamps),
                "Exit Timestamp": pd.to_datetime(exit_timestamps),
                "Avg Entry Price": [100.0, 100.0],
                "Avg Exit Price": [112.0, 90.0],
                "Size": [1.0, 1.0],
                "PnL": [1_578_907.98, -206_767.98],
                "Return": [0.12, -0.10],
            }
        )
        self.winning = _TradesView(1_578_907.98, 1)
        self.losing = _TradesView(-206_767.98, 1)

    def __len__(self):
        return len(self.records)

    def profit_factor(self):
        return 1.5

    def count(self, group_by=False):
        return pd.Series([2])

    def win_rate(self, group_by=False):
        return pd.Series([0.5])


class _Portfolio:
    def __init__(self, trades=None):
        self.trades = trades or _Trades()

    def benchmark_returns(self):
        return pd.Series([0.0, 0.01, -0.01])

    def total_return(self, group_by=True):
        if group_by is False:
            return pd.Series([0.02])
        return 0.02

    def annualized_return(self, group_by=False):
        return pd.Series([0.02])

    def max_drawdown(self, group_by=True):
        if group_by is False:
            return pd.Series([-0.05])
        return -0.05

    def returns(self, group_by=True):
        return pd.Series([0.0, 0.01, -0.005])

    def value(self):
        return pd.Series([10_000_000.0, 10_100_000.0, 10_200_000.0])

    def total_profit(self, group_by=True):
        if group_by is False:
            return pd.Series([200_000.0])
        return 200_000.0


def test_format_results_uses_trade_return_percentages_for_avg_win_loss():
    pf = _Portfolio()
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={},
        common_index=common_index,
        risk_params={"stop_loss_pct": 10},
        exec_type="close",
        init_cash=10_000_000,
    )

    assert result["avgProfit"] == 12.0
    assert result["avgLoss"] == 10.0


def test_format_results_marks_final_day_exit_as_backtest_end_over_max_hold():
    pf = _Portfolio(
        trades=_Trades(
            exit_types=[0, 0],
            exit_idxs=[1041, 2],
            entry_idxs=[0, 1],
            entry_timestamps=["2020-01-01", "2024-01-03"],
            exit_timestamps=["2022-11-07", "2024-01-04"],
        )
    )
    common_index = pd.date_range("2020-01-01", periods=1042, freq="D")

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={},
        common_index=common_index,
        risk_params={"max_holding_days": 63},
        exec_type="close",
        init_cash=10_000_000,
    )

    sell_signals = [signal for signal in result["signals"] if signal["type"] == "sell"]

    assert sell_signals[0]["date"] == common_index[-1].strftime("%Y-%m-%d")
    assert "백테스트 종료" in sell_signals[0]["condition"]
    assert "보유 기간 만료" not in sell_signals[0]["condition"]


def test_format_results_matches_exit_reason_when_reason_index_uses_microseconds():
    pf = _Portfolio(
        trades=_Trades(
            exit_types=[0, 0],
            entry_timestamps=["2022-01-05", "2022-01-06"],
            exit_timestamps=["2022-01-13", "2022-01-14"],
        )
    )
    common_index = pd.to_datetime(["2022-01-05", "2022-01-13", "2026-05-29"])
    reason_index = pd.DatetimeIndex(
        np.array(["2022-01-13", "2026-05-28"], dtype="datetime64[us]")
    )

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={
            "005930": pd.Series(
                ["5일선-20일선 데드크로스", "데이터 종료"],
                index=reason_index,
            )
        },
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=10_000_000,
    )

    sell_signals = [signal for signal in result["signals"] if signal["type"] == "sell"]

    assert "5일선-20일선 데드크로스" in sell_signals[0]["condition"]
    assert "데이터 종료" not in sell_signals[0]["condition"]
