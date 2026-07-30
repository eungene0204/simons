"""JSON Patch 적용기 — MODIFY_STRATEGY 패치를 StrategySpec에 안전하게 적용.

적용 전에 경로 유효성을 검증하고, 적용 후 결과 전체를 StrategySpec으로 재검증한다.
잘못된 경로/값은 PatchError로 거부한다(조용한 무시 금지).
"""

from __future__ import annotations

import copy
from typing import Any, List

from strategy_conversation.interpreter.models import ALLOWED_PATCH_OPS, PatchOp, StrategySpec


class PatchError(ValueError):
    pass


def _reject_state_ops(patches: List[PatchOp]) -> None:
    """허용목록 밖 연산을 거부한다 — 특히 상태를 쓰려는 연산.

    Pydantic Literal이 이미 대부분을 막지만, 이 검사는 **계약을 코드에 남기기 위한
    것**이다: 파생 상태(NOT_APPLICABLE·INVALID·CONFLICTED)는 패치로 기록되지 않고
    결정론 evaluator가 매 턴 계산한다. 이 자리에 MARK_* 를 더하고 싶어질 때 여기서
    막힌다(허용목록을 늘리는 것이 곧 그 계약을 깨는 일임을 드러낸다).
    """
    unknown = sorted({p.op for p in patches if p.op not in ALLOWED_PATCH_OPS})
    if unknown:
        raise PatchError(
            f"허용되지 않은 패치 연산입니다: {', '.join(unknown)} — "
            "상태(적용 불가·모순·미지원)는 패치가 아니라 매 턴 결정론 계산이 정합니다"
        )


def _resolve_parent(doc: Any, path: str):
    """JSON Pointer 경로의 (부모 컨테이너, 마지막 토큰)을 반환한다."""
    if not path.startswith("/"):
        raise PatchError(f"JSON Pointer 경로가 아닙니다: {path!r}")
    tokens = [t.replace("~1", "/").replace("~0", "~") for t in path.split("/")[1:]]
    if not tokens or tokens == [""]:
        raise PatchError("루트 전체 교체는 허용하지 않습니다")
    node = doc
    for token in tokens[:-1]:
        if isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError):
                raise PatchError(f"경로의 배열 인덱스가 유효하지 않습니다: {path!r}")
        elif isinstance(node, dict):
            if token not in node:
                raise PatchError(f"존재하지 않는 경로입니다: {path!r}")
            node = node[token]
        else:
            raise PatchError(f"경로 중간이 컨테이너가 아닙니다: {path!r}")
    return node, tokens[-1]


def apply_patches(strategy: StrategySpec, patches: List[PatchOp]) -> StrategySpec:
    """패치를 적용한 새 StrategySpec을 반환한다(원본 불변). 실패 시 PatchError."""
    _reject_state_ops(patches)
    doc = copy.deepcopy(strategy.model_dump())
    for patch in patches:
        parent, last = _resolve_parent(doc, patch.path)
        if isinstance(parent, list):
            if last == "-" and patch.op in ("add", "replace"):
                # JSON Pointer의 "-"(배열 끝)는 add 전용이지만, 4B가 추가 의도를
                # replace로 내는 드리프트 실측(2026-07-17) — 의미가 유일하므로 append로 수용
                parent.append(patch.value)
                continue
            try:
                index = int(last)
            except ValueError:
                raise PatchError(f"배열에 문자열 키를 쓸 수 없습니다: {patch.path!r}")
            if patch.op == "add":
                if not (0 <= index <= len(parent)):
                    raise PatchError(f"배열 인덱스 범위 밖입니다: {patch.path!r}")
                parent.insert(index, patch.value)
            elif not (0 <= index < len(parent)):
                raise PatchError(f"배열 인덱스 범위 밖입니다: {patch.path!r}")
            elif patch.op == "replace":
                parent[index] = patch.value
            else:  # remove
                del parent[index]
        elif isinstance(parent, dict):
            if patch.op in ("replace", "remove") and last not in parent:
                raise PatchError(f"존재하지 않는 필드입니다: {patch.path!r}")
            if patch.op == "remove":
                # 스키마 필드 삭제는 null 초기화로 해석한다(필드 자체는 계약상 존재)
                parent[last] = None
            else:
                parent[last] = patch.value
        else:
            raise PatchError(f"경로가 컨테이너를 가리키지 않습니다: {patch.path!r}")

    try:
        return StrategySpec.model_validate(doc)
    except Exception as exc:
        raise PatchError(f"패치 적용 결과가 스키마를 위반합니다: {str(exc)[:300]}")
