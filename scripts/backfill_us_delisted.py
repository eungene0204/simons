"""backfill_us_delisted.py — 미국 상장폐지 종목 리스트 수집 (Alpha Vantage LISTING_STATUS).

미국 데이터셋(data/ohlcv-us)에는 상폐 종목이 없어 생존편향이 있다(엔진이 경고 고지,
engine/universe_pit.py US 섹션). 이 스크립트는 그 수리의 1단계로, **상폐 종목의 정본
리스트**(티커·회사명·거래소·상장일·상폐일)를 무료 소스에서 수집해
data/us-delisted.json 으로 저장한다.

  소스: Alpha Vantage LISTING_STATUS (state=delisted, 호출 1회, CSV)
        무료 키 필요 — .env 의 ALPHA_VANTAGE_API_KEY (무료 한도 25콜/일, 여기선 1콜)

커버리지 (2026-08-31 실측):
  - 총 ~9,400건 (주식 ~7,500 + ETF ~2,000), 상폐일 기준 2009년~
  - 연 400~1,000건대로 실제 규모가 잡히는 구간은 **2015년 이후** — 2012~2014년은
    부분 수집(연 55~141건)이라 이 구간 백테스트의 생존편향은 완전히 못 걷어낸다
  - 교차검증: 2024년 NYSE/NASDAQ 주식 454건 ↔ stockanalysis.com 연도 페이지 411건,
    SEC EDGAR Form 25 2024Q2 신고 445건(증권 클래스별 신고 포함이라 상회가 정상)

주의 — 티커 재사용: 상폐 티커 중 ~330개는 현재 **다른 회사**가 쓰고 있다(실측).
이 리스트를 심볼만으로 현행 마스터·파케이에 조인하면 안 되고, 반드시 상폐일과
함께 다뤄야 한다. 산출물의 reusedByActive 필드가 해당 심볼 목록이다.

이 리스트만으로는 상폐 종목을 백테스트에 넣을 수 없다(주가 이력 별도 과제).
용도: ① 상폐 사실·시점의 정본 ② 향후 시세 소스 확보 시 백필 대상 목록
③ 전진(forward) 상폐 감지의 기준선.

사용:
  python scripts/backfill_us_delisted.py            # 수집 + 저장
  python scripts/backfill_us_delisted.py --dry-run  # 저장 없이 수집·검증만
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "us-delisted.json"
US_MASTER_PATH = ROOT / "data" / "us-stocks.json"

AV_URL = "https://www.alphavantage.co/query?function=LISTING_STATUS&state=delisted&apikey={key}"

# 소스가 조용히 축소되면(응답 구조 변경·키 차단 등) 여기서 걸린다 — 실측 9,451건 기준.
MIN_EXPECTED_TOTAL = 8000
ALLOWED_ASSET_TYPES = {"Stock", "ETF"}


def normalize_symbol(symbol: str) -> str:
    """야후·파케이 표기로 정규화 (BRK.B → BRK-B) — 지수 구성 수집과 동일 규칙."""
    return str(symbol).strip().upper().replace(".", "-")


def parse_rows(csv_text: str) -> list[dict]:
    """LISTING_STATUS CSV → 상폐 항목 목록. 심볼 없는 행은 버린다."""
    out = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        symbol = normalize_symbol(r.get("symbol", ""))
        if not symbol:
            continue
        out.append({
            "symbol": symbol,
            "name": str(r.get("name", "")).strip(),
            "exchange": str(r.get("exchange", "")).strip(),
            "assetType": str(r.get("assetType", "")).strip(),
            "ipoDate": str(r.get("ipoDate", "")).strip() or None,
            "delistingDate": str(r.get("delistingDate", "")).strip(),
        })
    return out


def validate_rows(rows: list[dict]) -> list[str]:
    """Fail Fast — 위반 메시지 목록(빈 목록=정상)."""
    problems = []
    if len(rows) < MIN_EXPECTED_TOTAL:
        problems.append(f"총 {len(rows)}건 — 기대 최소 {MIN_EXPECTED_TOTAL}건 미만 (소스 축소 의심)")
    symbols = [r["symbol"] for r in rows]
    if len(set(symbols)) != len(symbols):
        problems.append("심볼 중복")
    for r in rows:
        d = r["delistingDate"]
        if len(d) != 10 or d[4] != "-" or d[7] != "-":
            problems.append(f"{r['symbol']}: delistingDate 형식 이상 ({d!r})")
            break
        if r["assetType"] not in ALLOWED_ASSET_TYPES:
            problems.append(f"{r['symbol']}: 알 수 없는 assetType ({r['assetType']!r})")
            break
    return problems


def yearly_counts(rows: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        y = r["delistingDate"][:4]
        counts[y] = counts.get(y, 0) + 1
    return dict(sorted(counts.items()))


def reused_by_active(rows: list[dict], master_symbols: set[str]) -> list[str]:
    """현재 활성 마스터가 재사용 중인 상폐 티커 — 심볼 단독 조인 금지 대상."""
    return sorted({r["symbol"] for r in rows} & master_symbols)


def fetch_delisted(api_key: str) -> str:
    import requests

    resp = requests.get(AV_URL.format(key=api_key), timeout=60)
    resp.raise_for_status()
    text = resp.text
    if text.lstrip().startswith("{"):
        # CSV 대신 JSON이 오면 에러 응답(한도 초과·키 무효)이다
        raise RuntimeError(f"Alpha Vantage 에러 응답: {text[:200]}")
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="저장 없이 수집·검증만")
    args = ap.parse_args()

    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        from dotenv import load_dotenv  # 모듈 레벨 금지 — .env 오염 함정(메모리 참고)

        load_dotenv(ROOT / ".env")
        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        print("ALPHA_VANTAGE_API_KEY 미설정 — .env 확인")
        return 1

    rows = parse_rows(fetch_delisted(api_key))
    n_stock = sum(1 for r in rows if r["assetType"] == "Stock")
    print(f"수집: 총 {len(rows)}건 (주식 {n_stock} · ETF {len(rows) - n_stock})")

    problems = validate_rows(rows)
    if problems:
        for p in problems:
            print(f"검증 실패 — {p}")
        return 1

    master_symbols = {s["symbol"] for s in json.loads(US_MASTER_PATH.read_text())}
    reused = reused_by_active(rows, master_symbols)
    years = yearly_counts(rows)
    print(f"연도별: {years}")
    print(f"티커 재사용(현행 마스터와 충돌): {len(reused)}개")

    out = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(),
        "source": "Alpha Vantage LISTING_STATUS (state=delisted)",
        "note": "상폐 정본 리스트 — 연 400건대 이상으로 실제 규모가 잡히는 구간은 2015년 이후, "
                "2012~2014는 부분 수집. 주가 이력은 미포함(별도 과제). "
                "reusedByActive 심볼은 현행 마스터가 재사용 중이므로 심볼 단독 조인 금지.",
        "counts": {"total": len(rows), "stock": n_stock, "etf": len(rows) - n_stock,
                   "byYear": years},
        "reusedByActive": reused,
        "entries": rows,
    }
    if args.dry_run:
        print("dry-run — 저장하지 않음")
        return 0
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"저장: {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
