"""시장지수 백필 스크립트(scripts/backfill_index_history.py)의 순수 변환·병합·저장 계약.

네트워크는 부르지 않는다 — 토스·KIS 클라이언트를 가짜로 주입해 run()의 분기
(파일 없음→전체 백필, 있음→갱신 upsert, 토스 실패→기존 파일 보존)까지 고정한다.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_index_history.py"
_spec = importlib.util.spec_from_file_location("backfill_index_history", _SCRIPT)
bih = importlib.util.module_from_spec(_spec)
sys.modules["backfill_index_history"] = bih
_spec.loader.exec_module(bih)


def _toss_row(day: str, close: float) -> dict:
    return {"timestamp": f"{day}T00:00:00.000+09:00", "openPrice": str(close - 1),
            "highPrice": str(close + 1), "lowPrice": str(close - 2), "closePrice": str(close),
            "volume": "1000"}


def _kis_row(day: str, close: float) -> dict:
    return {"stck_bsop_date": day.replace("-", ""), "bstp_nmix_prpr": str(close),
            "bstp_nmix_oprc": str(close - 1), "bstp_nmix_hgpr": str(close + 1),
            "bstp_nmix_lwpr": str(close - 2), "acml_vol": "500"}


def test_toss_rows_become_ascending_frame_with_source():
    df = bih.toss_rows_to_frame([_toss_row("2024-01-03", 2510), _toss_row("2024-01-02", 2500)])
    assert list(df["close"]) == [2500.0, 2510.0]
    assert list(df["date"].dt.strftime("%Y-%m-%d")) == ["2024-01-02", "2024-01-03"]
    assert set(df["source"]) == {"toss"}
    assert list(df.columns) == list(bih.INDEX_COLUMNS)


def test_kis_rows_become_frame_and_skip_blank_dates():
    df = bih.kis_rows_to_frame([_kis_row("2010-01-05", 1690), {"stck_bsop_date": ""}, _kis_row("2010-01-04", 1680)])
    assert list(df["close"]) == [1680.0, 1690.0]
    assert set(df["source"]) == {"kis"}


def test_merge_prefers_primary_on_overlapping_dates():
    toss = bih.toss_rows_to_frame([_toss_row("2014-07-01", 2000), _toss_row("2014-07-02", 2010)])
    kis = bih.kis_rows_to_frame([_kis_row("2014-06-30", 1990), _kis_row("2014-07-01", 1999)])
    merged = bih.merge_sources(toss, kis)
    assert list(merged["date"].dt.strftime("%Y-%m-%d")) == ["2014-06-30", "2014-07-01", "2014-07-02"]
    assert list(merged["source"]) == ["kis", "toss", "toss"]
    assert merged.loc[merged["source"] == "toss", "close"].iloc[0] == 2000.0   # 겹친 날은 토스 값


def test_upsert_overwrites_existing_bars_with_fresh_ones():
    existing = bih.toss_rows_to_frame([_toss_row("2024-01-02", 2500), _toss_row("2024-01-03", 2510)])
    fresh = bih.toss_rows_to_frame([_toss_row("2024-01-03", 2511), _toss_row("2024-01-04", 2520)])
    out = bih.upsert(existing, fresh)
    assert list(out["close"]) == [2500.0, 2511.0, 2520.0]
    assert bih.upsert(None, fresh).equals(fresh)


def test_write_then_read_roundtrip_keeps_microsecond_datetime(tmp_path):
    df = bih.toss_rows_to_frame([_toss_row("2024-01-02", 2500)])
    path = bih.write_index("KOSPI", df, tmp_path)
    assert path == tmp_path / "KOSPI.parquet" and path.exists()
    import polars as pl
    assert pl.read_parquet(path).schema["date"] == pl.Datetime("us")   # OHLCV 조인 키와 같은 dtype
    back = bih.read_index("KOSPI", tmp_path)
    assert list(back["close"]) == [2500.0]


class _FakeToss:
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.calls = rows, fail, []

    def fetch_candles(self, market, max_pages=None):
        self.calls.append((market, max_pages))
        if self.fail:
            raise RuntimeError("boom")
        return self.rows


class _FakeKis:
    def __init__(self, rows):
        self.rows, self.before_calls = rows, []

    def fetch_before(self, market, until, floor=None):
        self.before_calls.append((market, until))
        return self.rows

    def fetch_window(self, code, d0, d1):
        return []


def test_run_full_backfill_merges_toss_and_kis(tmp_path):
    toss = _FakeToss([_toss_row("2014-07-02", 2010), _toss_row("2014-07-01", 2000)])
    kis = _FakeKis([_kis_row("2014-06-30", 1990)])
    rc = bih.run(["KOSPI"], full=False, index_dir=tmp_path,
                 toss_factory=lambda: toss, kis_factory=lambda: kis)
    assert rc == 0
    assert toss.calls == [("KOSPI", None)]          # 파일이 없으면 갱신 모드도 전체 수집
    assert kis.before_calls and kis.before_calls[0][1] == pd.Timestamp("2014-07-01")
    out = bih.read_index("KOSPI", tmp_path)
    assert list(out["source"]) == ["kis", "toss", "toss"]


def test_run_update_upserts_one_page_and_keeps_history(tmp_path):
    bih.write_index("KOSDAQ", bih.kis_rows_to_frame([_kis_row("2010-01-04", 500)]), tmp_path)
    toss = _FakeToss([_toss_row("2024-01-03", 850), _toss_row("2024-01-02", 840)])
    rc = bih.run(["KOSDAQ"], full=False, index_dir=tmp_path,
                 toss_factory=lambda: toss, kis_factory=lambda: pytest.fail("갱신은 KIS를 부르지 않는다"))
    assert rc == 0
    assert toss.calls == [("KOSDAQ", 1)]
    out = bih.read_index("KOSDAQ", tmp_path)
    assert list(out["close"]) == [500.0, 840.0, 850.0]


def test_run_keeps_existing_file_when_toss_fails(tmp_path):
    bih.write_index("KOSPI", bih.kis_rows_to_frame([_kis_row("2010-01-04", 1680)]), tmp_path)
    rc = bih.run(["KOSPI"], full=False, index_dir=tmp_path,
                 toss_factory=lambda: _FakeToss([], fail=True), kis_factory=lambda: _FakeKis([]))
    assert rc == 1
    assert list(bih.read_index("KOSPI", tmp_path)["close"]) == [1680.0]
