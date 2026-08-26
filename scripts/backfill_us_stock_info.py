"""토스증권 Open API 종목정보를 미국 마스터(data/us-stocks.json)에 백필한다.

GET /api/v1/stocks (200종목 배치)에서 받아 병합하는 필드:
  - name_kr             한글 종목명 (예: "애플") — 한글 검색용
  - isin                ISIN 코드
  - listed_date         상장일 (YYYY-MM-DD)
  - shares_outstanding  발행주식수 (정수)

주의:
  - OHLCV 파케이(data/ohlcv-us/*.parquet)는 건드리지 않는다 — 한국 파케이와
    컬럼·스키마 동일성이 회귀 테스트로 강제되는 계약이라 정적 메타데이터를 넣지 않는다.
  - 심볼 표기: 마스터=대시(BRK-B), 토스=점(BRK.B) — 요청 시 변환하고 응답을 복원한다.
  - 토스에서 조회되지 않는 종목(미거래 지원 등)은 기존 항목을 그대로 둔다.

사용법:
  python3 scripts/backfill_us_stock_info.py            # 실제 백필
  python3 scripts/backfill_us_stock_info.py --dry-run  # 파일 미저장, 커버리지만 출력
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "us-stocks.json"

BASE_URL = "https://openapi.tossinvest.com"
BATCH_MAX = 200          # /api/v1/stocks 심볼 상한
REQUEST_INTERVAL = 0.35  # STOCK 그룹 TPS 제한(1~20/s) 여유
REQUEST_TIMEOUT = 10


def get_token() -> str:
    client_id = os.environ.get("TOSS_INVEST_CLIENT_ID", "")
    client_secret = os.environ.get("TOSS_INVEST_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise SystemExit("TOSS_INVEST_CLIENT_ID/SECRET 환경변수가 필요합니다 (.env)")
    resp = requests.post(
        f"{BASE_URL}/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_stock_info(symbols: list[str], token: str) -> dict[str, dict]:
    """토스 종목정보를 {마스터 심볼: 응답 항목}으로 반환한다."""
    info: dict[str, dict] = {}
    for i in range(0, len(symbols), BATCH_MAX):
        batch = symbols[i : i + BATCH_MAX]
        # 클래스주 표기 차이: 마스터=대시(BRK-B), 토스=점(BRK.B)
        request_map = {s.replace("-", "."): s for s in batch}
        resp = requests.get(
            f"{BASE_URL}/api/v1/stocks",
            params={"symbols": ",".join(request_map.keys())},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        for item in resp.json().get("result", []):
            our_symbol = request_map.get(item.get("symbol", ""), item.get("symbol", ""))
            if our_symbol:
                info[our_symbol] = item
        done = min(i + BATCH_MAX, len(symbols))
        print(f"  {done}/{len(symbols)} 조회 (누적 매칭 {len(info)})")
        time.sleep(REQUEST_INTERVAL)
    return info


def build_info_fields(item: dict) -> dict:
    """토스 응답 항목 → 마스터에 병합할 필드 (값 없는 필드는 제외)."""
    fields: dict = {}
    if item.get("name"):
        fields["name_kr"] = item["name"]
    if item.get("isinCode"):
        fields["isin"] = item["isinCode"]
    if item.get("listDate"):
        fields["listed_date"] = item["listDate"]
    shares = item.get("sharesOutstanding")
    if shares:
        try:
            fields["shares_outstanding"] = int(float(shares))
        except (TypeError, ValueError):
            pass
    return fields


def merge_stock_info(master: list[dict], info_by_symbol: dict[str, dict]) -> int:
    """마스터 항목에 종목정보 필드를 병합한다. 갱신된 항목 수를 반환."""
    updated = 0
    for entry in master:
        item = info_by_symbol.get(entry.get("symbol", ""))
        if not item:
            continue
        fields = build_info_fields(item)
        if fields:
            entry.update(fields)
            updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="파일 미저장, 커버리지만 출력")
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass

    master = json.loads(MASTER_PATH.read_text())
    symbols = [s["symbol"] for s in master if s.get("symbol")]
    print(f"마스터 {len(symbols)}종목 — 토스 종목정보 조회 시작")

    token = get_token()
    info = fetch_stock_info(symbols, token)
    updated = merge_stock_info(master, info)

    missing = sorted(set(symbols) - set(info.keys()))
    print(f"갱신 {updated}종목 / 토스 미조회 {len(missing)}종목")
    if missing:
        print(f"미조회 예시: {missing[:20]}")

    if args.dry_run:
        print("--dry-run: 저장 생략")
        return

    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=1))
    print(f"저장 완료: {MASTER_PATH}")


if __name__ == "__main__":
    main()
