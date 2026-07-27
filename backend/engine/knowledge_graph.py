"""Investment Knowledge Graph(IKG) — 투자 개념·산업·공급망·기업·ETF를 잇는 지식 그래프(FR-STR-070).

용어집(term_lexicon)이 '용어 → 섹터' 평면 매핑이라면, IKG는 개념(Node)과 관계(Edge)를
저장해 "HBM → 반도체 / SK하이닉스·한미반도체 / 반도체 ETF / CAPEX"처럼 다층으로
탐색한다. 새 개념은 기존 그래프 수정 없이 Node·Edge 추가만으로 확장된다.

데이터 소스(모두 기존 정본 재사용 — 정본을 손으로 두 번 적지 않는다):
  - 시드 그래프: data/knowledge-graph.json (git 추적, 손으로 큐레이션)
  - 섹터 노드:   universe_pit.CANONICAL_SECTORS에서 자동 생성(id = "sector:<정본명>")
  - 기업 노드:   korea-stocks.json에서 참조 시 자동 생성(id = "company:<symbol>")
  - ETF 노드:    etf-master.json에서 참조 시 자동 생성(id = "etf:<symbol>")
  - 학습 노드:   term_lexicon.json(검색 그라운딩 산출물)을 오버레이로 편입 —
                 term_grounding이 새 용어를 학습하면 그래프도 함께 자란다(별도 저장소 없음)

빌더 업종 해석 체인(FR-STR-069)의 어휘집 조회와 LLM 사이에 결정적 그래프 조회로
배선된다(term_grounding.resolve_sector ①b 단계).

규제 안전: 그래프는 객관적 관계 데이터(생산·공급·소속)만 저장·표시한다.
추천·전망·우열 판단을 표현하는 노드/엣지는 만들지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import deque
from pathlib import Path
from typing import Any, Optional

# 조회 로그가 dev/운영 콘솔에 항상 보이게 전용 핸들러를 단다(engine/console_logging 참고
# — 2026-07-27 'KG 로그 안 보임' 제보).
from engine.console_logging import console_logger

logger = console_logger("knowledge_graph", "KG")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 레포 루트(data/의 부모)
_SEED_PATH = _BASE_DIR / "data" / "knowledge-graph.json"
_LEXICON_PATH = _BASE_DIR / "data" / "term_lexicon.json"
_CATALOG_PATH = _BASE_DIR / "data" / "kg-theme-catalog.json"
_NAVER_CATALOG_PATH = _BASE_DIR / "data" / "kg-naver-theme-catalog.json"
_STOCKS_PATH = _BASE_DIR / "data" / "korea-stocks.json"
_ETF_PATH = _BASE_DIR / "data" / "etf-master.json"

# 테스트 정본 용어 가드 — grounding·빌더 테스트가 '그래프 밖 용어'로 전제하는 표현.
# 카탈로그 ingest 스크립트와 로더의 별칭 생성이 공유한다(정의는 여기 한 곳) —
# 이 표현이 카탈로그 스캔 용어가 되면 검색 학습 경로 테스트가 죽는다.
TEST_RESERVED_TERMS: frozenset[str] = frozenset({
    "그린수소", "폐배터리", "위고비", "마운자로", "메타버스", "cowos", "신조어",
    "반도체소부장", "ess",
})


def _catalog_paths() -> tuple[Path, ...]:
    """카탈로그 합성 순서 — 네이버 금융(업종·테마별 종목)이 사용자 지정 1순위 신뢰
    소스(2026-07-27)라 주달보다 먼저 합성돼 같은 표기가 겹치면 네이버가 이긴다.
    호출 시점에 전역을 읽는다(테스트가 경로를 monkeypatch할 수 있게)."""
    return (_NAVER_CATALOG_PATH, _CATALOG_PATH)

# 지원 관계 어휘 — 시드에 미지의 타입이 들어오면 검증에서 잡는다(오타 fail-fast).
EDGE_TYPES: frozenset[str] = frozenset({
    "is_a", "part_of", "belongs_to", "related_to",
    "uses", "used_by", "used_in", "requires", "depends_on",
    "supplier", "customer", "competitor", "produced_by", "manufactured_by",
    "demanded_by", "invests_in",
    "related_company", "related_etf", "related_metric", "related_macro",
    "related_news", "related_universe",
    "cause", "affected_by", "benefits_from", "risk_factor", "substitute",
    "next_generation", "predecessor", "successor",
})

# 섹터 해석에 쓰는 '소속' 방향 엣지 — 개념에서 이 타입만 따라가면 정본 섹터에 닿는다.
_SECTOR_EDGE_TYPES = ("is_a", "part_of", "belongs_to")
_SECTOR_MAX_DEPTH = 3


def _norm_key(text: str) -> str:
    """스캔·비교용 키 — 공백 제거·소문자화(universe_pit._sector_key와 동일 관례)."""
    return (text or "").replace(" ", "").lower()


# 별칭 일반어 차단 — "카메라모듈/부품"의 '부품'처럼 단독으로는 테마를 특정하지 못하는
# 조각이 스캔 어휘가 되면 그 단어를 포함한 모든 질의에 오매칭된다("LCD 부품" 질의가
# 카메라모듈 테마에 걸리던 사고 2026-07-27). 수식어가 붙은 별칭("반도체 부품")은 통과.
_ALIAS_STOPWORDS: frozenset[str] = frozenset({
    "부품", "소재", "장비", "제품", "기기", "재료",
    # '화폐/금융자동화기기'의 '화폐' — 암호화폐·가상화폐 질의가 ATM 테마에 걸린다(2026-07-27).
    "화폐",
})


def _slash_aliases(name: str) -> list[str]:
    """복합 표기 테마명("LCD 부품/소재")의 결정적 표기 변형("LCD 부품"·"LCD 소재").

    의미 해석이 아니라 표기 정규화다 — 슬래시 병기 이름은 그대로는 스캔 부분 문자열에
    절대 걸리지 않아 도달 불가 노드가 된다('LCD 부품' 사고 2026-07-27). 괄호는 제거한
    본체 기준으로 변형을 만든다("지능형로봇/인공지능(AI)"→지능형로봇·인공지능 — 괄호가
    붙은 병기 이름이 통째로 도달 불가 노드가 되던 사고 2026-07-27). 괄호 안 텍스트
    (HBM/HBM3E의 별칭 승격)는 ingest의 괄호 동의어 승격이 담당하므로 여기서 만들지 않는다.
    섹터 어휘·테스트 정본 용어·별칭 일반어로 정규화되는 변형은 가드 계약대로 제외한다."""
    base = re.sub(r"\([^)]*\)", "", name or "").strip()
    m = re.fullmatch(r"(.*?)([^\s/]+(?:/[^\s/]+)+)(.*)", base)
    if not m:
        return []
    from engine.universe_pit import normalize_sector  # 지연 import(무거운 엔진 모듈)

    prefix, group, suffix = m.groups()
    aliases = []
    for part in group.split("/"):
        alias = f"{prefix}{part}{suffix}".strip()
        key = _norm_key(alias)
        if len(key) < 2 or key in TEST_RESERVED_TERMS or key in _ALIAS_STOPWORDS:
            continue
        if normalize_sector(alias):
            continue
        aliases.append(alias)
    return aliases


# ── 조회 로그 포맷터 — 무엇을 KG에서 찾았고 무엇이 나왔는지 추적(운영 관찰용) ──


def _log_preview(text: str, limit: int = 80) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[:limit] + "…"


def _fmt_concepts(concepts: list[dict]) -> str:
    return ", ".join(f"{n.get('name', n['id'])}[{n['id']}]" for n in concepts) or "(없음)"


def _fmt_items(items: list[str], limit: int = 20) -> str:
    shown = ", ".join(items[:limit])
    extra = len(items) - limit
    return (shown + (f" 외 {extra}건" if extra > 0 else "")) or "(없음)"


def _fmt_companies(companies: list[dict], limit: int = 20) -> str:
    return _fmt_items([f"{c['name']}({c['symbol']})" for c in companies], limit)


def _load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class KnowledgeGraph:
    """읽기 전용 그래프 뷰. 로드 시점에 시드+정본+학습 오버레이를 합성한다."""

    def __init__(self, nodes: dict[str, dict], edges: list[dict], issues: list[str]):
        self.nodes = nodes            # id → node dict
        self.edges = edges            # {source, type, target, note?}
        self.issues = issues          # 검증 경고(시드 무결성 테스트가 빈 목록을 단언)
        self._out: dict[str, list[dict]] = {}
        self._in: dict[str, list[dict]] = {}
        for e in edges:
            self._out.setdefault(e["source"], []).append(e)
            self._in.setdefault(e["target"], []).append(e)
        self._scan_index = self._build_scan_index()
        self._catalog_index = self._build_catalog_index()

    # ── 카탈로그 정합 인덱스(용어 → 카탈로그 테마 노드 정확 일치) ────────────────
    def _build_catalog_index(self) -> dict[str, list[str]]:
        """카탈로그 테마의 이름·동의어(표기 변형 포함) → [node_id] 정확 키 인덱스.

        스캔 인덱스와 달리 taken 경쟁을 하지 않는다 — 같은 표기를 학습 노드가 먼저
        가져갔어도('LCD 부품' 사고 2026-07-27) 카탈로그 테마를 찾을 수 있어야 한다."""
        index: dict[str, list[str]] = {}
        for node_id, node in self.nodes.items():
            if node.get("category") != "theme_catalog":
                continue
            for term in [node.get("name", "")] + list(node.get("synonyms", [])):
                key = _norm_key(term)
                if len(key) < 2:
                    continue
                bucket = index.setdefault(key, [])
                if node_id not in bucket:
                    bucket.append(node_id)
        return index

    def catalog_theme_nodes(self, term: str) -> list[dict]:
        """용어와 표기가 정확히 일치하는 카탈로그 테마 노드 목록.

        부분·접두 매칭 금지 — 복합 테마구 오확정 가드와 동일 원칙. 학습 앵커의
        카탈로그 정합 우선 조회(theme_listed_companies)가 소비한다."""
        return [self.nodes[nid] for nid in self._catalog_index.get(_norm_key(term), [])]

    # ── 스캔 인덱스(문장 → 개념 노드 결정적 인식) ────────────────────────────────
    def _build_scan_index(self) -> list[tuple[str, str]]:
        """개념 노드의 이름·별칭 → [(정규화 키, node_id)] (긴 키 우선).

        normalize_sector가 이미 해석하는 용어(반도체·AI 등)는 제외한다 — 상류의
        결정적 섹터 인식과 이중 매칭돼 어긋나는 일을 막는다. 자동 생성 노드
        (sector:/company:/etf:)는 각자 기존 경로(섹터 정규화·종목 인식)가 담당하므로
        스캔 대상이 아니다. 학습 노드(learned:)는 포함한다 — 읽기 경로 통합(2026-07-25):
        어휘집 별도 스캔 없이 그래프가 시드·학습 용어를 단일 경로로 인식한다. 같은
        용어가 시드와 학습에 모두 있으면 시드가 이긴다(삽입 순서 — 큐레이션 우선).
        카탈로그 노드(theme:)는 최하위 — 시드·학습 다음에 삽입돼 겹치면 진다."""
        from engine.universe_pit import normalize_sector  # 지연 import(무거운 엔진 모듈)

        index: list[tuple[str, str]] = []
        taken: dict[str, str] = {}
        for node_id, node in self.nodes.items():
            if node_id.startswith(("sector:", "company:", "etf:")):
                continue
            for term in [node.get("name", "")] + list(node.get("synonyms", [])):
                key = _norm_key(term)
                if len(key) < 2 or normalize_sector(term):
                    continue
                if taken.setdefault(key, node_id) != node_id:
                    continue  # 먼저 등록된 노드(시드) 우선 — 비결정적 인식 방지
                index.append((key, node_id))
        index.sort(key=lambda kv: -len(kv[0]))  # 긴 용어 우선(부분 문자열 가림 방지)
        return index

    def find_concepts(self, text: str) -> list[dict]:
        """문장에서 시드 개념 노드를 결정적으로 찾는다(검색·LLM 없이).

        라틴 약어(hbm·smr 등)는 \\b 대신 라틴 문자 lookaround로 경계를 잡는다 —
        'process'의 'ess' 같은 오매칭 방지(term_grounding과 동일 관례)."""
        t = _norm_key(text)
        found: list[dict] = []
        seen: set[str] = set()
        for key, node_id in self._scan_index:
            if node_id in seen:
                continue
            if re.fullmatch(r"[a-z0-9]+", key):
                if not re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", t):
                    continue
            elif key not in t:
                continue
            seen.add(node_id)
            found.append(self.nodes[node_id])
        # 진입점(섹터 해석·테마 조회 등)이 INFO로 요약하므로 원시 스캔은 DEBUG만 —
        # 학습·역스캔 루프의 대량 호출이 운영 로그를 덮지 않게 한다.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "KG 개념 스캔: 질의=%r → %s", _log_preview(text), _fmt_concepts(found)
            )
        return found

    # ── 탐색 ────────────────────────────────────────────────────────────────────
    def neighbors(self, node_id: str) -> list[tuple[str, str, str]]:
        """(edge_type, 상대 node_id, 방향 'out'|'in') 목록."""
        result = [(e["type"], e["target"], "out") for e in self._out.get(node_id, [])]
        result += [(e["type"], e["source"], "in") for e in self._in.get(node_id, [])]
        return result

    def resolve_sector(self, node_id: str) -> Optional[str]:
        """개념에서 소속 엣지(is_a/part_of/belongs_to)만 따라 정본 섹터를 찾는다.

        서로 다른 섹터 둘 이상에 닿으면 모호 → None(기존 되묻기/LLM 폴백 유지).
        데이터센터처럼 의도적으로 다업종인 개념은 시드에 소속 엣지를 두지 않는다."""
        found: set[str] = set()
        visited = {node_id}
        queue = deque([(node_id, 0)])
        while queue:
            current, depth = queue.popleft()
            if depth >= _SECTOR_MAX_DEPTH:
                continue
            for e in self._out.get(current, []):
                if e["type"] not in _SECTOR_EDGE_TYPES:
                    continue
                target = e["target"]
                if target.startswith("sector:"):
                    found.add(target.split(":", 1)[1])
                elif target not in visited:
                    visited.add(target)
                    queue.append((target, depth + 1))
        return next(iter(found)) if len(found) == 1 else None

    def listed_companies(self, node_id: str) -> list[dict]:
        """개념에 직접(깊이 1) 연결된 상장사 이웃 — 테마 유니버스 후보(FR-STR-071).

        학습 엣지가 실어온 출처 지지 수(support)·뉴스 최초 보도일(first_known_date)을
        함께 돌려준다(시드 엣지엔 없음). 공급망 전체로 번지지 않도록 깊이 1만 본다."""
        result: list[dict] = []
        seen: set[str] = set()
        for e in self._out.get(node_id, []) + self._in.get(node_id, []):
            other = e["target"] if e["source"] == node_id else e["source"]
            if not other.startswith("company:") or other in seen:
                continue
            seen.add(other)
            result.append({
                "symbol": other.split(":", 1)[1],
                "name": self.nodes.get(other, {}).get("name", other),
                "support": e.get("support", 1),
                "first_known_date": e.get("first_known_date"),
            })
        return result

    def neighbor_edges(self, node_id: str):
        """(엣지 원본, 반대편 노드 id) 순회 — 방향 무관, note·support 등 원본 필드 보존.

        listed_companies가 심볼 요약만 주는 것과 달리 엣지 자체가 필요한 소비자
        (concept_universe의 원장 점수 파싱 등)용 읽기 접근이다."""
        for e in self._out.get(node_id, []) + self._in.get(node_id, []):
            yield e, (e["target"] if e["source"] == node_id else e["source"])

    def listed_companies_via_concepts(self, node_id: str) -> list[dict]:
        """개념 이웃 1홉 너머의 직접 상장사 — 직접 상장사 엣지가 없는 테마의 폴백.

        'bts 관련주' 사고(2026-07-25): 검색 학습이 상장사 엣지를 검증하지 못해도(출처 1건
        pending) verified 개념 엣지(bts→K-팝 기획사)가 있으면 그 개념의 직접 상장사
        (하이브 등)가 답이었다. 그래프에 합성된 엣지는 전부 검증분이므로 신뢰 등급은
        유지되며, 공급망 전체로 번지지 않게 개념 경유는 정확히 1홉만 허용한다."""
        result: list[dict] = []
        seen: set[str] = set()
        for e in self._out.get(node_id, []) + self._in.get(node_id, []):
            other = e["target"] if e["source"] == node_id else e["source"]
            if other.startswith(("company:", "etf:", "sector:")):
                continue
            for c in self.listed_companies(other):
                if c["symbol"] in seen:
                    continue
                seen.add(c["symbol"])
                result.append(c)
        return result

    def expand(self, node_id: str, max_depth: int = 2) -> dict:
        """개념 주변을 BFS로 펼쳐 sectors/companies/etfs/concepts 버킷으로 분류한다.

        각 항목에 도달 경로(via)를 남긴다 — "HBM –produced_by→ SK하이닉스"처럼
        관계를 근거로 표시할 수 있게(객관적 관계 데이터 표시, 추천 아님)."""
        buckets: dict[str, list[dict]] = {"sectors": [], "companies": [], "etfs": [], "concepts": []}
        visited = {node_id}
        queue = deque([(node_id, 0, self.nodes[node_id].get("name", node_id))])
        while queue:
            current, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            for edge_type, other, direction in self.neighbors(current):
                if other in visited:
                    continue
                visited.add(other)
                node = self.nodes.get(other, {"id": other, "name": other})
                arrow = f"–{edge_type}→" if direction == "out" else f"←{edge_type}–"
                via = f"{path} {arrow} {node.get('name', other)}"
                entry = {"id": other, "name": node.get("name", other), "via": via}
                if other.startswith("sector:"):
                    buckets["sectors"].append(entry)
                elif other.startswith("company:"):
                    buckets["companies"].append({**entry, "symbol": other.split(":", 1)[1]})
                elif other.startswith("etf:"):
                    buckets["etfs"].append({**entry, "symbol": other.split(":", 1)[1]})
                else:
                    buckets["concepts"].append(entry)
                    queue.append((other, depth + 1, via))
        return buckets


# ─── 로드(시드 + 정본 + 학습 오버레이 합성) ─────────────────────────────────────

_CACHE_LOCK = threading.Lock()
_CACHED: Optional[tuple[tuple, KnowledgeGraph]] = None


def _mtimes() -> tuple:
    def mt(p: Path) -> float:
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0
    return (mt(_SEED_PATH), mt(_LEXICON_PATH)) + tuple(mt(p) for p in _catalog_paths())


def _stock_names() -> dict[str, str]:
    stocks = _load_json(_STOCKS_PATH, [])
    return {s["symbol"]: s["name"] for s in stocks if isinstance(s, dict) and s.get("symbol")}


def _etf_names() -> dict[str, str]:
    data = _load_json(_ETF_PATH, {})
    return {e["symbol"]: e["name"] for e in data.get("etfs", []) if e.get("symbol")}


def _build() -> KnowledgeGraph:
    from engine.universe_pit import CANONICAL_SECTORS

    seed = _load_json(_SEED_PATH, {})
    issues: list[str] = []
    nodes: dict[str, dict] = {}

    for sector in CANONICAL_SECTORS:
        nodes[f"sector:{sector}"] = {
            "id": f"sector:{sector}", "name": sector, "category": "industry",
        }

    for raw in seed.get("nodes", []):
        node_id = raw.get("id")
        if not node_id:
            issues.append(f"id 없는 노드: {raw}")
            continue
        if node_id in nodes:
            issues.append(f"중복 노드 id: {node_id}")
            continue
        nodes[node_id] = raw

    # 학습 오버레이 — term_grounding이 검색으로 학습한 용어를 그래프 노드로 편입.
    # 섹터가 매핑됐거나 verified 학습 엣지가 하나라도 있으면 노드가 된다(FR-STR-070b —
    # 섹터 매핑엔 실패했지만 시드 개념과의 관계는 검증된 용어를 버리지 않는다).
    for key, entry in _load_json(_LEXICON_PATH, {}).items():
        if not isinstance(entry, dict):
            continue
        has_verified_edge = any(
            isinstance(e, dict) and e.get("status") == "verified"
            for e in entry.get("edges", [])
        )
        if not entry.get("sector") and not has_verified_edge:
            continue
        node_id = f"learned:{key}"
        if node_id in nodes:
            continue
        nodes[node_id] = {
            "id": node_id, "name": entry.get("term", key), "category": "learned",
            "description": entry.get("definition"),
            # 테마 유니버스의 시점 편향 폴백(뉴스 보도일 없는 엣지뿐일 때) — FR-STR-071
            "searched_at": entry.get("searched_at"),
        }

    # 카탈로그 오버레이 — 외부 테마 분류(네이버 금융 업종·테마, 주달)를 최하위 순위로
    # 편입한다. 스캔 인덱스는 삽입 순서로 시드·학습이 우선하고(taken), 소속 엣지가 없어
    # 섹터 해석에는 관여하지 않는다 — 테마→종목 조회 전용. 카탈로그끼리는 네이버가
    # 먼저(_CATALOG_PATHS 순서, 사용자 지정 1순위 신뢰 소스 2026-07-27).
    # 수집·가드는 scripts/ingest_naver_themes.py·ingest_judal_themes.py
    # (시드 중복·섹터 어휘·테스트 용어 제외). 슬래시 병기 이름("LCD 부품/소재")은
    # 결정적 표기 변형을 동의어로 더해 스캔 도달 가능하게 한다.
    catalog_themes: list[dict] = []
    for path in _catalog_paths():
        catalog = _load_json(path, {})
        for theme in catalog.get("themes", []):
            if not isinstance(theme, dict) or not theme.get("id"):
                continue
            node_id = f"theme:{theme['id']}"
            if node_id in nodes:
                continue
            synonyms = list(theme.get("synonyms", []))
            synonyms += [a for a in _slash_aliases(theme.get("name", "")) if a not in synonyms]
            nodes[node_id] = {
                "id": node_id, "name": theme.get("name", theme["id"]),
                "category": "theme_catalog", "synonyms": synonyms,
                "source": catalog.get("source"), "retrieved_at": catalog.get("retrieved_at"),
            }
            catalog_themes.append(theme)

    stock_names = _stock_names()
    etf_names = _etf_names()

    def resolve_endpoint(ref: str, report: bool = True) -> bool:
        """엣지 끝점을 검증하고, 정본 참조(company:/etf:)면 노드를 자동 생성한다.

        report=False(학습 엣지 경로): 정본에 없는 참조를 issues에 남기지 않는다 —
        학습 데이터는 시드와 달리 무결성 단언 대상이 아니다."""
        if ref in nodes:
            return True
        if ref.startswith("company:"):
            symbol = ref.split(":", 1)[1]
            if symbol in stock_names:
                nodes[ref] = {"id": ref, "name": stock_names[symbol], "category": "company"}
                return True
            if report:
                issues.append(f"korea-stocks.json에 없는 종목 참조: {ref}")
            return False
        if ref.startswith("etf:"):
            symbol = ref.split(":", 1)[1]
            if symbol in etf_names:
                nodes[ref] = {"id": ref, "name": etf_names[symbol], "category": "etf"}
                return True
            if report:
                issues.append(f"etf-master.json에 없는 ETF 참조: {ref}")
            return False
        if report:
            issues.append(f"존재하지 않는 노드 참조: {ref}")
        return False

    edges: list[dict] = []
    for raw in seed.get("edges", []):
        source, edge_type, target = raw.get("source"), raw.get("type"), raw.get("target")
        if edge_type not in EDGE_TYPES:
            issues.append(f"미지원 엣지 타입: {edge_type} ({source} → {target})")
            continue
        if not resolve_endpoint(source) or not resolve_endpoint(target):
            continue
        edges.append(raw)

    for key, entry in _load_json(_LEXICON_PATH, {}).items():
        node_id = f"learned:{key}"
        if node_id not in nodes or not isinstance(entry, dict):
            continue
        sector = entry.get("sector")
        if sector and f"sector:{sector}" in nodes:
            edges.append({"source": node_id, "type": "belongs_to", "target": f"sector:{sector}"})
        # 학습 관계 엣지(FR-STR-070b) — 자동(출처 교차지지)·수동 검증된 verified만 합성한다.
        # pending은 콘솔 검토 대기, rejected는 반려분. 타입·타깃은 로더에서 재검증(닫힌 세계).
        # 정본 참조 타깃(company:/etf:, FR-STR-071 관련 기업 엣지)은 시드 엣지처럼 노드를
        # 자동 생성하되, 정본에 없는 참조는 issues 없이 조용히 건너뛴다(학습 데이터는
        # 시드와 달리 무결성 단언 대상이 아니다 — 상폐 이후 마스터에서 빠진 종목 등).
        for e in entry.get("edges", []):
            if (
                not isinstance(e, dict)
                or e.get("status") != "verified"
                or e.get("type") not in EDGE_TYPES
            ):
                continue
            target = e.get("target")
            if target not in nodes:
                if not (
                    isinstance(target, str)
                    and target.startswith(("company:", "etf:"))
                    and resolve_endpoint(target, report=False)
                ):
                    continue
            edge = {"source": node_id, "type": e["type"], "target": target}
            # 테마 유니버스 조회가 그래프 단일 경로로 동작하도록 학습 엣지의 출처 지지 수·
            # 뉴스 최초 보도일을 함께 실어 나른다(FR-STR-071 읽기 경로 통합).
            # note는 콘솔 수동 엣지(FR-STR-070b ⑦)의 근거 문구 — concept_universe가
            # 이유(reason)로 표시한다(자동 학습 엣지엔 note가 없다).
            for extra in ("support", "first_known_date", "note"):
                if e.get(extra) is not None:
                    edge[extra] = e[extra]
            edges.append(edge)

    # 카탈로그 엣지 — 정본에 없는 심볼은 조용히 스킵(카탈로그는 학습 데이터처럼
    # 무결성 단언 대상이 아니다 — 수집 시점 이후 마스터에서 빠진 종목 등).
    for theme in catalog_themes:
        node_id = f"theme:{theme.get('id')}"
        if node_id not in nodes:
            continue
        for stock in theme.get("stocks", []):
            symbol = stock.get("symbol") if isinstance(stock, dict) else None
            target = f"company:{symbol}"
            if not symbol or (target not in nodes and not resolve_endpoint(target, report=False)):
                continue
            edges.append({"source": node_id, "type": "related_company", "target": target})

    for issue in issues:
        logger.warning("지식그래프 검증: %s", issue)
    learned = sum(1 for n in nodes if n.startswith("learned:"))
    themed = sum(1 for n in nodes if n.startswith("theme:"))
    auto = sum(1 for n in nodes if n.startswith(("sector:", "company:", "etf:")))
    logger.info(
        "지식그래프 로드: 노드 %d개(시드 %d·학습 %d·카탈로그 %d·정본자동 %d), 엣지 %d개, 검증 경고 %d건",
        len(nodes), len(nodes) - learned - themed - auto, learned, themed, auto,
        len(edges), len(issues),
    )
    return KnowledgeGraph(nodes, edges, issues)


def get_graph() -> KnowledgeGraph:
    """합성 그래프(캐시). 시드·어휘집 파일이 바뀌면 자동 재로드된다."""
    global _CACHED
    stamp = _mtimes()
    with _CACHE_LOCK:
        if _CACHED is not None and _CACHED[0] == stamp:
            return _CACHED[1]
        graph = _build()
        _CACHED = (stamp, graph)
        return graph


# ─── 공개 진입점 ────────────────────────────────────────────────────────────────


def resolve_sector_from_text(text: str) -> Optional[str]:
    """문장 속 시드 개념(HBM·SMR 등)을 정본 섹터로 결정적으로 해석한다.

    개념이 없거나, 여러 개념이 서로 다른 섹터를 가리키면 None(기존 체인 폴백).
    term_grounding.resolve_sector의 ①b 단계로 배선된다."""
    graph = get_graph()
    concepts = graph.find_concepts(text)
    if not concepts:
        logger.info("KG 섹터 해석: 질의=%r → 매치된 개념 없음", _log_preview(text))
        return None
    per_concept = {n["id"]: graph.resolve_sector(n["id"]) for n in concepts}
    sectors = {s for s in per_concept.values() if s is not None}
    result = next(iter(sectors)) if len(sectors) == 1 else None
    logger.info(
        "KG 섹터 해석: 질의=%r → 개념=%s → 소속 섹터=%s → 결과=%s",
        _log_preview(text), _fmt_concepts(concepts),
        {graph.nodes[nid].get("name", nid): (s or "없음") for nid, s in per_concept.items()},
        result or ("모호(복수 섹터 %s)" % sorted(sectors) if len(sectors) > 1 else "없음"),
    )
    return result


def theme_listed_companies(text: str) -> Optional[dict]:
    """문장 속 테마(시드 개념·검색 학습 용어 공통)의 직접 상장사 목록(FR-STR-071).

    읽기 경로 통합(2026-07-25): 학습 용어도 스캔 인덱스에 포함되므로 어휘집 별도 스캔
    없이 그래프 단일 경로로 인식·해석한다. verified 학습 엣지만 그래프에 합성되므로
    결과는 자동으로 검증분이다(pending은 콘솔 승인 대기). first_known_date 대표값은
    기업별 뉴스 최초 보도일 최솟값, 없으면 학습 노드의 searched_at(시드 개념은 None —
    수동 큐레이션이라 시점 편향 경고 대상이 아니다)."""
    graph = get_graph()
    concepts = graph.find_concepts(text)
    if not concepts:
        logger.info("KG 테마 상장사 조회: 질의=%r → 매치된 개념 없음", _log_preview(text))
        return None
    anchor = concepts[0]
    via = "직접 엣지"
    companies: list[dict] = []
    catalog_hit = False
    # 카탈로그 표기 정합 우선('LCD 부품' 사고 2026-07-27, 시드 앵커 확장 2026-07-27) —
    # 앵커 유형과 무관하게 표기가 정확히 일치하는 카탈로그 테마(네이버 금융>주달
    # 업종/테마→종목)가 있으면 카탈로그 수록 종목이 유니버스 정의다. 사용자 지정
    # 1순위 신뢰 소스: 관련 종목 검색은 네이버 분류가 시드 큐레이션 엣지보다 우선
    # (온디바이스 AI — 시드 2곳 vs 네이버 24곳). 시드 직접 엣지는 카탈로그 정합이
    # 없는 개념(HBM 등 네이버 표기 불일치)의 유니버스 정의로 유지된다.
    # 앵커 동의어도 정합 대상이다 — 시드 'AI'(동의어 인공지능)가 네이버 '지능형로봇/
    # 인공지능(AI)'와 이름만으로는 절대 정합하지 못해 업종 근사(소프트웨어/플랫폼)로
    # 유니버스가 과대해지던 사고(2026-07-27). 동의어는 큐레이션된 표기 변형이므로
    # 의미 해석이 아니라 표기 정합이다.
    seen: set[str] = set()
    for term in [anchor.get("name", "")] + list(anchor.get("synonyms", [])):
        for theme_node in graph.catalog_theme_nodes(term):
            for c in graph.listed_companies(theme_node["id"]):
                if c["symbol"] not in seen:
                    seen.add(c["symbol"])
                    companies.append(c)
    if companies:
        catalog_hit = True
        via = "카탈로그 표기 정합"
    if not companies:
        companies = graph.listed_companies(anchor["id"])
    if not companies and anchor.get("category") == "learned":
        # 학습 용어 한정 폴백('bts 관련주' 사고 2026-07-25) — 직접 상장사가 검증되지
        # 않았어도 verified 개념 엣지 1홉 너머의 상장사를 후보로 쓴다. 시드·카탈로그
        # 앵커는 큐레이션이 직접 엣지를 책임지므로 기존 동작(직접 엣지만)을 유지한다.
        companies = graph.listed_companies_via_concepts(anchor["id"])
        via = "개념 1홉 폴백"
    if not companies:
        logger.info(
            "KG 테마 상장사 조회: 질의=%r → 앵커=%s[%s](%s) → 연결된 상장사 없음",
            _log_preview(text), anchor.get("name"), anchor["id"],
            anchor.get("category", "seed"),
        )
        return None
    dates = sorted(c["first_known_date"] for c in companies if c["first_known_date"])
    # 카탈로그 정합은 큐레이션 분류라 시점 편향 경고 대상이 아니다(시드 개념과 동일).
    first = dates[0] if dates else (
        None if catalog_hit else ((anchor.get("searched_at") or "")[:10] or None)
    )
    logger.info(
        "KG 테마 상장사 조회: 질의=%r → 앵커=%s[%s](%s) → %s로 상장사 %d곳=%s, 최초 보도일=%s",
        _log_preview(text), anchor.get("name"), anchor["id"],
        anchor.get("category", "seed"), via, len(companies),
        _fmt_companies(companies), first,
    )
    return {"term": anchor.get("name"), "companies": companies, "first_known_date": first}


def theme_backtest_companies(text: str) -> Optional[dict]:
    """백테스트 대상 제안용 테마 상장사 — 되묻기(FR-STR-071)·빌더 전용 확장 뷰.

    theme_listed_companies(정밀 목록 — 직접 엣지 우선, 이웃 개념 희석 금지)를 기본으로
    하되, 학습 앵커는 Concept Universe(FR-STR-072) 결정론 선정으로 확장한다 — 'bts 관련
    종목' 사고 2차(2026-07-25): 직접 학습 엣지 2곳(신세계·하이브)만으로는 컨셉 유니버스를
    대표하지 못했다(기획사 1홉·지분 관계 전부 누락). 기본 임계(0.5) 이상 선정만 싣는다 —
    최소 크기 완화 편입(score<0.5)을 백테스트 대상 제안에 섞지 않는다. 시드·카탈로그
    앵커는 큐레이션 직접 엣지가 유니버스 정의라 확장하지 않는다(지분 홉 노이즈 차단 —
    HBM 되묻기에 지주·계열 편입 방지). first_known_date는 직접 학습 엣지의 뉴스 보도일을
    심볼 매칭으로 이월해 시점 편향 경고를 유지한다."""
    base = theme_listed_companies(text)
    graph = get_graph()
    concepts = graph.find_concepts(text)
    anchor = concepts[0] if concepts else None
    if anchor is None or anchor.get("category") != "learned":
        if anchor is not None:
            logger.info(
                "KG 백테스트 테마 확장: 앵커=%s[%s](%s) → 학습 앵커 아님, 직접 목록 유지",
                anchor.get("name"), anchor["id"], anchor.get("category", "seed"),
            )
        return base
    if graph.catalog_theme_nodes(anchor.get("name", "")):
        # 카탈로그 표기 정합('LCD 부품' 사고 2026-07-27) — base가 이미 카탈로그 수록
        # 종목이다. Concept Universe 확장은 뉴스 동시언급 학습 엣지·개념 홉을 다시
        # 끌어와 무관 종목(PCB 경유 심텍 등)을 섞으므로 하지 않는다.
        logger.info(
            "KG 백테스트 테마 확장: 앵커=%s[%s] → 카탈로그 표기 정합, 카탈로그 목록 유지(확장 생략)",
            anchor.get("name"), anchor["id"],
        )
        return base
    try:
        from engine.concept_universe import BASE_THRESHOLD, build_concept_universe

        universe = build_concept_universe(text)
    except Exception:  # noqa: BLE001 — 유니버스 빌더 실패가 테마 되묻기를 막으면 안 된다
        logger.warning(
            "KG 백테스트 테마 확장: 앵커=%s[%s] → Concept Universe 빌드 실패, 직접 목록 유지",
            anchor.get("name"), anchor["id"], exc_info=True,
        )
        return base
    if not universe:
        logger.info(
            "KG 백테스트 테마 확장: 앵커=%s[%s] → Concept Universe 없음, 직접 목록 유지",
            anchor.get("name"), anchor["id"],
        )
        return base
    picked = [s for s in universe["stocks"] if s["score"] >= BASE_THRESHOLD]
    if not picked:
        logger.info(
            "KG 백테스트 테마 확장: 앵커=%s[%s] → 기본 임계(%.2f) 이상 선정 없음, 직접 목록 유지",
            anchor.get("name"), anchor["id"], BASE_THRESHOLD,
        )
        return base
    direct = {c["symbol"]: c for c in (base["companies"] if base else [])}
    companies = [
        {
            "symbol": s["symbol"],
            "name": s["name"],
            "support": direct.get(s["symbol"], {}).get("support", 1),
            "first_known_date": direct.get(s["symbol"], {}).get("first_known_date"),
        }
        for s in picked
    ]
    dates = sorted(c["first_known_date"] for c in companies if c["first_known_date"])
    first = (
        dates[0] if dates
        else (base or {}).get("first_known_date")
        or ((anchor.get("searched_at") or "")[:10] or None)
    )
    logger.info(
        "KG 백테스트 테마 확장: 앵커=%s[%s] → 직접 %d곳을 Concept Universe로 확장, 상장사 %d곳=%s, 최초 보도일=%s",
        anchor.get("name"), anchor["id"], len(direct), len(companies),
        _fmt_companies(companies), first,
    )
    return {"term": anchor.get("name"), "companies": companies, "first_known_date": first}


def related_universe(text: str, max_depth: int = 2) -> Optional[dict]:
    """문장 속 개념을 찾아 관련 섹터·상장기업·ETF·개념을 관계 근거(via)와 함께 펼친다.

    백테스트 유니버스 후보 데이터(객관적 관계 표시)이며 추천이 아니다. 개념이 없으면 None."""
    graph = get_graph()
    concepts = graph.find_concepts(text)
    if not concepts:
        logger.info("KG 관련 유니버스: 질의=%r → 매치된 개념 없음", _log_preview(text))
        return None
    anchor = concepts[0]
    expansion = graph.expand(anchor["id"], max_depth=max_depth)
    logger.info(
        "KG 관련 유니버스: 질의=%r → 앵커=%s[%s], 깊이 %d 확장 → 섹터=%s / 상장사 %d곳=%s / ETF %d개=%s / 개념 %d개=%s",
        _log_preview(text), anchor.get("name"), anchor["id"], max_depth,
        _fmt_items([s["name"] for s in expansion["sectors"]]),
        len(expansion["companies"]),
        _fmt_companies(expansion["companies"]),
        len(expansion["etfs"]),
        _fmt_companies(expansion["etfs"]),
        len(expansion["concepts"]),
        _fmt_items([c["name"] for c in expansion["concepts"]]),
    )
    return {"concept": anchor, **expansion}
