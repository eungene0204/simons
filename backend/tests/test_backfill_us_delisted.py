"""backfill_us_delisted.py — 파싱·검증 로직 (네트워크 불필요)."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_delisted.py"
_spec = importlib.util.spec_from_file_location("simons_us_delisted", _PATH)
dl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl)

_CSV = (
    "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
    "AAI,AIRTRAN HOLDINGS INC,NYSE,Stock,2001-09-17,2011-11-30,Delisted\n"
    "BRK.X,Fake Class Share,NASDAQ,Stock,2010-01-04,2020-06-01,Delisted\n"
    ",headless row,NYSE,Stock,2010-01-04,2020-06-01,Delisted\n"
)


def test_parse_rows_normalizes_and_drops_empty_symbols():
    rows = dl.parse_rows(_CSV)
    assert [r["symbol"] for r in rows] == ["AAI", "BRK-X"]  # 점→대시, 빈 심볼 제거
    assert rows[0]["delistingDate"] == "2011-11-30"
    assert rows[0]["assetType"] == "Stock"


def _rows(n, **overrides):
    base = {"symbol": "S", "name": "n", "exchange": "NYSE", "assetType": "Stock",
            "ipoDate": "2010-01-04", "delistingDate": "2020-06-01"}
    return [dict(base, symbol=f"S{i}", **overrides) for i in range(n)]


def test_validate_rows_flags_shrunken_source():
    ok = _rows(dl.MIN_EXPECTED_TOTAL)
    assert dl.validate_rows(ok) == []
    assert any("미만" in p for p in dl.validate_rows(_rows(100)))


def test_validate_rows_flags_duplicates_and_bad_dates():
    ok = _rows(dl.MIN_EXPECTED_TOTAL)
    dup = ok + [dict(ok[0])]
    assert any("중복" in p for p in dl.validate_rows(dup))

    bad_date = _rows(dl.MIN_EXPECTED_TOTAL, delistingDate="2020/06/01")
    assert any("형식" in p for p in dl.validate_rows(bad_date))

    bad_type = _rows(dl.MIN_EXPECTED_TOTAL, assetType="Bond")
    assert any("assetType" in p for p in dl.validate_rows(bad_type))


def test_reused_by_active_intersects_master():
    rows = [{"symbol": "ACB"}, {"symbol": "GONE"}]
    assert dl.reused_by_active(rows, {"ACB", "AAPL"}) == ["ACB"]


def test_yearly_counts_sorted():
    rows = [{"delistingDate": "2020-06-01"}, {"delistingDate": "2019-01-02"},
            {"delistingDate": "2020-12-31"}]
    assert dl.yearly_counts(rows) == {"2019": 1, "2020": 2}


def test_saved_delisted_file_consistency():
    """실제 저장 파일 무결성 — 수집을 다시 돌리지 않고 산출물만 검사한다."""
    path = Path(__file__).resolve().parents[2] / "data" / "us-delisted.json"
    if not path.exists():
        import pytest
        pytest.skip("us-delisted.json 미수집")
    import json
    data = json.loads(path.read_text())
    entries = data["entries"]
    assert dl.validate_rows(entries) == []
    assert data["counts"]["total"] == len(entries)
    # 티커 재사용 심볼은 반드시 항목에도 존재한다
    symbols = {e["symbol"] for e in entries}
    assert set(data["reusedByActive"]) <= symbols
