import pytest
import pandas as pd
import polars as pl
from engine.indicators import IndicatorEngine

def test_indicator_index_alignment():
    # Create DataFrame with RangeIndex but specific dates
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=30),
        'open': [100.0] * 30,
        'high': [105.0] * 30,
        'low': [95.0] * 30,
        'close': [102.0] * 30,
        'volume': [1000000.0] * 30
    })
    
    # Intentionally do not set index to 'date' here, just like how it comes from loader
    df_pl = pl.from_pandas(df)
    
    conditions = [
        {'id': 'ma_crossover', 'params': {'short': 5, 'long': 20}}
    ]
    
    res_pl = IndicatorEngine.calculate(df_pl, conditions)
    res_df = res_pl.to_pandas()
    
    # Check that moving averages were calculated and are not all NaNs
    assert 'close_5_sma' in res_df.columns
    assert 'close_20_sma' in res_df.columns
    
    # The first 4 rows of 5 SMA will be NaN, but the 5th should have a value
    assert not res_df['close_5_sma'].isna().all(), "close_5_sma is entirely NaN due to index alignment issue"
    assert not res_df['close_20_sma'].isna().all(), "close_20_sma is entirely NaN due to index alignment issue"
    
    # Check specific value
    assert res_df['close_5_sma'].iloc[4] == 102.0
    assert res_df['close_20_sma'].iloc[19] == 102.0


def _base_df_pl(periods=30):
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=periods),
        'open':   [100.0] * periods,
        'high':   [105.0] * periods,
        'low':    [95.0]  * periods,
        'close':  [102.0] * periods,
        'volume': [1000000.0] * periods,
    })
    return pl.from_pandas(df)


# ──────────────────────────────────────────────────────────────────────────────
# EMA 크로스오버 — shortPeriod/longPeriod 파라미터 지원 테스트
# ──────────────────────────────────────────────────────────────────────────────

def test_ema_dual_crossover_columns_computed():
    """shortPeriod/longPeriod 지정 시 두 EMA 컬럼이 모두 계산된다"""
    df_pl = _base_df_pl(30)
    conditions = [
        {'id': 'ema', 'params': {'shortPeriod': 5, 'longPeriod': 20}}
    ]
    res = IndicatorEngine.calculate(df_pl, conditions).to_pandas()

    assert 'close_5_ema'  in res.columns, "close_5_ema 컬럼이 없음"
    assert 'close_20_ema' in res.columns, "close_20_ema 컬럼이 없음"
    assert not res['close_5_ema'].isna().all(),  "close_5_ema 전체 NaN"
    assert not res['close_20_ema'].isna().all(), "close_20_ema 전체 NaN"


def test_ema_single_period_column_computed():
    """period 파라미터만 지정해도 단일 EMA 컬럼이 계산된다"""
    df_pl = _base_df_pl(30)
    conditions = [{'id': 'ema', 'params': {'period': 12}}]
    res = IndicatorEngine.calculate(df_pl, conditions).to_pandas()

    assert 'close_12_ema' in res.columns, "close_12_ema 컬럼이 없음"
    assert not res['close_12_ema'].isna().all(), "close_12_ema 전체 NaN"


def test_ema_dual_does_not_fallback_to_default_period():
    """shortPeriod/longPeriod 지정 시 기본 period(20)가 아닌 지정 컬럼만 계산된다"""
    df_pl = _base_df_pl(30)
    # shortPeriod=12, longPeriod=26 → close_12_ema, close_26_ema 필요
    conditions = [{'id': 'ema', 'params': {'shortPeriod': 12, 'longPeriod': 26}}]
    res = IndicatorEngine.calculate(df_pl, conditions).to_pandas()

    assert 'close_12_ema' in res.columns
    assert 'close_26_ema' in res.columns
