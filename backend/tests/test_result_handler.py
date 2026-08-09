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


def test_final_day_exit_keeps_simulator_override_reason():
    """마지막 봉에 발동한 시뮬레이터 확정 사유(리밸런싱 편출·손절 등)는 보존한다.

    회귀 전에는 날짜만 보고 마지막 날 청산을 전부 "백테스트 종료"로 덮어써
    실제 사유가 가려졌다.
    """
    pf = _Portfolio(
        trades=_Trades(
            exit_types=[0, 0],
            entry_timestamps=["2024-01-02", "2024-01-02"],
            exit_timestamps=["2024-01-03", "2024-01-04"],
        )
    )
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
        exit_reason_overrides={"005930": {"2024-01-04": "리밸런싱 제외 (목표 종목 이탈)"}},
    )

    sell_signals = [s for s in result["signals"] if s["type"] == "sell"]
    final_day = [s for s in sell_signals if s["date"] == "2024-01-04"]

    assert "리밸런싱 제외" in final_day[0]["condition"]
    assert "백테스트 종료" not in final_day[0]["condition"]


def test_final_day_exit_keeps_strategy_signal_reason():
    """마지막 봉에 실제 전략 매도 신호가 발동했으면 그 사유를 표시한다."""
    pf = _Portfolio(
        trades=_Trades(
            exit_types=[0, 0],
            entry_timestamps=["2024-01-02", "2024-01-02"],
            exit_timestamps=["2024-01-03", "2024-01-04"],
        )
    )
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={
            "005930": pd.Series(
                ["5일선-20일선 데드크로스"], index=pd.to_datetime(["2024-01-04"])
            )
        },
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=10_000_000,
    )

    sell_signals = [s for s in result["signals"] if s["type"] == "sell"]
    final_day = [s for s in sell_signals if s["date"] == "2024-01-04"]

    assert "데드크로스" in final_day[0]["condition"]
    assert "백테스트 종료" not in final_day[0]["condition"]


def test_final_day_forced_close_without_reason_is_labeled_backtest_end():
    """사유 없는 기말 강제 정산('데이터 종료' 포함)만 "백테스트 종료"로 표기한다."""
    pf = _Portfolio(
        trades=_Trades(
            exit_types=[0, 0],
            entry_timestamps=["2024-01-02", "2024-01-02"],
            exit_timestamps=["2024-01-03", "2024-01-04"],
        )
    )
    common_index = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])

    result = ResultHandler.format_results(
        pf=pf,
        processed_symbols=["005930"],
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={
            "005930": pd.Series(["데이터 종료"], index=pd.to_datetime(["2024-01-04"]))
        },
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=10_000_000,
    )

    sell_signals = [s for s in result["signals"] if s["type"] == "sell"]
    final_day = [s for s in sell_signals if s["date"] == "2024-01-04"]

    assert "백테스트 종료" in final_day[0]["condition"]


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


# ── 엔진 v12.0: 결과값 감사에서 찾은 지표 계산 오류의 회귀 테스트 ──────────────


def _metrics_result(pf, common_index, symbols=("005930",), init_cash=10_000_000):
    return ResultHandler.format_results(
        pf=pf,
        processed_symbols=list(symbols),
        _all_entries=None,
        _all_exits=None,
        all_entry_reasons={},
        all_exit_reasons={},
        common_index=common_index,
        risk_params={},
        exec_type="close",
        init_cash=init_cash,
    )


def test_time_base_counts_calendar_years_not_bars_over_252():
    """연수는 달력 경과일 기준이어야 한다.

    회귀 전에는 '봉 수 ÷ 252'로 셌는데 KRX 실제 거래일은 연 246.5일이라 연수를
    약 2% 적게 잡고 그만큼 CAGR을 과대계상했다.
    """
    idx = pd.DatetimeIndex(pd.date_range("2019-01-02", "2024-12-30", freq="B")[:1477])
    n_years, ppy = ResultHandler.time_base(idx)

    expected = (idx[-1] - idx[0]).days / 365.25
    assert n_years == pytest.approx(expected)
    assert n_years != pytest.approx(len(idx) / 252.0)
    assert ppy == pytest.approx(246.0)


def test_time_base_falls_back_when_span_is_degenerate():
    """경과일을 셀 수 없는 구간(봉 1개)은 봉 수 기준으로 되돌린다."""
    n_years, ppy = ResultHandler.time_base(pd.to_datetime(["2024-01-02"]))
    assert n_years == pytest.approx(1 / 246.0)
    assert ppy == pytest.approx(246.0)


def test_annualize_return_annualizes_periods_under_one_year():
    """1년 미만 구간도 정의대로 연환산한다.

    회귀 전에는 총수익률을 그대로 CAGR 칸에 넣어(13.11% → CAGR 13.11%) 라벨과
    값이 어긋났다.
    """
    half_year = 0.5
    assert ResultHandler.annualize_return(0.1311, half_year) == pytest.approx(
        ((1.1311 ** 2) - 1) * 100
    )
    # 전액 손실은 복리 밑이 0 이하라 -100%로 둔다
    assert ResultHandler.annualize_return(-1.0, 3.0) == -100.0


