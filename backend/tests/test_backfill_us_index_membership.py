"""backfill_us_index_membership.py — 파싱·검증 로직 (네트워크 불필요)."""

import importlib.util
from pathlib import Path

import pandas as pd

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_index_membership.py"
_spec = importlib.util.spec_from_file_location("simons_us_index_membership", _PATH)
idx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(idx)


def test_normalize_symbol_yahoo_notation():
    assert idx.normalize_symbol("BRK.B") == "BRK-B"
    assert idx.normalize_symbol(" aapl ") == "AAPL"


def test_parse_sp500_table_keeps_metadata():
    table = pd.DataFrame([{
        "Symbol": "BRK.B", "Security": "Berkshire Hathaway", "GICS Sector": "Financials",
        "GICS Sub-Industry": "Multi-Sector Holdings", "CIK": "1067983",
        "Date added": "2010-02-16",
    }])
    (m,) = idx.parse_sp500_table(table)
    assert m == {"symbol": "BRK-B", "name": "Berkshire Hathaway", "sector": "Financials",
                 "subIndustry": "Multi-Sector Holdings", "cik": "0001067983",
                 "dateAdded": "2010-02-16"}


def test_parse_nasdaq100_rows_strips_security_type_tail():
    rows = [
        {"symbol": "AAPL", "companyName": "Apple Inc. Common Stock"},
        {"symbol": "GOOG", "companyName": "Alphabet Inc. Class C Capital Stock"},
        {"symbol": "", "companyName": "무시"},
    ]
    out = idx.parse_nasdaq100_rows(rows)
    assert out == [{"symbol": "AAPL", "name": "Apple Inc."},
                   {"symbol": "GOOG", "name": "Alphabet Inc."}]


def test_parse_dow30_table_finds_columns_by_name():
    table = pd.DataFrame({"No.": [1], "Symbol": ["NVDA"],
                          "Company Name": ["NVIDIA Corporation"], "Market Cap": ["5T"]})
    assert idx.parse_dow30_table(table) == [{"symbol": "NVDA", "name": "NVIDIA Corporation"}]


def _members(symbols):
    return [{"symbol": s} for s in symbols]


def test_validate_counts_flags_out_of_range_and_duplicates():
    ok = {"SP500": _members([f"S{i}" for i in range(503)]),
          "NASDAQ100": _members([f"N{i}" for i in range(102)]),
          "DOW30": _members([f"D{i}" for i in range(30)])}
    assert idx.validate_counts(ok) == []

    bad = dict(ok, DOW30=_members([f"D{i}" for i in range(29)]))  # 표 구조 변경 시나리오
    assert any("DOW30" in p for p in idx.validate_counts(bad))

    dup = dict(ok, DOW30=_members(["D0"] * 30))
    assert any("중복" in p for p in idx.validate_counts(dup))


def test_coverage_report_lists_missing_symbols():
    indices = {"DOW30": _members(["AAPL", "NEWCO"])}
    report = idx.coverage_report(indices, master_symbols={"AAPL"}, parquet_symbols=set())
    assert report["DOW30"]["missingFromMaster"] == ["NEWCO"]
    assert report["DOW30"]["missingFromOhlcv"] == ["AAPL", "NEWCO"]


def test_saved_membership_file_consistency():
    """실제 저장 파일 무결성 — 수집을 다시 돌리지 않고 산출물만 검사한다."""
    path = Path(__file__).resolve().parents[2] / "data" / "us-index-membership.json"
    if not path.exists():
        import pytest
        pytest.skip("us-index-membership.json 미수집")
    import json
    data = json.loads(path.read_text())
    indices = data["indices"]
    assert idx.validate_counts(indices) == []
    sp = {m["symbol"] for m in indices["SP500"]}
    dow = {m["symbol"] for m in indices["DOW30"]}
    assert dow <= sp  # 다우 30은 전부 S&P500 소속이다
