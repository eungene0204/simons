import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Optional


def _default_store() -> dict[str, Any]:
    return {
        "updatedAt": None,
        "entries": [],
    }


def _history_path(path_override: Optional[str] = None) -> Path:
    if path_override:
        return Path(path_override)
    return Path(__file__).resolve().parent.parent / "data" / "universe-history.json"


def load_universe_history(path_override: Optional[str] = None) -> dict[str, Any]:
    path = _history_path(path_override)
    if not path.exists():
        return _default_store()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_store()

        entries = data.get("entries", [])
        if not isinstance(entries, list):
            entries = []

        entries = sorted(
            entries,
            key=lambda item: (item.get("date", ""), item.get("syncedAt", "")),
            reverse=True,
        )

        return {
            "updatedAt": data.get("updatedAt"),
            "entries": entries,
        }
    except Exception:
        return _default_store()


def _format_changed_stocks(stocks: list[dict[str, Any]]) -> str:
    if not stocks:
        return "없음"

    return ", ".join(
        f"{stock.get('name', '')}({stock.get('symbol', '')})"
        for stock in stocks
    )


def _normalize_stock(stock: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": stock.get("symbol", ""),
        "name": stock.get("name", ""),
        "market": stock.get("market", ""),
        "sector": stock.get("sector", ""),
        "industry": stock.get("industry", ""),
    }


def record_universe_sync(
    *,
    date: str,
    synced_at: str,
    total_count: int,
    kospi_count: int,
    kosdaq_count: int,
    added: list[dict[str, Any]],
    delisted: list[dict[str, Any]],
    path_override: Optional[str] = None,
    max_entries: int = 400,
) -> dict[str, Any]:
    path = _history_path(path_override)
    path.parent.mkdir(parents=True, exist_ok=True)

    store = load_universe_history(path_override)
    entries = [
        entry for entry in store["entries"]
        if not (entry.get("date") == date and entry.get("syncedAt") == synced_at)
    ]

    entry = {
        "date": date,
        "syncedAt": synced_at,
        "totalCount": total_count,
        "kospiCount": kospi_count,
        "kosdaqCount": kosdaq_count,
        "addedCount": len(added),
        "delistedCount": len(delisted),
        "added": [_normalize_stock(stock) for stock in added],
        "delisted": [_normalize_stock(stock) for stock in delisted],
    }

    entries.append(entry)
    entries = sorted(
        entries,
        key=lambda item: (item.get("date", ""), item.get("syncedAt", "")),
        reverse=True,
    )[:max_entries]

    store = {
        "updatedAt": synced_at,
        "entries": entries,
    }

    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as tmp:
        json.dump(store, tmp, ensure_ascii=False, indent=2)
        tmp_path = Path(tmp.name)

    tmp_path.replace(path)
    return entry


def build_universe_sync_log_lines(
    entry: dict[str, Any],
    history_store: Optional[dict[str, Any]] = None,
) -> list[str]:
    net_change = int(entry.get("addedCount", 0)) - int(entry.get("delistedCount", 0))
    recent_entries = (history_store or {}).get("entries", [])[:7]
    lines = [
        "[INFO] universe-sync summary",
        f"[INFO]   date: {entry.get('date')}",
        f"[INFO]   synced_at: {entry.get('syncedAt')}",
        (
            "[INFO]   counts: "
            f"total={entry.get('totalCount')} "
            f"kospi={entry.get('kospiCount')} "
            f"kosdaq={entry.get('kosdaqCount')}"
        ),
        (
            "[INFO]   changes: "
            f"net={net_change:+d} "
            f"added={entry.get('addedCount', 0)} "
            f"delisted={entry.get('delistedCount', 0)}"
        ),
        f"[INFO]   added_symbols: {_format_changed_stocks(entry.get('added', []))}",
        f"[INFO]   delisted_symbols: {_format_changed_stocks(entry.get('delisted', []))}",
        "[INFO] universe-sync recent-7d",
    ]

    if recent_entries:
        lines.extend(
            (
                "[INFO]   "
                f"{recent.get('date', '-')}: "
                f"전체 {recent.get('totalCount', 0)} / "
                f"KOSPI {recent.get('kospiCount', 0)} / "
                f"KOSDAQ {recent.get('kosdaqCount', 0)} / "
                f"신규 {recent.get('addedCount', 0)} / "
                f"제외 {recent.get('delistedCount', 0)}"
            )
            for recent in recent_entries
        )
    else:
        lines.append("[INFO]   기록 없음")

    return lines


def build_universe_startup_log_lines(
    history_store: Optional[dict[str, Any]],
) -> list[str]:
    entries = (history_store or {}).get("entries", [])
    if not entries:
        return ["[startup] universe-sync: 저장된 유니버스 이력이 없습니다"]

    latest_entry = entries[0]
    sync_lines = build_universe_sync_log_lines(latest_entry, history_store)
    return [line.replace("[INFO] ", "[startup] ", 1) for line in sync_lines]