def test_profit_factor_is_null_when_there_are_no_losing_trades():
    """손실 거래가 0건이면 손익비는 정의되지 않는다(∞) → null.

    회귀 전에는 safe()가 inf를 0.0으로 뭉개 전승한 전략이 손익비 0(최악)으로
    표시됐다.
    """
    pf = _Portfolio()
    pf.trades.profit_factor = lambda: float("inf")
    result = _metrics_result(pf, pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))

    assert result["profitFactor"] is None


def test_profit_factor_reports_finite_value_unchanged():
    pf = _Portfolio()
    result = _metrics_result(pf, pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))

    assert result["profitFactor"] == pytest.approx(1.5)


def test_kelly_is_computed_from_average_win_loss_ratio():
    """켈리 기준 f* = W − (1−W)/R.

    회귀 전에는 백엔드가 이 값을 아예 내려보내지 않아 프론트가 0으로 채웠고,
    AI 리포트 프롬프트에 '켈리 기준: 0.00%'가 사실처럼 주입됐다.
    """
    # _Trades 기본값: 거래 2건(return +12%, -10%) → W=0.5, R=1.2
    pf = _Portfolio()
    result = _metrics_result(pf, pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))

    expected = (0.5 - 0.5 / (12.0 / 10.0)) * 100
    assert result["kelly"] == pytest.approx(expected)


def test_kelly_is_null_when_one_side_has_no_sample():
    """승 또는 패 표본이 없으면 R을 정의할 수 없어 켈리도 null이다."""
    pnl = 1_000.0
    trades = _Trades()
    trades.records = pd.DataFrame(
        {"pnl": [pnl], "return": [0.2], "exit_type": [0], "exit_idx": [1], "entry_idx": [0]}
    )
    trades.records_readable = trades.records_readable.iloc[:1].copy()
    trades.winning = _TradesView(pnl, 1)
    trades.losing = _TradesView(0.0, 0)
    pf = _Portfolio(trades=trades)
    pf.trades.count = lambda group_by=False: pd.Series([1])
    pf.trades.win_rate = lambda group_by=False: pd.Series([1.0])

    result = _metrics_result(pf, pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))

    assert result["kelly"] is None


def test_per_asset_cagr_shares_the_same_base_as_per_asset_total_return():
    """종목별 cagr은 같은 행 totalReturn을 같은 연수로 연환산한 값이어야 한다.

    회귀 전에는 vbt annualized_return(포트폴리오 초기자본 기준 + 365일 연환산)을
    써서 같은 행에 분모가 두 개였다.
    """
    common_index = pd.DatetimeIndex(pd.date_range("2020-01-02", "2024-12-30", freq="B"))
    pf = _Portfolio()
    pf.trades.count = lambda group_by=False: pd.Series([2])
    pf.trades.win_rate = lambda group_by=False: pd.Series([0.5])

    result = _metrics_result(pf, common_index)
    stats = result["perAssetStats"]["005930"]

    n_years, _ = ResultHandler.time_base(common_index)
    assert stats["cagr"] == pytest.approx(
        ((1 + stats["totalReturn"] / 100) ** (1 / n_years) - 1) * 100
    )


def test_max_consecutive_losses_ignores_break_even_trades():
    """손익 0인 거래는 승도 패도 아니다 — 연속 패를 끊는다.

    회귀 전에는 `1 - is_win`으로 세어 본전 거래를 패로 취급했다.
    """
    trades = _Trades()
    trades.records = pd.DataFrame(
        {
            "pnl": [-100.0, 0.0, -100.0],
            "return": [-0.01, 0.0, -0.01],
            "exit_type": [0, 0, 0],
            "exit_idx": [1, 2, 3],
            "entry_idx": [0, 1, 2],
        }
    )
    pf = _Portfolio(trades=trades)
    pf.trades.count = lambda group_by=False: pd.Series([3])
    pf.trades.win_rate = lambda group_by=False: pd.Series([0.0])

    result = _metrics_result(pf, pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]))

    assert result["maxConsecutiveLosses"] == 1


def test_sharpe_and_volatility_use_sample_stddev_and_krx_annualization():
    """샤프·변동성은 표본 표준편차(ddof=1) × √246 이어야 한다.

    회귀 전에는 모집단 표준편차(ddof=0) × √252 라 변동성을 과소·샤프를 과대
    평가했다.
    """
    rets = pd.Series([0.0, 0.01, -0.005, 0.004, -0.002])
    pf = _Portfolio()
    pf.returns = lambda group_by=True: rets
    common_index = pd.DatetimeIndex(pd.date_range("2024-01-02", periods=len(rets), freq="B"))

    result = _metrics_result(pf, common_index)

    arr = rets.to_numpy(dtype=float)
    ann = np.sqrt(246.0)
    assert result["volatility"] == pytest.approx(arr.std(ddof=1) * ann * 100)
    assert result["sharpe"] == pytest.approx(arr.mean() * ann / arr.std(ddof=1))
