"""미국 투자 지식그래프(US KG) — 시드+카탈로그 합성, 테마어 → 구성 티커 registry.

한국 KG(engine/knowledge_graph.py)와 같은 구조 원칙을 따른다:

- **입력은 LLM이 추출한 짧은 테마어다**(사용자 원문이 아님 — 자연어 해석 구조 원칙).
  원문 문장 스캔은 없다. US 레인은 LLM-first라 원문을 읽는 소비자 자체가 없다.
- **합성 로드(정본 두 번 안 적기)**: 시드 `data/us-knowledge-graph.json`(큐레이션
  그래프 — 노드·엣지·동의어) + 테마 카탈로그 `data/us-theme-catalog.json`(평면
  테마→티커 목록) + GICS 업종 레이어(us-stocks.json의 섹터 11·산업 253 분류를
  소속 엣지로 — 전 종목 등재, 콘솔 탐색·향후 GICS 필터 기반이며 테마 해석 불참)
  + 학습 오버레이 `data/us-term-lexicon.json`(us_term_grounding이 SEC 공시 전문검색으로
  학습한 테마어 — verified 구성만 합성, pending은 콘솔 승인 대기).
  같은 별칭이 겹치면 시드(큐레이션)가 이긴다 — 한국 KG의 시드>카탈로그 삽입 순서
  계약과 동일하고, 학습분은 그 아래(시드 > 카탈로그 > 학습).
- **company:TICKER 자동 노드**: us-stocks.json·us-etf-master.json 정본에서 참조 시
  생성. 시드의 정본 밖 티커는 issues로 fail-fast(무결성 테스트가 0을 단언),
  카탈로그의 정본 밖 티커는 조용히 스킵(한국 카탈로그 로더 계약과 동일).
- **mtime 캐시**: 데이터 파일이 바뀌면 다음 조회에서 재로드.

한국 KG 대비 의도적 부재(미국엔 해당 소스·소비자가 없다):
- 문장 스캔(find_concepts) — 원문을 읽는 KR nl_parser 경로가 US엔 없음
- 섹터 해석(resolve_sector) — 미국 GICS 업종 필터 자체가 미지원
- 지분 엣지 — DART 타법인출자현황이 KR 전용
"""

from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# 조회 로그가 dev/운영 콘솔에 항상 보이게 전용 핸들러를 단다(한국 KG와 동일 관례).
from engine.console_logging import console_logger
from engine.knowledge_graph import EDGE_TYPES

logger = console_logger("us_knowledge_graph", "US-KG")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 레포 루트(data/의 부모)
_SEED_PATH = _BASE_DIR / "data" / "us-knowledge-graph.json"
_CATALOG_PATH = _BASE_DIR / "data" / "us-theme-catalog.json"
_STOCKS_PATH = _BASE_DIR / "data" / "us-stocks.json"
_ETF_PATH = _BASE_DIR / "data" / "us-etf-master.json"
_LEXICON_PATH = _BASE_DIR / "data" / "us-term-lexicon.json"  # 공시 검색 학습 원장

# 상장사로 전개되는 관계 타입 — 한국 KG listed_companies와 같은 계약(직접 엣지만).
_COMPANY_EDGE_TYPES = frozenset({
    "produced_by", "manufactured_by", "supplier", "customer",
    "related_company", "invests_in",
})

# 시장 한정어 접두 — "미국 사이버보안"의 '미국'은 테마 정체성이 아니다.
_MARKET_PREFIX = "미국"

# GICS 섹터 11종 한글 표기 — us-stocks.json의 sector 값이 정본(영문), 표기만 병기.
_GICS_SECTOR_KR = {
    "Energy": "에너지",
    "Materials": "소재",
    "Industrials": "산업재",
    "Consumer Discretionary": "임의소비재",
    "Consumer Staples": "필수소비재",
    "Health Care": "헬스케어",
    "Financials": "금융",
    "Information Technology": "정보기술",
    "Communication Services": "커뮤니케이션서비스",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
}


def _norm_key(text: str) -> str:
    """별칭 정규화 키 — 공백 제거·소문자. 정확 일치 전용(부분 매칭은 오폭원)."""
    return (text or "").strip().lower().replace(" ", "")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


