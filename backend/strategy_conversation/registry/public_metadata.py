"""전략 그래프용 공개 지표 메타데이터 — REGISTRY·온톨로지에서 결정론적으로 추출한다.

사용자 화면(읽기 전용 전략 그래프)이 지표 이름·단위·지원 상태·분류를 그리는 데 필요한 공개
필드만 담는다. 관리자 덤프(`concept_ontology.ontology_graph`)와 달리 다음은 **싣지 않는다**:
  - 무결성 위반 목록(issues)과 지표 내부 메모(notes) — 운영 진단 정보
  - 파라미터 default·recommended_value — 사용자가 말하지 않은 값을 채우는 데 쓰이면 안 된다
  - 개념의 동의어·전개 기본 파라미터·설명 — 인터프리터 계약용 내부 정보
사용자 전략·원문은 입력으로 받지 않으며, LLM·검색을 호출하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List

from strategy_conversation.registry import display_labels
from strategy_conversation.registry.concept_ontology import get_ontology
from strategy_conversation.registry.indicator_registry import REGISTRY


def _name_en(spec) -> str:
    """영어 표시명 — display_labels 정본(표에 없으면 id 꼬리를 읽기 좋게)."""
    label = display_labels._EN_LABELS.get(spec.id)
    if label:
        return label
    tail = spec.id.split(".", 1)[-1].replace("_", " ")
    return tail[:1].upper() + tail[1:]


def build_public_metadata() -> dict:
    """공개 메타데이터 DTO. 같은 레지스트리·시드면 항상 같은 결과(version 포함)."""
    ontology = get_ontology()

    indicators: Dict[str, dict] = {}
    bindings: Dict[str, str] = {}
    for spec_id in sorted(REGISTRY):
        spec = REGISTRY[spec_id]
        indicators[spec.id] = {
            "name": spec.display_name,
            "nameEn": _name_en(spec),
            "category": spec.category,
            "supported": spec.supported,
            "dataPending": spec.data_pending,
            "partialData": spec.partial_data,
            "unit": spec.value_type,
            "operators": list(spec.allowed_operators),
            "parameters": {
                name: {
                    "minimum": param.minimum,
                    "maximum": param.maximum,
                    "required": param.required,
                }
                for name, param in sorted(spec.parameters.items())
            },
            "classId": ontology.members.get(spec.id),
            "alternatives": list(spec.alternatives),
        }
        if spec.engine_binding is not None:
            # 엔진 조건(type/id)을 canonical 잎으로 되짚는 색인 — "종류:필드" → 잎 ID.
            # 한 엔진 조건을 여러 잎이 공유하면(볼린저 밴드 지정 변형) 잎 ID 꼬리가 필드와 같은
            # 일반 잎이 대표다 — 변형 구분은 조건 파라미터가 하며 색인은 고르지 않는다.
            key = f"{spec.engine_binding[0]}:{spec.engine_binding[1]}"
            if key not in bindings or spec.id.split(".", 1)[-1] == spec.engine_binding[1]:
                bindings[key] = spec.id

    classes: List[dict] = [
        {"id": cls.id, "name": cls.name, "parent": cls.parent, "description": cls.description}
        for cls in sorted(ontology.classes.values(), key=lambda c: c.id)
    ]
    concepts: List[dict] = [
        {
            "id": concept.id,
            "name": concept.name,
            "supported": concept.supported,
            "expandsTo": (concept.expansion or {}).get("factor"),
            "requires": list(concept.requires),
        }
        for concept in sorted(ontology.concepts.values(), key=lambda c: c.id)
    ]

    body = {
        "indicators": indicators,
        "bindings": dict(sorted(bindings.items())),
        "classes": classes,
        "concepts": concepts,
    }
    digest = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {"version": digest, **body}
