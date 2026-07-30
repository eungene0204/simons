"""개념↔종목 관계의 근거·관련도 원장(설계 스펙 § 8.5).

`data/kg-research/*.json`은 사람이 공식 자료를 조사해 남긴 원장이다. 여기엔 각 종목이
그 개념과 **왜** 연결되는지(reason·business_evidence·sources)와 **얼마나 직접적인지**
(relation_type·relevance·relevance_score)가 이미 적혀 있다.

그런데 그 정보가 시드 그래프(`knowledge-graph.json`)로 넘어갈 때 **관계 종류(엣지 타입)와
한 줄 note만 남고 나머지가 사라졌다** — 런타임은 "이 종목이 이 테마에 속한다"만 알 뿐
"직접 생산인지 단순 테마성인지"를 구분할 수 없었다. 이 모듈이 그 간극을 잇는다.

**판정을 새로 하지 않는다.** 원장에 적힌 것을 읽어 엣지에 붙일 뿐이며, 원장에 없는
관계에는 아무것도 붙이지 않는다(근거를 지어내지 않는다).

[규제 안전] 관계 유형은 **과거·현재의 사실**만 담는다. 설계 스펙 § 8.5가 나열한
'정책 수혜 가능성'은 미래 전망이라 도입하지 않는다 — 근거로 표기하는 순간 그것은
객관적 데이터 표시가 아니라 전망 제공이 된다(CLAUDE.md 규제 안전 원칙).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("engine.kg_research")

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_RESEARCH_DIR = _BASE_DIR / "data" / "kg-research"

# 원장의 관련도 등급 → 이 관계가 얼마나 직접적인가. 시드 그래프에는 Core/Strong만
# 편입되지만(docs/kg_concept_builder.md § 11), 등급 자체는 그대로 전달한다.
_RELEVANCE_ORDER = ("Core", "Strong", "Moderate", "Weak", "Unverified")

# 원장이 실제로 쓰는 관계 유형(2026-07-30 전수 확인: Producer 104·Supplier 15·
# Related 6·Investor 3·Infrastructure 1). 목록을 먼저 정하고 데이터를 맞추지 않는다 —
# 원장이 정본이다. 전부 과거·현재의 사실 서술이며 전망은 없다.
_KNOWN_RELATION_TYPES = frozenset({
    "Producer",        # 직접 생산·개발
    "Supplier",        # 핵심 부품·소재·장비 공급
    "Investor",        # 지분 관계
    "Infrastructure",  # 산업 인프라 제공(간접 연관)
    "Related",         # 그 밖의 사업 연관 — 직접성이 낮다
})

# 직접적인 사업 관계로 볼 유형. 설계 스펙 § 8.5의 "직접적인 사업 관계와 단순 테마성
# 관계를 구분한다"가 이 경계다. Related·Infrastructure는 사실이되 직접 생산·공급이
# 아니므로 직접 관계로 세지 않는다.
_DIRECT_RELATION_TYPES = frozenset({"Producer", "Supplier"})


def _relation_record(stock: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """원장의 종목 한 건 → 엣지에 붙일 관계 메타. 필수 값이 없으면 None."""
    symbol = (stock.get("ticker") or "").strip()
    if not symbol:
        return None
    relation = (stock.get("relation_type") or "").strip()
    relevance = (stock.get("relevance") or "").strip()
    record: Dict[str, Any] = {
        # 원장 어휘를 그대로 쓴다 — 목록 밖 값도 버리지 않고 전달한다(원장이 정본이고,
        # 여기서 걸러내면 새 관계 유형을 추가할 때 조용히 사라진다). 다만 알려진
        # 유형인지는 표시해 소비자가 판단할 수 있게 한다.
        "relation_type": relation or None,
        "relation_known": relation in _KNOWN_RELATION_TYPES,
        # 직접 사업 관계인가, 그 밖의 연관인가(스펙 § 8.5의 구분).
        "direct": relation in _DIRECT_RELATION_TYPES,
        "relevance": relevance or None,
        "relevance_score": stock.get("relevance_score"),
        # 근거는 사실 서술이다(무엇을 만드는가·매출 비중·공시). 전망·평가가 아니다.
        "reason": (stock.get("reason") or "").strip() or None,
        "business_evidence": (stock.get("business_evidence") or "").strip() or None,
        "verified": bool(stock.get("verified")),
        "source_count": len(stock.get("sources") or []),
    }
    return record


def _load() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """(concept_id, symbol) → 관계 메타. 원장 파일이 없으면 빈 인덱스."""
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    if not _RESEARCH_DIR.is_dir():
        return index
    for path in sorted(_RESEARCH_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # 원장 한 건이 깨져도 나머지 관계는 살린다 — 근거 표기는 부가 정보다.
            logger.warning("관계 원장 로드 실패(건너뜀) | path=%s err=%r", path.name, exc)
            continue
        concept_id = ((data.get("concept") or {}).get("id") or path.stem).strip()
        for stock in data.get("stocks") or []:
            if not isinstance(stock, dict):
                continue
            record = _relation_record(stock)
            if record is not None:
                index[(concept_id, record_symbol(stock))] = record
    return index


def record_symbol(stock: Dict[str, Any]) -> str:
    return (stock.get("ticker") or "").strip()


_cache: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None
_cache_mtime: Optional[float] = None


def _dir_mtime() -> float:
    """원장 디렉터리의 최신 변경 시각 — 그래프 캐시와 같은 무효화 방식."""
    if not _RESEARCH_DIR.is_dir():
        return 0.0
    try:
        return max(
            [os.path.getmtime(_RESEARCH_DIR)]
            + [os.path.getmtime(p) for p in _RESEARCH_DIR.glob("*.json")]
        )
    except OSError:
        return 0.0


def relation_index() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """관계 메타 인덱스(캐시). 원장이 바뀌면 다시 읽는다."""
    global _cache, _cache_mtime
    mtime = _dir_mtime()
    if _cache is None or _cache_mtime != mtime:
        _cache = _load()
        _cache_mtime = mtime
        logger.info("관계 원장 로드 | 관계 %d건", len(_cache))
    return _cache


def lookup(concept_id: str, symbol: str) -> Optional[Dict[str, Any]]:
    """이 개념↔종목 관계의 근거·관련도. 원장에 없으면 None(지어내지 않는다)."""
    return relation_index().get((concept_id, symbol))


def relevance_rank(relevance: Optional[str]) -> int:
    """관련도 등급의 순서(작을수록 직접적). 목록 밖·없음은 가장 뒤."""
    try:
        return _RELEVANCE_ORDER.index(relevance or "")
    except ValueError:
        return len(_RELEVANCE_ORDER)


def _reset_for_tests() -> None:
    global _cache, _cache_mtime
    _cache = None
    _cache_mtime = None