class USKnowledgeGraph:
    """읽기 전용 그래프 뷰. 로드 시점에 시드+정본+카탈로그를 합성한다."""

    def __init__(self, nodes: dict[str, dict], edges: list[dict], issues: list[str]):
        self.nodes = nodes            # id → node dict
        self.edges = edges            # {source, type, target, note?}
        self.issues = issues          # 검증 경고(시드 무결성 테스트가 빈 목록을 단언)
        self._out: dict[str, list[dict]] = {}
        self._in: dict[str, list[dict]] = {}
        for e in edges:
            self._out.setdefault(e["source"], []).append(e)
            self._in.setdefault(e["target"], []).append(e)
        self._theme_index = self._build_theme_index()

    # ── 테마 별칭 인덱스(정확 일치 전용) ────────────────────────────────────────
    def _build_theme_index(self) -> dict[str, str]:
        """이름·동의어 → node_id. 삽입 순서=시드 먼저 — 겹치면 시드(큐레이션) 승.

        GICS 레이어(sector:/industry:)는 제외한다 — 미국 업종 필터는 백테스트
        미지원이라, 테마어가 업종명에 우연히 닿아 조용히 유니버스로 확정되는 일을
        막는다(콘솔 탐색·향후 GICS 필터 기반용 레이어일 뿐 해석에 불참)."""
        index: dict[str, str] = {}
        for node_id, node in self.nodes.items():
            if node_id.startswith(("company:", "etf:", "sector:", "industry:")):
                continue
            terms = [node.get("name", ""), node.get("name_en", "")]
            terms += list(node.get("synonyms", []))
            for term in terms:
                key = _norm_key(term)
                if len(key) < 2:
                    continue
                index.setdefault(key, node_id)
        return index

    def theme_node(self, term: str) -> Optional[dict]:
        """테마어와 표기가 정확히 일치하는 노드. 부분·접두 매칭 금지."""
        node_id = self._theme_index.get(_norm_key(term))
        return self.nodes.get(node_id) if node_id else None

    def companies(self, node_id: str) -> list[str]:
        """노드에 직접(깊이 1) 연결된 상장사 티커 — 테마 유니버스 구성.

        시드·카탈로그 모두 회사 엣지로 합성돼 있어(한국 KG와 동일) 단일 경로다.
        공급망 전체로 번지지 않도록 직접 엣지만 본다."""
        found: list[str] = []
        for e in self._out.get(node_id, []):
            if e["type"] not in _COMPANY_EDGE_TYPES:
                continue
            target = e["target"]
            if target.startswith("company:"):
                symbol = target.split(":", 1)[1]
                if symbol not in found:
                    found.append(symbol)
        return found

    def concept_member_companies(self, node_id: str) -> list[str]:
        """개념 앵커의 구성 — 소속(part_of/is_a) 하위 테마 상장사의 합집합(깊이 1).

        직접 종목 엣지가 없는 앵커(ai·semiconductor·datacenter)의 유니버스 전개.
        2026-08-26 사용자 결정: 앵커 비확정(None)을 하위 테마 합집합 확정으로 전환 —
        /us에서 'AI 관련주'가 유니버스로 서야 한다(KR KG의 광의 테마와 동일한 눈높이).
        공급망 주변부(benefits_from·demanded_by·used_in 등)는 구성원이 아니다 —
        소속 관계(part_of/is_a)만 센다(공급망 전체로 번지지 않는다는 기존 원칙 유지)."""
        found: list[str] = []
        for e in self._in.get(node_id, []):
            if e["type"] not in ("part_of", "is_a"):
                continue
            for symbol in self.companies(e["source"]):
                if symbol not in found:
                    found.append(symbol)
        return found


# ── 합성 로드(mtime 캐시) ──────────────────────────────────────────────────────

_CACHED: Optional[USKnowledgeGraph] = None
_CACHED_MTIMES: Optional[tuple] = None
_CACHE_LOCK = threading.Lock()


def _mtimes() -> tuple:
    paths = (_SEED_PATH, _CATALOG_PATH, _STOCKS_PATH, _ETF_PATH, _LEXICON_PATH)
    return tuple(p.stat().st_mtime if p.exists() else None for p in paths)


