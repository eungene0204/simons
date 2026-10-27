"""방문자가 바꿀 수 있는 지표 파라미터 — 설명자 생성과 덮어쓰기 검증(docs/development/strategy-simulation.md §3.7).

수정 가능 여부·범위·이름은 전부 REGISTRY(IndicatorSpec/ParamSpec)에서 읽는다. 프론트엔드는 이 설명자를 그대로
그린다. 원본 스냅샷에 이미 있는 숫자 값만 대상이며(없는 값을 만들거나 default로 채우지 않는다), 적용은 깊은
복사본에만 한다. 사용자 원문 해석·LLM 호출 없음.
"""
from __future__ import annotations

import copy
import math
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from strategy_conversation.registry.display_labels import unit_label
from strategy_conversation.registry.indicator_registry import REGISTRY
from strategy_conversation.validation.completeness_validator import _PARAM_LABELS

ROLES = ("entry", "exit")
_VALUE_KEY = "value"
_UNITS = {"percent": "%", "ratio": "배", "억원": "억원", "point": ""}
# 엔진이 REGISTRY 파라미터명과 다른 철자로 읽는 키(엔진 signals.py가 읽는 형태) — 나머지는 camelCase↔snake_case.
_ENGINE_KEY_ALIASES = {"shortMA": "short_period", "longMA": "long_period"}


class OverrideError(Exception):
    """덮어쓰기 검증 실패. errors = [{"path", "code", "message"}]."""

    def __init__(self, errors: List[Dict[str, str]]):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


def _registry_name(engine_key: str) -> str:
    return _ENGINE_KEY_ALIASES.get(engine_key) or re.sub(r"(?<!^)(?=[A-Z])", "_", engine_key).lower()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@lru_cache(maxsize=1)
def _specs_by_binding() -> Dict[Tuple[str, str], list]:
    index: Dict[Tuple[str, str], list] = {}
    for spec in REGISTRY.values():
        if spec.engine_binding:
            index.setdefault(spec.engine_binding, []).append(spec)
    for (_, field), specs in index.items():
        # 한 엔진 조건을 여러 잎이 공유하면 잎 ID 꼬리가 필드와 같은 일반 잎이 대표다(public_metadata와 같은 규칙).
        specs.sort(key=lambda s: s.id.split(".", 1)[-1] != field)
    return index


def _candidate_specs(cond: Dict[str, Any]) -> list:
    index, cid = _specs_by_binding(), cond.get("id")
    kinds = ["technical_signal"] if cond.get("type") == "indicator" else ["fundamental_filter", "technical_signal"]
    for kind in kinds:
        if (kind, cid) in index:
            return index[(kind, cid)]
    return []


def _describe(role: str, idx: int, cond: Dict[str, Any], key: str, value: float) -> Dict[str, Any]:
    specs = _candidate_specs(cond)
    path = f"{role}.conditions.{idx}.params.{key}"
    out: Dict[str, Any] = {"path": path, "role": role, "index": idx, "original": value, "editable": False}
    if not specs or specs[0].supported == "UNSUPPORTED" or specs[0].data_pending:
        return {**out, "label": str(cond.get("id")), "reason": "UNSUPPORTED_INDICATOR"}
    spec = specs[0]
    name = _registry_name(key)
    if key == _VALUE_KEY:
        lo_hi, unit, param = spec.value_range, unit_label(spec.value_type, _UNITS), "기준값"
    else:
        pspec = next((s.parameters[name] for s in specs if name in s.parameters), None)
        lo_hi = (pspec.minimum, pspec.maximum) if pspec and pspec.minimum is not None and pspec.maximum is not None else None
        unit, param = "일", _PARAM_LABELS.get(name, name.replace("_", " "))
    out.update(label=f"{spec.display_name} · {param}", unit=unit)
    if lo_hi is None:
        return {**out, "reason": "NO_RANGE_METADATA"}
    return {**out, "minimum": lo_hi[0], "maximum": lo_hi[1], "integer": key != _VALUE_KEY, "editable": True}


def build_editable_params(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """조건별 숫자 파라미터 설명자. 문자열 키(operator·mode·side 등)는 파라미터가 아니라 나열하지 않는다."""
    result: List[Dict[str, Any]] = []
    for role in ROLES:
        conditions = (snapshot.get(role) or {}).get("conditions") or []
        for idx, cond in enumerate(conditions):
            params = cond.get("params") if isinstance(cond, dict) else None
            for key, value in (params or {}).items():
                if _is_number(value):
                    result.append(_describe(role, idx, cond, key, value))
    return result


def apply_overrides(
    snapshot: Dict[str, Any], overrides: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """(수정된 깊은 복사본, 원본과 달라진 덮어쓰기). 원본 snapshot은 바꾸지 않는다. 위반은 OverrideError."""
    by_path = {d["path"]: d for d in build_editable_params(snapshot)}
    errors: List[Dict[str, str]] = []
    seen, changed = set(), []
    for item in overrides if isinstance(overrides, list) else []:
        path = item.get("path") if isinstance(item, dict) else None
        value = item.get("value") if isinstance(item, dict) else None
        if path in seen:
            errors.append({"path": str(path), "code": "DUPLICATE_PATH", "message": "같은 항목이 중복되었습니다."})
            continue
        seen.add(path)
        desc = by_path.get(path)
        if desc is None:
            errors.append({"path": str(path), "code": "UNKNOWN_PATH", "message": "수정할 수 없는 항목입니다."})
        elif not desc["editable"]:
            errors.append({"path": path, "code": "NOT_EDITABLE", "message": "이 항목은 수정할 수 없습니다."})
        elif not _is_number(value):
            errors.append({"path": path, "code": "NOT_A_NUMBER", "message": "숫자를 입력해 주세요."})
        elif not desc["minimum"] <= value <= desc["maximum"]:
            errors.append({"path": path, "code": "OUT_OF_RANGE",
                           "message": f"{desc['minimum']:g}~{desc['maximum']:g} 범위의 값을 입력해 주세요."})
        elif desc["integer"] and float(value) != int(value):
            errors.append({"path": path, "code": "NOT_INTEGER", "message": "정수를 입력해 주세요."})
        elif value != desc["original"]:
            changed.append({"path": path, "value": int(value) if desc["integer"] else value})
    if errors:
        raise OverrideError(errors)

    modified = copy.deepcopy(snapshot)
    for item in changed:
        role, _, idx, _, key = item["path"].split(".")
        modified[role]["conditions"][int(idx)]["params"][key] = item["value"]
    return modified, changed


__all__ = ["OverrideError", "build_editable_params", "apply_overrides"]
