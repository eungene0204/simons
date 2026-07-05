"""MACD/스토캐스틱/볼린저 기간 파라미터화 테스트 (engine/indicator_columns.py).

기본값이면 기존 stockstats 컬럼(macd/kdjk/boll_ub)을 그대로 써서 과거 결과와의
동일성을 보존하고, 파라미터가 명시되면 파라미터화 컬럼을 계산·사용해야 한다.
"""

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine.indicator_columns import (
    bollinger_columns,
    macd_columns,
    stochastic_columns,
)
from engine.indicators import IndicatorEngine
from engine.signals import SignalEngine


@pytest.fixture
def ohlcv_df() -> pl.DataFrame:
    n = 200
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0.1, 1.2, n))
    pdf = pd.DataFrame({
        "date": pd.date_range("2024-01-02", periods=n).strftime("%Y-%m-%d"),
        "open": close + rng.normal(0, 0.3, n),
        "high": close + np.abs(rng.normal(0.8, 0.4, n)),
        "low": close - np.abs(rng.normal(0.8, 0.4, n)),
        "close": close,
        "volume": np.full(n, 10_000.0),
    })
    return pl.from_pandas(pdf)


class TestColumnNaming:
    def test_defaults_keep_legacy_columns(self):
        assert macd_columns({}) == ("macd", "macds")
        assert stochastic_columns({}) == ("kdjk", "kdjd")
        assert bollinger_columns({}) == ("boll_ub", "boll_lb")

    def test_custom_params_use_parameterized_columns(self):
        assert macd_columns({"fastPeriod": 10, "slowPeriod": 20, "signalPeriod": 5}) == (
            "macd_10,20,5", "macds_10,20,5",
        )
        assert stochastic_columns({"period": 14}) == ("kdjk_14", "kdjd_14")
        assert bollinger_columns({"period": 30}) == ("boll_ub_30", "boll_lb_30")
        assert bollinger_columns({"period": 30, "stdDev": 2.5}) == (
            "boll_ub_30_2p5", "boll_lb_30_2p5",
        )


class TestIndicatorCalculation:
    def test_macd_custom_periods_computed(self, ohlcv_df):
        cond = {"id": "macd", "params": {"fastPeriod": 10, "slowPeriod": 20, "signalPeriod": 5}}
        out = IndicatorEngine.calculate(ohlcv_df, [cond])
        assert "macd_10,20,5" in out.columns
        assert "macds_10,20,5" in out.columns

    def test_stochastic_custom_period_computed(self, ohlcv_df):
        cond = {"id": "stochastic", "params": {"period": 14}}
        out = IndicatorEngine.calculate(ohlcv_df, [cond])
        assert "kdjk_14" in out.columns
        assert "kdjd_14" in out.columns

    def test_bollinger_custom_period_and_std(self, ohlcv_df):
        cond = {"id": "bollinger_bands", "params": {"period": 30, "stdDev": 2.5}}
        out = IndicatorEngine.calculate(ohlcv_df, [cond])
        assert "boll_ub_30_2p5" in out.columns
        assert "boll_lb_30_2p5" in out.columns

        # 항등식 검증: ub == sma + 2.5σ (rolling std)
        pdf = out.to_pandas()
        sma = pdf["close"].rolling(30).mean()
        std = pdf["close"].rolling(30).std()
        expected_ub = (sma + 2.5 * std).to_numpy()
        actual_ub = pdf["boll_ub_30_2p5"].to_numpy()
        mask = ~np.isnan(expected_ub)
        assert np.allclose(actual_ub[mask], expected_ub[mask], rtol=1e-6)

    def test_default_params_keep_legacy_columns(self, ohlcv_df):
        conds = [
            {"id": "macd", "params": {}},
            {"id": "stochastic", "params": {}},
            {"id": "bollinger_bands", "params": {}},
        ]
        out = IndicatorEngine.calculate(ohlcv_df, conds)
        for col in ["macd", "macds", "kdjk", "kdjd", "boll_ub", "boll_lb"]:
            assert col in out.columns


class TestSignalEvaluation:
    def test_macd_custom_crossover_signals(self, ohlcv_df):
        cond = {"id": "macd", "params": {"fastPeriod": 5, "slowPeriod": 15, "signalPeriod": 4}}
        df = IndicatorEngine.calculate(ohlcv_df, [cond])
        engine = SignalEngine()
        signals = engine._eval_vec(cond, df)
        assert signals.dtype == bool
        assert signals.any()  # 200일 랜덤워크에서 단기 MACD 골든크로스는 반드시 발생

    def test_macd_custom_differs_from_default(self, ohlcv_df):
        default_cond = {"id": "macd", "params": {}}
        custom_cond = {"id": "macd", "params": {"fastPeriod": 5, "slowPeriod": 15, "signalPeriod": 4}}
        df = IndicatorEngine.calculate(ohlcv_df, [default_cond, custom_cond])
        engine = SignalEngine()
        default_signals = engine._eval_vec(default_cond, df)
        custom_signals = engine._eval_vec(custom_cond, df)
        assert not np.array_equal(default_signals, custom_signals)

    def test_stochastic_custom_period_level_mode(self, ohlcv_df):
        cond = {"id": "stochastic", "params": {"period": 14, "mode": "level", "value": 30}}
        df = IndicatorEngine.calculate(ohlcv_df, [cond])
        engine = SignalEngine()
        signals = engine._eval_vec(cond, df)
        pdf = df.to_pandas()
        expected = (pdf["kdjk_14"] < 30).fillna(False).to_numpy()
        assert np.array_equal(signals, expected)

    def test_bollinger_custom_band_touch(self, ohlcv_df):
        cond = {"id": "bollinger_bands", "params": {"period": 30, "stdDev": 2.5}}
        df = IndicatorEngine.calculate(ohlcv_df, [cond])
        engine = SignalEngine()
        signals = engine._eval_vec(cond, df)
        pdf = df.to_pandas()
        expected = (pdf["close"] <= pdf["boll_lb_30_2p5"]).fillna(False).to_numpy()
        assert np.array_equal(signals, expected)

    def test_row_evaluator_matches_vectorized_for_custom_macd(self, ohlcv_df):
        cond = {"id": "macd", "params": {"fastPeriod": 5, "slowPeriod": 15, "signalPeriod": 4}}
        df = IndicatorEngine.calculate(ohlcv_df, [cond])
        engine = SignalEngine()
        vec = engine._eval_vec(cond, df)
        rows = np.array([engine.evaluate_condition(cond, idx, df) for idx in range(len(df))])
        assert np.array_equal(vec, rows)
