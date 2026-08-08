"""scripts/repair_dart_fiscal_year_end.py — DART 레코드 결산일 재라벨 로직 테스트.

핵심 계약(2026-08-07):
  · DART 레코드가 `{year}-12-31`로 고정 기록돼 비12월 결산 회사에서 같은 회계연도의
    KIS 값과 다른 레코드로 갈라지던 것을 실제 결산일로 옮긴다.
  · 대상 레코드가 이미 있으면 **병합**하고 원본을 지운다(레코드가 늘어나면 안 된다).
  · KIS 유래 필드는 옮기지 않는다 — DART 유래 필드와 available_from만 따라간다.
  · 결산월은 **연도별**로 본다(사업보고서 이름) — acc_mt 하나로는 결산기를 바꾼
    회사의 변경 이전 연도를 틀리게 만든다.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "repair_dart_fiscal_year_end.py"
)
_spec = importlib.util.spec_from_file_location("repair_dart_fiscal_year_end", _SCRIPT)
fy_repair = importlib.util.module_from_spec(_spec)
sys.modules["repair_dart_fiscal_year_end"] = fy_repair
_spec.loader.exec_module(fy_repair)


def _june_fy_cache() -> list[dict]:
    """6월 결산 회사 — KIS는 06-30, DART는 12-31로 갈려 있는 실제 형태(097870)."""
    return [
        {"year_end": "2024-06-30", "eps": 500.0, "bps": 8000.0, "net_margin": 3.0},
        {"year_end": "2024-12-31", "available_from": "2024-09-27",
         "operating_cash_flow": 5_000_000_000.0, "owner_net_income": 45.2,
         "total_equity": 90_000_000_000.0},
        {"year_end": "2025-06-30", "eps": 320.0, "bps": 8300.0, "net_margin": 2.0},
    ]


def _write_cache(tmp_path: Path, symbol: str, records: list[dict]) -> Path:
    cache_dir = tmp_path / "fundamentals"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{symbol}.json"
    path.write_text(json.dumps({"symbol": symbol, "fundamentals": records}), encoding="utf-8")
    return path


@pytest.fixture
def repair_env(tmp_path, monkeypatch):
    monkeypatch.setattr(fy_repair, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(fy_repair, "_CACHE_DIR", tmp_path / "fundamentals")
    monkeypatch.setattr(fy_repair, "_OHLCV_DIR", tmp_path / "ohlcv")
    monkeypatch.setattr(fy_repair.ff, "_get_dart_corp_code", lambda symbol: "00123456")
    return tmp_path


def test_kis_fiscal_month_ignores_mislabeled_dart_records():
    """대상 선별 힌트는 KIS 레코드만 본다 — 12-31 DART 레코드에 끌려가면 안 된다."""
    assert fy_repair.kis_fiscal_month(_june_fy_cache()) == "06"


def test_dart_record_is_merged_into_the_real_fiscal_year_end(repair_env, monkeypatch):
    _write_cache(repair_env, "097870", _june_fy_cache())
    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods",
                        lambda corp: {y: ("06", f"{y}-09-19") for y in range(2015, 2027)})

    status, _, moved = fy_repair.repair_symbol("097870", dry_run=False)
    assert (status, moved) == ("moved_1", 1)

    records = json.loads(
        (repair_env / "fundamentals" / "097870.json").read_text(encoding="utf-8")
    )["fundamentals"]
    year_ends = sorted(r["year_end"] for r in records)
    assert year_ends == ["2024-06-30", "2025-06-30"]  # 12-31 레코드가 사라졌다

    merged = next(r for r in records if r["year_end"] == "2024-06-30")
    assert merged["operating_cash_flow"] == 5_000_000_000.0
    assert merged["owner_net_income"] == 45.2
    assert merged["available_from"] == "2024-09-27"
    assert merged["eps"] == 500.0  # KIS 값은 그대로 남는다


def test_dart_record_is_relabelled_when_no_kis_record_exists(repair_env, monkeypatch):
    """대응 KIS 레코드가 없으면 라벨만 바꾼다(데이터를 버리지 않는다)."""
    records = [
        {"year_end": "2023-06-30", "eps": 100.0},
        {"year_end": "2024-06-30", "eps": 120.0},
        {"year_end": "2022-12-31", "available_from": "2022-09-20",
         "operating_cash_flow": 1_000.0},
    ]
    _write_cache(repair_env, "097870", records)
    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods",
                        lambda corp: {y: ("06", f"{y}-09-19") for y in range(2015, 2027)})

    status, _, moved = fy_repair.repair_symbol("097870", dry_run=False)
    assert (status, moved) == ("moved_1", 1)

    out = json.loads(
        (repair_env / "fundamentals" / "097870.json").read_text(encoding="utf-8")
    )["fundamentals"]
    assert sorted(r["year_end"] for r in out) == ["2022-06-30", "2023-06-30", "2024-06-30"]


def test_december_fiscal_year_is_left_alone(repair_env, monkeypatch):
    """그 해의 결산월이 12면 라벨이 이미 맞다 — KIS 힌트가 달라도 손대지 않는다."""
    _write_cache(repair_env, "000220", _june_fy_cache())
    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods",
                        lambda corp: {y: ("12", f"{y+1}-03-15") for y in range(2015, 2027)})

    status, changed, moved = fy_repair.repair_symbol("000220", dry_run=False)
    assert (status, changed, moved) == ("clean", [], 0)


def test_december_fy_symbols_are_not_candidates(repair_env, monkeypatch):
    """12월 결산 회사는 DART 조회조차 하지 않는다(쿼터 절감)."""
    _write_cache(repair_env, "005930", [
        {"year_end": "2024-12-31", "eps": 100.0, "operating_cash_flow": 1.0},
        {"year_end": "2025-12-31", "eps": 120.0, "operating_cash_flow": 2.0},
    ])

    def explode(corp):  # pragma: no cover - 호출되면 실패해야 한다
        raise AssertionError("12월 결산 종목에 공시 목록을 조회했다")

    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods", explode)
    assert fy_repair.repair_symbol("005930", dry_run=False)[0] == "not_candidate"


def test_dry_run_does_not_write(repair_env, monkeypatch):
    path = _write_cache(repair_env, "097870", _june_fy_cache())
    before = path.read_text(encoding="utf-8")
    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods",
                        lambda corp: {y: ("06", f"{y}-09-19") for y in range(2015, 2027)})

    status, _, moved = fy_repair.repair_symbol("097870", dry_run=True)
    assert (status, moved) == ("moved_1", 1)
    assert path.read_text(encoding="utf-8") == before


def test_fiscal_year_change_uses_per_year_month(repair_env, monkeypatch):
    """결산기를 바꾼 회사(유유제약 형태) — 변경 이전 연도는 옛 결산월로 옮겨야 한다.

    acc_mt 하나(현재=12)로 처리하면 2015·2016년 DART 값이 12-31에 남아 KIS 3월
    레코드와 영영 갈라진다.
    """
    records = [
        {"year_end": "2015-03-31", "eps": 10.0},
        {"year_end": "2015-12-31", "available_from": "2015-06-29",
         "operating_cash_flow": 111.0},
        {"year_end": "2016-03-31", "eps": 12.0},
        {"year_end": "2016-12-31", "available_from": "2016-06-29",
         "operating_cash_flow": 222.0},
        {"year_end": "2017-12-31", "eps": 14.0, "available_from": "2018-03-16",
         "operating_cash_flow": 333.0},
    ]
    _write_cache(repair_env, "000220", records)
    monkeypatch.setattr(fy_repair.ff, "_fetch_dart_annual_report_periods", lambda corp: {
        2015: ("03", "2015-06-29"), 2016: ("03", "2016-06-29"),
        2017: ("12", "2018-03-16"),
    })

    status, _, moved = fy_repair.repair_symbol("000220", dry_run=False)
    assert (status, moved) == ("moved_2", 2)

    out = json.loads(
        (repair_env / "fundamentals" / "000220.json").read_text(encoding="utf-8")
    )["fundamentals"]
    assert sorted(r["year_end"] for r in out) == [
        "2015-03-31", "2016-03-31", "2017-12-31",
    ]
    merged = next(r for r in out if r["year_end"] == "2015-03-31")
    assert (merged["operating_cash_flow"], merged["eps"]) == (111.0, 10.0)
    # 전환 이후(2017)는 이미 12-31이 맞으므로 그대로다
    assert next(r for r in out if r["year_end"] == "2017-12-31")["operating_cash_flow"] == 333.0
