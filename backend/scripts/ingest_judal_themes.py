"""주달(judal.co.kr) 테마→종목 분류 수집 → data/kg-theme-catalog.json 생성.

사용자 지정 신뢰 소스(2026-07-25 지시: 개별 종목 검증 생략, 테마→종목만 수집).
시드(knowledge-graph.json)와 분리된 **카탈로그 레이어** — 로더(engine/knowledge_graph.py)가
시드·학습 다음 순위로 합성하며, Core/Strong 큐레이션 계약은 시드에만 적용된다.

포함 범위(사용자 결정): 산업·기술·원자재 테마 + 그룹주 테마.
제외: 정치인·인물, 계절·재해·질병 이벤트, 시장 분류 목록(ETF·스팩·고배당 등).

기계적 가드(신뢰도와 무관, 시스템 계약):
  ① 정본 가드 — korea-stocks.json에 없는 심볼 드롭
  ② 섹터 어휘 가드 — 이름이 normalize_sector로 해석되는 테마(반도체·로봇 등)는 스킵:
     스캔 인덱스에서 자동 제외돼 도달 불가한 죽은 노드가 된다(섹터 유니버스가 담당)
  ③ 시드 우선 가드 — 시드 노드 이름·동의어와 겹치는 테마 스킵(전고체 배터리·의료AI 등):
     시드=검증된 Core/Strong 큐레이션이 우선한다는 계약(docs/kg_concept_builder.md)
  ④ 테스트 정본 용어 가드 — grounding 테스트가 '그래프 밖 용어'로 쓰는 표현
     (폐배터리·메타버스·위고비 등)은 노드·동의어 금지(가드 ③ 확장, 학습 경로 보존)

실행: cd backend && python3 scripts/ingest_judal_themes.py
재실행 시 전체 재수집 후 덮어쓴다(갱신 절차).
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.universe_pit import normalize_sector  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUT_PATH = BASE_DIR / "data" / "kg-theme-catalog.json"
SEED_PATH = BASE_DIR / "data" / "knowledge-graph.json"
STOCKS_PATH = BASE_DIR / "data" / "korea-stocks.json"

MAIN_URL = "https://www.judal.co.kr/"
THEME_URL = "https://www.judal.co.kr/?view=stockList&themeIdx={idx}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
FETCH_DELAY_S = 0.3

# 제외 목록(사용자 결정 2026-07-25) — 이름은 주달 표기 그대로(종목 수 괄호 제거 후).
EXCLUDE_PERSON = {
    "김경수", "김동연", "김민석", "안철수", "이준석", "오세훈", "한동훈", "홍준표",
    "방탄소년단",
}
EXCLUDE_EVENT = {
    "가을", "겨울", "봄", "여름(폭염)", "태풍(장마)", "지진", "빈대", "괴질",
    "흑사병(페스트)", "독감", "조류독감", "코로나 바이러스", "코로나 진단키트",
    "아프리카 돼지열병", "엠폭스(원숭이두창)", "지카 바이러스", "노로 바이러스",
    "방역관련주", "마스크", "혈장치료", "이버멕틴", "남북경협", "대북주", "개성공단",
    "미중무역전쟁", "한일령", "우크라이나 재건", "네옴시티", "저유가", "환율하락수혜",
    "경기침체(경기방어)", "일자리", "출산장려정책", "세종시", "고속버스터미널 재개발",
    "방사능", "미세먼지",
}
EXCLUDE_MARKET = {
    "ETF", "ETN", "스팩", "MSCI Korea", "밸류업", "고배당", "배당성향 40퍼센트",
    "자사주 소각", "지주사", "지방코스닥기업", "코스닥 퇴출기준", "상장폐지 위험종목",
    "SG증권대량매도", "중국국적주", "미국투자", "인도투자", "일본투자", "중국투자",
    "금은투자",
}

# 소스 원본 오류(사용자 제보 2026-07-25) — 주달 자체가 잘못 만든 테마는 재수집에도 제외.
# '반도체 제품(SOC)': 이름은 반도체 계열인데 종목은 전부 건설사(삼성물산·현대건설 등) —
# 사회간접자본(SOC) 인프라 테마를 반도체 제품(System on Chip) 이름으로 오분류한 원본 오류.
# 건설사는 섹터 유니버스가 이미 커버하고 'SOC' 약어는 반도체와 중의적이라 제거가 안전하다.
EXCLUDE_SOURCE_ERROR = {
    "반도체 제품(SOC)",
}

# 가드 ④ — grounding·빌더 테스트가 '그래프 밖'을 전제하는 정본 용어(_norm_key 기준).
# 여기 있는 표현이 카탈로그 스캔 용어가 되면 검색 학습 경로 테스트가 죽는다.
TEST_RESERVED_TERMS = {
    "그린수소", "폐배터리", "위고비", "마운자로", "메타버스", "cowos", "신조어",
    "반도체소부장", "ess",
}

# 괄호 안 토큰을 동의어로 승격할 때의 일반어 차단 목록(부분 문자열 오폭 방지).
SYNONYM_STOPWORDS = {"차량용", "경구용", "원격", "소재부품", "언택트", "애그플레이션"}


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", "", (text or "")).lower()


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_theme_list(html: str) -> list[dict]:
    pat = re.compile(r'themeIdx=(\d+)"[^>]*>\s*<span>([^<]+?)\((\d+)\)</span>', re.S)
    seen: dict[str, dict] = {}
    for idx, name, count in pat.findall(html):
        seen.setdefault(idx, {"idx": int(idx), "name": name.strip(), "count": int(count)})
    return list(seen.values())


def parse_theme_stocks(html: str) -> list[tuple[str, str]]:
    pat = re.compile(r'code=(\d{6})"[^>]*>\s*<b[^>]*>([^<]+)</b>', re.S)
    out, seen = [], set()
    for code, name in pat.findall(html):
        if code not in seen:
            seen.add(code)
            out.append((code, name.strip()))
    return out


def strip_paren(name: str) -> str:
    return re.sub(r"\([^)]*\)", "", name).strip()


def paren_tokens(name: str) -> list[str]:
    tokens: list[str] = []
    for inner in re.findall(r"\(([^)]*)\)", name):
        tokens.extend(t.strip() for t in inner.split("/") if t.strip())
    return tokens


def make_synonyms(name: str, seed_terms: set[str]) -> list[str]:
    """괄호 토큰만 동의어로 — 라틴/숫자 포함 또는 한글 4자 이상, 가드 통과분."""
    synonyms = []
    for token in paren_tokens(name):
        key = _norm_key(token)
        if len(key) < 2 or key in TEST_RESERVED_TERMS or key in seed_terms:
            continue
        if token in SYNONYM_STOPWORDS or normalize_sector(token):
            continue
        if not (re.search(r"[a-zA-Z0-9]", token) or len(token.replace(" ", "")) >= 4):
            continue
        synonyms.append(token)
    return synonyms


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

    themes = parse_theme_list(_fetch(MAIN_URL))
    print(f"주달 테마 {len(themes)}개 발견")

    report = {"included": 0, "excluded_person": 0, "excluded_event": 0,
              "excluded_market": 0, "excluded_source_error": 0,
              "skipped_sector_vocab": [], "skipped_seed_dup": [],
              "skipped_test_reserved": [], "dropped_symbols": 0, "edge_count": 0}
    catalog_themes: list[dict] = []

    for theme in sorted(themes, key=lambda t: t["idx"]):
        name = theme["name"]
        base = strip_paren(name)
        if name in EXCLUDE_PERSON or base in EXCLUDE_PERSON:
            report["excluded_person"] += 1
            continue
        if name in EXCLUDE_EVENT:
            report["excluded_event"] += 1
            continue
        if name in EXCLUDE_MARKET or base in EXCLUDE_MARKET:
            report["excluded_market"] += 1
            continue
        if name in EXCLUDE_SOURCE_ERROR:
            report["excluded_source_error"] += 1
            continue
        if _norm_key(name) in TEST_RESERVED_TERMS or _norm_key(base) in TEST_RESERVED_TERMS:
            report["skipped_test_reserved"].append(name)
            continue
        if normalize_sector(name) or normalize_sector(base):
            report["skipped_sector_vocab"].append(name)
            continue
        if _norm_key(name) in seed_terms or _norm_key(base) in seed_terms:
            report["skipped_seed_dup"].append(name)
            continue

        html = _fetch(THEME_URL.format(idx=theme["idx"]))
        time.sleep(FETCH_DELAY_S)
        pairs = parse_theme_stocks(html)
        kept = [{"symbol": c, "name": n} for c, n in pairs if c in master_symbols]
        report["dropped_symbols"] += len(pairs) - len(kept)
        if not kept:
            continue

        is_group = "그룹" in name
        catalog_themes.append({
            "id": f"judal-{theme['idx']}",
            "name": name,
            "kind": "group" if is_group else "industry",
            "synonyms": make_synonyms(name, seed_terms),
            "stocks": kept,
        })
        report["included"] += 1
        report["edge_count"] += len(kept)
        print(f"  [{report['included']:3}] {name} — 종목 {len(kept)}")

    payload = {
        "version": 1,
        "source": "judal.co.kr",
        "source_note": "사용자 지정 신뢰 소스(2026-07-25) — 테마→종목 분류만 수집, 개별 검증 생략. "
                       "시드(Core/Strong 큐레이션)와 분리된 카탈로그 레이어",
        "retrieved_at": date.today().isoformat(),
        "themes": catalog_themes,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print("\n=== 수집 결과 ===")
    print(f"포함 테마 {report['included']} / 엣지 {report['edge_count']}")
    print(f"제외 — 인물 {report['excluded_person']} · 이벤트 {report['excluded_event']}"
          f" · 시장분류 {report['excluded_market']} · 소스오류 {report['excluded_source_error']}")
    print(f"스킵 — 섹터 어휘 {len(report['skipped_sector_vocab'])}: {report['skipped_sector_vocab']}")
    print(f"스킵 — 시드 중복 {len(report['skipped_seed_dup'])}: {report['skipped_seed_dup']}")
    print(f"스킵 — 테스트 정본 용어 {len(report['skipped_test_reserved'])}: {report['skipped_test_reserved']}")
    print(f"정본에 없는 심볼 드롭 {report['dropped_symbols']}")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
