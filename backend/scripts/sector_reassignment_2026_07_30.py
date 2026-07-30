"""섹터 재귀속 판정 (2026-07-30) — 3자 교차 검증 불일치 96건 일괄 처리.

`audit_sector_sources.py`가 낸 "현행 ≠ DART 코드" 불일치를 종목마다 판정한다.
코드가 항상 옳지 않으므로 자동 적용하지 않는다.

  APPLY  코드가 맞다 → 소속을 코드 값으로 바꾼다(korea-stocks.json + 오버레이 재생성)
  KEEP   코드가 틀렸다 → 현행 유지 + OVERRIDDEN_SYMBOLS 등록
         (등록해야 감사 리포트가 깨끗해진다 — 안 하면 다음 사람이 같은 판정을 반복한다)

판정은 **전이 유형(현행 → 코드) 단위 규칙**과 **개별 예외**로 표현한다. 심볼을 손으로
나열하면 오기가 난다(첫 시도에서 32건을 잘못 적었다) — 규칙은 실데이터에 적용해 검증된다.

    python backend/scripts/sector_reassignment_2026_07_30.py [--apply]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

KOREA_STOCKS = REPO / "data" / "korea-stocks.json"

# ── KEEP: 코드가 틀린 전이 유형 ───────────────────────────────────────────────
# (현행, 코드) 쌍 → 사유. 이 전이는 코드를 따르면 퇴행한다.
KEEP_TRANSITIONS: dict[tuple[str, str], str] = {
    # 로봇: KSIC에 산업용 로봇 코드(2928)가 있지만 등록한 상장사가 거의 없어 대부분
    # 292(일반 기계) 등으로 흩어진다 — 코드를 따르면 로봇 유니버스가 비어버린다.
    ("로봇", "기계/장비"): "로봇 — KSIC 2928 미등록(292 등으로 흩어짐). 사명 기준 분류 유지",
    ("로봇", "의료기기"): "수술·재활 로봇 — 로봇 전문기업으로 유지",
    ("로봇", "IT 하드웨어"): "로봇 전문기업 — 등록 업종이 하드웨어로 잡혔을 뿐",
    ("로봇", "소프트웨어"): "로봇 SW 전문기업 — 로봇으로 유지",
    ("로봇", "유통/상사"): "로봇 전문기업 — 등록 업종이 도매로 잡혔을 뿐",
    # 리츠: 등록 업종은 신탁업(642)이지만 부동산 간접투자 상품이다.
    ("부동산", "증권"): "리츠(REIT) — 등록 업종은 신탁업이나 부동산 유니버스가 맞다",
    # 창투사·벤처캐피탈: 649는 '기타 금융업'이라 지주사와 섞인다. 금융투자업이 맞다.
    ("증권", "지주회사"): "창투사·벤처캐피탈 — 649가 지주사와 섞인 코드. 금융투자업 유지",
    # 반도체 장비: 우리 체계엔 장비 전용 섹터가 없고, 네이버도 '반도체와반도체장비'로 묶는다.
    ("반도체", "기계/장비"): "반도체 장비 제조사 — 장비 전용 섹터 없음(네이버도 반도체와 묶음)",
    # 사업지주: 지주 구조로 등록됐지만 사업을 직접 한다 — 사업 섹터에 둔다.
    ("조선", "지주회사"): "조선 사업지주 — 사업 섹터 유지(분할 시 이미 조선으로 판정)",
    ("화학", "지주회사"): "사업지주 — 실제 사업(소재 제조)이 있어 사업 섹터 유지",
    ("에너지/원자력", "지주회사"): "사업회사 — 등록만 지주 구조",
    # 출판업으로 등록된 교육기업.
    ("교육", "미디어/엔터"): "교육기업 — 등록 업종이 서적출판(5811)일 뿐. 네이버도 교육서비스",
}

# ── 개별 예외 (전이 규칙보다 우선) ────────────────────────────────────────────
# 사명으로 판정한 종목명 키(심볼 오기 방지 — 실행 시 실데이터로 검증된다).
KEEP_BY_NAME: dict[str, str] = {
    # 코드가 화학(204)이지만 경피약물전달(마이크로니들) 제약이다.
    "라파스": "마이크로니들 경피약물전달 — 제약에 가깝다. 원료·소재 경계로 화학 유지",
    # 화장품 원료사 — 납품처가 화장품일 뿐 사업은 화학(분할 시 정한 경계).
    "엔에프씨": "화장품 원료·소재사 — 화학 유지(분할 시 정한 경계)",
}
# 코드도 현행도 아닌 제3의 답이 맞는 경우.
CUSTOM_BY_NAME: dict[str, tuple[str, str]] = {
    # 현행 화학 / 코드 화장품 — 둘 다 아니다. 아모레퍼시픽이 별도 상장된 순수지주다.
    "아모레퍼시픽홀딩스": ("지주회사", "순수지주 — 사업회사(아모레퍼시픽)가 별도 상장"),
}
APPLY_BY_NAME: dict[str, str] = {
    # 역방향 — 코드가 맞고 현행이 틀렸다. 사명에 '로봇/로보'가 없어 사명 규칙에도 안 걸렸다.
    "에스피시스템스": "KSIC 29280 산업용 로봇으로 정확히 등록 — 로봇이 맞다",
    # 사명에 '로보틱스'가 있어 로봇이 됐으나 등록 업종은 화학이다.
    "해성에어로보틱스": "등록 업종 화학(259) — 사명 '로보틱스'로 잘못 잡혔다",
}


def decide(candidate: dict) -> tuple[str, str]:
    name = candidate["name"]
    if name in CUSTOM_BY_NAME:
        target, reason = CUSTOM_BY_NAME[name]
        candidate["code_says"] = target   # 적용 대상을 제3의 답으로 바꾼다
        return "APPLY", f"[CUSTOM] {reason}"
    if name in KEEP_BY_NAME:
        return "KEEP", KEEP_BY_NAME[name]
    if name in APPLY_BY_NAME:
        return "APPLY", APPLY_BY_NAME[name]
    key = (candidate["current"], candidate["code_says"])
    if key in KEEP_TRANSITIONS:
        return "KEEP", KEEP_TRANSITIONS[key]
    # 나머지는 코드가 맞다 — 대부분 사명 부분 문자열 오매칭의 피해자
    # ('바이오'·'에너지'·'반도체'가 사명에 있어 그 섹터로 배정됐다).
    return "APPLY", f"등록 업종({candidate['code']}) 기준"


def load_candidates() -> list[dict]:
    from engine.ksic_sectors import sector_for_code
    from engine.sector_mapper import OVERRIDDEN_SYMBOLS

    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]
    dart = json.loads((REPO / "data" / "dart-industry.json").read_text(encoding="utf-8"))
    out = []
    for row in rows:
        symbol = row["symbol"]
        if symbol in OVERRIDDEN_SYMBOLS:
            continue
        code = (dart.get(symbol, {}) or {}).get("induty_code") or ""
        by_code = sector_for_code(code)
        if by_code and by_code != row.get("sector"):
            out.append({
                "symbol": symbol, "name": row.get("name") or symbol,
                "current": row.get("sector"), "code_says": by_code, "code": code,
            })
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    candidates = load_candidates()
    decisions = {c["symbol"]: (c, *decide(c)) for c in candidates}
    applies = {s: v for s, v in decisions.items() if v[1] == "APPLY"}
    keeps = {s: v for s, v in decisions.items() if v[1] == "KEEP"}

    # 사명 키가 실데이터에 없으면 오기이거나 이미 적용된 것이다. 재실행(멱등)을 막지
    # 않도록 경고만 한다 — APPLY/CUSTOM 판정은 반영되면 후보에서 빠지는 게 정상이다.
    names = {c["name"] for c in candidates}
    absent = (set(KEEP_BY_NAME) | set(APPLY_BY_NAME) | set(CUSTOM_BY_NAME)) - names
    if absent:
        print(f"ℹ 후보에 없는 판정 {len(absent)}건(이미 적용됐거나 오기): {sorted(absent)}")

    print(f"불일치 {len(candidates)}건 → APPLY {len(applies)} / KEEP {len(keeps)}")
    print("\n=== APPLY (소속 변경) ===")
    for _s, (c, _d, reason) in sorted(applies.items(), key=lambda x: x[1][0]["name"]):
        print(f"  {c['name']:<18} {c['current']:<12} → {c['code_says']:<12} {reason}")
    print("\n=== KEEP (현행 유지 + 예외 등록) ===")
    tally: collections.Counter = collections.Counter()
    for _s, (c, _d, reason) in keeps.items():
        tally[reason] += 1
    for reason, count in tally.most_common():
        print(f"  {count:3d}  {reason}")

    if not args.apply:
        print("\n[dry-run] 실제 적용은 --apply")
        return 0

    # ① APPLY — korea-stocks.json 캐시 갱신(정본 오버레이는 이걸 읽어 재생성한다)
    payload = json.loads(KOREA_STOCKS.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]
    changed = 0
    for row in rows:
        hit = applies.get(row.get("symbol"))
        if hit:
            row["sector"] = hit[0]["code_says"]
            changed += 1
    KOREA_STOCKS.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n✅ {changed}종목 소속 변경 (korea-stocks.json)")

    # ② KEEP — OVERRIDDEN_SYMBOLS 등록용 코드 조각 출력(손으로 붙인다: 사유가 코드 주석이다)
    print("\n=== sector_mapper.OVERRIDDEN_SYMBOLS에 추가할 항목 ===")
    for _s, (c, _d, reason) in sorted(keeps.items(), key=lambda x: (x[1][0]["current"], x[1][0]["name"])):
        print(f'    "{c["symbol"]}": "{c["current"]}",  # {c["name"]} — {reason}')
    print("\n다음: build_sector_membership.py --apply 로 정본 오버레이 재생성")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
