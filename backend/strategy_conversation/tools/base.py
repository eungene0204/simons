"""Tool 경계 — Planner → Tool/Engine → Responder 전환(Phase 1)의 공통 인터페이스.

기존 서비스(지식그래프·검색 그라운딩·registry·검증·컴파일)를 이름 있는 도구로 등록해,
고정 파이프라인(primary.py)과 이후 Phase 3의 planner가 같은 경계를 통해 호출하게 한다.
이 레이어는 동작을 바꾸지 않는다 — 입출력의 **형식만** pydantic으로 검증한다(자연어
해석 계약 § 3: 의미 판단은 여기서 하지 않는다).

경계 규칙:
- 도메인 예외(StrategyCompileError 등)는 삼키지 않고 그대로 전파한다 — 폴백·되묻기
  판단은 호출부 소관이다. ToolError는 도구 계약 위반(미등록 이름·입출력 형식)에만 쓴다.
- deterministic=False 도구(검색·LLM 개입)는 planner 도입 시 별도 예산·로그 대상이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Type

from pydantic import BaseModel, ValidationError


class ToolError(ValueError):
    """도구 계약 위반 — 미등록 도구, 입력/출력 형식 불일치."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str  # planner에 노출될 한 줄 설명(한국어)
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    fn: Callable[[BaseModel], BaseModel]
    deterministic: bool  # True=순수 조회/계산, False=외부 검색·LLM 개입


_REGISTRY: Dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise ToolError(f"도구 이름 중복 등록: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec:
    spec = _REGISTRY.get(name)
    if spec is None:
        raise ToolError(f"등록되지 않은 도구: {name}")
    return spec


def list_tools() -> List[ToolSpec]:
    return list(_REGISTRY.values())


def call(name: str, **payload) -> BaseModel:
    """도구 호출 단일 진입점 — 입력 형식 검증 → 실행 → 출력 계약 확인."""
    spec = get_tool(name)
    try:
        inp = spec.input_model.model_validate(payload)
    except ValidationError as exc:
        raise ToolError(f"도구 '{name}' 입력 형식 위반: {exc}") from exc
    out = spec.fn(inp)
    if not isinstance(out, spec.output_model):
        raise ToolError(
            f"도구 '{name}' 출력 계약 위반: {type(out).__name__} != {spec.output_model.__name__}"
        )
    return out