@lru_cache(maxsize=1)
def _registry_names() -> dict[str, str]:
    """정본 티커 → 표시명(한글명 우선). 주식+ETF 합본."""
    names: dict[str, str] = {}
    for s in _load_json(_STOCKS_PATH, []):
        if s.get("symbol"):
            names[s["symbol"]] = s.get("name_kr") or s.get("name") or s["symbol"]
    for e in _load_json(_ETF_PATH, {}).get("etfs", []):
        if e.get("symbol"):
            names.setdefault(e["symbol"], e.get("name_kr") or e.get("name") or e["symbol"])
    return names


def _build() -> USKnowledgeGraph:
    issues: list[str] = []
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    registry = _registry_names()

    # 1) 시드 — 큐레이션 그래프(삽입 순서 최상위 = 별칭 경쟁에서 이긴다)
    seed = _load_json(_SEED_PATH, {"nodes": [], "edges": []})
    for node in seed.get("nodes", []):
        node_id = node.get("id")
        if not node_id:
            issues.append("시드 노드에 id 없음")
            continue
        if node_id in nodes:
            issues.append(f"시드 노드 id 중복: {node_id}")
            continue
        nodes[node_id] = dict(node)
    for edge in seed.get("edges", []):
        source, etype, target = edge.get("source"), edge.get("type"), edge.get("target")
        if not source or not etype or not target:
            issues.append(f"시드 엣지 필드 결측: {edge}")
            continue
        if etype not in EDGE_TYPES:
            issues.append(f"시드 엣지 타입 미지원: {source} -{etype}-> {target}")
            continue
        if source not in nodes:
            issues.append(f"시드 엣지 source 미정의: {source} -{etype}-> {target}")
            continue
        if target.startswith(("company:", "etf:")):
            symbol = target.split(":", 1)[1]
            if symbol not in registry:
                issues.append(f"시드 엣지 target 정본 부재: {source} -{etype}-> {target}")
                continue
            nodes.setdefault(target, {
                "id": target,
                "name": registry[symbol],
                "category": "etf" if target.startswith("etf:") else "company",
            })
        elif target not in nodes:
            issues.append(f"시드 엣지 target 미정의: {source} -{etype}-> {target}")
            continue
        edges.append(dict(edge))

    # 2) 테마 카탈로그 — 평면 테마→티커를 related_company 엣지로 합성(KR 카탈로그와
    #    동일 표현 — 콘솔 시각화·companies()가 단일 경로를 탄다). 정본 밖 티커는
    #    조용히 스킵(KR 계약과 동일).
    catalog = _load_json(_CATALOG_PATH, {"themes": []})
    for theme in catalog.get("themes", []):
        node_id = f"theme:{theme.get('id')}"
        if not theme.get("id") or node_id in nodes:
            continue
        nodes[node_id] = {
            "id": node_id,
            "name": theme.get("name", ""),
            "name_en": theme.get("name_en"),
            "category": "theme_catalog",
            "synonyms": list(theme.get("aliases", [])),
        }
        for symbol in theme.get("symbols", []):
            if symbol not in registry:
                continue
            target = f"company:{symbol}"
            nodes.setdefault(target, {
                "id": target, "name": registry[symbol], "category": "company",
            })
            edges.append({"source": node_id, "type": "related_company", "target": target})
        # 상위 개념 소속(concepts) — 시드의 개념 앵커에 part_of 엣지로 합류한다.
        # 앵커의 유니버스 전개(concept_member_companies)가 이 소속을 따라 하위 테마
        # 합집합을 만든다. 시드에 없는 개념 참조는 무결성 경고(fail-fast — 테스트가 0 단언).
        for concept_id in theme.get("concepts", []):
            if concept_id in nodes:
                edges.append({"source": node_id, "type": "part_of", "target": concept_id})
            else:
                issues.append(f"카탈로그 테마 '{theme['id']}'의 concepts 미정의: {concept_id}")

    # 2b) 학습 오버레이 — us_term_grounding이 공시 검색으로 학습한 테마어를 노드로 편입.
    #     별칭 경쟁에서 최하위다(시드 > 카탈로그 > 학습) — 큐레이션 정본이 항상 이긴다.
    #     verified 구성만 합성한다: pending은 관리자 콘솔 승인 대기분이라 유니버스로
    #     서지 않는다(한국 KG의 학습 엣지 계약과 동일). 정본 밖 티커는 조용히 스킵.
    from engine.us_industry_registry import classification_label  # 지연(순환 방지)

    learned_count = 0
    for key, entry in _load_json(_LEXICON_PATH, {}).items():
        if not isinstance(entry, dict):
            continue
        if classification_label(entry.get("term") or key) is not None:
            # [축 구분] 분류 라벨과 같은 표현은 학습 테마로 세우지 않는다 — 원장에 남은
            # 과거 오염이나 정본 갱신으로 새로 분류가 된 표현이 테마 축을 가리는 것을
            # 막는다(쓰기 방지는 us_term_grounding, 여기는 읽기 쪽 방어).
            continue
        members = [
            m for m in entry.get("members") or []
            if isinstance(m, dict) and m.get("symbol") and m.get("status") == "verified"
        ]
        if not members:
            continue  # 소속을 못 찾았거나 전부 검토 대기 — 노드로 세우지 않는다
        node_id = f"learned:{key}"
        if node_id in nodes:
            continue
        nodes[node_id] = {
            "id": node_id,
            "name": entry.get("term", key),
            "category": "learned_theme",
            "synonyms": [entry.get("term", key)],
            "source": entry.get("source"),
            "searched_at": entry.get("searched_at"),
            # 소속 최초 관측일과 관측 창 시작일 — 테마는 '오늘의 명부'가 아니라
            # 시점을 가진 관측이다(분류 축과 갈리는 지점, FR-STR-074 ⑦).
            "first_known_date": entry.get("first_known_date"),
            "observed_from": entry.get("observed_from"),
        }
        learned_count += 1
        for member in members:
            symbol = member["symbol"]
            if symbol not in registry:
                continue
            target = f"company:{symbol}"
            nodes.setdefault(target, {
                "id": target, "name": registry[symbol], "category": "company",
            })
            edges.append({"source": node_id, "type": "related_company", "target": target})

    # 3) GICS 업종 레이어 — us-stocks.json의 섹터(11)·산업 분류를 소속 엣지로 합성.
    #    전 종목이 그래프에 들어온다(콘솔 탐색·향후 GICS 필터 기반). 테마 해석에는
    #    불참(_build_theme_index가 sector:/industry: 제외). 산업이 두 섹터에 걸치면
    #    (Consumer Electronics 실측 1건) 소속 엣지를 모두 남긴다 — 정본이 그렇다.
    #    분류 결측 종목(실측 98)은 소속 엣지 없이 테마 참조 시에만 등재.
    industry_sectors: set[tuple[str, str]] = set()
    for s in _load_json(_STOCKS_PATH, []):
        symbol, sector = s.get("symbol"), (s.get("sector") or "").strip()
        industry = (s.get("industry") or "").strip()
        if not symbol or symbol not in registry or not sector:
            continue
        sector_id = f"sector:{sector}"
        nodes.setdefault(sector_id, {
            "id": sector_id,
            "name": _GICS_SECTOR_KR.get(sector, sector),
            "name_en": sector,
            "category": "gics_sector",
        })
        company_id = f"company:{symbol}"
        nodes.setdefault(company_id, {
            "id": company_id, "name": registry[symbol], "category": "company",
        })
        if industry:
            industry_id = f"industry:{industry}"
            nodes.setdefault(industry_id, {
                "id": industry_id, "name": industry, "category": "gics_industry",
            })
            edges.append({"source": company_id, "type": "belongs_to", "target": industry_id})
            if (industry, sector) not in industry_sectors:
                industry_sectors.add((industry, sector))
                edges.append({"source": industry_id, "type": "part_of", "target": sector_id})
        else:
            edges.append({"source": company_id, "type": "belongs_to", "target": sector_id})

    graph = USKnowledgeGraph(nodes, edges, issues)
    logger.info(
        "US KG 로드: 노드 %d개(시드 %d)·엣지 %d개·카탈로그 테마 %d개·학습 테마 %d개·경고 %d건",
        len(nodes), len(seed.get("nodes", [])), len(edges),
        len(catalog.get("themes", [])), learned_count, len(issues),
    )
    for issue in issues:
        logger.warning("US KG 무결성: %s", issue)
    return graph


