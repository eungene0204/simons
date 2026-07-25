"""Concept Universe Builder — 개념 중심 백테스트 유니버스 결정론 생성(FR-STR-072).

업종(Sector) 유니버스가 아니다 — Concept(테마·기술·제품·인물 IP 등)와 사업적 관련이
검증된 종목 집합이다. "BTS 관련주"가 미디어/엔터 업종 전체가 되면 안 되고, 반대로
관련 기업 1곳만으로 축소되어도 안 된다.

관련도(score)는 LLM 자기평가가 아니라 KG에 이미 축적된 근거에서 결정론 산출한다
(FR-STR-070b 신뢰도 원칙 — 동일 Concept엔 항상 동일 결과, 재현 가능):
  - 시드 엣지: note의 원장 점수 "(Core 95)"/"(Producer/Strong 72)" → 0.95/0.72.
    점수 표기가 없으면 0.70 — 시드 편입 규약이 Core/Strong만 허용하므로 최소 등급.
  - 학습 verified related_company: 0.55 + 0.05×support(출처 수), 상한 0.80.
    콘솔 승인(수동 verified)도 같은 식 — 사람 검토가 출처 1건을 보증한 것.
  - 개념 1홉 경유(anchor –verified→ 개념 –엣지→ 종목): 그 종목 점수 × 0.85(거리 감쇠).
  - 카탈로그(주달 테마): 0.45 — 기본 임계(0.5) 미만이라 완화 단계에서만 편입
    (카탈로그 최하위 신뢰 계층 관례).
pending/rejected 엣지는 어느 층에도 불참(검증 원칙 — 그래프 합성 게이트와 동일).

선정 규칙: score >= 0.5 기본. 그 결과가 MIN_SIZE(10) 미만이면 점수순으로 floor(0.30)
이상 후보를 추가해 10개까지 완화하되, 후보 자체가 부족하면 있는 만큼만 반환한다 —
'최소 10개 보장'을 위해 근거 없는 종목을 지어내는 것은 억지 테마주 제외 원칙과
모순이므로 하지 않는다. MAX_SIZE(30) 초과분은 점수순 상위 30개만.

[규제 안전] score·이유는 공시·IR·검색 출처 등 객관적 관계 근거의 표시일 뿐이며
추천·전망이 아니다. 정렬은 관련도 기준이지 우열·수익성 판단이 아니다.
"""

from __future__ import annotations

import re
from typing import Optional

from engine.knowledge_graph import get_graph

MIN_SIZE = 10
MAX_SIZE = 30
BASE_THRESHOLD = 0.5
RELAX_FLOOR = 0.30

_SEED_DEFAULT_SCORE = 0.70          # 시드 편입 규약상 최소 등급(Strong)
_LEARNED_BASE, _LEARNED_STEP, _LEARNED_CAP = 0.55, 0.05, 0.80
_HOP_DECAY = 0.85
_CATALOG_SCORE = 0.45

# 원장 점수 표기 — "(Core 95)"·"(Producer/Strong 72)"·"(Supplier/Core 88)" 등
_NOTE_SCORE_RE = re.compile(r"(?:Core|Strong)\s*(\d{2,3})")


def _score_from_note(note: Optional[str]) -> float:
    """시드 엣지 note의 원장 점수를 0~1 실수로 — 표기가 없으면 시드 최소 등급."""
    m = _NOTE_SCORE_RE.search(note or "")
    if not m:
        return _SEED_DEFAULT_SCORE
    return min(int(m.group(1)), 100) / 100.0


def _strip_score_suffix(note: str) -> str:
    """이유 표기용 — note 끝의 '(Core 95)'류 점수 괄호를 제거한다(점수는 별도 필드)."""
    return re.sub(r"\s*\((?:[A-Za-z/]+\s*)?(?:Core|Strong)\s*\d{2,3}\)\s*$", "", note).strip()


def _learned_score(support) -> float:
    n = support if isinstance(support, int) and support > 0 else 1
    return round(min(_LEARNED_BASE + _LEARNED_STEP * n, _LEARNED_CAP), 4)


