"""
Build data/kospi200-cache.json and data/kosdaq150-cache.json — 지수 구성종목 명부.

출처는 KIS 종목마스터 하나로 통일한다(engine/kis_master.py). 과거 KOSPI200 명부는
네이버 스크래핑으로 만들었는데, 21페이지를 훑어야 하고 영숫자 신규 상장 코드를
누락해 수동 보정 목록(_KOSPI200_SUPPLEMENTAL_SYMBOLS)을 달고 있었다. KIS 마스터는
두 지수를 모두 담고 영숫자 코드도 포함해 보정이 필요 없다.

명부 형식은 기존 kospi200-cache.json 과 동일한 {fetched_at, symbols} —
engine/live_signal_utils.resolve_live_universe(자동매매)와
engine/strategy_converter._load_universe(백테스트)가 같은 파일을 읽는다.

검증(종목 수·코드 형식·시장 소속)에 실패하면 해당 지수 파일을 쓰지 않는다.

야간 동기화(scripts/sync_data.py)가 매일 부른다(2026-09-21) — 명부가 매일 새로워지고, 그날의
명단이 시점별 명단 이력(data/index-membership)에 덧붙는다.

Run:
    cd backend && python scripts/build_index_rosters.py

Idempotent. Network-bound (KIS 마스터 다운로드).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.index_membership import record_observed_roster
from engine.kis_master import INDEX_SPECS, MasterLayoutError, fetch_index_members

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_OUT_NAMES = {"kospi200": "kospi200-cache.json", "kosdaq150": "kosdaq150-cache.json"}


def main() -> None:
    failures = []
    for index_id in INDEX_SPECS:
        out_path = _DATA_DIR / _OUT_NAMES[index_id]
        print(f"[{index_id}] KIS 종목마스터 조회 중...")
        try:
            members = fetch_index_members(index_id)
        except (MasterLayoutError, OSError) as error:
            print(f"[{index_id}] 실패 — 파일을 쓰지 않는다: {error}")
            failures.append(index_id)
            continue

        symbols = sorted(symbol for symbol, _ in members)
        out_path.write_text(
            json.dumps({"fetched_at": time.time(), "symbols": symbols}, ensure_ascii=False),
            encoding="utf-8",
        )
        # 시점별 명단 이력에 오늘의 관측을 덧붙인다 — 직전 명단과 다르면 오늘 날짜의 편입·편출이 된다
        # (과거분은 KRX 수집기, 그 뒤는 이 일일 관측 — engine/index_membership.py).
        change = record_observed_roster(index_id, symbols, time.strftime("%Y-%m-%d"))
        if change:
            print(f"[{index_id}] 구성 변경 기록 — 편입 {change['added']} · 편출 {change['removed']}")
        preview = ", ".join(f"{symbol}({name})" for symbol, name in members[:4])
        print(f"[{index_id}] {len(symbols)}종목 저장 → {out_path}")
        print(f"[{index_id}] 샘플: {preview} ...")

    if failures:
        raise SystemExit(f"실패한 지수: {', '.join(failures)}")


if __name__ == "__main__":
    main()
