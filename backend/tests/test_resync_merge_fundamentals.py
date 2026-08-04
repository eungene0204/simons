"""resync_kis_adjusted._merge_fundamentals 컬럼 보존 계약.

2026-08-04 사고: 이월 컬럼이 화이트리스트 5개(sector/eps/bps/roe_or_gpa/debt_ratio)라,
KIS 히스토리 백필이 parquet을 재작성할 때 목록 밖 컬럼이 전부 소실됐다. dividends가
1,016종목(삼성전자·SK하이닉스·현대차 포함)에서 날아가 배당 지표가 통째로 비었다.
이월은 뺄 것만 정하는 블랙리스트여야 한다.
"""
import os
import sys

import pandas as pd
import polars as pl
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "scripts"))
import resync_kis_adjusted as rk  # noqa: E402


@pytest.fixture
def old_parquet(tmp_path, monkeypatch):
    """보강 컬럼이 붙은 기존 parquet을 만들고 _OHLCV_DIR을 그쪽으로 돌린다."""
    monkeypatch.setattr(rk, "_OHLCV_DIR", tmp_path)

    def _write(df: pd.DataFrame, sym: str = "005930"):
        pl.from_pandas(df).write_parquet(tmp_path / f"{sym}.parquet")
        return sym

    return _write


def _old_frame(dates):
    """가격 + 연간 펀더멘털 + 배당 + 종가파생이 모두 붙은 parquet 한 장."""
    return pd.DataFrame({
        "date": dates,
        "open": [100.0] * len(dates),
        "high": [100.0] * len(dates),
        "low": [100.0] * len(dates),
        "close": [100.0] * len(dates),
        "volume": [10.0] * len(dates),
        "change": [0.0] * len(dates),
        "sector": ["전기전자"] * len(dates),
        "eps": [5.0] * len(dates),
        "bps": [50.0] * len(dates),
        "roe_or_gpa": [10.0] * len(dates),
        "debt_ratio": [40.0] * len(dates),
        # 화이트리스트 밖이라 예전 구현에서 소실되던 컬럼들
        "dividends": [0.0, 0.0, 3.0][: len(dates)] + [0.0] * max(0, len(dates) - 3),
        "net_income": [1000.0] * len(dates),
        "roa": [7.0] * len(dates),
        "ebitda": [2000.0] * len(dates),
        "total_equity": [5000.0] * len(dates),
        "net_income_growth_status": ["normal"] * len(dates),
        # 종가 파생 — 새 종가 기준으로 다시 계산돼야 하므로 이월하면 안 된다
        "per": [20.0] * len(dates),
        "pbr": [2.0] * len(dates),
        "market_cap": [9999.0] * len(dates),
        "dividend_yield": [3.0] * len(dates),
    })


def _new_frame(dates, close=200.0):
    """KIS가 새로 준 가격만 담긴 프레임(_fetch_full 출력 형태)."""
    return pd.DataFrame({
        "date": dates,
        "open": [close] * len(dates),
        "high": [close] * len(dates),
        "low": [close] * len(dates),
        "close": [close] * len(dates),
        "volume": [20.0] * len(dates),
        "change": [0.0] * len(dates),
    })


def test_non_price_columns_survive_rewrite(old_parquet):
    """회귀: 화이트리스트 밖 보강 컬럼이 재작성 후에도 남아야 한다."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    sym = old_parquet(_old_frame(dates))

    merged = rk._merge_fundamentals(_new_frame(dates), sym)

    for col in ("dividends", "net_income", "roa", "ebitda", "total_equity",
                "net_income_growth_status", "sector", "eps", "bps",
                "roe_or_gpa", "debt_ratio"):
        assert col in merged.columns, f"{col} 컬럼이 재작성으로 소실됐다"


def test_dividends_values_preserved_not_smeared(old_parquet):
    """dividends는 값이 보존되고, ex-date 값이 이후 봉으로 번지지 않아야 한다."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    sym = old_parquet(_old_frame(dates))

    merged = rk._merge_fundamentals(_new_frame(dates), sym)

    # 원본은 세 번째 봉에만 3.0 — 전진충전되면 마지막 봉도 3.0이 된다(오염).
    assert merged["dividends"].tolist() == [0.0, 0.0, 3.0, 0.0]


def test_annual_fundamentals_forward_filled(old_parquet):
    """연간 펀더멘털은 기존 데이터 이후 구간으로 전진충전된다(기존 동작 유지)."""
    old_dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    sym = old_parquet(_old_frame(old_dates))

    new_dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    merged = rk._merge_fundamentals(_new_frame(new_dates), sym)

    assert merged["eps"].tolist() == [5.0, 5.0, 5.0]
    assert merged["net_income"].tolist() == [1000.0, 1000.0, 1000.0]
    # 이벤트 시리즈는 전진충전 대상이 아니라 새 구간이 결측으로 남는다.
    assert pd.isna(merged["dividends"].iloc[2])


def test_close_derived_columns_dropped_for_recompute(old_parquet):
    """종가 파생 컬럼은 옛 기준 값이 이월되지 않아야 한다(백필이 새 종가로 재계산)."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    sym = old_parquet(_old_frame(dates))

    merged = rk._merge_fundamentals(_new_frame(dates, close=200.0), sym)

    # per/pbr은 이 함수가 새 종가로 다시 계산한다.
    assert merged["per"].tolist() == [40.0, 40.0]   # 200/5, 옛 값 20.0이 아님
    assert merged["pbr"].tolist() == [4.0, 4.0]     # 200/50, 옛 값 2.0이 아님
    # 나머지는 결측으로 남겨 펀더멘털 백필이 채우게 한다 — 낡은 기준 값 고착 방지.
    assert "market_cap" not in merged.columns
    assert "dividend_yield" not in merged.columns


def test_price_columns_come_from_new_data(old_parquet):
    """가격은 KIS 새 값이 정본 — 옛 parquet 값이 덮어쓰지 않는다."""
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    sym = old_parquet(_old_frame(dates))

    merged = rk._merge_fundamentals(_new_frame(dates, close=200.0), sym)

    assert merged["close"].tolist() == [200.0, 200.0]
    assert merged["volume"].tolist() == [20.0, 20.0]


def test_no_old_parquet_is_noop(old_parquet, tmp_path, monkeypatch):
    """기존 parquet이 없으면(신규 종목) 그대로 통과한다."""
    monkeypatch.setattr(rk, "_OHLCV_DIR", tmp_path)
    dates = pd.to_datetime(["2024-01-02"])

    merged = rk._merge_fundamentals(_new_frame(dates), "999999")

    assert merged["close"].tolist() == [200.0]
    assert "eps" not in merged.columns
