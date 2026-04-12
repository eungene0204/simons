"""DataResolver 유닛 테스트 — 누락 데이터 해결 엔진."""

import numpy as np
import polars as pl
import pytest
from unittest.mock import patch, MagicMock

from engine.data_resolver import DataResolver, _collect_all_conditions, _get_required_columns


# ── 헬퍼 ─────────────────────────────────────────────────────────────

def _make_ohlcv(rows: int = 100) -> pl.DataFrame:
    """기본 OHLCV DataFrame 생성."""
    dates = [f"2024-01-{i+1:02d}" for i in range(rows)]
    return pl.DataFrame({
        "date": dates,
        "open": np.random.uniform(1000, 2000, rows),
        "high": np.random.uniform(1500, 2500, rows),
        "low": np.random.uniform(500, 1000, rows),
        "close": np.random.uniform(1000, 2000, rows),
        "volume": np.random.randint(10000, 100000, rows),
    })


def _make_entry_group(*conditions):
    return {"logic": "OR", "conditions": list(conditions)}


def _make_condition(cid: str, params: dict = None, ctype: str = "filter"):
    return {"id": cid, "params": params or {}, "type": ctype}


# ── _collect_all_conditions ──────────────────────────────────────────

class TestCollectAllConditions:
    def test_flat_conditions(self):
        group = {"conditions": [
            {"id": "rsi", "params": {}},
            {"id": "per", "params": {}},
        ]}
        result = _collect_all_conditions(group)
        assert len(result) == 2
        assert result[0]["id"] == "rsi"

    def test_nested_conditions(self):
        group = {"conditions": [
            {"id": "rsi", "params": {}},
            {"conditions": [
                {"id": "per", "params": {}},
                {"id": "pbr", "params": {}},
            ]},
        ]}
        result = _collect_all_conditions(group)
        assert len(result) == 3

    def test_none_group(self):
        assert _collect_all_conditions(None) == []

    def test_empty_group(self):
        assert _collect_all_conditions({}) == []


# ── _get_required_columns ────────────────────────────────────────────

class TestGetRequiredColumns:
    def test_rsi(self):
        cols = _get_required_columns({"id": "rsi", "params": {"period": 14}})
        assert cols == ["rsi_14"]

    def test_per(self):
        cols = _get_required_columns({"id": "per", "params": {}})
        assert cols == ["per"]

    def test_ma_crossover(self):
        cols = _get_required_columns({"id": "ma_crossover", "params": {"shortMA": 5, "longMA": 20}})
        assert "close_5_sma" in cols
        assert "close_20_sma" in cols

    def test_trading_value(self):
        cols = _get_required_columns({"id": "trading_value", "params": {}})
        assert cols == ["trading_value_20_sma"]

    def test_market_cap(self):
        cols = _get_required_columns({"id": "market_cap", "params": {}})
        assert cols == ["market_cap"]

    def test_unknown_id(self):
        cols = _get_required_columns({"id": "unknown_thing", "params": {}})
        assert cols == []


# ── DataResolver.resolve ─────────────────────────────────────────���───

