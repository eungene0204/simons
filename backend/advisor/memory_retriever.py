"""
Context builder for RAG + Experience Memory advisor flows.

The first implementation is repository-agnostic: callers pass strategy rows and
experience rows loaded from any storage. Later phases can wire this to Prisma or
another vector store without changing the retrieval semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from .similarity import search_similar_strategies, summarize_similarity_results
from .strategy_identity import canonical_strategy_string, strategy_id_for


def _experience_strategy_id(row: Dict[str, Any]) -> str:
    return str(row.get("strategy_id") or row.get("strategyId") or row.get("strategyHash") or "")


def _case_metrics(row: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = row.get(key) or row.get(key.replace("_", ""))
    return value if isinstance(value, dict) else {}


def build_retrieved_cases(
    similar_strategy_ids: Sequence[str],
    experiences: Sequence[Dict[str, Any]],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    id_rank = {strategy_id: index for index, strategy_id in enumerate(similar_strategy_ids)}
    matched = [
        row
        for row in experiences
        if _experience_strategy_id(row) in id_rank
    ]
    matched.sort(key=lambda row: id_rank[_experience_strategy_id(row)])

    cases: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in matched:
        strategy_id = _experience_strategy_id(row)
        if strategy_id in seen:
            continue
        seen.add(strategy_id)
        cases.append({
            "case_strategy_id": strategy_id,
            "similarity_reason": row.get("similarity_reason") or "RAG 검색으로 선택된 유사 전략입니다.",
            "before_metrics": _case_metrics(row, "before_backtest"),
            "after_metrics": _case_metrics(row, "after_backtest"),
            "lesson": row.get("lesson") or "",
            "advice_success": (row.get("evaluation") or {}).get("advice_success")
            if isinstance(row.get("evaluation"), dict)
            else None,
            "retrieval_categories": row.get("retrieval_categories") or [],
        })
        if len(cases) >= limit:
            break
    return cases


def retrieve_memory_context(
    user_prompt: str,
    strategy_dsl: Dict[str, Any],
    strategy_cases: Sequence[Dict[str, Any]],
    experiences: Sequence[Dict[str, Any]],
    top_k: int = 5,
) -> Dict[str, Any]:
    strategy_id = strategy_id_for(strategy_dsl)
    similar = search_similar_strategies(user_prompt, strategy_dsl, strategy_cases, top_k=top_k)
    similar_ids = [item.strategy_id for item in similar]
    retrieved_cases = build_retrieved_cases(similar_ids, experiences, limit=top_k)

    top_score = similar[0].combined_score if similar else 0.0
    top_structure_score = similar[0].structure_score if similar else 0.0
    confidence = "low"
    if retrieved_cases and top_score >= 0.65 and top_structure_score >= 0.55:
        confidence = "high"
    elif retrieved_cases and top_score >= 0.45 and top_structure_score >= 0.40:
        confidence = "medium"
    data_sufficiency = "sufficient" if retrieved_cases and confidence != "low" else "insufficient"

    return {
        "strategy_id": strategy_id,
        "canonical_strategy_dsl": canonical_strategy_string(strategy_dsl),
        "similar_strategy_ids": similar_ids,
        "similar_strategies": summarize_similarity_results(similar),
        "retrieved_cases": retrieved_cases,
        "confidence": confidence,
        "data_sufficiency": data_sufficiency,
        "search_quality": {
            "matched_count": len(similar),
            "retrieved_count": len(retrieved_cases),
            "top_combined_score": top_score,
            "top_structure_score": top_structure_score,
        },
    }
