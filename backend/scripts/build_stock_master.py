"""
Build data/stock-master.json — the survivorship-bias-free stock master.

Merges three sources into a single point-in-time membership table:
  1. FDR active listings (KOSPI/KOSDAQ): current symbols, market, shares.
  2. FDR KRX-DELISTING: delisted symbols with market, listing/delisting dates,
     reason, listed shares, and merger target (ToSymbol).
  3. Local OHLCV parquet date coverage (dataStart/dataEnd) — the ground truth of
     what we can actually price/trade.

The as-of universe resolver (engine/universe_pit.py) reads this file to decide,
for any backtest window, which symbols were *alive and priceable* during it —
including names that have since delisted. That is what removes survivorship bias.

Run:
    cd backend && python scripts/build_stock_master.py

Idempotent. Network-bound (FDR). Common stocks only (SecuGroup == 주권).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sector_mapper import get_sector_from_krx_industry

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_OHLCV_DIR = _PROJECT_ROOT / "data" / "ohlcv"
_OUT_PATH = _PROJECT_ROOT / "data" / "stock-master.json"

# Delisted names older than this are dropped — we have no OHLCV depth for them and
# they only bloat the file. Our local price history starts ~2013-2016.
_DELISTING_FLOOR = "2015-01-01"
_KST = timezone(timedelta(hours=9))


def _scan_local_ohlcv_coverage() -> dict[str, tuple[str, str]]:
    """symbol -> (dataStart, dataEnd) from local parquet date columns."""
    coverage: dict[str, tuple[str, str]] = {}
    for f in glob.glob(str(_OHLCV_DIR / "*.parquet")):
        sym = os.path.basename(f)[:-8]
        try:
            d = pl.read_parquet(f, columns=["date"])["date"]
            if len(d) == 0:
                continue
            coverage[sym] = (str(d.min())[:10], str(d.max())[:10])
        except Exception:
            continue
    return coverage


# KIND 상장법인목록 — 회사명·종목코드·업종·**상장일**을 인증 없이 내려주는 엑셀(euc-kr HTML 표).
# scripts/sync_data.py::_fetch_kind_market이 korea-stocks.json을 만들 때 쓰는 것과 같은 출처다.
_KIND_LIST_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do"
_KIND_MARKET_TYPES = ("stockMkt", "kosdaqMkt")


def _fetch_kind_listing_table() -> "pd.DataFrame":
    """KIND 상장법인목록(유가+코스닥)을 한 표로. 실패는 예외로 올린다."""
    import io

    import pandas as pd
    import requests

    frames = []
    for market_type in _KIND_MARKET_TYPES:
        response = requests.get(
            _KIND_LIST_URL,
            params={"method": "download", "searchType": "13", "marketType": market_type},
            timeout=30,
        )
        response.raise_for_status()
        response.encoding = "euc-kr"
        frames.append(pd.read_html(io.StringIO(response.text))[0])
    return pd.concat(frames, ignore_index=True)


def load_kind_listing_dates() -> dict[str, str]:
    """symbol -> 상장일(YYYY-MM-DD) — KIND 상장법인목록.

    현행 상장 목록(StockListing("KOSPI"/"KOSDAQ"))에는 상장일 컬럼이 없어 "신규 상장
    종목" 유니버스(FR-STR-073)를 판정할 수 없다. KIND 상장법인목록은 무료·인증 없이
    현행 상장 보통주의 상장일을 사실상 전부 제공한다(실측 2026-07-29: 현행 상장 대비
    99.5%). 상장일이 비어 있는 행(주로 우선주)은 제외한다.

    2026-09-22: **KIND를 직접 부른다**. 종전에는 FDR의 "KRX-DESC"로 같은 목록을 받았는데
    그 경로가 404를 내면서(상류 변경) 야간 종목 마스터 갱신이 통째로 실패했고, 마스터가
    낡으면 생존편향이 경고 없이 되살아난다(project_pit_master_staleness). 같은 저장소가
    이미 쓰는 직접 호출(sync_data._fetch_kind_market)과 같은 출처·같은 표라, FDR 한 겹을
    걷어낸 것이다. FDR 경로는 폴백으로 남긴다 — KIND가 막히는 날을 위해서다.
    """
    import pandas as pd

    try:
        df = _fetch_kind_listing_table()
        codes = df["종목코드"].astype(str).str.strip().str.zfill(6)
        dates = pd.to_datetime(df["상장일"], errors="coerce")
    except Exception as error:  # noqa: BLE001 — 한 출처가 막히면 다른 출처로 간다
        print(f"[stock-master] KIND 직접 조회 실패({error}) — FDR KRX-DESC로 폴백")
        import FinanceDataReader as fdr

        df = fdr.StockListing("KRX-DESC")
        codes = df["Code"].astype(str).str.strip()
        dates = pd.to_datetime(df["ListingDate"], errors="coerce")

    out: dict[str, str] = {}
    for code, listed in zip(codes, dates):
        if code and pd.notna(listed):
            out[code] = str(listed)[:10]
    return out


def _load_active(fdr) -> dict[str, dict]:
    """Current KOSPI/KOSDAQ commons from FDR. Code/Name/Market/Stocks.

    상장일은 현행 상장 목록에 없어 KIND 상장법인목록(KRX-DESC)에서 붙인다.
    """
    listing_dates = load_kind_listing_dates()
    out: dict[str, dict] = {}
    for market in ("KOSPI", "KOSDAQ"):
        df = fdr.StockListing(market)
        code_col = "Code" if "Code" in df.columns else "Symbol"
        for _, r in df.iterrows():
            sym = str(r[code_col]).strip()
            if not sym or len(sym) > 6 and not sym.isalnum():
                continue
            shares = r.get("Stocks")
            out[sym] = {
                "symbol": sym,
                "name": str(r.get("Name", "")).strip(),
                "market": market,
                "secuGroup": "주권",
                "listingDate": listing_dates.get(sym),  # 미커버 시 OHLCV dataStart가 하한
                "delistingDate": None,
                "shares": int(shares) if pd.notna(shares) else None,
                "reason": None,
                "toSymbol": None,
            }
    return out


# 상장폐지 추론 — 현행 상장 목록에서 사라지고 **가격까지 멈춘** 종목(2026-09-22).
# 상류 상폐 명부(FDR KRX-DELISTING)가 죽어도 새 상폐분이 마스터에 들어오게 하는 보조 경로다.
# 대기 거래일을 두는 이유: 목록 조회가 한 번 덜 받아온 날(그 종목은 가격이 계속 붙는다)과
# 실제 폐지(가격이 끊긴다)를 가르는 유일한 신호가 '가격이 멈췄는가'이기 때문이다.
_ABSENCE_MIN_GAP_DAYS = 5      # 시장 최신 거래일과 그 종목 마지막 거래일의 차(달력일)
_ABSENCE_MAX_PER_RUN = 20      # 한 번에 이보다 많으면 목록 조회 사고로 본다(전부 보류)


def infer_delistings_from_absence(
    master: dict, coverage: dict, active: dict,
    *, min_gap_days: int = _ABSENCE_MIN_GAP_DAYS, cap: int = _ABSENCE_MAX_PER_RUN,
) -> tuple[dict[str, dict], str | None]:
    """현행 목록에서 빠지고 가격이 멈춘 '상장 중' 종목 → {symbol: 상폐 필드}. (결과, 보류 사유).

    상폐일은 **마지막 거래일**(dataEnd)로 둔다 — KRX 상폐일은 정리매매 종료 다음 날이지만,
    우리가 아는 사실은 '이 날까지 거래됐다'뿐이고 백테스트는 이 날짜를 넘겨 보유하지 않는다.
    """
    from datetime import date

    ends = [end for _, end in coverage.values() if end]
    if not ends:
        return {}, "가격 커버리지가 비어 판정할 수 없다"
    market_end = max(ends)
    found: dict[str, dict] = {}
    for row in master.get("stocks", []):
        symbol = row.get("symbol")
        if row.get("delistingDate") or symbol in active:
            continue
        cov = coverage.get(symbol)
        if not cov or not cov[1]:
            continue
        gap = (date.fromisoformat(market_end) - date.fromisoformat(cov[1])).days
        if gap < min_gap_days:
            continue
        found[symbol] = {
            "symbol": symbol,
            "name": row.get("name", ""),
            "market": row.get("market"),
            "delistingDate": cov[1],
            "reason": "현행 상장 목록 이탈 + 가격 중단(추론)",
            "toSymbol": None,
        }
    if len(found) > cap:
        return {}, f"상폐 추론 {len(found)}건 — 상한({cap}) 초과라 전부 보류(목록 조회 사고 의심)"
    return found, None


class DelistingSourceUnavailable(RuntimeError):
    """상장폐지 명부를 받지 못했다 — '상폐 0건'과 구분해야 한다(생존편향이 조용히 되살아난다)."""


def _load_delisted(fdr) -> dict[str, dict]:
    """Delisted KOSPI/KOSDAQ commons (>= floor) from FDR KRX-DELISTING.

    2026-09-22 실측: 이 출처가 **빈 표**(행 0·컬럼 0)를 돌려준다(상류 변경). 종전에는 그대로
    KeyError로 죽어 야간 마스터 갱신 전체가 멈췄다 — 빈 응답은 '상폐가 없다'가 아니라 '못
    받았다'이므로, 조용히 0건으로 넘기지도 않고 전용 예외로 올린다(호출부가 나머지 갱신은
    진행하고 이 사실을 눈에 띄게 남긴다).
    """
    d = fdr.StockListing("KRX-DELISTING")
    required = {"DelistingDate", "ListingDate", "SecuGroup", "Market", "Symbol"}
    if len(d) == 0 or not required <= set(d.columns):
        raise DelistingSourceUnavailable(
            f"KRX-DELISTING 응답에 필요한 컬럼이 없다(행 {len(d)}, 컬럼 {list(d.columns)[:6]})"
        )
    d["DelistingDate"] = pd.to_datetime(d["DelistingDate"], errors="coerce")
    d["ListingDate"] = pd.to_datetime(d["ListingDate"], errors="coerce")
    mask = (
        (d["SecuGroup"] == "주권")
        & (d["Market"].isin(["KOSPI", "KOSDAQ"]))
        & (d["DelistingDate"] >= _DELISTING_FLOOR)
    )
    out: dict[str, dict] = {}
    for _, r in d[mask].iterrows():
        sym = str(r["Symbol"]).strip()
        shares = r.get("ListingShares")
        to_sym = r.get("ToSymbol")
        name = str(r.get("Name", "")).strip()
        # KRX 업종명 → 정본 섹터. 섹터 분류 SOT(korea-stocks.json)는 현재 상장 종목만
        # 담으므로, 상폐 종목은 여기서 채워야 섹터 유니버스 백테스트에 포함된다(생존 편향 제거).
        industry = str(r.get("Industry", "")).strip() if pd.notna(r.get("Industry")) else ""
        out[sym] = {
            "symbol": sym,
            "name": name,
            "market": str(r["Market"]).strip(),
            "secuGroup": "주권",
            "listingDate": str(r["ListingDate"])[:10] if pd.notna(r["ListingDate"]) else None,
            "delistingDate": str(r["DelistingDate"])[:10],
            "shares": int(shares) if pd.notna(shares) else None,
            "reason": str(r.get("Reason", "")).strip() or None,
            "toSymbol": str(to_sym).strip() if pd.notna(to_sym) and str(to_sym).strip() else None,
            "industry": industry or None,
            "sector": get_sector_from_krx_industry(sym, industry, name) if industry else None,
        }
    return out


def build() -> dict:
    import FinanceDataReader as fdr

    print("[stock-master] scanning local OHLCV coverage...")
    coverage = _scan_local_ohlcv_coverage()
    print(f"[stock-master]   {len(coverage)} local parquet files")

    print("[stock-master] loading FDR active listings (KOSPI/KOSDAQ)...")
    active = _load_active(fdr)
    print(f"[stock-master]   {len(active)} active commons")

    print("[stock-master] loading FDR KRX-DELISTING...")
    delisted = _load_delisted(fdr)
    print(f"[stock-master]   {len(delisted)} delisted commons (>= {_DELISTING_FLOOR})")

    # Active wins over delisted on symbol collision (re-listed / re-used codes).
    merged: dict[str, dict] = {**delisted, **active}

    # Attach local OHLCV coverage (ground truth of priceability).
    for sym, entry in merged.items():
        cov = coverage.get(sym)
        entry["dataStart"] = cov[0] if cov else None
        entry["dataEnd"] = cov[1] if cov else None
        entry["hasOhlcv"] = cov is not None

    stocks = sorted(merged.values(), key=lambda s: s["symbol"])
    payload = {
        "generatedAt": datetime.now(_KST).isoformat(),
        "delistingFloor": _DELISTING_FLOOR,
        "counts": {
            "total": len(stocks),
            "active": sum(1 for s in stocks if s["delistingDate"] is None),
            "delisted": sum(1 for s in stocks if s["delistingDate"] is not None),
            "withOhlcv": sum(1 for s in stocks if s["hasOhlcv"]),
            "delistedWithOhlcv": sum(1 for s in stocks if s["delistingDate"] and s["hasOhlcv"]),
            "delistedMissingOhlcv": sum(1 for s in stocks if s["delistingDate"] and not s["hasOhlcv"]),
        },
        "stocks": stocks,
    }
    return payload


def main() -> None:
    payload = build()
    _OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    c = payload["counts"]
    print(f"[stock-master] wrote {_OUT_PATH}")
    print(f"[stock-master]   total={c['total']} active={c['active']} delisted={c['delisted']}")
    print(f"[stock-master]   delisted_with_ohlcv={c['delistedWithOhlcv']} "
          f"delisted_missing_ohlcv={c['delistedMissingOhlcv']}")


if __name__ == "__main__":
    main()
