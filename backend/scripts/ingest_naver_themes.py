"""네이버 금융(finance.naver.com) 업종별·테마별 종목 수집 → data/kg-naver-theme-catalog.json.

사용자 지정 1순위 신뢰 소스(2026-07-27 지시: 관련 종목 검색은 네이버 주식의 업종별·
테마별 종목을 가져온다). 주달 카탈로그(ingest_judal_themes.py)와 같은 **카탈로그
레이어** 스키마이며, 로더(engine/knowledge_graph.py)가 주달보다 먼저 합성한다 —
같은 표기가 겹치면 네이버가 이긴다.

포함 범위(주달과 동일한 기계적 스코프): 산업·기술·원자재 테마 + 업종 분류.
제외: 정치인·인맥, 계절·재해·질병 이벤트, 시장 분류 목록.

기계적 가드(신뢰도와 무관, 시스템 계약):
  ① 정본 가드 — korea-stocks.json에 없는 심볼 드롭
  ② 섹터 어휘 가드 — 이름이 normalize_sector로 해석되는 테마 스킵(섹터 유니버스 담당)
  ③ 테스트 정본 용어 가드 — engine/knowledge_graph.TEST_RESERVED_TERMS 스킵

시드 우선 가드는 폐지(2026-07-27 사용자 지시: 관련 종목은 네이버가 항상 우선) —
시드와 같은 이름의 테마도 수집한다. 스캔 인식은 시드가 계속 이기고(taken),
테마→종목 유니버스는 카탈로그 표기 정합이 시드 직접 엣지보다 우선한다
(engine/knowledge_graph.theme_listed_companies).

실행: cd backend && python3 scripts/ingest_naver_themes.py
재실행 시 전체 재수집 후 덮어쓴다(갱신 절차 — 라이브 편입분도 재수집으로 자연 갱신).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_judal_themes import (  # noqa: E402 — 제외 목록·동의어 규칙 공유(DRY)
    EXCLUDE_EVENT,
    EXCLUDE_MARKET,
    EXCLUDE_PERSON,
    _norm_key,
    make_synonyms,
    strip_paren,
)

from engine.knowledge_graph import TEST_RESERVED_TERMS  # noqa: E402
from engine.naver_theme_live import (  # noqa: E402 — 라이브 편입과 파서·스코프 가드 공유
    DETAIL_URL,
    EXCLUDE_NAME_PATTERNS,
    FETCH_DELAY_S,
    THEME_LIST_URL,
    UPJONG_LIST_URL,
    _fetch,
    parse_group_list,
    parse_group_stocks,
    parse_theme_page_count,
)
from engine.universe_pit import normalize_sector  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT_PATH = BASE_DIR / "data" / "kg-naver-theme-catalog.json"
SEED_PATH = BASE_DIR / "data" / "knowledge-graph.json"
STOCKS_PATH = BASE_DIR / "data" / "korea-stocks.json"


def main() -> None:
    stocks = json.load(open(STOCKS_PATH, encoding="utf-8"))
    master_symbols = {s["symbol"] for s in stocks if isinstance(s, dict) and s.get("symbol")}

    seed = json.load(open(SEED_PATH, encoding="utf-8"))
    seed_terms: set[str] = set()
    for node in seed.get("nodes", []):
        for term in [node.get("name", "")] + list(node.get("synonyms", [])):
            key = _norm_key(term)
            if key:
                seed_terms.add(key)

    first_page = _fetch(THEME_LIST_URL.format(page=1))
    groups: list[dict] = [{**g, "kind": "theme"} for g in parse_group_list(first_page, "theme")]
    for page in range(2, parse_theme_page_count(first_page) + 1):
        time.sleep(FETCH_DELAY_S)
        groups += [
            {**g, "kind": "theme"}
            for g in parse_group_list(_fetch(THEME_LIST_URL.format(page=page)), "theme")
        ]
    time.sleep(FETCH_DELAY_S)
    groups += [
        {**g, "kind": "upjong"}
        for g in parse_group_list(_fetch(UPJONG_LIST_URL), "upjong")
    ]
    print(f"네이버 테마 {sum(g['kind'] == 'theme' for g in groups)}개 · "
          f"업종 {sum(g['kind'] == 'upjong' for g in groups)}개 발견")

    report = {"included": 0, "excluded_scope": [], "skipped_sector_vocab": [],
              "skipped_test_reserved": [], "dropped_symbols": 0, "edge_count": 0}
    catalog_themes: list[dict] = []
    seen_ids: set[str] = set()

    for group in groups:
        name, kind = group["name"], group["kind"]
        theme_id = f"naver-{kind}-{group['no']}"
        if theme_id in seen_ids:
            continue
        seen_ids.add(theme_id)
        base = strip_paren(name)
        if (name in EXCLUDE_PERSON or base in EXCLUDE_PERSON or name in EXCLUDE_EVENT
                or name in EXCLUDE_MARKET or base in EXCLUDE_MARKET
                or EXCLUDE_NAME_PATTERNS.search(name)):
            report["excluded_scope"].append(name)
            continue
        if _norm_key(name) in TEST_RESERVED_TERMS or _norm_key(base) in TEST_RESERVED_TERMS:
            report["skipped_test_reserved"].append(name)
            continue
        if normalize_sector(name) or normalize_sector(base):
            report["skipped_sector_vocab"].append(name)
            continue

        time.sleep(FETCH_DELAY_S)
        pairs = parse_group_stocks(_fetch(DETAIL_URL.format(kind=kind, no=group["no"])))
        kept = [{"symbol": c, "name": n} for c, n in pairs if c in master_symbols]
        report["dropped_symbols"] += len(pairs) - len(kept)
        if not kept:
            continue

        catalog_themes.append({
            "id": theme_id,
            "name": name,
            "kind": "industry" if kind == "upjong" else "theme",
            "synonyms": make_synonyms(name, seed_terms),
            "stocks": kept,
        })
        report["included"] += 1
        report["edge_count"] += len(kept)
        print(f"  [{report['included']:3}] ({kind}) {name} — 종목 {len(kept)}")

    payload = {
        "version": 1,
        "source": "finance.naver.com",
        "source_note": "사용자 지정 1순위 신뢰 소스(2026-07-27) — 네이버 금융 업종별·테마별 "
                       "종목 분류 수집, 개별 검증 생략. 주달 카탈로그보다 먼저 합성된다",
        "retrieved_at": date.today().isoformat(),
        "themes": catalog_themes,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print("\n=== 수집 결과 ===")
    print(f"포함 테마 {report['included']} / 엣지 {report['edge_count']}")
    print(f"제외 — 스코프(인물·이벤트·시장분류) {len(report['excluded_scope'])}: {report['excluded_scope']}")
    print(f"스킵 — 섹터 어휘 {len(report['skipped_sector_vocab'])}: {report['skipped_sector_vocab']}")
    print(f"스킵 — 테스트 정본 용어 {len(report['skipped_test_reserved'])}: {report['skipped_test_reserved']}")
    print(f"정본에 없는 심볼 드롭 {report['dropped_symbols']}")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