def get_graph() -> USKnowledgeGraph:
    """합성 그래프(캐시). 데이터 파일 mtime이 바뀌면 재로드."""
    global _CACHED, _CACHED_MTIMES
    current = _mtimes()
    with _CACHE_LOCK:
        if _CACHED is None or _CACHED_MTIMES != current:
            _registry_names.cache_clear()
            _CACHED = _build()
            _CACHED_MTIMES = current
        return _CACHED


def theme_term_candidates(term: str) -> list[str]:
    """테마어의 조회 후보 표기 목록(원표기 → 한정어를 벗긴 표기 순).

    '미국' 접두와 '관련주/테마' 접미는 시장·범주 한정어일 뿐 테마 정체성이 아니다 —
    벗긴 조합까지 정확 일치로 본다("미국 빅테크 관련주" → "빅테크"). 영어 입력 레인의
    시장 접두("US"·"U.S."·"American")와 범주 접미("stocks"·"names"·"-related" 등 —
    '관련주'의 영어 판)도 같은 이유로 벗긴다(2026-08-26 실측: "US cloud software
    stocks"·"crypto-related"가 정확 일치에 실패해 테마가 소실되거나 한국 체인으로
    흘렀다). 부분 매칭은 하지 않는다 — 오폭원."""
    candidates = [term.strip()]
    en_stripped = re.sub(r"^(?:the\s+)?(?:u\.?s\.?a?\.?|american)\s+", "",
                         term.strip(), flags=re.IGNORECASE)
    if en_stripped != term.strip():
        candidates.append(en_stripped)
    if _norm_key(term).startswith(_norm_key(_MARKET_PREFIX)):
        candidates.append(term.strip()[len(_MARKET_PREFIX):].strip())
    for base in list(candidates):
        for suffix in ("관련주", "테마"):
            if base.endswith(suffix) and len(base) > len(suffix):
                candidates.append(base[: -len(suffix)].strip())
        stripped = base
        while True:  # "crypto-related stocks" → "crypto-related" → "crypto"
            trimmed = re.sub(
                r"[\s-]+(?:related|linked|stocks?|names?|companies|shares|sector|theme)$",
                "", stripped, flags=re.IGNORECASE)
            if trimmed == stripped or not trimmed:
                break
            stripped = trimmed.strip()
            candidates.append(stripped)
    return candidates


