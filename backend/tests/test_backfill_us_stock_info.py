"""backfill_us_stock_info.py — 순수 병합 로직 검증 (네트워크 불필요)."""

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_us_stock_info.py"
_spec = importlib.util.spec_from_file_location("simons_backfill_us_info", _PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_build_info_fields_maps_and_drops_empty():
    fields = mod.build_info_fields({
        "symbol": "AAPL",
        "name": "애플",
        "englishName": "Apple",
        "isinCode": "US0378331005",
        "listDate": "1980-12-12",
        "delistDate": None,
        "sharesOutstanding": "14594180000",
    })
    assert fields == {
        "name_kr": "애플",
        "isin": "US0378331005",
        "listed_date": "1980-12-12",
        "shares_outstanding": 14594180000,
    }


def test_build_info_fields_tolerates_missing_values():
    assert mod.build_info_fields({"symbol": "X", "name": "", "sharesOutstanding": "abc"}) == {}


def test_merge_updates_only_matched_entries():
    master = [
        {"symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ"},
        {"symbol": "ZZZZ", "name": "Unknown Corp", "market": "NYSE"},
    ]
    updated = mod.merge_stock_info(master, {
        "AAPL": {"name": "애플", "isinCode": "US0378331005"},
    })
    assert updated == 1
    assert master[0]["name_kr"] == "애플"
    assert master[0]["name"] == "Apple Inc."   # 기존 필드 유지
    assert "name_kr" not in master[1]          # 미조회 종목은 그대로


def test_class_share_request_uses_dot_and_restores_dash(monkeypatch):
    requested = []

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"result": [{"symbol": "BRK.B", "name": "버크셔 해서웨이"}]}

    def fake_get(url, params=None, headers=None, timeout=None):
        requested.append(params["symbols"])
        return _Resp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)

    info = mod.fetch_stock_info(["BRK-B"], token="tok")
    assert requested == ["BRK.B"]
    assert "BRK-B" in info and info["BRK-B"]["name"] == "버크셔 해서웨이"