class TestDataResolverResolve:
    def test_no_missing_data_returns_quickly(self):
        """모든 데이터가 이미 있으면 로그 1개(확인 완료)만 남긴다."""
        df = _make_ohlcv().with_columns(pl.Series("per", np.random.uniform(5, 20, 100)))
        entry = _make_entry_group(_make_condition("per", {"operator": "<", "value": 15}))

        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, entry, None)

        assert len(logs) >= 1
        assert any("확인 완료" in l["message"] for l in logs)

    def test_trading_value_computed_from_close_volume(self):
        """trading_value_20_sma 누락 시 close*volume으로 계산."""
        df = _make_ohlcv()
        entry = _make_entry_group(
            _make_condition("trading_value", {"operator": ">=", "value": 100})
        )

        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, entry, None)

        assert "trading_value_20_sma" in result_df.columns
        assert any("거래대금" in l["message"] and l["level"] == "SUCCESS" for l in logs)

    def test_per_computed_from_eps(self):
        """per 누락이지만 eps가 있으면 close/eps로 계산."""
        df = _make_ohlcv().with_columns(
            pl.Series("eps", np.full(100, 5000.0))
        )
        entry = _make_entry_group(_make_condition("per", {"operator": "<", "value": 15}))

        resolver = DataResolver()
        # fundamental_fetcher가 호출되지 않도록 mock
        with patch("engine.data_resolver.DataResolver._resolve_fundamentals", return_value=df):
            result_df, logs = resolver.resolve("005930", df, entry, None)

        assert "per" in result_df.columns
        # PER = close / eps → 값이 있어야 함
        per_vals = result_df["per"].to_numpy()
        assert np.any(np.isfinite(per_vals))

    def test_pbr_computed_from_bps(self):
        """pbr 누락이지만 bps가 있으면 close/bps로 계산."""
        df = _make_ohlcv().with_columns(
            pl.Series("bps", np.full(100, 50000.0))
        )
        entry = _make_entry_group(_make_condition("pbr", {"operator": "<", "value": 1.5}))

        resolver = DataResolver()
        with patch("engine.data_resolver.DataResolver._resolve_fundamentals", return_value=df):
            result_df, logs = resolver.resolve("005930", df, entry, None)

        assert "pbr" in result_df.columns

    @patch("engine.data_resolver.DataResolver._fetch_shares_outstanding", return_value=1000000)
    def test_market_cap_computed(self, mock_shares):
        """market_cap 누락 시 상장주식수 × close로 계산."""
        df = _make_ohlcv()
        entry = _make_entry_group(
            _make_condition("market_cap", {"operator": ">=", "value": 100})
        )

        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, entry, None)

        assert "market_cap" in result_df.columns
        assert any("시가총액 계산 완료" in l["message"] for l in logs)

    @patch("engine.data_resolver.DataResolver._fetch_shares_outstanding", return_value=None)
    def test_market_cap_fails_gracefully(self, mock_shares):
        """상장주식수 조회 실패 시 경고 로그만 남기고 계속."""
        df = _make_ohlcv()
        entry = _make_entry_group(
            _make_condition("market_cap", {"operator": ">=", "value": 100})
        )

        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, entry, None)

        assert any("상장주식수 조회 실패" in l["message"] for l in logs)
        # market_cap 컬럼이 없어도 에러 없이 종료
        assert any("미해결 데이터" in l["message"] for l in logs)

    def test_all_null_column_treated_as_missing(self):
        """컬럼이 존재하지만 전부 null이면 누락으로 처리."""
        df = _make_ohlcv().with_columns(
            pl.Series("per", [None] * 100, dtype=pl.Float64)
        )
        entry = _make_entry_group(_make_condition("per", {"operator": "<", "value": 15}))

        resolver = DataResolver()
        # fundamental_fetcher mock — _resolve_fundamentals 내부에서 import하므로 메서드 자체를 mock
        with patch("engine.fundamental_fetcher.fetch_fundamentals", return_value=None):
            result_df, logs = resolver.resolve("005930", df, entry, None)

        assert any("누락 데이터 감지" in l["message"] for l in logs)

    def test_empty_conditions_returns_early(self):
        """조건이 없으면 즉시 반환."""
        df = _make_ohlcv()
        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, None, None)
        assert logs == []

    def test_resolution_logs_have_correct_structure(self):
        """로그 항목이 {level, message} 구조인지 확인."""
        df = _make_ohlcv()
        entry = _make_entry_group(
            _make_condition("trading_value", {"operator": ">=", "value": 100})
        )

        resolver = DataResolver()
        _, logs = resolver.resolve("005930", df, entry, None)

        for log in logs:
            assert "level" in log
            assert "message" in log
            assert log["level"] in ("INFO", "WARN", "ERROR", "SUCCESS")

    @patch("engine.fundamental_fetcher.fetch_fundamentals")
    def test_fundamentals_fetched_on_missing_roe(self, mock_fetch):
        """roe_or_gpa 누락 시 fetch_fundamentals 호출."""
        mock_fetch.return_value = [
            {"year_end": "2023-12-31", "eps": 5000, "bps": 50000, "roe_or_gpa": 12.5, "debt_ratio": 45.0}
        ]
        df = _make_ohlcv()
        # date를 실제 datetime으로 변환 (enrich가 date 컬럼을 파싱)
        import pandas as pd
        pdf = df.to_pandas()
        pdf["date"] = pd.date_range("2024-06-01", periods=100, freq="D")
        df = pl.from_pandas(pdf)

        entry = _make_entry_group(
            _make_condition("roe_or_gpa", {"operator": ">=", "value": 10})
        )

        resolver = DataResolver()
        result_df, logs = resolver.resolve("005930", df, entry, None)

        mock_fetch.assert_called_once_with("005930")
        assert any("펀더멘털" in l["message"] for l in logs)