def _company_candidates_of(graph, node_id: str, node_name: str) -> list[dict]:
    """노드의 직접(깊이 1) 상장사 후보 — 엣지 근거에서 점수·이유를 결정론 산출."""
    out: list[dict] = []
    for edge, other in graph.neighbor_edges(node_id):
        if not other.startswith("company:"):
            continue
        symbol = other.split(":", 1)[1]
        name = graph.nodes.get(other, {}).get("name", symbol)
        note = edge.get("note")
        support = edge.get("support")
        if node_id.startswith("theme:"):
            score = _CATALOG_SCORE
            reason = f"'{node_name}' 테마 카탈로그 수록 종목"
        elif support is not None:  # 학습 엣지(로더가 support를 실어 나름)
            score = _learned_score(support)
            reason = f"검색 출처 {support}건에서 '{node_name}'와(과) 함께 언급 확인"
        else:  # 시드 엣지(수동 큐레이션 원장)
            score = _score_from_note(note)
            reason = _strip_score_suffix(note) if note else f"'{node_name}' 등록 관계({edge.get('type')})"
        out.append({"symbol": symbol, "name": name, "score": score, "reason": reason})
    return out


def _collect_candidates(graph, anchor: dict) -> list[dict]:
    """직접 상장사 + verified 개념 1홉 경유 상장사(감쇠) — 심볼별 최고 점수만 유지."""
    anchor_id = anchor["id"]
    best: dict[str, dict] = {}

    def _keep(c: dict) -> None:
        prev = best.get(c["symbol"])
        if prev is None or c["score"] > prev["score"]:
            best[c["symbol"]] = c

    for c in _company_candidates_of(graph, anchor_id, anchor.get("name", anchor_id)):
        _keep(c)
    for edge, other in graph.neighbor_edges(anchor_id):
        if other.startswith(("company:", "etf:", "sector:")):
            continue
        concept_name = graph.nodes.get(other, {}).get("name", other)
        for c in _company_candidates_of(graph, other, concept_name):
            _keep({
                **c,
                "score": round(c["score"] * _HOP_DECAY, 4),
                "reason": f"{concept_name} 경유 — {c['reason']}",
            })
    return list(best.values())


def _select(candidates: list[dict]) -> tuple[list[dict], float]:
    """선정 규칙 적용 → (선정 목록, 적용 임계). 정렬은 점수 내림차순, 동점은 심볼 오름차순
    (재현성 — 동일 입력엔 항상 동일 출력)."""
    ranked = sorted(candidates, key=lambda c: (-c["score"], c["symbol"]))
    picked = [c for c in ranked if c["score"] >= BASE_THRESHOLD]
    threshold = BASE_THRESHOLD
    if len(picked) < MIN_SIZE:
        for c in ranked[len(picked):]:
            if c["score"] < RELAX_FLOOR or len(picked) >= MIN_SIZE:
                break
            picked.append(c)
            threshold = c["score"]
    return picked[:MAX_SIZE], threshold


def build_concept_universe(concept_text: str) -> Optional[dict]:
    """Concept 텍스트 → 개념 중심 유니버스(없으면 None — 그래프가 모르는 개념).

    반환: {concept, concept_id, size, threshold_used, relaxed, stocks:[{symbol, name,
    score, reason}]}. threshold_used < 0.5(relaxed=True)는 최소 크기 확보를 위해
    완화가 일어났다는 재현성 메타데이터다."""
    graph = get_graph()
    concepts = graph.find_concepts(concept_text)
    if not concepts:
        return None
    anchor = concepts[0]
    candidates = _collect_candidates(graph, anchor)
    if not candidates:
        return None
    stocks, threshold = _select(candidates)
    return {
        "concept": anchor.get("name", anchor["id"]),
        "concept_id": anchor["id"],
        "size": len(stocks),
        "threshold_used": threshold,
        "relaxed": threshold < BASE_THRESHOLD,
        "stocks": stocks,
    }
