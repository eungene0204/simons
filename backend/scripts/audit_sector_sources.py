"""섹터 분류 3자 교차 검증 — 현재 배정 / DART 업종코드 / 네이버 업종.

세 소스가 서로 다른 종목을 드러낸다. 어느 하나가 항상 옳지는 않다:
  · 현재 배정  — 사람 손이 들어간 최종값(OVERRIDDEN_SYMBOLS 포함)
  · DART 코드  — 등록 주업종. 구조화돼 있어 문자열 사고가 없지만 실제 주력과 다를 수 있다
                 (삼성전자=264 통신·방송장비)
  · 네이버      — GICS식 분류. 커버리지 61%지만 실사업에 가깝다(대한항공='항공사')

세 소스가 갈리는 종목이 검토 대상이다. 자동으로 고치지 않는다 — 목록만 낸다.

    python backend/scripts/audit_sector_sources.py [--only-disagree]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from engine.ksic_sectors import sector_for_code  # noqa: E402
from engine.sector_mapper import OVERRIDDEN_SYMBOLS  # noqa: E402


def load() -> tuple[dict, dict, dict, dict]:
    payload = json.loads((REPO / "data" / "korea-stocks.json").read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload["stocks"]
    current = {s["symbol"]: s.get("sector") for s in rows}
    names = {s["symbol"]: s.get("name") for s in rows}

    dart_path = REPO / "data" / "dart-industry.json"
    dart = json.loads(dart_path.read_text(encoding="utf-8")) if dart_path.exists() else {}
    codes = {k: (v.get("induty_code") or "") for k, v in dart.items()}

    naver: dict[str, str] = {}
    cat = REPO / "data" / "kg-naver-theme-catalog.json"
    if cat.exists():
        for theme in json.loads(cat.read_text(encoding="utf-8"))["themes"]:
            if theme.get("kind") == "industry":
                for stock in theme.get("stocks", []):
                    naver.setdefault(stock["symbol"], theme["name"])
    return current, names, codes, naver


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-disagree", action="store_true", help="불일치만 출력")
    args = parser.parse_args()

    current, names, codes, naver = load()
    rows = []
    for symbol, sector in current.items():
        code = codes.get(symbol, "")
        by_code = sector_for_code(code)
        rows.append((symbol, names.get(symbol), sector, by_code, code, naver.get(symbol)))

    have_code = [r for r in rows if r[3]]
    agree = [r for r in have_code if r[2] == r[3]]
    disagree = [r for r in have_code if r[2] != r[3]]
    overridden = [r for r in disagree if r[0] in OVERRIDDEN_SYMBOLS]
    review = [r for r in disagree if r[0] not in OVERRIDDEN_SYMBOLS]

    print(f"전체 {len(rows)}종목")
    print(f"  DART 코드 보유       {len(have_code)} ({100*len(have_code)/len(rows):.0f}%)")
    print(f"  네이버 업종 보유      {sum(1 for r in rows if r[5])}")
    print(f"  코드와 일치          {len(agree)}")
    print(f"  코드와 불일치        {len(disagree)}  (의도적 오버라이드 {len(overridden)} / 검토 대상 {len(review)})")

    if not args.only_disagree:
        print()
        by_transition = collections.Counter(f"{r[2]} → {r[3]}" for r in review)
        print("=== 검토 대상 전이 유형 ===")
        for key, count in by_transition.most_common():
            print(f"  {count:3d}  {key}")

    print()
    print("=== 검토 대상 상세 (현재 ≠ 코드, 오버라이드 아님) ===")
    print(f"{'종목':<16}{'현재':<14}{'DART코드':<14}{'코드':<7}네이버")
    print("-" * 84)
    for _sym, name, cur, by_code, code, nv in sorted(review, key=lambda r: (r[2] or "", r[1] or "")):
        print(f"{(name or ''):<16}{(cur or '-'):<14}{by_code:<14}{code:<7}{nv or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
