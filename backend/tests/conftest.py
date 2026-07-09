"""
pytest conftest.py - 테스트용 공용 fixture
"""

import os
import tempfile

import numpy as np
import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


def _ensure_test_runtime_cache_dirs() -> None:
    numba_cache_dir = os.environ.get("NUMBA_CACHE_DIR")
    if not numba_cache_dir:
        numba_cache_dir = os.path.join(tempfile.gettempdir(), "simons-numba-cache")
        os.environ["NUMBA_CACHE_DIR"] = numba_cache_dir
    os.makedirs(numba_cache_dir, exist_ok=True)

    mpl_config_dir = os.environ.get("MPLCONFIGDIR")
    if not mpl_config_dir:
        mpl_config_dir = os.path.join(tempfile.gettempdir(), "simons-matplotlib")
        os.environ["MPLCONFIGDIR"] = mpl_config_dir
    os.makedirs(mpl_config_dir, exist_ok=True)


_ensure_test_runtime_cache_dirs()


# ────────────────────────────────────────────────────────────────────
# 앱 DB(Postgres) 테스트 픽스처
# 코드가 db.connect()로 읽는 DATABASE_URL을 로컬 simons_test로 지정하고,
# 각 테스트 전에 모든 앱 테이블을 TRUNCATE해 격리한다.
# 스키마는 prisma/migrations/0_init/migration.sql로 미리 적재돼 있어야 한다.
# ────────────────────────────────────────────────────────────────────

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://simons:simons@localhost:5432/simons_test",
)


@pytest.fixture
def app_db():
    import sys
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    import db as _db

    conn = _db.connect()
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ).fetchall()
    ]
    if tables:
        conn.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")
        conn.commit()
    try:
        yield conn
    finally:
        conn.close()
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev


# ────────────────────────────────────────────────────────────────────
# 간단한 OHLCV 생성 헬퍼 (MockDataGenerator 대체)
# ────────────────────────────────────────────────────────────────────

def _generate_ohlcv(symbol: str, base_price: float, days: int,
                    start_date: str = "2023-01-01", seed: int = 42) -> pd.DataFrame:
    """재현 가능한 랜덤 OHLCV DataFrame 생성"""
    rng = np.random.default_rng(seed + hash(symbol) % 10000)
    dates = pd.bdate_range(start_date, periods=days)
    returns = rng.normal(0.0005, 0.02, days)
    closes = base_price * np.cumprod(1 + returns)
    opens = closes * (1 + rng.normal(0, 0.005, days))
    highs = np.maximum(closes, opens) * (1 + rng.uniform(0, 0.015, days))
    lows = np.minimum(closes, opens) * (1 - rng.uniform(0, 0.015, days))
    volumes = rng.integers(100_000, 5_000_000, days).astype(int)

    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens.astype(int),
        "high": highs.astype(int),
        "low": lows.astype(int),
        "close": closes.astype(int),
        "volume": volumes,
    })


def _write_parquet(df: pd.DataFrame, path: str):
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path)


# ────────────────────────────────────────────────────────────────────
# Session-level generator stub
# ────────────────────────────────────────────────────────────────────

class _MockGen:
    def __init__(self, seed=42):
        self.seed = seed

    def generate_ohlcv(self, symbol, base_price=50000, days=252,
                       start_date="2023-01-01", **_kwargs) -> pd.DataFrame:
        return _generate_ohlcv(symbol, base_price, days, start_date, self.seed)


@pytest.fixture(autouse=True)
def _disable_parse_validator_network(monkeypatch):
    """parse() 룰베이스 검증 LLM 레이어는 항상 인라인이지만, 유닛 테스트는 네트워크에
    의존하면 안 된다(로컬 ollama가 떠 있으면 실제 호출이 나간다). 기본적으로 LLM 도달
    불가로 만들어 graceful degrade(원본 그대로)시킨다. 검증 로직 자체는
    test_parse_validator.py가 _run_validation_llm을 직접 patch해서 검증한다."""
    try:
        from engine import parse_validator
    except Exception:
        return
    monkeypatch.setattr(parse_validator, "_ollama_reachable", lambda *a, **k: False)


@pytest.fixture(scope="session")
def mock_gen():
    return _MockGen(seed=42)


# ────────────────────────────────────────────────────────────────────
# 단일 종목 OHLCV DataFrame fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ohlcv(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("MOCK", base_price=50_000, days=252)


@pytest.fixture
def mock_bull(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("BULL", base_price=50_000, days=252)


@pytest.fixture
def mock_bear(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("BEAR", base_price=50_000, days=252)


@pytest.fixture
def mock_sideways(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("SIDE", base_price=50_000, days=252)


@pytest.fixture
def mock_volatile(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("VOLA", base_price=50_000, days=252)


@pytest.fixture
def mock_crash(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("CRASH", base_price=50_000, days=252)


@pytest.fixture
def mock_short(mock_gen) -> pd.DataFrame:
    return mock_gen.generate_ohlcv("SHORT", base_price=10_000, days=20)


# ────────────────────────────────────────────────────────────────────
# Parquet 디렉토리 fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_data_dir(mock_gen, tmp_path) -> str:
    data_dir = str(tmp_path / "ohlcv")
    os.makedirs(data_dir, exist_ok=True)
    for sym, price in [("ALPHA", 50_000), ("BETA", 30_000), ("GAMMA", 80_000)]:
        df = mock_gen.generate_ohlcv(sym, price, 252)
        _write_parquet(df, os.path.join(data_dir, f"{sym}.parquet"))
    return data_dir


@pytest.fixture
def mock_data_dir_bull(mock_gen, tmp_path) -> str:
    data_dir = str(tmp_path / "ohlcv_bull")
    os.makedirs(data_dir, exist_ok=True)
    for sym in ["BULL_A", "BULL_B"]:
        df = mock_gen.generate_ohlcv(sym, 50_000, 252)
        _write_parquet(df, os.path.join(data_dir, f"{sym}.parquet"))
    return data_dir


@pytest.fixture
def mock_data_dir_crash(mock_gen, tmp_path) -> str:
    data_dir = str(tmp_path / "ohlcv_crash")
    os.makedirs(data_dir, exist_ok=True)
    df = mock_gen.generate_ohlcv("CRASH_A", 100_000, 252)
    _write_parquet(df, os.path.join(data_dir, "CRASH_A.parquet"))
    return data_dir


# ────────────────────────────────────────────────────────────────────
# Simulator 용 행렬 fixtures
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def sim_matrices(mock_gen):
    symbols = ["SIM_A", "SIM_B", "SIM_C"]
    days = 60
    dfs = {sym: mock_gen.generate_ohlcv(sym, 50_000, days) for sym in symbols}

    dates = pd.to_datetime(dfs[symbols[0]]["date"])
    closes = pd.DataFrame({sym: dfs[sym]["close"].values for sym in symbols}, index=dates)
    opens = pd.DataFrame({sym: dfs[sym]["open"].values for sym in symbols}, index=dates)

    entries = pd.DataFrame(False, index=dates, columns=symbols)
    exits = pd.DataFrame(False, index=dates, columns=symbols)

    for i in range(0, days - 10, 20):
        entries.iloc[i] = True
        exits.iloc[i + 10] = True

    return closes, opens, entries, exits


# ────────────────────────────────────────────────────────────────────
# Polars DataFrame fixture
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_polars(mock_gen):
    df = mock_gen.generate_ohlcv("POLARS", 50_000, 252)
    return pl.from_pandas(df)
