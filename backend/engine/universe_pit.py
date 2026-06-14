"""
Point-in-time (survivorship-bias-free) universe resolution.

Reads data/stock-master.json (built by scripts/build_stock_master.py) and answers:
"for a backtest window [start, end], which symbols were alive and priceable —
including names that have since delisted?"

This replaces the legacy resolution that drew only from the *current* listed set
(korea-stocks.json / kospi200-cache.json), which silently excluded every stock
that delisted during the window and thereby inflated returns / understated risk.

Membership rule (grounded in real local price coverage):
    market matches AND hasOhlcv AND dataStart <= end AND dataEnd >= start

"대형주" / KOSPI200 is treated as a point-in-time top-N-by-market-cap subset of the
alive KOSPI names; the hard top-N gate is applied in the backtest engine (it needs
daily close prices), while this module supplies the alive-KOSPI superset and the
static share counts used to compute market cap.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock-master.json"

# When a backtest has no explicit start (period=FULL), bound the lower edge here.
_DEFAULT_START_FLOOR = "2015-01-01"

# "대형주" / KOSPI200 point-in-time size cutoff.
LARGE_CAP_TOP_N = 200


@lru_cache(maxsize=1)
def _load_master() -> list[dict]:
    if not _MASTER_PATH.exists():
        return []
    return json.loads(_MASTER_PATH.read_text(encoding="utf-8")).get("stocks", [])


def reload_master() -> None:
    """Drop the cached master (call after regenerating the file)."""
    _load_master.cache_clear()


def parse_universe_markets(universe_id: Optional[str]) -> tuple[list[str], bool]:
    """universe_id ("kospi", "kospi200", "kosdaq_kospi", ...) -> (markets, is_large_cap).

    Returns ([], False) when the id is not a recognized market universe (e.g. a
    custom symbol set), signalling the caller to leave the symbol list untouched.
    """
    if not universe_id:
        return [], False
    tokens = {t for t in universe_id.lower().split("_") if t}
    if not tokens or not tokens <= {"kospi", "kosdaq", "kospi200"}:
        return [], False
    is_large_cap = "kospi200" in tokens
    markets: list[str] = []
    if "kospi" in tokens or "kospi200" in tokens:
        markets.append("KOSPI")
    if "kosdaq" in tokens:
        markets.append("KOSDAQ")
    return markets, is_large_cap


def _alive(stock: dict, start: str, end: str) -> bool:
    if not stock.get("hasOhlcv"):
        return False
    ds, de = stock.get("dataStart"), stock.get("dataEnd")
    if not ds or not de:
        return False
    return ds <= end and de >= start


def resolve_symbols(universe_id: Optional[str], start: Optional[str], end: str) -> Optional[list[str]]:
    """As-of symbol list for the window, or None if universe_id is not a market universe.

    For a large-cap (KOSPI200) universe this returns the alive-KOSPI superset; the
    engine then applies the point-in-time top-N market-cap gate.
    """
    markets, _ = parse_universe_markets(universe_id)
    if not markets:
        return None
    lo = start or _DEFAULT_START_FLOOR
    target = set(markets)
    symbols = [
        s["symbol"] for s in _load_master()
        if s.get("market") in target and _alive(s, lo, end)
    ]
    return sorted(symbols)


def get_shares(symbols: list[str]) -> dict[str, float]:
    """symbol -> listed shares (static, from master) for market-cap ranking."""
    wanted = set(symbols)
    out: dict[str, float] = {}
    for s in _load_master():
        if s["symbol"] in wanted and s.get("shares"):
            out[s["symbol"]] = float(s["shares"])
    return out


def get_delisting_dates(symbols: list[str]) -> dict[str, str]:
    """symbol -> delistingDate, only for names that actually delisted.

    Lets the engine label a forced exit at a delisted name's last trading day as
    "상장폐지" rather than the generic "데이터 종료".
    """
    wanted = set(symbols)
    return {
        s["symbol"]: s["delistingDate"]
        for s in _load_master()
        if s["symbol"] in wanted and s.get("delistingDate")
    }
