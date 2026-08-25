"""backfill_us_index_membership.py — 미국 지수 구성종목 수집 (S&P500·나스닥100·다우30).

**현행(current) 구성종목**을 무료 소스에서 수집해 data/us-index-membership.json으로
저장한다. 소스는 지수마다 다르다 — 2026년 현재 위키피디아에는 S&P500 목록만 남아 있고
나스닥100·다우 구성 표는 사라졌다(수집 시점에 자동 검증).

  - S&P500   : Wikipedia "List of S&P 500 companies" (503행 — GICS 섹터·CIK·편입일 포함,
               개별주 마스터 백필과 같은 소스)
  - 나스닥100 : Nasdaq 공식 API (api.nasdaq.com/api/quote/list-type/nasdaq100,
               듀얼클래스 포함 ~102 상장)
  - 다우30    : stockanalysis.com 다우 구성 표 (정확히 30행)

**편입/편출 이력(PIT)은 이 스크립트가 수집하지 않는다** — 무료 소스에 신뢰할 수 있는
이력 데이터가 없다. 과거 시점 유니버스는 KOSPI200 선례(PIT 시총 상위 N 근사,
engine/universe_pit.py)를 따르고, 이 파일의 현행 구성은 ① "현재 구성종목" 유니버스
② 근사 품질 검증 기준으로 쓴다. S&P500의 dateAdded(현행 종목의 편입일)는 참고용으로
함께 저장한다.

검증(Fail Fast): 지수별 종목 수가 정상 범위를 벗어나면 종료 코드 1 — 소스 페이지
구조가 바뀌어 엉뚱한 표를 읽으면 조용히 오염되는 대신 여기서 멈춘다. 개별주
마스터(us-stocks.json)·파케이(data/ohlcv-us) 커버리지도 함께 기록한다.

사용:
  python scripts/backfill_us_index_membership.py            # 수집 + 저장
  python scripts/backfill_us_index_membership.py --dry-run  # 저장 없이 수집·검증만
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "us-index-membership.json"
US_MASTER_PATH = ROOT / "data" / "us-stocks.json"
US_OHLCV_DIR = ROOT / "data" / "ohlcv-us"

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_API_URL = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
DOW30_URL = "https://stockanalysis.com/list/dow-jones-stocks/"

_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# 소스 표 구조가 바뀌어 엉뚱한 데이터를 읽으면 여기서 걸린다.
#   S&P500: 회사 500 + 듀얼클래스 상장 → 500~510 / 나스닥100: 100 + 듀얼클래스 → 98~106
EXPECTED_RANGE = {"SP500": (495, 510), "NASDAQ100": (98, 106), "DOW30": (30, 30)}


def normalize_symbol(symbol: str) -> str:
    """야후·파케이 표기로 정규화 (BRK.B → BRK-B)."""
    return str(symbol).strip().upper().replace(".", "-")


def parse_sp500_table(table: pd.DataFrame) -> list[dict]:
    """Wikipedia S&P500 표 → 구성 목록 (섹터·CIK·편입일 포함)."""
    out = []
    for _, row in table.iterrows():
        out.append({
            "symbol": normalize_symbol(row["Symbol"]),
            "name": str(row["Security"]).strip(),
            "sector": str(row["GICS Sector"]).strip(),
            "subIndustry": str(row["GICS Sub-Industry"]).strip(),
            "cik": str(row["CIK"]).strip().zfill(10),
            "dateAdded": str(row.get("Date added", "")).strip() or None,
        })
    return out


def parse_nasdaq100_rows(rows: list[dict]) -> list[dict]:
    """Nasdaq API rows → 구성 목록. 듀얼클래스(GOOG/GOOGL)는 상장별로 그대로 둔다."""
    out = []
    for r in rows:
        symbol = normalize_symbol(r.get("symbol", ""))
        if not symbol:
            continue
        name = str(r.get("companyName", "")).strip()
        # "Apple Inc. Common Stock" → 증권 종류 꼬리는 이름이 아니다
        for tail in (" Common Stock", " Class A Common Stock", " Class B Common Stock",
                     " Class C Capital Stock", " Ordinary Shares", " Common Shares"):
            if name.endswith(tail):
                name = name[: -len(tail)]
                break
        out.append({"symbol": symbol, "name": name})
    return out


def parse_dow30_table(table: pd.DataFrame) -> list[dict]:
    """stockanalysis.com 다우 표 → 구성 목록."""
    sym_col = next(c for c in table.columns if "symbol" in str(c).lower())
    name_col = next(c for c in table.columns if "company" in str(c).lower())
    return [
        {"symbol": normalize_symbol(row[sym_col]), "name": str(row[name_col]).strip()}
        for _, row in table.iterrows()
    ]


def fetch_sp500() -> list[dict]:
    import requests

    resp = requests.get(WIKI_SP500_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    return parse_sp500_table(pd.read_html(io.StringIO(resp.text))[0])


def fetch_nasdaq100() -> list[dict]:
    import requests

    resp = requests.get(NASDAQ100_API_URL, headers=_BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    rows = resp.json().get("data", {}).get("data", {}).get("rows", [])
    return parse_nasdaq100_rows(rows)


def fetch_dow30() -> list[dict]:
    import requests

    resp = requests.get(DOW30_URL, headers=_BROWSER_HEADERS, timeout=30)
    resp.raise_for_status()
    tables = pd.read_html(io.StringIO(resp.text))
    table = next(t for t in tables
                 if any("symbol" in str(c).lower() for c in t.columns) and len(t) >= 20)
    return parse_dow30_table(table)


def validate_counts(indices: dict[str, list[dict]]) -> list[str]:
    """지수별 종목 수 정상 범위 검사. 위반 메시지 목록을 돌려준다(빈 목록=정상)."""
    problems = []
    for key, members in indices.items():
        lo, hi = EXPECTED_RANGE[key]
        n = len(members)
        if not lo <= n <= hi:
            problems.append(f"{key}: {n}종목 — 정상 범위 {lo}~{hi} 밖 (소스 구조 변경 의심)")
        symbols = [m["symbol"] for m in members]
        if len(set(symbols)) != len(symbols):
            problems.append(f"{key}: 심볼 중복")
    return problems


def coverage_report(indices: dict[str, list[dict]],
                    master_symbols: set[str], parquet_symbols: set[str]) -> dict:
    """개별주 마스터·파케이 대비 커버리지 — 빠진 종목은 백필 대상 목록이 된다."""
    report = {}
    for key, members in indices.items():
        symbols = {m["symbol"] for m in members}
        report[key] = {
            "count": len(symbols),
            "missingFromMaster": sorted(symbols - master_symbols),
            "missingFromOhlcv": sorted(symbols - parquet_symbols),
        }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="저장 없이 수집·검증만")
    args = ap.parse_args()

    indices: dict[str, list[dict]] = {}
    for key, fetch in (("SP500", fetch_sp500), ("NASDAQ100", fetch_nasdaq100),
                       ("DOW30", fetch_dow30)):
        indices[key] = fetch()
        print(f"{key}: {len(indices[key])}종목")

    problems = validate_counts(indices)
    if problems:
        for p in problems:
            print(f"검증 실패 — {p}")
        return 1

    master_symbols = {s["symbol"] for s in json.loads(US_MASTER_PATH.read_text())}
    parquet_symbols = {p.stem for p in US_OHLCV_DIR.glob("*.parquet")}
    coverage = coverage_report(indices, master_symbols, parquet_symbols)
    for key, cov in coverage.items():
        miss_m, miss_o = cov["missingFromMaster"], cov["missingFromOhlcv"]
        print(f"  {key} 커버리지 — 마스터 누락 {len(miss_m)}"
              + (f" ({', '.join(miss_m)})" if miss_m else "")
              + f" · 파케이 누락 {len(miss_o)}"
              + (f" ({', '.join(miss_o)})" if miss_o else ""))

    out = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(),
        "sources": {"SP500": WIKI_SP500_URL, "NASDAQ100": NASDAQ100_API_URL, "DOW30": DOW30_URL},
        "note": "현행 구성만 수집 — 편입/편출 이력(PIT)은 무료 소스 부재로 미수집. "
                "과거 시점 유니버스는 PIT 시총 상위 N 근사를 쓴다(engine/universe_pit.py 선례).",
        "coverage": coverage,
        "indices": indices,
    }
    if args.dry_run:
        print("dry-run — 저장하지 않음")
        return 0
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"저장: {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
