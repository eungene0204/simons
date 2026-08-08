import os
import sys

import numpy as np
import pandas as pd
import pytest

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


def test_per_asset_total_return_uses_trade_cost_basis_not_account_capital():
    """단일 종목 1회 거래 시 종목분석표 수익률이 계좌 전체자본(10,000,000원)이
    아니라 해당 거래에 실제 투입된 원가(진입가×수량) 대비로 계산되어야 한다.
    회귀 전에는 pf.total_return(group_by=False)이 전체자본을 분모로 써서
    매매기록 인라인 수익률(예: +316.36%)과 다른 값(예: 31.30%)이 나왔다."""
    entry_price = 20_619.0
    size = 48.0
    pnl = 3_129_685.0
    trade_return = pnl / (entry_price * size)  # 거래 원가 대비 수익률 (≈3.1636 → +316.36%)

    trades = _Trades()
    trades.records = pd.DataFrame(
        {
            "pnl": [pnl],
            "return": [trade_return],
            "exit_type": [0],
            "exit_idx": [1],
            "entry_idx": [0],
        }
    )
    trades.records_readable = pd.DataFrame(
        {
            "Column": ["034020"],
            "Column Idx": [0],
            "Entry Timestamp": pd.to_datetime(["2024-01-02"]),
            "Exit Timestamp": pd.to_datetime(["2024-01-03"]),
            "Avg Entry Price": [entry_price],
            "Avg Exit Price": [85_957.0],
            "Size": [size],
            "PnL": [pnl],
            "Return": [trade_return],
        }
    )
    trades.winning = _TradesView(pnl, 1)
    trades.losing = _TradesView(0.0, 0)
    pf = _Portfolio(trades=trades)
    pf.count = lambda group_by=False: pd.Series([1])
    pf.trades.count = lambda group_by=False: pd.Series([1])
    pf.trades.win_rate = lambda group_by=False: pd.Series([1.0])
    pf.total_profit = lambda group_by=True: pnl if group_by is True else pd.Series([pnl])
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03"])

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["034020"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={},
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=10_000_000,
    )

    sell_signal = next(s for s in result["signals"] if s["type"] == "sell")
    per_asset_return = result["perAssetStats"]["034020"]["totalReturn"]

    assert per_asset_return == pytest.approx(trade_return * 100, abs=0.01)
    assert f"{trade_return * 100:+.2f}%" in sell_signal["condition"]


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


# ── 벤치마크 커버리지 (엔진 v11.0) ───────────────────────────────────────────

def _bench_result(benchmark_prices, common_index):
    return ResultHandler.format_results(
        pf=_Portfolio(),
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={},
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=10_000_000,
        benchmark_prices=benchmark_prices,
    )


def test_benchmark_equity_is_null_before_the_index_exists():
    """벤치마크 지수 상장 이전 구간에 가짜 평탄선을 그리지 않는다.

    회귀 전에는 .bfill()이 첫 가격을 뒤채워 그 구간 수익률이 0%로 깔렸고,
    수익곡선에 초기자본에서 평탄한 선이 그려져 "그때 벤치마크는 제자리였다"는
    거짓 정보가 됐다(존재하지 않던 지수다).
    """
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.Series([100.0, 110.0], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))

    result = _bench_result(prices, common_index)

    assert result["benchmark_equity"][0] is None
    assert result["benchmark_equity"][1] == pytest.approx(10_000_000)
    assert result["benchmark_equity"][2] == pytest.approx(11_000_000)


def test_benchmark_return_measures_only_the_covered_window():
    """벤치마크 수익률은 지수가 실제로 존재한 구간 기준이다.

    (뒤채우기 구간은 수익률 0%라 누적곱이 같았으므로 이 값은 회귀 전후 동일하다 —
    기간 불일치 자체는 데이터로 메울 수 없어 엔진이 경고로 고지한다.)
    """
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.Series([100.0, 110.0], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))

    result = _bench_result(prices, common_index)

    assert result["buyAndHoldReturn"] == pytest.approx(10.0)


def test_benchmark_with_full_coverage_has_no_nulls():
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.Series([100.0, 100.0, 120.0], index=common_index)

    result = _bench_result(prices, common_index)

    assert None not in result["benchmark_equity"]
    assert result["benchmark_equity"][0] == pytest.approx(10_000_000)
    assert result["buyAndHoldReturn"] == pytest.approx(20.0)


def test_benchmark_partial_flags_a_shorter_comparison_window():
    """벤치마크가 구간 일부만 덮으면 표시 쪽이 알 수 있게 flag를 세운다.

    두 수익률의 기간이 다르면 차이(초과수익률)가 비교값이 되지 못하는데,
    값만 보면 구별할 수 없어 화면이 잘못된 비교를 그릴 수 있다.
    """
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.Series([100.0, 110.0], index=pd.to_datetime(["2024-01-03", "2024-01-04"]))

    assert _bench_result(prices, common_index)["benchmark_partial"] is True


def test_benchmark_partial_is_false_with_full_coverage():
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    prices = pd.Series([100.0, 100.0, 120.0], index=common_index)

    assert _bench_result(prices, common_index)["benchmark_partial"] is False
