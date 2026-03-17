"""
pytest conftest.py - MockDataGenerator 기반 공용 fixture
=========================================================
모든 백엔드 테스트에서 사용 가능한 공용 fixture를 정의합니다.

사용 예:
    def test_something(mock_ohlcv, mock_data_dir):
        engine = BacktestEngine(data_dir=mock_data_dir)
        ...
"""

import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest

from engine.mock_data_generator import MockDataGenerator, make_test_parquet

# ────────────────────────────────────────────────────────────────────
# Generator fixture
# ────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def mock_gen() -> MockDataGenerator:
    """재현 가능한 MockDataGenerator (seed=42, 세션 공유)"""
    return MockDataGenerator(seed=42)


# ────────────────────────────────────────────────────────────────────
# 단일 종목 OHLCV DataFrame fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ohlcv(mock_gen) -> pd.DataFrame:
    """252일 realistic 시나리오 OHLCV (기준가 50,000원)"""
    return mock_gen.generate_ohlcv("MOCK", base_price=50_000, days=252, scenario="realistic")


@pytest.fixture
def mock_bull(mock_gen) -> pd.DataFrame:
    """252일 상승장 OHLCV"""
    return mock_gen.generate_ohlcv("BULL", base_price=50_000, days=252, scenario="bull")


@pytest.fixture
def mock_bear(mock_gen) -> pd.DataFrame:
    """252일 하락장 OHLCV"""
    return mock_gen.generate_ohlcv("BEAR", base_price=50_000, days=252, scenario="bear")


@pytest.fixture
def mock_sideways(mock_gen) -> pd.DataFrame:
    """252일 횡보장 OHLCV"""
    return mock_gen.generate_ohlcv("SIDE", base_price=50_000, days=252, scenario="sideways")


@pytest.fixture
def mock_volatile(mock_gen) -> pd.DataFrame:
    """252일 고변동성 OHLCV"""
    return mock_gen.generate_ohlcv("VOLA", base_price=50_000, days=252, scenario="volatile")


@pytest.fixture
def mock_crash(mock_gen) -> pd.DataFrame:
    """252일 급락 후 회복 OHLCV"""
    return mock_gen.generate_ohlcv("CRASH", base_price=50_000, days=252, scenario="crash_recovery")


@pytest.fixture
def mock_short(mock_gen) -> pd.DataFrame:
    """20일 단기 OHLCV (지표 계산 전 단위 테스트용)"""
    return mock_gen.generate_ohlcv("SHORT", base_price=10_000, days=20, scenario="realistic")


# ────────────────────────────────────────────────────────────────────
# Parquet 디렉토리 fixtures (BacktestEngine / DataLoader 용)
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_data_dir(mock_gen, tmp_path) -> str:
    """
    tmp_path에 3개 종목 parquet 파일을 생성하고 디렉토리 경로를 반환합니다.
    BacktestEngine(data_dir=mock_data_dir) 패턴에서 사용합니다.

    종목:
        ALPHA  (realistic, 50,000원)
        BETA   (bull,      30,000원)
        GAMMA  (bear,      80,000원)
    """
    data_dir = str(tmp_path / "ohlcv")
    make_test_parquet(
        output_dir=data_dir,
        symbols=["ALPHA", "BETA", "GAMMA"],
        base_prices={"ALPHA": 50_000, "BETA": 30_000, "GAMMA": 80_000},
        days=252,
        start_date="2023-01-01",
        scenario="realistic",
        seed=42,
    )
    return data_dir


@pytest.fixture
def mock_data_dir_bull(mock_gen, tmp_path) -> str:
    """상승장 시나리오 parquet 디렉토리"""
    data_dir = str(tmp_path / "ohlcv_bull")
    make_test_parquet(
        output_dir=data_dir,
        symbols=["BULL_A", "BULL_B"],
        base_prices={"BULL_A": 50_000, "BULL_B": 50_000},
        days=252,
        scenario="bull",
        seed=42,
    )
    return data_dir


@pytest.fixture
def mock_data_dir_crash(mock_gen, tmp_path) -> str:
    """급락/회복 시나리오 parquet 디렉토리"""
    data_dir = str(tmp_path / "ohlcv_crash")
    make_test_parquet(
        output_dir=data_dir,
        symbols=["CRASH_A"],
        base_prices={"CRASH_A": 100_000},
        days=252,
        scenario="crash_recovery",
        seed=42,
    )
    return data_dir


# ────────────────────────────────────────────────────────────────────
# Simulator 용 행렬 fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def sim_matrices(mock_gen):
    """
    Simulator.run()에 직접 전달 가능한 DataFrame 행렬 반환.

    Returns:
        (price_df, exec_price_df, entries_df, exits_df)
    """
    symbols = ["SIM_A", "SIM_B", "SIM_C"]
    days = 60
    dfs = {sym: mock_gen.generate_ohlcv(sym, 50_000, days, "2023-01-01", "realistic")
           for sym in symbols}

    dates = pd.to_datetime(dfs[symbols[0]]["date"])
    closes = pd.DataFrame({sym: dfs[sym]["close"].values for sym in symbols}, index=dates)
    opens  = pd.DataFrame({sym: dfs[sym]["open"].values  for sym in symbols}, index=dates)

    entries = pd.DataFrame(False, index=dates, columns=symbols)
    exits   = pd.DataFrame(False, index=dates, columns=symbols)

    # 매 20일마다 진입, 10일 후 청산
    for i in range(0, days - 10, 20):
        entries.iloc[i]      = True
        exits.iloc[i + 10]   = True

    return closes, opens, entries, exits


# ────────────────────────────────────────────────────────────────────
# Polars DataFrame fixture (signals.py / indicators.py 용)
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_polars(mock_gen):
    """
    Polars DataFrame 형식 OHLCV (SignalEngine 입력 형식).
    컬럼: date(str), open, high, low, close, volume
    """
    import polars as pl
    df = mock_gen.generate_ohlcv("POLARS", 50_000, 252, "2023-01-01", "realistic")
    return pl.from_pandas(df)
