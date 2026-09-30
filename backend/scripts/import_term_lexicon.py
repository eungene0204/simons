"""파일 어휘집 → 공유 DB(TermLexiconEntry) 가져오기 — 1회 이관·검수 항목 편입용.

학습 어휘집의 정본은 공유 DB다(engine/lexicon_store, 2026-09-30). 종전 파일
(data/term_lexicon.json)은 환경마다 따로 자라 잡음(QA 입력 학습분)이 섞여 있으므로
**검수한 키만** 골라 넣는다(--keys). 병합 규칙은 lexicon_store.merge_entry:
기존 DB 항목이 기준, 기존 pending만 들어온 verified로 승격, 반려(rejected) 유지.

용법(백엔드 루트, DATABASE_URL=공유 DB):
  python3 scripts/import_term_lexicon.py --file /path/term_lexicon.json --dry-run
  python3 scripts/import_term_lexicon.py --file /path/term_lexicon.json --keys bts,블랙핑크
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="파일 어휘집 → 공유 DB 가져오기")
    ap.add_argument("--file", required=True, type=Path, help="가져올 term_lexicon.json")
    ap.add_argument("--keys", default=None, help="쉼표로 구분한 키(생략=파일 전체)")
    ap.add_argument("--dry-run", action="store_true", help="바뀔 내용만 출력")
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    from engine import lexicon_store

    if not lexicon_store.uses_db(lexicon_store.DEFAULT_PATH):
        print("[import] 공유 DB 저장소가 아니다(DATABASE_URL·TERM_LEXICON_STORE 확인)")
        return 2

    source = json.loads(args.file.read_text(encoding="utf-8"))
    keys = [k.strip() for k in args.keys.split(",")] if args.keys else list(source)
    missing = [k for k in keys if k not in source]
    if missing:
        print(f"[import] 파일에 없는 키: {missing}")
        return 2

    current = lexicon_store.snapshot()
    for key in keys:
        before = current.get(key)
        after = lexicon_store.merge_entry(before, source[key])
        if after == before:
            print(f"  = {key}")
            continue
        verified = sum(1 for e in after.get("edges", []) if e.get("status") == "verified")
        print(f"  {'+' if before is None else '~'} {key}  sector={after.get('sector')} "
              f"verified_edges={verified}")
        if not args.dry_run:
            lexicon_store.save_entry(lexicon_store.DEFAULT_PATH, key, after)
    print(f"[import] {'dry-run ' if args.dry_run else ''}완료 — {len(keys)}개 키")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
