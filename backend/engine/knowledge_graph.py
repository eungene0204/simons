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

logger = logging.getLogger("knowledge_graph")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 레포 루트(data/의 부모)
_SEED_PATH = _BASE_DIR / "data" / "knowledge-graph.json"
_LEXICON_PATH = _BASE_DIR / "data" / "term_lexicon.json"
_STOCKS_PATH = _BASE_DIR / "data" / "korea-stocks.json"
_ETF_PATH = _BASE_DIR / "data" / "etf-master.json"

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

    # ── 스캔 인덱스(문장 → 개념 노드 결정적 인식) ────────────────────────────────
    def _build_scan_index(self) -> list[tuple[str, str]]:
        """개념 노드의 이름·별칭 → [(정규화 키, node_id)] (긴 키 우선).

        normalize_sector가 이미 해석하는 용어(반도체·AI 등)는 제외한다 — 상류의
        결정적 섹터 인식과 이중 매칭돼 어긋나는 일을 막는다. 자동 생성 노드
        (sector:/company:/etf:)와 학습 노드는 각자 기존 경로(섹터 정규화·종목 인식·
        어휘집 스캔)가 담당하므로 스캔 대상이 아니다."""
        from engine.universe_pit import normalize_sector  # 지연 import(무거운 엔진 모듈)

        index: list[tuple[str, str]] = []
        for node_id, node in self.nodes.items():
            if ":" in node_id or node.get("category") == "learned":
                continue
            for term in [node.get("name", "")] + list(node.get("synonyms", [])):
                key = _norm_key(term)
                if len(key) < 2 or normalize_sector(term):
                    continue
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
    return (mt(_SEED_PATH), mt(_LEXICON_PATH))


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
        }

    stock_names = _stock_names()
    etf_names = _etf_names()

    def resolve_endpoint(ref: str) -> bool:
        """엣지 끝점을 검증하고, 정본 참조(company:/etf:)면 노드를 자동 생성한다."""
        if ref in nodes:
            return True
        if ref.startswith("company:"):
            symbol = ref.split(":", 1)[1]
            if symbol in stock_names:
                nodes[ref] = {"id": ref, "name": stock_names[symbol], "category": "company"}
                return True
            issues.append(f"korea-stocks.json에 없는 종목 참조: {ref}")
            return False
        if ref.startswith("etf:"):
            symbol = ref.split(":", 1)[1]
            if symbol in etf_names:
                nodes[ref] = {"id": ref, "name": etf_names[symbol], "category": "etf"}
                return True
            issues.append(f"etf-master.json에 없는 ETF 참조: {ref}")
            return False
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
        for e in entry.get("edges", []):
            if (
                isinstance(e, dict)
                and e.get("status") == "verified"
                and e.get("type") in EDGE_TYPES
                and e.get("target") in nodes
            ):
                edges.append({"source": node_id, "type": e["type"], "target": e["target"]})

    for issue in issues:
        logger.warning("지식그래프 검증: %s", issue)
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
    sectors = {
        sector
        for node in graph.find_concepts(text)
        if (sector := graph.resolve_sector(node["id"])) is not None
    }
    return next(iter(sectors)) if len(sectors) == 1 else None


def related_universe(text: str, max_depth: int = 2) -> Optional[dict]:
    """문장 속 개념을 찾아 관련 섹터·상장기업·ETF·개념을 관계 근거(via)와 함께 펼친다.

    백테스트 유니버스 후보 데이터(객관적 관계 표시)이며 추천이 아니다. 개념이 없으면 None."""
    graph = get_graph()
    concepts = graph.find_concepts(text)
    if not concepts:
        return None
    anchor = concepts[0]
    expansion = graph.expand(anchor["id"], max_depth=max_depth)
    return {"concept": anchor, **expansion}
