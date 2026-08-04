"""scripts/repair_fundamental_available_from.py — 정정일 오염 수리 로직 테스트.

2026-08-04 사고: DART rcept_no가 정정본을 가리켜 available_from이 원공시일 대신
정정 접수일로 기록 → PIT 병합이 수년 낡은 연도 값을 참조(유성티엔에스 FY2017 참조).
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "repair_fundamental_available_from.py"
_spec = importlib.util.spec_from_file_location("repair_available_from", _SCRIPT)
repair = importlib.util.module_from_spec(_spec)
sys.modules["repair_available_from"] = repair
_spec.loader.exec_module(repair)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    cache_dir = tmp_path / "fundamentals"
    ohlcv_dir = tmp_path / "ohlcv"
    cache_dir.mkdir()
    ohlcv_dir.mkdir()
    monkeypatch.setattr(repair, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(repair, "_OHLCV_DIR", ohlcv_dir)
    monkeypatch.setattr(repair, "_REPO_ROOT", tmp_path)
    return cache_dir, ohlcv_dir


def _write_cache(cache_dir: Path, symbol: str, records: list[dict]) -> None:
    (cache_dir / f"{symbol}.json").write_text(json.dumps({
        "symbol": symbol, "fetched_at": "2026-08-04T01:00:00", "fundamentals": records,
    }, ensure_ascii=False), encoding="utf-8")


def test_repair_clamps_cache_and_rebuilds_parquet(workspace, monkeypatch):
    cache_dir, ohlcv_dir = workspace
    _write_cache(cache_dir, "024800", [
        # 오염: FY2020 원공시는 2021-03-18인데 정정 접수일(2023-03-17)로 기록됨
        {"year_end": "2020-12-31", "available_from": "2023-03-17", "eps": 200.0},
        # 정상: 원공시일과 일치 — 불변이어야 함
        {"year_end": "2017-12-31", "available_from": "2018-04-02", "eps": 100.0},
    ])
    pl.DataFrame({
        "date": [pd.Timestamp("2022-02-03")], "close": [1000.0],
        "eps": [100.0], "per": [10.0],  # 오염 탓 FY2017 값이 채워져 있던 상태
    }).write_parquet(ohlcv_dir / "024800.parquet")

    monkeypatch.setattr(repair.ff, "_get_dart_corp_code", lambda s: "00123456")
    monkeypatch.setattr(
        repair.ff, "_fetch_dart_original_filing_dates",
        lambda corp: {2020: "2021-03-18", 2017: "2018-04-02"},
    )

    status, changed = repair.repair_symbol("024800", dry_run=False)

    assert status == "repaired_1rec"
    assert changed == ["fundamentals/024800.json", "ohlcv/024800.parquet"]
    saved = json.loads((cache_dir / "024800.json").read_text(encoding="utf-8"))
    by_year = {r["year_end"]: r["available_from"] for r in saved["fundamentals"]}
    assert by_year["2020-12-31"] == "2021-03-18"  # 클램프됨
    assert by_year["2017-12-31"] == "2018-04-02"  # 불변
    # parquet: 2022-02-03은 이제 FY2020 커버 구간 — eps/per가 FY2020 기준으로 재구축
    rebuilt = pl.read_parquet(ohlcv_dir / "024800.parquet")
    assert rebuilt["eps"][0] == pytest.approx(200.0)
    assert rebuilt["per"][0] == pytest.approx(1000.0 / 200.0)


def test_repair_noop_when_dates_already_original(workspace, monkeypatch):
    cache_dir, _ = workspace
    _write_cache(cache_dir, "005930", [
        {"year_end": "2020-12-31", "available_from": "2021-03-09", "eps": 300.0},
    ])
    monkeypatch.setattr(repair.ff, "_get_dart_corp_code", lambda s: "00126380")
    monkeypatch.setattr(
        repair.ff, "_fetch_dart_original_filing_dates", lambda corp: {2020: "2021-03-09"},
    )
    status, changed = repair.repair_symbol("005930", dry_run=False)
    assert status == "already_clean"
    assert changed == []


def test_find_suspicious_symbols_flags_only_late_records(workspace):
    cache_dir, _ = workspace
    _write_cache(cache_dir, "024800", [
        {"year_end": "2020-12-31", "available_from": "2023-03-17", "eps": 1.0},
    ])
    _write_cache(cache_dir, "005930", [
        {"year_end": "2020-12-31", "available_from": "2021-03-09", "eps": 1.0},
    ])
    _write_cache(cache_dir, "000001", [
        {"year_end": "2020-12-31", "eps": 1.0},  # available_from 없음(+90d 폴백) — 정상
    ])
    assert repair.find_suspicious_symbols(120) == ["024800"]
