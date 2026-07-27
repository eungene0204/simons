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

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from engine.knowledge_graph import get_graph

from engine.console_logging import console_logger

logger = console_logger("concept_universe", "KG-UNIVERSE")

MIN_SIZE = 10
MAX_SIZE = 30
BASE_THRESHOLD = 0.5
RELAX_FLOOR = 0.30

_SEED_DEFAULT_SCORE = 0.70          # 시드 편입 규약상 최소 등급(Strong)
_LEARNED_BASE, _LEARNED_STEP, _LEARNED_CAP = 0.55, 0.05, 0.80
_HOP_DECAY = 0.85
_CATALOG_SCORE = 0.45
# 지분 관계(회사 홉) 감쇠 — 유니버스 종목의 주주/피출자사(DART 타법인출자현황,
# FR-STR-072b). 0.7이면 부모 점수 0.72 이상만 기본 임계(0.5)를 넘는다 — 재벌
# 지주 관계가 모든 유니버스로 번지지 않게 고점수 부모만 전파하는 자기 제한.
_EQUITY_DECAY = 0.70

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


# ─── 지분 관계 레이어(FR-STR-072b) — DART 타법인출자현황 산출물 ─────────────────
# KG 그래프 본체에 합성하지 않고 여기서만 읽는다 — related_universe 확장·테마 되묻기
# 등 기존 그래프 소비자의 의미 변화를 차단(수집·소비 범위를 Concept Universe로 한정).

_EQUITY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "kg-equity-edges.json"
_EQUITY_CACHE: Optional[tuple[float, dict]] = None


def _equity_neighbors_map() -> dict:
    """symbol → [{symbol, name, note, role}] 양방향 인덱스(mtime 캐시).

    A –invests_in→ B(A가 B 지분 보유): B의 이웃엔 A(role=주주), A의 이웃엔 B(role=출자사)."""
    global _EQUITY_CACHE
    try:
        mtime = os.path.getmtime(_EQUITY_PATH)
    except OSError:
        return {}
    if _EQUITY_CACHE is not None and _EQUITY_CACHE[0] == mtime:
        return _EQUITY_CACHE[1]
    try:
        data = json.loads(_EQUITY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    index: dict[str, list[dict]] = {}
    for e in data.get("edges", []):
        src, tgt = e.get("source", ""), e.get("target", "")
        if not (src.startswith("company:") and tgt.startswith("company:")):
            continue
        s_sym, t_sym = src.split(":", 1)[1], tgt.split(":", 1)[1]
        note = e.get("note", "")
        index.setdefault(t_sym, []).append({"symbol": s_sym, "role": "주주", "note": note})
        index.setdefault(s_sym, []).append({"symbol": t_sym, "role": "출자사", "note": note})
    _EQUITY_CACHE = (mtime, index)
    return index


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

    # 지분 관계 회사 홉(FR-STR-072b) — 위 후보들의 주주/피출자사를 ×감쇠로 1단계만
    # 편입한다(체이닝 금지 — 스냅샷 순회). '넷마블(하이브 지분 9.2%)'이 이 경로다.
    equity = _equity_neighbors_map()
    if equity:
        graph_nodes = graph.nodes
        for parent in list(best.values()):
            for rel in equity.get(parent["symbol"], []):
                name = graph_nodes.get(f"company:{rel['symbol']}", {}).get("name")
                if name is None:
                    try:  # 그래프 밖 종목은 정본 마스터에서 — 없으면(상폐 등) 조용히 스킵
                        from stock_analysis.symbol_resolver import resolve_by_symbol
                        ref = resolve_by_symbol(rel["symbol"])
                    except Exception:  # noqa: BLE001 — 마스터 미가용이 조회를 막으면 안 된다
                        ref = None
                    if ref is None:
                        continue
                    name = ref.name
                _keep({
                    "symbol": rel["symbol"], "name": name,
                    "score": round(parent["score"] * _EQUITY_DECAY, 4),
                    "reason": f"{parent['name']} {rel['role']}(공시 근거) — {rel['note']}",
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
        logger.info(
            "Concept Universe: 질의=%r → KG에 매치된 개념 없음",
            " ".join(concept_text.split())[:80],
        )
        return None
    anchor = concepts[0]
    candidates = _collect_candidates(graph, anchor)
    if not candidates:
        logger.info(
            "Concept Universe: 앵커=%s[%s] → 상장사 후보 없음",
            anchor.get("name", anchor["id"]), anchor["id"],
        )
        return None
    stocks, threshold = _select(candidates)
    logger.info(
        "Concept Universe: 앵커=%s[%s] → 후보 %d곳 → 선정 %d곳(임계 %.2f%s): %s",
        anchor.get("name", anchor["id"]), anchor["id"], len(candidates), len(stocks),
        threshold, ", 완화 적용" if threshold < BASE_THRESHOLD else "",
        ", ".join(f"{s['name']}({s['symbol']}) {s['score']:.2f}" for s in stocks),
    )
    return {
        "concept": anchor.get("name", anchor["id"]),
        "concept_id": anchor["id"],
        "size": len(stocks),
        "threshold_used": threshold,
        "relaxed": threshold < BASE_THRESHOLD,
        "stocks": stocks,
    }
