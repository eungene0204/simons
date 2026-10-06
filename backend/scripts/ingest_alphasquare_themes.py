"""알파스퀘어(alphasquare.co.kr) 테마별 종목 수집 → data/kg-alphasquare-theme-catalog.json.

2026-10-06 사용자 지시로 수집한다. 웹 화면이 쓰는 비인증 API(api.alphasquare.co.kr/theme/v2)
를 읽는다. 네이버·주달 카탈로그와 같은 카탈로그 레이어 스키마이며, 로더 연결(합성 순서)은
별도 결정 사항이라 이 스크립트는 파일만 만든다.

가드는 네이버 수집기와 동일하다: 정본 심볼·섹터 어휘·테스트 정본 용어·스코프 제외.
알파스퀘어가 is_old로 표시한 낡은 테마는 수집하지 않는다.

실행: cd backend && python3 scripts/ingest_alphasquare_themes.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
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
from engine.naver_theme_live import FETCH_DELAY_S  # noqa: E402
from engine.universe_pit import normalize_sector  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT_PATH = BASE_DIR / "data" / "kg-alphasquare-theme-catalog.json"
SEED_PATH = BASE_DIR / "data" / "knowledge-graph.json"
STOCKS_PATH = BASE_DIR / "data" / "korea-stocks.json"

API_BASE = "https://api.alphasquare.co.kr/theme/v2"
ALL_THEMES_URL = API_BASE + "/all-themes"
THEME_STOCKS_URL = API_BASE + "/themes/{id}/stocks"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"


def _fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_theme_index(fetch=_fetch_json) -> list[dict]:
    """대분류 아래 테마를 평탄화 — 0개면 API 변경으로 보고 즉시 실패(조용한 고장 방지)."""
    themes = [
        {"id": t["id"], "name": t["name"].strip(), "big_theme": big["name"],
         "is_old": bool(t.get("is_old"))}
        for big in fetch(ALL_THEMES_URL).get("data", [])
        for t in big.get("themes", [])
    ]
    if not themes:
        raise RuntimeError("알파스퀘어 테마 목록이 비었습니다 — API 형식 변경 의심")
    return themes


def fetch_theme_pairs(theme_id: int, fetch=_fetch_json) -> list[tuple[str, str]]:
    return [
        (s["code"], s.get("ko_name") or s.get("cname") or s["code"])
        for s in fetch(THEME_STOCKS_URL.format(id=theme_id))
        if s.get("country_code") == "KR" and s.get("is_alive", True)
    ]


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

    themes = fetch_theme_index()
    print(f"알파스퀘어 테마 {len(themes)}개 발견")

    report = {"included": 0, "excluded_scope": [], "skipped_old": [], "skipped_sector_vocab": [],
              "skipped_test_reserved": [], "dropped_symbols": 0, "edge_count": 0}
    catalog_themes: list[dict] = []
    seen_ids: set[int] = set()

    for theme in themes:
        name = theme["name"]
        if theme["id"] in seen_ids:
            continue
        seen_ids.add(theme["id"])
        base = strip_paren(name)
        if theme["is_old"]:
            report["skipped_old"].append(name)
            continue
        if (name in EXCLUDE_PERSON or base in EXCLUDE_PERSON or name in EXCLUDE_EVENT
                or name in EXCLUDE_MARKET or base in EXCLUDE_MARKET):
            report["excluded_scope"].append(name)
            continue
        if _norm_key(name) in TEST_RESERVED_TERMS or _norm_key(base) in TEST_RESERVED_TERMS:
            report["skipped_test_reserved"].append(name)
            continue
        if normalize_sector(name) or normalize_sector(base):
            report["skipped_sector_vocab"].append(name)
            continue

        time.sleep(FETCH_DELAY_S)
        pairs = fetch_theme_pairs(theme["id"])
        kept = [{"symbol": c, "name": n} for c, n in pairs if c in master_symbols]
        report["dropped_symbols"] += len(pairs) - len(kept)
        if not kept:
            continue

        catalog_themes.append({
            "id": f"alphasquare-theme-{theme['id']}",
            "name": name,
            "kind": "theme",
            "big_theme": theme["big_theme"],
            "synonyms": make_synonyms(name, seed_terms),
            "stocks": kept,
        })
        report["included"] += 1
        report["edge_count"] += len(kept)
        print(f"  [{report['included']:3}] ({theme['big_theme']}) {name} — 종목 {len(kept)}")

    payload = {
        "version": 1,
        "source": "alphasquare.co.kr",
        "source_note": "2026-10-06 사용자 지시 수집 — 알파스퀘어 테마별 종목 분류(비인증 웹 API), "
                       "개별 검증 생략. 로더 합성 순서는 미정(미연결)",
        "retrieved_at": date.today().isoformat(),
        "themes": catalog_themes,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print("\n=== 수집 결과 ===")
    print(f"포함 테마 {report['included']} / 엣지 {report['edge_count']}")
    print(f"스킵 — 낡은 테마(is_old) {len(report['skipped_old'])}: {report['skipped_old']}")
    print(f"제외 — 스코프(인물·이벤트·시장분류) {len(report['excluded_scope'])}: {report['excluded_scope']}")
    print(f"스킵 — 섹터 어휘 {len(report['skipped_sector_vocab'])}: {report['skipped_sector_vocab']}")
    print(f"스킵 — 테스트 정본 용어 {len(report['skipped_test_reserved'])}: {report['skipped_test_reserved']}")
    print(f"정본에 없는 심볼 드롭 {report['dropped_symbols']}")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
