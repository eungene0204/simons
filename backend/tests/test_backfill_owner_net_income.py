"""scripts/backfill_owner_net_income.py — DART 손익 값 백필/복원 로직 테스트.

핵심 계약(2026-08-07~08):
  · 조회 대상은 OCF 보유 연도 — 그 해에 DART 응답이 있었다는 뜻이다.
  · parquet 반영은 `rebuild_fundamental_columns`(캐시 우선)여야 한다. net_income은
    KIS 재계산본을 **교체**하는 값이라 기존 parquet 값 우선(merge)이면 반영되지 않는다.
  · `--remerge-only`는 미러 pull로 컬럼이 날아간 뒤 DART 호출 0으로 되살리는 경로다 —
    2026-08-08에 이 경로가 삭제된 import를 참조해 2,191종목 전부 조용히 실패했다
    (파일은 안 바뀌었지만 성공으로 보고되지도 않았다). 회귀로 고정한다.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "backfill_owner_net_income.py"
)
_spec = importlib.util.spec_from_file_location("backfill_owner_net_income", _SCRIPT)
owner_backfill = importlib.util.module_from_spec(_spec)
sys.modules["backfill_owner_net_income"] = owner_backfill
_spec.loader.exec_module(owner_backfill)


_RECORDS = [
    {"year_end": "2024-12-31", "available_from": "2025-03-11",
     "operating_cash_flow": 1_000.0, "net_income": 1_500.0, "owner_net_income": 1_200.0},
    {"year_end": "2025-12-31", "available_from": "2026-03-10",
     "operating_cash_flow": 2_000.0, "net_income": 1_800.0, "owner_net_income": 1_400.0},
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(owner_backfill, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(owner_backfill, "_CACHE_DIR", tmp_path / "fundamentals")
    monkeypatch.setattr(owner_backfill, "_OHLCV_DIR", tmp_path / "ohlcv")
    (tmp_path / "fundamentals").mkdir()
    (tmp_path / "ohlcv").mkdir()
    (tmp_path / "fundamentals" / "005930.json").write_text(
        json.dumps({"symbol": "005930", "fundamentals": _RECORDS}), encoding="utf-8"
    )
    # 미러 pull 직후 상태 — owner_net_income 컬럼이 없고 net_income은 프로덕션(KIS) 값.
    # 첫 행은 FY2024 공시 이후·FY2025 공시 이전이라 FY2024 값이, 둘째 행은 FY2025 값이 붙는다.
    pl.from_pandas(pd.DataFrame({
        "date": pd.to_datetime(["2025-06-02", "2026-08-07"]),
        "close": [70_000.0, 71_000.0],
        "net_income": [9_999.0, 9_999.0],
    })).write_parquet(tmp_path / "ohlcv" / "005930.parquet")
    return tmp_path


def test_pending_years_covers_every_year_with_dart_data():
    assert owner_backfill.pending_years(_RECORDS) == [2024, 2025]


def test_pending_years_skips_years_without_dart_response():
    records = [{"year_end": "2013-12-31", "eps": 100.0}]   # KIS만 있는 연도
    assert owner_backfill.pending_years(records) == []


def test_remerge_restores_column_after_mirror_pull(env):
    """미러 pull로 사라진 컬럼이 캐시에서 되살아나야 한다(DART 호출 0)."""
    status, changed = owner_backfill.remerge_symbol("005930", dry_run=False)
    assert status == "remerged"
    assert changed == ["ohlcv/005930.parquet"]

    out = pl.read_parquet(env / "ohlcv" / "005930.parquet")
    assert "owner_net_income" in out.columns
    assert out["owner_net_income"].to_list() == [1_200.0, 1_400.0]


def test_remerge_replaces_production_net_income_with_dart_value(env):
    """net_income은 '더하기'가 아니라 '교체'다 — 기존 parquet 값이 남으면 안 된다."""
    owner_backfill.remerge_symbol("005930", dry_run=False)
    out = pl.read_parquet(env / "ohlcv" / "005930.parquet")
    assert out["net_income"].to_list() == [1_500.0, 1_800.0]   # 9,999가 아니다


def test_remerge_covers_symbols_without_owner_values(env):
    """지배주주순이익이 없는 종목도 대상이다 — 분기 행 제거는 그런 종목에도 걸린다.

    지표 보유로 거르면 그 종목의 eps·PER·성장률이 옛 값으로 남는다.
    """
    (env / "fundamentals" / "000660.json").write_text(
        json.dumps({"symbol": "000660", "fundamentals": [
            {"year_end": "2025-12-31", "available_from": "2026-03-10", "net_income": 7_000.0},
        ]}), encoding="utf-8",
    )
    pl.from_pandas(pd.DataFrame({
        "date": pd.to_datetime(["2026-08-07"]),
        "close": [100.0],
        "net_income": [1.0],       # 프로덕션의 옛 값
    })).write_parquet(env / "ohlcv" / "000660.parquet")

    assert owner_backfill.remerge_symbol("000660", dry_run=False)[0] == "remerged"
    out = pl.read_parquet(env / "ohlcv" / "000660.parquet")
    assert out["net_income"].to_list() == [7_000.0]


def test_remerge_skips_write_when_nothing_changes(env):
    """바뀐 게 없으면 파일을 쓰지 않는다 — 전 종목 재기록은 미러 전체 재전송을 부른다."""
    owner_backfill.remerge_symbol("005930", dry_run=False)          # 1회차: 반영
    assert owner_backfill.remerge_symbol("005930", dry_run=False) == ("unchanged", [])


def test_remerge_dry_run_leaves_parquet_untouched(env):
    before = (env / "ohlcv" / "005930.parquet").read_bytes()
    assert owner_backfill.remerge_symbol("005930", dry_run=True)[0] == "remerged"
    assert (env / "ohlcv" / "005930.parquet").read_bytes() == before
