"""토스증권 Open API 종목정보를 한국 마스터(data/korea-stocks.json)에 백필한다.

GET /api/v1/stocks (200종목 배치)에서 받아 병합하는 필드:
  - name_en  영문 종목명 (예: "SamsungElec") — 영어 검색용

토스에서 조회되지 않는 종목은 기존 항목을 그대로 둔다.

사용법:
  python3 scripts/backfill_kr_stock_info.py            # 실제 백필
  python3 scripts/backfill_kr_stock_info.py --dry-run  # 파일 미저장, 커버리지만 출력
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "korea-stocks.json"

BASE_URL = "https://openapi.tossinvest.com"
BATCH_MAX = 200
REQUEST_INTERVAL = 0.35
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
    """토스 종목정보를 {심볼: 응답 항목}으로 반환한다 (KR 코드는 표기 변환 불필요)."""
    info: dict[str, dict] = {}
    for i in range(0, len(symbols), BATCH_MAX):
        batch = symbols[i : i + BATCH_MAX]
        resp = requests.get(
            f"{BASE_URL}/api/v1/stocks",
            params={"symbols": ",".join(batch)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        for item in resp.json().get("result", []):
            symbol = item.get("symbol", "")
            if symbol:
                info[symbol] = item
        done = min(i + BATCH_MAX, len(symbols))
        print(f"  {done}/{len(symbols)} 조회 (누적 매칭 {len(info)})")
        time.sleep(REQUEST_INTERVAL)
    return info


def merge_english_names(master: list[dict], info_by_symbol: dict[str, dict]) -> int:
    """마스터 항목에 name_en을 병합한다. 갱신된 항목 수를 반환."""
    updated = 0
    for entry in master:
        item = info_by_symbol.get(entry.get("symbol", ""))
        english = (item or {}).get("englishName")
        if english:
            entry["name_en"] = english
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
    updated = merge_english_names(master, info)

    missing = sorted(set(symbols) - set(info.keys()))
    print(f"갱신 {updated}종목 / 토스 미조회 {len(missing)}종목")
    if missing:
        print(f"미조회 예시: {missing[:20]}")

    if args.dry_run:
        print("--dry-run: 저장 생략")
        return

    MASTER_PATH.write_text(json.dumps(master, ensure_ascii=False, indent=2))
    print(f"저장 완료: {MASTER_PATH}")


if __name__ == "__main__":
    main()
