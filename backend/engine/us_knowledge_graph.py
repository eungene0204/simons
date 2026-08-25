"""미국 투자 지식그래프(US KG) — 시드+카탈로그 합성, 테마어 → 구성 티커 registry.

한국 KG(engine/knowledge_graph.py)와 같은 구조 원칙을 따른다:

- **입력은 LLM이 추출한 짧은 테마어다**(사용자 원문이 아님 — 자연어 해석 구조 원칙).
  원문 문장 스캔은 없다. US 레인은 LLM-first라 원문을 읽는 소비자 자체가 없다.
- **합성 로드(정본 두 번 안 적기)**: 시드 `data/us-knowledge-graph.json`(큐레이션
  그래프 — 노드·엣지·동의어) + 테마 카탈로그 `data/us-theme-catalog.json`(평면
  테마→티커 목록) + GICS 업종 레이어(us-stocks.json의 섹터 11·산업 253 분류를
  소속 엣지로 — 전 종목 등재, 콘솔 탐색·향후 GICS 필터 기반이며 테마 해석 불참).
  같은 별칭이 겹치면 시드(큐레이션)가 이긴다 — 한국 KG의 시드>카탈로그 삽입 순서
  계약과 동일.
- **company:TICKER 자동 노드**: us-stocks.json·us-etf-master.json 정본에서 참조 시
  생성. 시드의 정본 밖 티커는 issues로 fail-fast(무결성 테스트가 0을 단언),
  카탈로그의 정본 밖 티커는 조용히 스킵(한국 카탈로그 로더 계약과 동일).
- **mtime 캐시**: 데이터 파일이 바뀌면 다음 조회에서 재로드.

한국 KG 대비 의도적 부재(미국엔 해당 소스·소비자가 없다):
- 문장 스캔(find_concepts) — 원문을 읽는 KR nl_parser 경로가 US엔 없음
- 섹터 해석(resolve_sector) — 미국 GICS 업종 필터 자체가 미지원
- 학습 오버레이(term_lexicon) — 네이버 뉴스 그라운딩 검색이 KR 전용
- 지분 엣지 — DART 타법인출자현황이 KR 전용
"""

from __future__ import annotations

import json
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


# ── 합성 로드(mtime 캐시) ──────────────────────────────────────────────────────

_CACHED: Optional[USKnowledgeGraph] = None
_CACHED_MTIMES: Optional[tuple] = None
_CACHE_LOCK = threading.Lock()


def _mtimes() -> tuple:
    paths = (_SEED_PATH, _CATALOG_PATH, _STOCKS_PATH, _ETF_PATH)
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
        "US KG 로드: 노드 %d개(시드 %d)·엣지 %d개·카탈로그 테마 %d개·경고 %d건",
        len(nodes), len(seed.get("nodes", [])), len(edges),
        len(catalog.get("themes", [])), len(issues),
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


def resolve_theme(term: Optional[str]) -> Optional[tuple[str, list[str]]]:
    """테마어 → (정본 테마명, 구성 티커 목록). 그래프 밖이면 None.

    '미국' 접두는 벗겨 본다("미국 사이버보안" → "사이버보안") — 시장 한정어일 뿐
    테마 정체성이 아니다. 정확 일치만 — 부분 매칭은 오폭원. 구성이 비는 개념 앵커
    노드(ai·datacenter 등)는 None — 범위가 넓어 단일 유니버스로 확정하지 않는다."""
    if not term or not isinstance(term, str):
        return None
    graph = get_graph()
    # '미국' 접두와 '관련주/테마' 접미는 시장·범주 한정어일 뿐 테마 정체성이 아니다 —
    # 벗긴 조합까지 정확 일치로 본다("미국 빅테크 관련주" → "빅테크"). 부분 매칭은 않는다.
    candidates = [term.strip()]
    if _norm_key(term).startswith(_norm_key(_MARKET_PREFIX)):
        candidates.append(term.strip()[len(_MARKET_PREFIX):].strip())
    for base in list(candidates):
        for suffix in ("관련주", "테마"):
            if base.endswith(suffix) and len(base) > len(suffix):
                candidates.append(base[: -len(suffix)].strip())
    node = None
    for cand in candidates:
        node = graph.theme_node(cand)
        if node is not None:
            break
    if node is None:
        return None
    symbols = graph.companies(node["id"])
    if not symbols:
        return None
    return node.get("name", ""), symbols
