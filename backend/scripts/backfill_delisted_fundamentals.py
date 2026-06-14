"""
Backfill fundamentals (EPS/BPS/PER/PBR/ROE/debt-ratio) for delisted stocks.

The price-level survivorship fix (universe_pit + OHLCV backfill) puts delisted names
back in the universe, but fundamental *filters* (e.g. PBR <= 1) still can't select them
without per-stock fundamentals — and KIS/Naver do not serve delisted tickers. DART
(전자공시) does: a delisted company filed annual reports while it was listed.

For each delisted common we pull annual 자본총계 / 부채총계 / 당기순이익 from DART and derive:
    BPS = 자본총계 / shares,  EPS = 당기순이익 / shares
    ROE = 당기순이익 / 자본총계 * 100,  부채비율 = 부채총계 / 자본총계 * 100
then enrich the OHLCV parquet (PER/PBR computed daily with a 90-day publish lag, exactly
like active names). This is what makes fundamental strategies truly survivorship-free.

Run (after build_stock_master.py + backfill_delisted_ohlcv.py):
    cd backend && python scripts/backfill_delisted_fundamentals.py

Idempotent: caches DART corpCode + per-stock fundamentals JSON, skips parquets already
enriched. Shares come from the master (delisting-time count) — a documented approximation
for companies whose share count changed materially across their listed years.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import polars as pl
import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.fundamental_fetcher import enrich_ohlcv_with_fundamentals  # noqa: E402

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_MASTER_PATH = _PROJECT_ROOT / "data" / "stock-master.json"
_FUND_CACHE_DIR = _PROJECT_ROOT / "data" / "fundamentals"
_CORPCODE_CACHE = _PROJECT_ROOT / "data" / "dart_corpcode.json"

_DART = "https://opendart.fss.or.kr/api"
_ANNUAL = "11011"  # 사업보고서
_YEAR_FLOOR = 2013  # local price history depth
_SLEEP = 0.05

load_dotenv(_PROJECT_ROOT / ".env")
_KEY = os.getenv("DART_API_KEY", "").strip()


def _download_corpcode() -> dict[str, str]:
    """symbol -> DART corp_code (cached)."""
    if _CORPCODE_CACHE.exists():
        return json.loads(_CORPCODE_CACHE.read_text(encoding="utf-8"))
    r = requests.get(f"{_DART}/corpCode.xml", params={"crtfc_key": _KEY}, timeout=60)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(z.read(z.namelist()[0]))
    mapping: dict[str, str] = {}
    for el in root.iter("list"):
        sc = (el.findtext("stock_code") or "").strip()
        cc = (el.findtext("corp_code") or "").strip()
        if len(sc) == 6 and cc:
            mapping[sc] = cc
    _CORPCODE_CACHE.write_text(json.dumps(mapping), encoding="utf-8")
    return mapping


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fetch_year(corp_code: str, year: int) -> dict | None:
    """Annual 자본총계/부채총계/당기순이익 for a fiscal year (consolidated preferred)."""
    r = requests.get(
        f"{_DART}/fnlttSinglAcnt.json",
        params={"crtfc_key": _KEY, "corp_code": corp_code,
                "bsns_year": str(year), "reprt_code": _ANNUAL},
        timeout=15,
    ).json()
    if r.get("status") != "000":
        return None
    by_div: dict[str, dict[str, str]] = {}
    for it in r.get("list", []):
        by_div.setdefault(it.get("fs_div", "OFS"), {})[it.get("account_nm", "")] = it.get("thstrm_amount")
    accounts = by_div.get("CFS") or by_div.get("OFS") or {}

    def pick(target: str) -> float | None:
        if target in accounts:
            return _num(accounts[target])
        for nm, v in accounts.items():
            if target in nm:
                return _num(v)
        return None

    equity = pick("자본총계")
    debt = pick("부채총계")
    income = pick("당기순이익")
    if equity is None:
        return None
    return {"equity": equity, "debt": debt, "income": income}


def _fundamentals_for(corp_code: str, shares: float, start_year: int, end_year: int) -> list[dict]:
    out: list[dict] = []
    for year in range(start_year, end_year + 1):
        fin = _fetch_year(corp_code, year)
        time.sleep(_SLEEP)
        if not fin or not shares:
            continue
        equity, debt, income = fin["equity"], fin["debt"], fin["income"]
        entry = {"year_end": f"{year}-12-31", "bps": equity / shares}
        if income is not None:
            entry["eps"] = income / shares
            if equity:
                entry["roe_or_gpa"] = income / equity * 100.0
        if debt is not None and equity:
            entry["debt_ratio"] = debt / equity * 100.0
        out.append(entry)
    return out


def _cached_fundamentals(sym: str) -> list[dict] | None:
    p = _FUND_CACHE_DIR / f"{sym}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("fundamentals")
        except Exception:
            return None
    return None


def _write_cache(sym: str, fundamentals: list[dict]) -> None:
    _FUND_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (_FUND_CACHE_DIR / f"{sym}.json").write_text(
        json.dumps({"symbol": sym, "source": "dart", "fundamentals": fundamentals},
                   ensure_ascii=False, indent=2), encoding="utf-8")


def _enrich_parquet(sym: str, fundamentals: list[dict]) -> bool:
    path = _OHLCV_DIR / f"{sym}.parquet"
    if not path.exists():
        return False
    pdf = pl.read_parquet(path).to_pandas()
    enriched = enrich_ohlcv_with_fundamentals(pdf, fundamentals)
    pl.from_pandas(enriched).write_parquet(path)
    return enriched["pbr"].notna().any()


def main() -> None:
    master = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    sym2corp = _download_corpcode()
    targets = [s for s in master["stocks"] if s["delistingDate"] and s["hasOhlcv"]]
    print(f"[fund] {len(targets)} delisted commons with OHLCV; corpCode map={len(sym2corp)}")

    enriched = no_corp = no_fin = 0
    for i, s in enumerate(targets, 1):
        sym = s["symbol"]
        shares = s.get("shares")
        start = max(_YEAR_FLOOR, int((s.get("dataStart") or "2013")[:4]) - 1)
        end = int(s["delistingDate"][:4])

        fundamentals = _cached_fundamentals(sym)
        if fundamentals is None:
            corp = sym2corp.get(sym)
            if not corp or not shares:
                no_corp += 1
                continue
            fundamentals = _fundamentals_for(corp, float(shares), start, end)
            if fundamentals:
                _write_cache(sym, fundamentals)
        if not fundamentals:
            no_fin += 1
            continue

        if _enrich_parquet(sym, fundamentals):
            enriched += 1
        if i % 50 == 0:
            print(f"[fund] {i}/{len(targets)} enriched={enriched} no_corp={no_corp} no_fin={no_fin}")

    print(f"[fund] done: enriched={enriched} no_corp={no_corp} no_fin={no_fin}")


if __name__ == "__main__":
    main()
