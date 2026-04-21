"""
CandidateGenerator — deterministic template × param-grid enumeration.

입력: 선택된 템플릿, 유니버스, max_candidates, seed
출력: 중복 제거된 candidate 리스트 (DSL dict + canonical SHA256 hash)

재현성: 동일 seed + 동일 templates + 동일 universes → 동일 후보 시퀀스.
LLM 사용 금지 (환각/프롬프트 인젝션 차단). 결정론적 템플릿만.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from engine.strategy_converter import to_backtest_request
from research.templates import TEMPLATE_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class Candidate:
    template: str
    dsl_hash: str
    backtest_request: Dict[str, Any]
    parsed_dsl: Dict[str, Any]  # serialized ParsedStrategy for audit


def _canonical_hash(payload: Dict[str, Any]) -> str:
    """Canonical SHA256 of DSL: sort keys, no whitespace."""
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class CandidateGenerator:
    def __init__(
        self,
        templates: Sequence[str],
        universes: Sequence[Sequence[str]],
        seed: int = 42,
    ):
        unknown = [t for t in templates if t not in TEMPLATE_REGISTRY]
        if unknown:
            raise ValueError(f"Unknown templates: {unknown}. Available: {list(TEMPLATE_REGISTRY)}")
        self.templates = list(templates)
        self.universes = [list(u) for u in universes]
        self.seed = seed

    def generate(self, max_n: int = 200) -> List[Candidate]:
        """Enumerate (template × grid × universe), dedup by canonical hash, cap to max_n."""
        rng = random.Random(self.seed)
        seen: set[str] = set()
        candidates: List[Candidate] = []

        # Deterministic order: sort templates first, then expand grids
        expansion: List[tuple[str, Dict[str, Any], List[str]]] = []
        for tmpl_name in sorted(self.templates):
            tmpl = TEMPLATE_REGISTRY[tmpl_name]
            for params in tmpl.PARAM_GRID:
                for uni in self.universes:
                    expansion.append((tmpl_name, dict(params), list(uni)))

        rng.shuffle(expansion)  # seeded shuffle for variety but reproducible

        for tmpl_name, params, uni in expansion:
            if len(candidates) >= max_n:
                break
            tmpl = TEMPLATE_REGISTRY[tmpl_name]
            try:
                parsed = tmpl.build(params, uni)
            except ValueError as e:
                logger.debug(f"[Generator] {tmpl_name} skip: {e}")
                continue

            try:
                bt_req = to_backtest_request(parsed)
            except Exception as e:
                logger.warning(f"[Generator] {tmpl_name} convert failed: {e}")
                continue

            # Hash on the canonical DSL (without volatile symbols list)
            canonical_payload = {
                "template": tmpl_name,
                "entry": bt_req.get("entry"),
                "exit": bt_req.get("exit"),
                "risk": _hashable_risk(bt_req.get("risk", {})),
                "universe": bt_req.get("universe_id"),
            }
            h = _canonical_hash(canonical_payload)
            if h in seen:
                continue
            seen.add(h)

            candidates.append(
                Candidate(
                    template=tmpl_name,
                    dsl_hash=h,
                    backtest_request=bt_req,
                    parsed_dsl=parsed.model_dump(mode="json"),
                )
            )

        logger.info(f"[Generator] produced {len(candidates)} unique candidates from {len(expansion)} expansions")
        return candidates


def _hashable_risk(risk: Dict[str, Any]) -> Dict[str, Any]:
    """Strip volatile fields (init_cash is per-run, not a strategy property)."""
    exclude = {"init_cash"}
    return {k: v for k, v in sorted(risk.items()) if k not in exclude}