def normalize_theme_term(term: str) -> str:
    """한정어를 모두 벗긴 테마 정체성 표기 — 검색 그라운딩의 질의어·학습 테마명.

    "mrna-Related" → "mrna", "US cloud software stocks" → "cloud software".
    조회(resolve_theme)와 같은 규칙을 쓰므로 학습된 이름이 다음 턴에 그대로 다시 잡힌다."""
    return theme_term_candidates(term)[-1] if term and isinstance(term, str) else ""


def resolve_theme(term: Optional[str]) -> Optional[tuple[str, list[str]]]:
    """테마어 → (정본 테마명, 구성 티커 목록). 그래프 밖이면 None.

    '미국' 접두는 벗겨 본다("미국 사이버보안" → "사이버보안") — 시장 한정어일 뿐
    테마 정체성이 아니다. 영어 입력 레인의 시장 접두("US"·"U.S."·"American")와 범주
    접미("stocks"·"names"·"-related" 등 — '관련주'의 영어 판)도 같은 이유로 벗긴다
    (2026-08-26 실측: "US cloud software stocks"·"crypto-related"가 정확 일치에 실패해
    테마가 소실되거나 한국 체인으로 흘렀다). 정확 일치만 — 부분 매칭은 오폭원. 직접
    구성이 비는 개념 앵커 노드(ai·semiconductor·datacenter)는 소속(part_of/is_a) 하위
    테마의 합집합으로 전개한다(concept_member_companies — 2026-08-26 사용자 결정,
    종전 '앵커=None' 비확정 설계를 대체). 하위 소속까지 비면 그대로 None."""
    if not term or not isinstance(term, str):
        return None
    graph = get_graph()
    candidates = theme_term_candidates(term)
    node = None
    for cand in candidates:
        node = graph.theme_node(cand)
        if node is not None:
            break
    if node is None:
        return None
    symbols = graph.companies(node["id"])
    if not symbols:
        symbols = graph.concept_member_companies(node["id"])
    if not symbols:
        return None
    return node.get("name", ""), symbols
