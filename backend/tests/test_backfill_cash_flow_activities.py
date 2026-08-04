"""scripts/backfill_cash_flow_activities.py — 투자·재무활동 현금흐름 백필 로직 테스트.

핵심 계약(2026-08-05):
  · 조회 대상은 'OCF는 있는데 투자활동이 없는' 연도뿐 — 3분류가 한 응답에서 나오므로
    OCF가 없는 연도는 재조회해도 소득이 없다(쿼터 절감의 근거).
  · 캐시 레코드에는 두 키만 추가하고 기존 필드·available_from은 건드리지 않는다.
  · DART status 020은 QuotaExhausted로 즉시 중단(부분 저장 후 재개 가능).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "backfill_cash_flow_activities.py"
)
_spec = importlib.util.spec_from_file_location("backfill_cash_flow_activities", _SCRIPT)
cf_backfill = importlib.util.module_from_spec(_spec)
sys.modules["backfill_cash_flow_activities"] = cf_backfill
_spec.loader.exec_module(cf_backfill)


# ── pending_years: 쿼터 절감 술어 ──

def test_pending_years_selects_only_years_with_ocf_but_no_investing():
    records = [
        {"year_end": "2024-12-31", "operating_cash_flow": 100.0},              # 대상
        {"year_end": "2023-12-31", "operating_cash_flow": 90.0,
         "investing_cash_flow": -5.0},                                          # 이미 채움
        {"year_end": "2022-12-31", "eps": 1.0},                                 # OCF 없음
        {"year_end": "2021-12-31", "operating_cash_flow": 80.0},               # 대상
    ]
    assert cf_backfill.pending_years(records) == [2021, 2024]


def test_pending_years_ignores_malformed_year_end():
    records = [{"year_end": "", "operating_cash_flow": 1.0},
               {"operating_cash_flow": 1.0}]
    assert cf_backfill.pending_years(records) == []


# ── 캐시 병합: 두 키만 추가 ──

@pytest.fixture
def cache_only_workspace(tmp_path, monkeypatch):
    cache_dir = tmp_path / "fundamentals"
    cache_dir.mkdir()
    monkeypatch.setattr(cf_backfill, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(cf_backfill, "_OHLCV_DIR", tmp_path / "ohlcv")  # parquet 없음
    monkeypatch.setattr(cf_backfill, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(cf_backfill.ff, "_get_dart_corp_code", lambda symbol: "00126380")
    return cache_dir


def test_backfill_symbol_adds_only_two_keys_and_preserves_available_from(
    cache_only_workspace, monkeypatch
):
    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "symbol": "005930",
        "fundamentals": [{
            "year_end": "2024-12-31",
            "available_from": "2025-03-11",
            "operating_cash_flow": 72_982_621_000_000.0,
            "capex": 1.0,
            "eps": 5.0,
        }],
    }), encoding="utf-8")

    monkeypatch.setattr(cf_backfill, "_fetch_activity_totals", lambda corp, year: (
        {"investing_cash_flow": -85_381_702_000_000.0,
         "financing_cash_flow": -7_797_243_000_000.0}, 1,
    ))

    status, paths, calls = cf_backfill.backfill_symbol("005930", dry_run=False)

    assert status == "filled_1y"
    assert calls == 1
    record = json.loads(
        (cache_only_workspace / "005930.json").read_text(encoding="utf-8")
    )["fundamentals"][0]
    assert record == {
        "year_end": "2024-12-31",
        "available_from": "2025-03-11",          # 불변
        "operating_cash_flow": 72_982_621_000_000.0,
        "capex": 1.0,
        "eps": 5.0,
        "investing_cash_flow": -85_381_702_000_000.0,
        "financing_cash_flow": -7_797_243_000_000.0,
    }
    assert paths == ["fundamentals/005930.json"]


def test_backfill_symbol_writes_to_the_ocf_record_when_year_keys_collide(
    cache_only_workspace, monkeypatch
):
    """같은 해에 결산월이 다른 레코드가 함께 있어도(KIS 9월 + DART 12월) 값은 OCF를
    가진 레코드에 실려야 한다 — 연도만으로 키를 잡으면 엉뚱한 레코드에 기록된다."""
    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "fundamentals": [
            {"year_end": "2025-12-31", "operating_cash_flow": 500.0},
            {"year_end": "2025-09-30", "eps": 3.0},  # OCF 없음 — 뒤에 오지만 대상 아님
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(cf_backfill, "_fetch_activity_totals", lambda corp, year: (
        {"investing_cash_flow": -10.0}, 1,
    ))

    cf_backfill.backfill_symbol("005930", dry_run=False)

    records = json.loads(
        (cache_only_workspace / "005930.json").read_text(encoding="utf-8")
    )["fundamentals"]
    by_end = {r["year_end"]: r for r in records}
    assert by_end["2025-12-31"]["investing_cash_flow"] == -10.0
    assert "investing_cash_flow" not in by_end["2025-09-30"]


def test_backfill_symbol_skips_write_when_dart_has_no_activity_totals(
    cache_only_workspace, monkeypatch
):
    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "fundamentals": [{"year_end": "2024-12-31", "operating_cash_flow": 1.0}],
    }), encoding="utf-8")
    monkeypatch.setattr(cf_backfill, "_fetch_activity_totals", lambda corp, year: ({}, 2))

    status, paths, calls = cf_backfill.backfill_symbol("005930", dry_run=False)

    assert (status, paths, calls) == ("no_activity_data", [], 2)


def test_backfill_symbol_reports_nothing_pending_when_already_complete(
    cache_only_workspace,
):
    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "fundamentals": [{"year_end": "2024-12-31", "operating_cash_flow": 1.0,
                          "investing_cash_flow": -2.0}],
    }), encoding="utf-8")

    assert cf_backfill.backfill_symbol("005930", dry_run=False) == ("nothing_pending", [], 0)


# ── --remerge-only: 미러 pull 이후 컬럼 복원 (DART 호출 0) ──

def test_remerge_symbol_restores_columns_without_touching_dart(
    cache_only_workspace, monkeypatch, tmp_path
):
    """프로덕션 pull로 되돌아온 parquet에 캐시의 3분류를 다시 얹는다."""
    import pandas as pd
    import polars as pl

    ohlcv_dir = tmp_path / "ohlcv"
    ohlcv_dir.mkdir()
    monkeypatch.setattr(cf_backfill, "_OHLCV_DIR", ohlcv_dir)
    monkeypatch.setattr(cf_backfill.ff, "_fetch_dart_json", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("remerge는 DART를 호출하면 안 된다")
    ))

    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "fundamentals": [{
            "year_end": "2024-12-31", "available_from": "2025-03-11",
            "operating_cash_flow": 100.0,
            "investing_cash_flow": -80.0, "financing_cash_flow": -7.0,
        }],
    }), encoding="utf-8")

    dates = pd.to_datetime(["2025-06-02", "2025-06-03"])
    pl.from_pandas(pd.DataFrame({
        "date": dates, "open": [1.0, 1.0], "high": [1.0, 1.0],
        "low": [1.0, 1.0], "close": [1.0, 1.0], "volume": [10, 10],
    })).write_parquet(ohlcv_dir / "005930.parquet")

    status, paths = cf_backfill.remerge_symbol("005930", dry_run=False)

    assert status == "remerged"
    assert paths == ["ohlcv/005930.parquet"]
    out = pl.read_parquet(ohlcv_dir / "005930.parquet").to_pandas()
    assert out["investing_cash_flow"].dropna().unique().tolist() == [-80.0]
    assert out["financing_cash_flow"].dropna().unique().tolist() == [-7.0]


def test_remerge_symbol_skips_when_cache_has_no_activity_data(
    cache_only_workspace, monkeypatch, tmp_path
):
    monkeypatch.setattr(cf_backfill, "_OHLCV_DIR", tmp_path / "ohlcv")
    (cache_only_workspace / "005930.json").write_text(json.dumps({
        "fundamentals": [{"year_end": "2024-12-31", "operating_cash_flow": 1.0}],
    }), encoding="utf-8")

    assert cf_backfill.remerge_symbol("005930", dry_run=False) == ("nothing_to_merge", [])


# ── 쿼터 소진 ──

def test_fetch_activity_totals_raises_on_dart_quota_status(monkeypatch):
    monkeypatch.setattr(cf_backfill.ff, "_fetch_dart_json", lambda path, params: {"status": "020"})
    with pytest.raises(cf_backfill.QuotaExhausted):
        cf_backfill._fetch_activity_totals("00126380", 2024)


def test_fetch_activity_totals_falls_back_to_separate_statements(monkeypatch):
    def fake_fetch(path, params):
        if params["fs_div"] == "CFS":
            return {"status": "013"}
        return {"status": "000", "list": [{
            "sj_div": "CF",
            "account_id": "ifrs-full_CashFlowsFromUsedInFinancingActivities",
            "account_nm": "재무활동현금흐름",
            "thstrm_amount": "-1,000",
            "rcept_no": "20250311001085",
        }]}

    monkeypatch.setattr(cf_backfill.ff, "_fetch_dart_json", fake_fetch)
    found, calls = cf_backfill._fetch_activity_totals("00126380", 2024)

    assert found == {"financing_cash_flow": -1000.0}
    assert calls == 2


# ── 진행 상황 저장/재개 ──

def test_progress_roundtrip_enables_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(cf_backfill, "_PROGRESS_PATH", tmp_path / "progress.json")
    assert cf_backfill.load_progress() == set()
    cf_backfill.save_progress({"005930", "000660"})
    assert cf_backfill.load_progress() == {"000660", "005930"}
