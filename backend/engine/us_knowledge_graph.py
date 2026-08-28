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

# 회사 앵커 관련주에 큐레이션 동료를 얹을 때의 응집도 하한(2026-08-29).
# 앵커와 같은 GICS 산업을 공유하는 구성 비율이 이보다 낮은 테마는 '대표 테마'가
# 아니다 — 실측: NVDA→AI 반도체 0.86 · JPM→대형 은행 0.60 · LLY→헬스케어 대형주
# 0.43 · TSLA→전기차·자율주행 0.40 이 통과하고, 동료 테마가 없는 AAPL의 최고값
# 0.03(AI 빅데이터 30종)은 걸린다. 하한이 없으면 '애플 관련주'가 30종으로 번진다.
_PEER_THEME_MIN_COHESION = 0.30

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
    """별칭 정규화 키 — 공백·하이픈 제거·소문자. 정확 일치 전용(부분 매칭은 오폭원).

    하이픈은 공백과 같은 **낱말 구분자**로 본다. 영어 레인이 복합어를 하이픈으로 묶어
    내놓기 때문에("humanoid-robotics", "GLP-1 obesity-drug", "data-center power
    infrastructure") 하이픈을 남기면 같은 테마가 표기 하나로 카탈로그를 빗나간다
    (2026-08-27 실측: /us 영어 게이트에서 테마 6건이 이 이유로 미해석 → 공시 학습으로
    새고, 그중 실패분이 원장에 남아 재시도까지 막혔다). 정규화이지 해석이 아니다 —
    양쪽(정본 별칭·조회어)이 같은 규칙을 통과하므로 짝이 어긋나지 않는다.
    충돌 위험은 별칭 충돌 금지 테스트가 감시한다."""
    return (text or "").strip().lower().replace(" ", "").replace("-", "")


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
        막는다(콘솔 탐색·향후 GICS 필터 기반용 레이어일 뿐 해석에 불참).

        회사 앵커 관련주(related:)도 제외한다 — 이 축의 조회는 앵커 티커로 하지
        표기 별칭으로 하지 않는다(resolve_company_related). 별칭을 색인에 넣으면
        'Nvidia 관련주'와 'nvidia Related Stock'의 표기 차이가 곧 미스가 된다."""
        index: dict[str, str] = {}
        for node_id, node in self.nodes.items():
            if node_id.startswith(("company:", "etf:", "sector:", "industry:", "related:")):
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

    def company_industry(self, symbol: str) -> Optional[str]:
        """회사의 GICS 산업 노드 id — 대표 테마 판정용(해석에는 쓰지 않는다)."""
        for e in self._out.get(f"company:{symbol}", []):
            target = e.get("target", "")
            if target.startswith("industry:"):
                return target
        return None

    def representative_theme(self, symbol: str) -> Optional[str]:
        """앵커가 속한 테마 중 **앵커를 가장 잘 대표하는** 노드 id | None.

        회사 앵커 관련주(resolve_company_related)를 큐레이션으로 보강할 때, 앵커가
        여러 테마에 걸쳐 있으면 어느 테마의 동료를 얹을지 골라야 한다. NVDA는 AI
        반도체·빅테크·휴머노이드 로봇·로봇 자동화·AI 빅데이터 5곳에 속하는데,
        '엔비디아 관련주'로 사람이 떠올리는 동료는 반도체 쪽이다.

        판정은 **앵커와 같은 GICS 산업을 공유하는 구성 비율**(응집도)로 한다 —
        구성 수가 가장 적은 테마를 고르면 NVDA가 휴머노이드 로봇(6종)으로 빠져
        AVGO·MRVL을 놓친다(2026-08-29 실측). 동률이면 좁은 테마, 그다음 id 사전순
        (결정성). GICS·ETF·회사·회사앵커 노드는 후보가 아니다.
        """
        anchor_industry = self.company_industry(symbol)
        if anchor_industry is None:
            return None
        best: Optional[tuple[float, int, str]] = None
        for e in self._in.get(f"company:{symbol}", []):
            if e["type"] not in _COMPANY_EDGE_TYPES:
                continue
            source = e["source"]
            if source.startswith(("company:", "etf:", "sector:", "industry:", "related:")):
                continue
            members = self.companies(source)
            peers = [m for m in members if m != symbol]
            if not peers:
                continue  # 앵커 혼자인 테마엔 얹을 동료가 없다
            same = sum(1 for m in peers if self.company_industry(m) == anchor_industry)
            cohesion = same / len(peers)
            if cohesion < _PEER_THEME_MIN_COHESION:
                continue
            # 응집도 내림차순 → 좁은 테마 → id 사전순
            key = (-cohesion, len(members), source)
            if best is None or key < best:
                best = key
        return best[2] if best else None


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
        # 회사 앵커 관련주는 테마가 아니라 **관계 집합**이다 — 별도 id·범주로 세우고
        # 테마 색인에서 격리한다(_build_theme_index). 조회는 앵커 티커로 한다.
        _is_related = entry.get("kind") == "company_related"
        node_id = f"related:{entry.get('anchor')}" if _is_related else f"learned:{key}"
        if node_id in nodes:
            continue
        nodes[node_id] = {
            "id": node_id,
            "name": entry.get("term", key),
            "category": "company_related" if _is_related else "learned_theme",
            "synonyms": [entry.get("term", key)],
            **({"anchor": entry.get("anchor")} if _is_related else {}),
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
        for peeled in _group_suffix_peels(base):
            candidates.append(peeled)
    return candidates


def _plural_variants(candidates: list[str]) -> list[str]:
    """영어 단·복수 표기 변형 — **조회 전용** 추가 후보(정체성 표기가 아니다).

    분류 registry가 이미 허용하는 것과 같은 계약이다. 정본은 복수로 적히는 일이
    흔한데("obesity drugs") 입력은 범주 접미를 벗기면서 단수가 된다
    ("GLP-1 obesity-drug stocks" → "GLP-1 obesity-drug") — 2026-08-27 실측: 이 한 글자
    때문에 카탈로그에 있는 테마가 공시 학습으로 새고 되묻기로 끝났다(게이트 88번).

    theme_term_candidates에 섞지 않는 이유: 그 목록의 **마지막 항목이 곧 테마 정체성**
    (normalize_theme_term — 학습 이름·질의어)이라, 변형이 꼬리에 붙으면 'Moderna'가
    'Modernas'로 학습되고 개별 기업명 차단 게이트까지 빗나간다(실측 회귀).
    빗나간 변형은 정확 일치에 실패해 조용히 사라진다(오폭이 아니라 미스)."""
    out: list[str] = []
    for base in candidates:
        head, _, last = base.rpartition(" ")
        word = last or base
        if len(word) <= 3:
            continue
        variant = word[:-1] if word.endswith("s") else word + "s"
        candidate = f"{head} {variant}".strip()
        if candidate not in candidates and candidate not in out:
            out.append(candidate)
    return out


# 범주(집합) 접미 — '관련주'와 그 영어 판. 표현이 **한 종목**이 아니라 **종목의 집합**을
# 가리킨다는 표기 신호다. 시장 접두('미국'·'US')와 달리 정체성이 아니라 범주를 바꾼다.
_GROUP_SUFFIX_EN_RE = re.compile(
    r"[\s-]+(?:related|linked|stocks?|names?|companies|shares|sector|theme)$",
    re.IGNORECASE,
)
_GROUP_SUFFIX_KR = ("관련주", "테마")


def _group_suffix_peels(base: str) -> list[str]:
    """범주 접미를 한 겹씩 벗긴 표기들(벗길 것이 없으면 빈 목록)."""
    peels: list[str] = []
    for suffix in _GROUP_SUFFIX_KR:
        if base.endswith(suffix) and len(base) > len(suffix):
            peels.append(base[: -len(suffix)].strip())
    stripped = base
    while True:  # "crypto-related stocks" → "crypto-related" → "crypto"
        trimmed = _GROUP_SUFFIX_EN_RE.sub("", stripped)
        if trimmed == stripped or not trimmed:
            break
        stripped = trimmed.strip()
        peels.append(stripped)
    return peels


def has_group_suffix(term: Optional[str]) -> bool:
    """표현이 범주 접미('관련주'·"related stocks")를 달고 있는가 — 순수 표기 판정.

    입력은 LLM/planner가 뽑은 짧은 표현이고 판정은 어미 표기뿐이다(§ 판정 기준:
    표기만 보면 결정 가능 → 정규화). **의미를 읽지 않는다** — 무엇에 관한 집합인지는
    아래 해석 레인(테마 카탈로그·회사 앵커)이 정한다.

    쓰임: 'nvidia Related Stock'을 단일 종목 NVDA로 접는 오분류 차단(2026-08-27 사고).
    시장 접두('미국 애플')는 여기 해당하지 않는다 — 접두는 범주를 바꾸지 않는다."""
    if not term or not isinstance(term, str):
        return False
    return bool(_group_suffix_peels(term.strip()))


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
    # 정확 일치 사다리를 먼저 다 훑고, 그래도 없으면 단·복수 변형까지 본다 — 변형은
    # 조회 전용이라 정체성 표기(normalize_theme_term)를 건드리지 않는다.
    node = None
    for cand in [*candidates, *_plural_variants(candidates)]:
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


def resolve_company_related(term: Optional[str]) -> Optional[tuple[str, list[str]]]:
    """'X 관련주'(X=개별 상장사) → (표시명, 관계 기업 티커) | None. 학습분만.

    조회는 **앵커 티커**로 한다 — 'Nvidia 관련주'와 'nvidia Related Stock'은 같은
    관계 집합이므로 표기를 색인 키로 삼으면 언어별로 갈린다(테마 색인이 related:를
    제외하는 이유). 앵커 확정은 정본 registry 정확 일치이고(us_company_anchor),
    범주 접미가 없는 표현은 이 축이 아니다(단일 종목 지정 소관).

    학습 이력이 없으면 None — 여기서 검색하지 않는다(결정론 조회 계층). 학습은
    호출부의 그라운딩 단계(ground_us_company_related) 소관이다."""
    if not term or not isinstance(term, str) or not has_group_suffix(term):
        return None
    from engine.us_term_grounding import us_company_anchor  # 지연 import(순환 방지)

    anchor = us_company_anchor(normalize_theme_term(term))
    if anchor is None:
        return None
    graph = get_graph()
    node = graph.nodes.get(f"related:{anchor[0]}")
    if node is None:
        return None
    symbols = graph.companies(node["id"])
    if not symbols:
        return None
    # 학습분에 **앵커 대표 테마의 동료**를 얹는다(2026-08-29 사용자 결정).
    # 공시 전문검색은 '자기 공시에 앵커를 적은 회사'(고객·파트너·의존 기업)를
    # 찾으므로, 나란히 경쟁하는 동료는 후보에 오르지도 않는다 — 'Nvidia 관련주'
    # 후보 40곳에 AVGO·MRVL·TSM·MU·SMCI가 아예 없었다. 큐레이션은 이미 이들을
    # 'AI 반도체'로 묶어 두고 있었는데 이 축이 보지 않아 조용히 빠졌다.
    # 학습 이력이 있을 때만 얹는다 — 없으면 종전대로 None을 돌려 그라운딩 단계가
    # 학습을 시도한다(결정론 조회 계층이 학습 기회를 가로채지 않는다).
    peer_theme = graph.representative_theme(anchor[0])
    if peer_theme:
        for symbol in graph.companies(peer_theme):
            if symbol not in symbols:
                symbols.append(symbol)
    return (company_related_label(anchor[1]), symbols)


def company_related_label(company_name: str) -> str:
    """앵커 회사명 → 표시 라벨. 원장은 한국어 정본이고 표시는 요청 언어를 따른다.

    us_display_name과 같은 계약 — /us(en) 요약 카드에 'Nvidia 관련주'가 그대로 나가면
    영어 화면에 한국어가 섞인다. 엔진은 심볼만 쓰므로 이 값은 표시 메타데이터다."""
    import ui_language  # 지연 import(엔진 모듈의 요청 컨텍스트 의존 최소화)

    if ui_language.get_ui_language() == "en":
        return f"{company_name}-related stocks"
    return f"{company_name} 관련주"
