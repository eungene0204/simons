from pathlib import Path

from universe_history import (
    build_universe_sync_log_lines,
    build_universe_startup_log_lines,
    load_universe_history,
    record_universe_sync,
)


def test_record_universe_sync_writes_added_and_delisted_symbols(tmp_path: Path):
    history_path = tmp_path / "universe-history.json"

    record_universe_sync(
        date="2026-04-07",
        synced_at="2026-04-07T00:00:00+09:00",
        total_count=2617,
        kospi_count=837,
        kosdaq_count=1780,
        added=[
            {"symbol": "123456", "name": "신규종목", "market": "KOSDAQ", "sector": "IT"},
        ],
        delisted=[
            {"symbol": "654321", "name": "상폐종목", "market": "KOSPI", "industry": "기타"},
        ],
        path_override=str(history_path),
    )

    store = load_universe_history(str(history_path))
    assert store["updatedAt"] == "2026-04-07T00:00:00+09:00"
    assert len(store["entries"]) == 1

    entry = store["entries"][0]
    assert entry["date"] == "2026-04-07"
    assert entry["totalCount"] == 2617
    assert entry["kospiCount"] == 837
    assert entry["kosdaqCount"] == 1780
    assert entry["addedCount"] == 1
    assert entry["delistedCount"] == 1
    assert entry["added"][0]["symbol"] == "123456"
    assert entry["delisted"][0]["symbol"] == "654321"


def test_record_universe_sync_sorts_latest_entry_first(tmp_path: Path):
    history_path = tmp_path / "universe-history.json"

    record_universe_sync(
        date="2026-04-06",
        synced_at="2026-04-06T00:00:00+09:00",
        total_count=2615,
        kospi_count=836,
        kosdaq_count=1779,
        added=[],
        delisted=[],
        path_override=str(history_path),
    )
    record_universe_sync(
        date="2026-04-07",
        synced_at="2026-04-07T00:00:00+09:00",
        total_count=2617,
        kospi_count=837,
        kosdaq_count=1780,
        added=[],
        delisted=[],
        path_override=str(history_path),
    )

    store = load_universe_history(str(history_path))
    assert [entry["date"] for entry in store["entries"]] == ["2026-04-07", "2026-04-06"]


def test_build_universe_sync_log_lines_includes_recent_and_changes(tmp_path: Path):
    history_path = tmp_path / "universe-history.json"

    record_universe_sync(
        date="2026-04-06",
        synced_at="2026-04-06T00:00:00+09:00",
        total_count=2615,
        kospi_count=836,
        kosdaq_count=1779,
        added=[],
        delisted=[],
        path_override=str(history_path),
    )
    entry = record_universe_sync(
        date="2026-04-07",
        synced_at="2026-04-07T00:00:00+09:00",
        total_count=2617,
        kospi_count=837,
        kosdaq_count=1780,
        added=[{"symbol": "123456", "name": "신규종목", "market": "KOSDAQ"}],
        delisted=[{"symbol": "654321", "name": "상폐종목", "market": "KOSPI"}],
        path_override=str(history_path),
    )

    lines = build_universe_sync_log_lines(entry, load_universe_history(str(history_path)))

    assert lines[0] == "[INFO] universe-sync summary"
    assert "date: 2026-04-07" in lines[1]
    assert "changes: net=+0 added=1 delisted=1" in lines[4]
    assert "신규종목(123456)" in lines[5]
    assert "상폐종목(654321)" in lines[6]
    assert lines[7] == "[INFO] universe-sync recent-7d"
    assert "2026-04-07: 전체 2617 / KOSPI 837 / KOSDAQ 1780 / 신규 1 / 제외 1" in lines[8]
    assert "2026-04-06: 전체 2615 / KOSPI 836 / KOSDAQ 1779 / 신규 0 / 제외 0" in lines[9]


def test_build_universe_startup_log_lines_uses_latest_entry(tmp_path: Path):
    history_path = tmp_path / "universe-history.json"

    record_universe_sync(
        date="2026-04-07",
        synced_at="2026-04-07T00:00:00+09:00",
        total_count=2617,
        kospi_count=837,
        kosdaq_count=1780,
        added=[{"symbol": "123456", "name": "신규종목", "market": "KOSDAQ"}],
        delisted=[],
        path_override=str(history_path),
    )

    lines = build_universe_startup_log_lines(load_universe_history(str(history_path)))

    assert lines[0] == "[startup] universe-sync summary"
    assert "date: 2026-04-07" in lines[1]
    assert "신규종목(123456)" in lines[5]


def test_build_universe_startup_log_lines_without_history():
    lines = build_universe_startup_log_lines({"updatedAt": None, "entries": []})

    assert lines == ["[startup] universe-sync: 저장된 유니버스 이력이 없습니다"]
