"""scripts/repair_kis_placeholder_fundamentals.py — parquet 자리표시자 서명 행 비우기 + 재구축.

핵심 회귀: rebuild_fundamental_columns는 '캐시가 모르는 날은 기존 값 보존'이라, 자리표시자
연도를 캐시에서 걷어내도 parquet의 옛 0(eps=bps=sps=0·부채비율 0)이 그대로 살아남는다.
스크립트는 서명 행을 **먼저 비운 뒤** 재구축해야 한다(2026-08-17, 삼진제약 실측).
"""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "repair_kis_placeholder_fundamentals.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("repair_kis_placeholder_fundamentals", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _parquet_with_placeholder_then_valid() -> pd.DataFrame:
    """2021년 자리표시자(0·0·0·부채비율 0) → 2022년 정상값이 forward-fill된 parquet."""
    dates = pd.date_range("2021-04-01", "2023-06-30", freq="B")
    df = pd.DataFrame({"date": dates, "close": 10000.0})
    valid_from = df["date"] >= "2022-04-01"
    df["eps"] = np.where(valid_from, 2000.0, 0.0)
    df["bps"] = np.where(valid_from, 20000.0, 0.0)
    df["sps"] = np.where(valid_from, 50000.0, 0.0)
    df["debt_ratio"] = np.where(valid_from, 45.0, 0.0)
    df["roe_or_gpa"] = np.where(valid_from, 10.0, 0.0)
    df["per"] = np.where(valid_from, 5.0, np.nan)
    df["operating_cash_flow"] = 3.0e10  # DART 유래 — 서명 행에서도 재구축이 캐시로 되살린다
    return df


def test_clear_placeholder_rows_blanks_only_signature_rows(script):
    df = _parquet_with_placeholder_then_valid()
    n = script.clear_placeholder_rows(df)
    sig = df["date"] < "2022-04-01"
    assert n == int(sig.sum()) > 0
    assert df.loc[sig, ["eps", "bps", "sps", "debt_ratio", "roe_or_gpa", "per"]].isna().all().all()
    assert (df.loc[~sig, "eps"] == 2000.0).all() and (df.loc[~sig, "debt_ratio"] == 45.0).all()


def test_rebuild_after_clear_does_not_resurrect_old_zeros(script):
    """비우지 않고 재구축하면 옛 0이 남고(부채비율 0 = '≤ N' 거짓 통과), 비우면 없음이 된다."""
    records = [  # 수리된 캐시: 2021 자리표시자 제거, 2022만 남음(+DART)
        {"year_end": "2022-12-31", "available_from": "2023-03-15", "eps": 2000.0, "bps": 20000.0,
         "sps": 50000.0, "debt_ratio": 45.0, "roe_or_gpa": 10.0, "operating_cash_flow": 3.0e10},
        {"year_end": "2021-12-31", "available_from": "2022-03-15", "operating_cash_flow": 2.5e10},
    ]
    from engine.fundamental_backfill import rebuild_fundamental_columns

    naive = rebuild_fundamental_columns(_parquet_with_placeholder_then_valid(), records)
    early = naive["date"] < "2022-03-15"
    assert (naive.loc[early, "debt_ratio"] == 0.0).all()  # 비우지 않으면 옛 0이 보존된다

    df = _parquet_with_placeholder_then_valid()
    script.clear_placeholder_rows(df)
    fixed = rebuild_fundamental_columns(df, records)
    assert fixed.loc[early, ["eps", "bps", "debt_ratio", "roe_or_gpa", "per"]].isna().all().all()
    # 서명 행이지만 DART 2021 레코드가 덮는 구간(03-15~03-31): DART 유래는 캐시로 복원된다
    covered_sig = (fixed["date"] >= "2022-03-15") & (fixed["date"] < "2022-04-01")
    assert covered_sig.any() and (fixed.loc[covered_sig, "operating_cash_flow"] == 2.5e10).all()
    assert fixed.loc[covered_sig, "eps"].isna().all()  # KIS 자리표시자였던 값은 되살아나지 않는다
    late = fixed["date"] >= "2023-03-15"
    assert (fixed.loc[late, "eps"] == 2000.0).all() and (fixed.loc[late, "per"] == 5.0).all()


def test_find_targets_orders_latest_placeholder_first(script, tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(script, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(script, "_ACTIVE_PATH", tmp_path / "korea-stocks.json")
    (tmp_path / "korea-stocks.json").write_text(json.dumps([{"symbol": s} for s in ("000001", "000002", "000003")]))
    ph = {"eps": 0.0, "bps": 0.0, "sps": 0.0}
    ok = {"eps": 100.0, "bps": 1000.0, "sps": 5000.0}
    (tmp_path / "000001.json").write_text(json.dumps({"fundamentals": [  # 선행만 → 나중
        {"year_end": "2010-12-31", **ph}, {"year_end": "2024-12-31", **ok}]}))
    (tmp_path / "000002.json").write_text(json.dumps({"fundamentals": [  # 최신이 자리표시자 → 먼저
        {"year_end": "2023-12-31", **ok}, {"year_end": "2024-12-31", **ph}]}))
    (tmp_path / "000003.json").write_text(json.dumps({"fundamentals": [{"year_end": "2024-12-31", **ok}]}))
    assert script.find_targets() == ["000002", "000001"]
