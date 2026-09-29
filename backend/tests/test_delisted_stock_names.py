import json

import pytest

from engine import market_data


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "delisted-stocks.json"
    monkeypatch.setattr(market_data, "_DELISTED_FILE", path)
    return path


def test_name_survives_save_reload_and_unmark(ledger):
    store = market_data.DelistedSymbolStore()
    assert store.mark("005390.KS", " 신성통상 ")
    assert json.loads(ledger.read_text()) == {
        "symbols": ["005390"], "names": {"005390": "신성통상"},
    }
    restored = market_data.DelistedSymbolStore()
    assert restored.is_delisted("005390.KS")
    assert not restored.mark("005390")
    assert restored.unmark("005390")
    assert json.loads(ledger.read_text()) == {"symbols": [], "names": {}}


def test_legacy_codes_are_backfilled_on_save(ledger):
    ledger.write_text(json.dumps({"symbols": ["005390.KS"]}))
    (ledger.parent / "stock-master.json").write_text(json.dumps({
        "stocks": [{"symbol": "005390", "name": "신성통상"}],
    }))
    store = market_data.DelistedSymbolStore()
    assert store.all() == ["005390"]
    assert not store.mark("005390")
    assert json.loads(ledger.read_text())["names"] == {"005390": "신성통상"}


@pytest.mark.parametrize("names", [None, [], 123])
def test_invalid_name_metadata_keeps_delisted_membership(ledger, names):
    ledger.write_text(json.dumps({"symbols": ["005390"], "names": names}))
    store = market_data.DelistedSymbolStore()
    assert store.is_delisted("005390")
    assert not store.mark("005390", "신성통상")
    assert json.loads(ledger.read_text())["names"] == {"005390": "신성통상"}


@pytest.mark.parametrize("name", [None, "", "  ", "005390", 123])
def test_unknown_name_is_rejected_without_changing_ledger(ledger, name):
    store = market_data.DelistedSymbolStore()
    with pytest.raises(ValueError, match="종목명"):
        store.mark("005390", name)
    assert store.all() == []
    assert not ledger.exists()


def test_sync_passes_the_removed_stock_name(monkeypatch):
    from scripts import sync_data
    import requests

    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {"added": True}
    monkeypatch.setattr(requests, "post", lambda url, **kw: calls.append((url, kw)) or Response())
    assert sync_data._mark_delisted("005390", "신성통상")
    assert calls[0][1]["json"] == {"name": "신성통상"}


@pytest.mark.asyncio
async def test_registration_api_rejects_missing_name(ledger, monkeypatch):
    import main
    from fastapi import HTTPException

    monkeypatch.setattr(main, "delisted_store", market_data.DelistedSymbolStore())
    with pytest.raises(HTTPException) as error:
        await main.mark_delisted("005390")
    assert error.value.status_code == 422
    assert not ledger.exists()
    assert (await main.mark_delisted("005390", {"name": "신성통상"}))["added"]
