"""backfill_us_fundamentals_edgar.py — SEC EDGAR로 미국 재무 팩터 이력 확장 (2009~).

yfinance 분기 재무는 최근 ~5분기뿐이라 TTM 팩터(PER·ROE·매출 등)가 약 3개월치만
존재한다(2026-08-25 감사). EDGAR `companyfacts` XBRL은 분기 재무 전 이력(대략 2008~)을
무료 제공하므로, 이것으로 파케이의 **재무 컬럼만** 역사적으로 재구축한다.

구조 — 기존 파이프라인 전면 재사용:
  EDGAR facts → (yfinance 재무제표 모양의 inc/bs/cf 프레임) 어댑터
             → stocks.build_quarterly / build_annual_growth   (지표 정의 동일)
             → stocks.build_daily_frame                        (룩어헤드 lag·15개월 cap 동일)
  가격·배당·시총은 저장 파케이 값을 그대로 쓴다(야후 재조회 없음) — 주식수는
  market_cap/close 역산(증분 레인과 같은 방식). 병합은 **EDGAR 우선, 기존값 폴백**
  (combine_first): 이력은 늘고, EDGAR 개념 매핑이 안 되는 종목·구간은 기존 yfinance
  값을 잃지 않는다.

분기화 규약:
  - 기간(duration) 개념: 같은 (start,end)는 최신 filed만. ~90일 기간은 직접 채택,
    YTD 보고(반기·9개월·연간)는 같은 start의 연속 구간 차분으로 분기값 유도(Q4=FY-9M 포함).
  - 시점(instant) 개념(재무상태표): 같은 end는 최신 filed만.
  - 성장률은 연간(FY 기간) 값으로 계산 — 기존 연간 규약과 동일.
  - USD 단위만 사용. 비USD 보고 기업(486개)은 어댑터가 빈 프레임을 내고 기존값 유지.

한계(지어내지 않는다):
  - EBITDA = 영업이익 + 감가상각(D&A), EBIT = 영업이익 근사. 은행·보험 등 개념 체계가
    다른 업종은 해당 항목이 NaN으로 남는다(커버리지로 고지).
  - total_debt는 장·단기 차입 개념 합산 근사(EV 계산에만 사용).

사용:
  python scripts/backfill_us_fundamentals_edgar.py --symbols AAPL,MSFT   # 시험
  python scripts/backfill_us_fundamentals_edgar.py                       # 전량 (이어받기 가능)
  python scripts/backfill_us_fundamentals_edgar.py --force               # 완료 마커 무시
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "simons_backfill_us_stocks", ROOT / "scripts" / "backfill_us_stocks.py")
stocks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stocks)

OUT_DIR = ROOT / "data" / "ohlcv-us"
MASTER_PATH = ROOT / "data" / "us-stocks.json"
DONE_MARKER = OUT_DIR / ".edgar_fundamentals_done"

# 최신 filed 우선 dedupe 뒤 분기 판정에 쓰는 기간 경계(일)
_QTR_MIN, _QTR_MAX = 70, 100
_ANNUAL_MIN, _ANNUAL_MAX = 330, 400

# yfinance 재무제표 행 이름 → EDGAR us-gaap 개념(우선순위 순).
# build_quarterly의 _row 폴백과 짝을 맞춘다 — 행 이름이 계약이다.
_INC_CONCEPTS = {
    "Total Revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                      "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                      "SalesRevenueGoodsNet", "SalesRevenueServicesNet"],
    "Net Income": ["NetIncomeLoss"],
    "Net Income Common Stockholders": ["NetIncomeLossAvailableToCommonStockholdersBasic",
                                       "NetIncomeLoss"],
    "Gross Profit": ["GrossProfit"],
    "Operating Income": ["OperatingIncomeLoss"],
    "Basic EPS": ["EarningsPerShareBasic", "EarningsPerShareDiluted"],
}
_DA_CONCEPTS = ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                "DepreciationAmortizationAndAccretionNet"]
_BS_CONCEPTS = {
    "Stockholders Equity": ["StockholdersEquity",
                            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "Total Assets": ["Assets"],
    "Total Liabilities Net Minority Interest": ["Liabilities"],
    "Current Assets": ["AssetsCurrent"],
    "Current Liabilities": ["LiabilitiesCurrent"],
    "Inventory": ["InventoryNet"],
    "Retained Earnings": ["RetainedEarningsAccumulatedDeficit"],
    "Capital Stock": ["CommonStockValue"],
    "Cash And Cash Equivalents": ["CashAndCashEquivalentsAtCarryingValue",
                                  "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
}
_DEBT_CONCEPTS = [["LongTermDebtNoncurrent", "LongTermDebtCurrent"],   # 합산 우선
                  ["LongTermDebt"]]                                     # 폴백(전체)
_CF_CONCEPTS = {
    "Operating Cash Flow": ["NetCashProvidedByUsedInOperatingActivities",
                            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "Investing Cash Flow": ["NetCashProvidedByUsedInInvestingActivities",
                            "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"],
    "Financing Cash Flow": ["NetCashProvidedByUsedInFinancingActivities",
                            "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"],
    "Capital Expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
}

# 재무 컬럼(병합 대상) — 가격·배당·시총 계열은 저장값을 유지한다
_KEEP_COLS = {"date", "open", "high", "low", "close", "volume", "change", "sector",
              "market_cap", "dividends", "dividend_yield", "dividend_growth"}
FIN_COLS = [c for c in stocks.COLUMNS if c not in _KEEP_COLS]


def _points(facts: dict, concept: str) -> list[dict]:
    units = facts.get("us-gaap", {}).get(concept, {}).get("units", {})
    # 금액은 USD, 주당 값은 USD/shares — 그 외 통화는 쓰지 않는다(환산 없이 섞으면 오염)
    return units.get("USD") or units.get("USD/shares") or []


def _dedupe_latest_filed(points: list[dict], key_fn) -> dict:
    best: dict = {}
    for p in points:
        if "val" not in p or not p.get("end"):
            continue
        key = key_fn(p)
        if key is None:
            continue
        if key not in best or p.get("filed", "") > best[key].get("filed", ""):
            best[key] = p
    return best


def quarterly_from_durations(points: list[dict]) -> pd.Series:
    """기간 보고값 → 분기 시리즈(기간 종료일 index).

    ~90일 보고는 직접 채택. YTD 보고(반기·9개월·연간)는 같은 start를 공유하는 연속
    구간의 차분으로 분기값을 유도한다(Q4 = FY − 9M 포함). 직접 보고가 차분보다 우선.
    """
    best = _dedupe_latest_filed(points, lambda p: (p.get("start"), p["end"]) if p.get("start") else None)
    direct: dict[pd.Timestamp, float] = {}
    by_start: dict[pd.Timestamp, list] = defaultdict(list)
    for (s, e), p in best.items():
        start, end = pd.Timestamp(s), pd.Timestamp(e)
        days = (end - start).days
        if _QTR_MIN <= days <= _QTR_MAX:
            direct[end] = float(p["val"])
        by_start[start].append((end, float(p["val"])))

    derived: dict[pd.Timestamp, float] = {}
    for start, lst in by_start.items():
        lst.sort()
        for (e1, v1), (e2, v2) in zip(lst, lst[1:]):
            if _QTR_MIN <= (e2 - e1).days <= _QTR_MAX:
                derived[e2] = v2 - v1
    merged = {**derived, **direct}  # 직접 보고 우선
    return pd.Series(merged, dtype=float).sort_index()


def annual_from_durations(points: list[dict]) -> pd.Series:
    """연간(FY 기간) 보고값 → 회계연도 종료일 index 시리즈."""
    best = _dedupe_latest_filed(points, lambda p: (p.get("start"), p["end"]) if p.get("start") else None)
    vals = {}
    for (s, e), p in best.items():
        if _ANNUAL_MIN <= (pd.Timestamp(e) - pd.Timestamp(s)).days <= _ANNUAL_MAX:
            vals[pd.Timestamp(e)] = float(p["val"])
    return pd.Series(vals, dtype=float).sort_index()


def instant_series(points: list[dict]) -> pd.Series:
    """시점(재무상태표) 보고값 → 기말 index 시리즈."""
    best = _dedupe_latest_filed(points, lambda p: p["end"] if not p.get("start") else None)
    return pd.Series({pd.Timestamp(e): float(p["val"]) for e, p in best.items()},
                     dtype=float).sort_index()


def _merged_series(facts: dict, concepts: list[str], extract) -> pd.Series:
    """개념 우선순위 병합 — 회사가 세월에 따라 보고 개념을 갈아타는 경우(AAPL 매출:
    SalesRevenueNet→RevenueFromContract…)가 흔해서, 첫 번째 비어있지 않은 개념만 쓰면
    과거 이력이 유실된다. 앞선 개념이 겹치는 시점에서 우선하고 나머지는 뒤가 채운다."""
    merged = pd.Series(dtype=float)
    for c in concepts:
        s = extract(_points(facts, c))
        if s.empty:
            continue
        merged = s if merged.empty else merged.combine_first(s)
    return merged


def _debt_series(facts: dict) -> pd.Series:
    for group in _DEBT_CONCEPTS:
        parts = [instant_series(_points(facts, c)) for c in group]
        parts = [p for p in parts if not p.empty]
        if parts:
            return sum((p.reindex(sorted(set().union(*[set(x.index) for x in parts])))
                        .fillna(0.0) for p in parts), start=0.0)
    return pd.Series(dtype=float)


def build_statement_frames(facts: dict):
    """EDGAR facts → yfinance 모양의 (분기 inc/bs/cf, 연간 inc/cf) 프레임 5종."""
    inc_rows = {name: _merged_series(facts, concepts, quarterly_from_durations)
                for name, concepts in _INC_CONCEPTS.items()}
    # EBITDA = 영업이익 + D&A, EBIT = 영업이익 근사 (없으면 NaN — 지어내지 않는다)
    oi = inc_rows["Operating Income"]
    da = _merged_series(facts, _DA_CONCEPTS, quarterly_from_durations)
    if not oi.empty and not da.empty:
        idx = oi.index.intersection(da.index)
        inc_rows["EBITDA"] = (oi.reindex(idx) + da.reindex(idx))
    inc_rows["EBIT"] = oi

    cf_rows = {name: _merged_series(facts, concepts, quarterly_from_durations)
               for name, concepts in _CF_CONCEPTS.items()}
    ocf, capex = cf_rows["Operating Cash Flow"], cf_rows["Capital Expenditure"]
    if not ocf.empty and not capex.empty:
        idx = ocf.index.intersection(capex.index)
        cf_rows["Free Cash Flow"] = ocf.reindex(idx) - capex.reindex(idx).abs()

    bs_rows = {name: _merged_series(facts, concepts, instant_series)
               for name, concepts in _BS_CONCEPTS.items()}
    bs_rows["Total Debt"] = _debt_series(facts)

    def frame(rows: dict) -> pd.DataFrame:
        rows = {k: v for k, v in rows.items() if v is not None and not v.empty}
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).T  # index=행 이름, columns=기간 종료일 (yfinance 모양)

    inc_a_rows = {name: _merged_series(facts, concepts, annual_from_durations)
                  for name, concepts in _INC_CONCEPTS.items()}
    oi_a = inc_a_rows["Operating Income"]
    da_a = _merged_series(facts, _DA_CONCEPTS, annual_from_durations)
    if not oi_a.empty and not da_a.empty:
        idx = oi_a.index.intersection(da_a.index)
        inc_a_rows["EBITDA"] = (oi_a.reindex(idx) + da_a.reindex(idx))
    cf_a_rows = {name: _merged_series(facts, concepts, annual_from_durations)
                 for name, concepts in _CF_CONCEPTS.items()}
    ocf_a, capex_a = cf_a_rows["Operating Cash Flow"], cf_a_rows["Capital Expenditure"]
    if not ocf_a.empty and not capex_a.empty:
        idx = ocf_a.index.intersection(capex_a.index)
        cf_a_rows["Free Cash Flow"] = ocf_a.reindex(idx) - capex_a.reindex(idx).abs()

    return frame(inc_rows), frame(bs_rows), frame(cf_rows), frame(inc_a_rows), frame(cf_a_rows)


def fetch_companyfacts(cik: str) -> dict:
    import requests

    url = stocks.SEC_FACTS_URL.format(cik=str(cik).zfill(10))
    resp = requests.get(url, headers={"User-Agent": stocks.SEC_USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("facts", {})


def rebuild_financials(stored: pd.DataFrame, facts: dict) -> pd.DataFrame | None:
    """저장 파케이 + EDGAR facts → 재무 컬럼을 병합(EDGAR 우선, 기존값 폴백)한 프레임.

    가격·배당·시총·섹터는 저장값 그대로. EDGAR에서 아무 프레임도 못 만들면 None.
    """
    inc, bs, cf, inc_a, cf_a = build_statement_frames(facts)
    if inc.empty and bs.empty and cf.empty:
        return None
    qdf = stocks.build_quarterly(inc, bs, cf)
    adf = stocks.build_annual_growth(inc_a, cf_a)
    if qdf.empty and adf.empty:
        return None

    # 파케이는 datetime64[us], 내부 계산(merge_asof 등)은 ns 기준 — ns로 통일해 넘긴다
    dates = pd.DatetimeIndex(stored["date"]).astype("datetime64[ns]")
    # 주식수 = 시총 역산(증분 레인과 같은 방식) — 분할·클래스 문제를 저장 시총이 이미 흡수했다
    with np.errstate(invalid="ignore", divide="ignore"):
        shares = pd.Series(
            (stored["market_cap"].to_numpy() * stocks.EOK) / stored["close"].to_numpy(),
            index=dates)
    shares = shares.where(np.isfinite(shares))
    hist = pd.DataFrame({
        "Open": stored["open"].to_numpy(), "High": stored["high"].to_numpy(),
        "Low": stored["low"].to_numpy(), "Close": stored["close"].to_numpy(),
        "Volume": stored["volume"].to_numpy(),
        "Dividends": stored["dividends"].fillna(0.0).to_numpy(),
        "Stock Splits": 0.0,  # 주식수를 이미 분할 수정된 시총에서 역산했으므로 재조정 불필요
    }, index=dates)

    sector = stored["sector"].dropna().iloc[-1] if stored["sector"].notna().any() else ""
    rebuilt = stocks.build_daily_frame(hist, qdf, shares.dropna(), sector, adf)
    if len(rebuilt) != len(stored):
        raise RuntimeError(f"행 수 불일치: {len(rebuilt)} != {len(stored)}")

    merged = stored.copy()
    for col in FIN_COLS:
        merged[col] = rebuilt[col].combine_first(stored[col])
    for col in stocks.STATUS_COLUMNS:
        merged[col] = merged[col].astype("string")
    return merged


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", help="쉼표 구분 티커 (기본: 마스터 전체)")
    ap.add_argument("--limit", type=int, help="앞에서 N종목만")
    ap.add_argument("--force", action="store_true", help="완료 마커 무시하고 다시")
    ap.add_argument("--sleep", type=float, default=0.15,
                    help="요청 간 대기(초) — SEC 공정 이용 한도(10req/s) 준수")
    args = ap.parse_args()

    master = json.loads(MASTER_PATH.read_text())
    by_symbol = {m["symbol"]: m for m in master}
    symbols = [s.strip().upper() for s in args.symbols.split(",")] \
        if args.symbols else [m["symbol"] for m in master]
    if args.limit:
        symbols = symbols[: args.limit]

    done: set[str] = set()
    if DONE_MARKER.exists() and not args.force:
        done = set(DONE_MARKER.read_text().split())

    ok = skip = no_cik = no_facts = fail = 0
    failed: list[str] = []
    t0 = time.time()
    for i, sym in enumerate(symbols, 1):
        path = OUT_DIR / f"{sym}.parquet"
        if sym in done or not path.exists():
            skip += 1
            continue
        cik = by_symbol.get(sym, {}).get("cik")
        if not cik:
            no_cik += 1
            continue
        try:
            import requests

            try:
                facts = fetch_companyfacts(cik)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    # 폐쇄형 펀드·트러스트 등 10-K/10-Q 미제출 등록자 — companyfacts가
                    # 아예 없다(N-CEN/N-PORT 제출). 재무가 없는 게 정상이므로 기존값 유지.
                    facts = None
                else:
                    raise
            merged = None
            if facts is not None:
                stored = pd.read_parquet(path)
                merged = rebuild_financials(stored, facts)
            if merged is None:
                no_facts += 1  # companyfacts 없음·비USD 보고·개념 부재 — 기존값 유지
            else:
                merged.to_parquet(path, index=False)
                ok += 1
            with DONE_MARKER.open("a") as f:
                f.write(sym + "\n")
        except Exception as exc:
            fail += 1
            failed.append(sym)
            print(f"[{i}/{len(symbols)}] {sym}: 실패({exc})")
        if i % 200 == 0:
            rate = i / max(time.time() - t0, 1)
            print(f"[{i}/{len(symbols)}] 갱신 {ok} · 개념없음 {no_facts} · 스킵 {skip}"
                  f" · CIK없음 {no_cik} · 실패 {fail} ({rate:.1f}종목/s)", flush=True)
        time.sleep(args.sleep)

    print(f"\n완료: 갱신 {ok} · 개념없음(기존 유지) {no_facts} · 스킵 {skip}"
          f" · CIK없음 {no_cik} · 실패 {fail}")
    if failed:
        print("실패 종목:", ", ".join(failed[:40]) + (" …" if len(failed) > 40 else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
