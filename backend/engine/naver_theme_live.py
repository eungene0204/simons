"""네이버 금융 테마·업종 라이브 조회 → 카탈로그(KG) 편입 — KG 미스 용어의 1순위 검색.

사용자 지시(2026-07-27): "우리 KG에 없으면 네이버를 항상 우선 검색해서 KG에 넣어줘" —
검색 그라운딩(뉴스 API 학습)보다 먼저 네이버 금융 업종·테마 분류에서 표기 정합을 찾고,
정합 시 해당 테마·수록 종목을 data/kg-naver-theme-catalog.json에 편입한다. 그래프는
mtime 캐시로 즉시 재로드되므로 이후 같은 용어는 카탈로그 스캔이 결정적으로 해석한다.

배치 수집(scripts/ingest_naver_themes.py)과 목록·상세 파서를 공유한다(이 모듈이 정의,
스크립트가 임포트). 의미 해석이 아니라 표기 정합이다 — 입력은 결정적 추출 또는 LLM이
뽑은 짧은 용어 문자열이며(자연어 해석 구조 원칙), 매칭은 정규화 키 정확 일치만 한다
(부분·접두 매칭 금지 — 복합 테마구 오확정 가드와 동일 원칙).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

from engine.console_logging import console_logger

logger = console_logger(__name__, "KG-NAVER")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = _BASE_DIR / "data" / "kg-naver-theme-catalog.json"

THEME_LIST_URL = "https://finance.naver.com/sise/theme.naver?&page={page}"
UPJONG_LIST_URL = "https://finance.naver.com/sise/sise_group.naver?type=upjong"
DETAIL_URL = "https://finance.naver.com/sise/sise_group_detail.naver?type={kind}&no={no}"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
FETCH_DELAY_S = 0.2

# 네이버 표기의 인물·이벤트 테마 스코프 제외(인물·정치·선거·재해·질병) 결정적 키워드 가드 —
# 배치 수집과 라이브 편입이 같은 스코프 계약을 지키게 여기서 정의한다.
EXCLUDE_NAME_PATTERNS = re.compile(
    r"인맥|정치|선거|대선|월드컵|올림픽|코로나|독감|엠폭스|장마|폭염|황사|지진"
)


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("euc-kr", errors="ignore")  # 네이버 금융은 EUC-KR


def parse_group_list(html: str, kind: str) -> list[dict]:
    """목록 페이지에서 (no, 이름) 추출 — kind는 'theme'|'upjong'."""
    pat = re.compile(
        rf'href="/sise/sise_group_detail\.naver\?type={kind}&no=(\d+)"[^>]*>([^<]+)</a>'
    )
    seen: dict[str, dict] = {}
    for no, name in pat.findall(html):
        seen.setdefault(no, {"no": int(no), "name": name.strip()})
    return list(seen.values())


def parse_theme_page_count(html: str) -> int:
    pages = re.findall(r"theme\.naver\?[^\"]*page=(\d+)", html)
    return max((int(p) for p in pages), default=1)


def parse_group_stocks(html: str) -> list[tuple[str, str]]:
    """상세 페이지의 종목 (코드, 이름) — 차트 링크(텍스트 없는 앵커)는 자연 제외."""
    pat = re.compile(r'href="/item/main\.naver\?code=(\d{6})"[^>]*>([^<]+)</a>')
    out, seen = [], set()
    for code, name in pat.findall(html):
        if code not in seen:
            seen.add(code)
            out.append((code, name.strip()))
    return out


def strip_paren(name: str) -> str:
    return re.sub(r"\([^)]*\)", "", name).strip()


def fetch_group_index(fetch=_fetch) -> list[dict]:
    """네이버 금융 테마(전 페이지)+업종 목록 — [{no, name, kind}]."""
    first_page = fetch(THEME_LIST_URL.format(page=1))
    groups = [{**g, "kind": "theme"} for g in parse_group_list(first_page, "theme")]
    for page in range(2, parse_theme_page_count(first_page) + 1):
        time.sleep(FETCH_DELAY_S)
        groups += [
            {**g, "kind": "theme"}
            for g in parse_group_list(fetch(THEME_LIST_URL.format(page=page)), "theme")
        ]
    time.sleep(FETCH_DELAY_S)
    groups += [
        {**g, "kind": "upjong"}
        for g in parse_group_list(fetch(UPJONG_LIST_URL), "upjong")
    ]
    return groups


def _group_match_keys(name: str) -> set[str]:
    """분류 이름의 결정적 표기 변형 키 — 원명·괄호 제거 본체·슬래시 병기 변형."""
    from engine.knowledge_graph import _norm_key, _slash_aliases

    base = strip_paren(name)
    keys = {_norm_key(name), _norm_key(base)}
    for alias in _slash_aliases(name) + _slash_aliases(base):
        keys.add(_norm_key(alias))
    return {k for k in keys if len(k) >= 2}


def fetch_group_stocks(group: dict, fetch=None) -> list[dict]:
    """분류 상세 페이지의 수록 종목(정본 필터 후) — [{"symbol","name"}]. 수집 실패는 빈 목록."""
    from engine.knowledge_graph import _stock_names

    fetch = fetch or _fetch
    try:
        time.sleep(FETCH_DELAY_S)
        pairs = parse_group_stocks(fetch(DETAIL_URL.format(kind=group["kind"], no=group["no"])))
    except Exception:  # noqa: BLE001 — 상세 실패 분류만 건너뛴다
        logger.info("네이버 분류 상세 수집 실패: %s(no=%s)", group["name"], group["no"], exc_info=True)
        return []
    master_symbols = set(_stock_names())
    return [{"symbol": c, "name": n} for c, n in pairs if c in master_symbols]


def lookup_and_ingest(
    term: str, catalog_path: Path | None = None, fetch=None,
    groups: list[dict] | None = None,
) -> bool:
    """용어와 표기가 정합하는 네이버 금융 테마·업종을 찾아 카탈로그에 편입한다.

    반환 True = 1개 이상 편입(그래프가 즉시 인식) / False = 정합 없음·수집 실패.
    실패는 호출부의 기존 체인(검색 그라운딩 학습)으로 조용히 폴백한다.
    groups는 미리 수집한 분류 목록(fetch_group_index 결과) — 호출부가 학습 레인과
    목록 수집을 공유할 때 넘긴다(없으면 여기서 수집)."""
    from engine.knowledge_graph import TEST_RESERVED_TERMS, _norm_key

    key = _norm_key(term)
    if len(key) < 2 or key in TEST_RESERVED_TERMS:
        return False
    fetch = fetch or _fetch
    if groups is None:
        try:
            groups = fetch_group_index(fetch)
        except Exception:  # noqa: BLE001 — 수집 실패는 기존 검색 학습 체인으로 폴백
            logger.info("네이버 분류 조회 실패(용어=%r) — 검색 학습 체인으로 폴백", term, exc_info=True)
            return False

    matches = [
        g for g in groups
        if key in _group_match_keys(g["name"]) and not EXCLUDE_NAME_PATTERNS.search(g["name"])
    ]
    if not matches:
        logger.info("네이버 분류 정합 없음: 용어=%r (분류 %d개 대조)", term, len(groups))
        return False

    entries: list[dict] = []
    for group in matches:
        kept = fetch_group_stocks(group, fetch=fetch)
        if not kept:
            continue
        synonyms = [term] if _norm_key(group["name"]) != key else []
        entries.append({
            "id": f"naver-{group['kind']}-{group['no']}",
            "name": group["name"],
            "kind": "industry" if group["kind"] == "upjong" else "theme",
            "synonyms": synonyms,
            "stocks": kept,
        })
    if not entries:
        return False
    _append_to_catalog(entries, catalog_path or CATALOG_PATH)
    logger.info(
        "네이버 분류 편입: 용어=%r → %s",
        term,
        ", ".join(f"{e['name']}(종목 {len(e['stocks'])})" for e in entries),
    )
    return True


def _append_to_catalog(entries: list[dict], path: Path) -> None:
    """카탈로그 파일에 새 테마를 병합 저장(같은 id는 최신 수집분으로 교체)."""
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        catalog = {
            "version": 1, "source": "finance.naver.com",
            "source_note": "라이브 편입 시작분 — 배치 수집(ingest_naver_themes.py) 전 최초 생성",
            "retrieved_at": date.today().isoformat(), "themes": [],
        }
    new_ids = {e["id"] for e in entries}
    themes = [t for t in catalog.get("themes", []) if t.get("id") not in new_ids]
    catalog["themes"] = themes + entries
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
