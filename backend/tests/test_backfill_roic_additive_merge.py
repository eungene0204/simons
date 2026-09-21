"""ROIC·FCF 마진 백필의 parquet 쓰기는 **빈 칸만 채운다**(2026-09-21).

종전의 캐시 우선 재구축은 캐시에 값이 없는 키를 NaN으로 덮어, 캐시 밖에서 채워진 EPS·BPS 등을
백필을 거친 199종목에서 지웠다(운영 parquet과 전수 대조로 발견). 새 컬럼만 더해져야 한다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import polars as pl

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_roic_fcf_margin.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("backfill_roic_fcf_margin", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["backfill_roic_fcf_margin"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    return module


def test_parquet_write_fills_gaps_without_erasing_values_the_cache_lacks(tmp_path, monkeypatch):
    script = _load_script()
    monkeypatch.setattr(script, "_OHLCV_DIR", tmp_path)
    monkeypatch.setattr(script, "_REPO_ROOT", tmp_path)
    dates = pd.bdate_range("2021-01-04", "2021-12-30")  # 전진충전 상한(15개월) 안
    pl.DataFrame({
        "date": dates.to_list(),
        "close": [1000.0] * len(dates),
        "eps": [123.0] * len(dates),                      # 캐시에는 없는 값(다른 경로로 채워짐)
    }).write_parquet(tmp_path / "000001.parquet")
    records = [{"year_end": "2020-12-31", "available_from": "2021-03-31",
                "eps": None, "roic": 12.5, "fcf_margin": 8.0, "revenue": 500.0}]

    changed = script._rebuild_parquet("000001", records, dry_run=False)

    out = pl.read_parquet(tmp_path / "000001.parquet").to_pandas()
    assert changed
    assert out["eps"].eq(123.0).all()                     # 기존 값은 그대로
    assert out.loc[out["date"] >= "2021-03-31", "roic"].eq(12.5).all()   # 새 컬럼은 채워진다
    assert out.loc[out["date"] < "2021-03-31", "roic"].isna().all()
