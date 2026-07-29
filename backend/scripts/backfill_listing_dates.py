"""
Backfill listingDate for *currently listed* stocks in data/stock-master.json.

상폐 종목의 상장일은 FDR KRX-DELISTING이 함께 주므로 이미 채워져 있지만, 현행 상장
종목은 FDR StockListing("KOSPI"/"KOSDAQ")에 상장일 컬럼이 없어 listingDate=null로
남아 있었다. 그 결과 "신규 상장 종목" 유니버스(FR-STR-073)를 판정할 근거가 없다.

상장일 소스는 FDR "KRX-DESC"(KIND 상장법인목록)다 — 무료·인증 불필요이며 현행 상장
보통주를 사실상 전부 커버한다(실측 2026-07-29: 2,755/2,768 = 99.5%. 미커버 13종목은
KIND 목록에 없는 구종목으로, 로컬 OHLCV 시작일이 백필 하한이라 신규 상장으로 오인되지
않는다). KRX Open API(sto/stk_isu_base_info)의 LIST_DD도 같은 값을 주지만 서비스 승인이
필요해 현재 401이다.

전체 재빌드(build_stock_master.py) 없이 기존 파일을 제자리 패치한다. 멱등.
신규 재빌드는 build_stock_master.py가 같은 소스로 listingDate를 직접 채운다.

Run:
    cd backend && python scripts/backfill_listing_dates.py

data/stock-master.json은 git 추적 파일이고 프로덕션 compose가 ./data를 마운트하므로,
백필 결과를 커밋하면 배포(git pull)로 프로덕션에 자동 반영된다(별도 실행 불필요).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_stock_master import load_kind_listing_dates  # noqa: E402

_MASTER_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "stock-master.json"


def main() -> None:
    if not _MASTER_PATH.exists():
        raise SystemExit(f"{_MASTER_PATH} 없음 — 먼저 build_stock_master.py를 실행하세요.")
    payload = json.loads(_MASTER_PATH.read_text(encoding="utf-8"))
    stocks = payload.get("stocks", [])

    print("[listing-dates] loading FDR KRX-DESC (KIND 상장법인목록)...")
    dates = load_kind_listing_dates()
    print(f"[listing-dates]   {len(dates)} listing dates")
    if not dates:
        raise SystemExit("[listing-dates] 상장일을 하나도 받지 못했습니다 — 중단(기존 파일 유지)")

    filled = 0
    changed = 0
    for s in stocks:
        # 상폐 엔트리의 상장일은 KRX-DELISTING이 준 값이 정본이다(덮어쓰지 않는다).
        if s.get("delistingDate"):
            continue
        new = dates.get(s.get("symbol"))
        if not new:
            continue
        old = s.get("listingDate")
        if old == new:
            continue
        s["listingDate"] = new
        changed += 1
        if old is None:
            filled += 1

    active = [s for s in stocks if not s.get("delistingDate")]
    covered = sum(1 for s in active if s.get("listingDate"))
    payload["counts"] = {
        **payload.get("counts", {}),
        "activeWithListingDate": covered,
    }
    _MASTER_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[listing-dates] wrote {_MASTER_PATH}")
    print(f"[listing-dates]   filled={filled} changed={changed} "
          f"coverage={covered}/{len(active)} active")


if __name__ == "__main__":
    main()
