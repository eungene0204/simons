import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts import sync_data


def test_symbols_only_returns_nonzero_when_symbol_refresh_falls_back(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "ohlcv"
    data_dir.mkdir(parents=True)
    stocks_path = tmp_path / "data" / "korea-stocks.json"
    stocks_path.write_text(
        json.dumps([{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}], ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_data, "_notify_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(sync_data, "sync_symbols", lambda path: ([], [], []))
    monkeypatch.setattr(sync_data, "validate_stock_list", lambda stocks: [])
    monkeypatch.setattr(
        sync_data,
        "record_universe_sync",
        lambda **kwargs: {
            "date": kwargs["date"],
            "totalCount": kwargs["total_count"],
            "addedCount": len(kwargs["added"]),
            "delistedCount": len(kwargs["delisted"]),
        },
    )

    assert sync_data.main(["--symbols-only"]) == 2


def test_symbols_only_returns_zero_when_symbol_refresh_succeeds(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "ohlcv"
    data_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sync_data, "_notify_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync_data,
        "sync_symbols",
        lambda path: ([{"symbol": "005930", "name": "삼성전자", "market": "KOSPI"}], [], []),
    )
    monkeypatch.setattr(sync_data, "validate_stock_list", lambda stocks: [])
    monkeypatch.setattr(
        sync_data,
        "record_universe_sync",
        lambda **kwargs: {
            "date": kwargs["date"],
            "totalCount": kwargs["total_count"],
            "addedCount": len(kwargs["added"]),
            "delistedCount": len(kwargs["delisted"]),
        },
    )

    assert sync_data.main(["--symbols-only"]) == 0
