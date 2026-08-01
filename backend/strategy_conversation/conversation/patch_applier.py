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


_CONDITION_LIST_FIELDS = ("entry_conditions", "exit_conditions")


def _drop_stale_parameters(doc: Any, changed_factor_paths: List[tuple]) -> None:
    """factor가 교체된 조건에서 **새 factor의 spec에 없는 파라미터 키**를 떨어낸다.

    입력은 LLM 출력(패치 적용 결과)이고 판정 근거는 registry 조회뿐이다 — 원문 해석이
    아니라 결정론 정규화다(§ 3-2). 필드 단위 패치로 factor만 바꾸면 이전 지표의
    파라미터가 그대로 남아("PER에 알 수 없는 파라미터 short_period") 검증이 실패한다.
    이전 factor의 파라미터는 새 factor에서 의미가 없으므로 보존할 값이 아니다.
    """
    from strategy_conversation.registry.indicator_registry import REGISTRY

    for field_name, index in changed_factor_paths:
        try:
            cond = doc[field_name][index]
        except (KeyError, IndexError, TypeError):
            continue
        if not isinstance(cond, dict) or not isinstance(cond.get("parameters"), dict):
            continue
        spec = REGISTRY.get(cond.get("factor"))
        if spec is None:
            continue
        cond["parameters"] = {
            k: v for k, v in cond["parameters"].items() if k in spec.parameters
        }


def _changed_factor_conditions(
    before: Any, doc: Any, patches: List[PatchOp]
) -> List[tuple]:
    """factor가 실제로 바뀐 조건의 (리스트 필드명, 인덱스) 목록."""
    out: List[tuple] = []
    for patch in patches:
        tokens = [t for t in patch.path.split("/") if t]
        if len(tokens) != 3 or tokens[0] not in _CONDITION_LIST_FIELDS:
            continue
        if tokens[2] != "factor" or not tokens[1].isdigit():
            continue
        index = int(tokens[1])
        try:
            old = before[tokens[0]][index].get("factor")
            new = doc[tokens[0]][index].get("factor")
        except (KeyError, IndexError, AttributeError, TypeError):
            continue
        if old != new:
            out.append((tokens[0], index))
    return out


def _promote_patches_on_absent_condition(doc: Any, patches: List[PatchOp]) -> List[PatchOp]:
    """비어 있는 조건 배열의 없는 인덱스를 겨냥한 필드 패치들을 조건 추가 하나로 합친다.

    9B 드리프트 실측(2026-07-31 QA): 초안의 exit_conditions가 비어 있는데
    `replace /exit_conditions/0/factor` + `replace /exit_conditions/0/operator`를 낸다.
    가리킬 대상이 없어 PatchError → 폴백 → "해석하지 못했어요"로 끝나므로,
    '볼린저밴드 상단 닿으면 매도' 같은 청산 조건 답변이 통째로 사라졌다.

    합치는 것은 **LLM이 같은 인덱스에 대해 이미 낸 필드들**뿐이다 — 값을 지어내지 않고
    구조만 바로잡으므로 형식 정규화다(§ 3-2). factor가 없으면 조건으로 성립하지 않아
    승격하지 않는다(불완전한 조건을 만들어 검증을 통과시키지 않는다). 인덱스가 실재하면
    기존 경로 그대로다 — 이 함수는 '없는 인덱스'에만 개입한다.
    """
    groups: dict[tuple[str, int], List[PatchOp]] = {}
    for patch in patches:
        tokens = [t for t in patch.path.split("/") if t]
        if len(tokens) != 3 or tokens[0] not in _CONDITION_LIST_FIELDS:
            continue
        if patch.op != "replace" or not tokens[1].isdigit():
            continue
        current = doc.get(tokens[0])
        if not isinstance(current, list) or int(tokens[1]) < len(current):
            continue
        groups.setdefault((tokens[0], int(tokens[1])), []).append(patch)
    if not groups:
        return patches

    promoted: List[PatchOp] = []
    absorbed = {id(p) for group in groups.values() for p in group}
    for (list_field, _index), group in groups.items():
        value = {p.path.rsplit("/", 1)[1]: p.value for p in group}
        if not value.get("factor"):
            continue          # 조건의 정체가 없다 — 승격하지 않고 기존 실패에 맡긴다
        source = next((p.source_text for p in group if p.source_text), None)
        promoted.append(PatchOp.model_validate({
            "op": "add", "path": f"/{list_field}/-", "value": value, "source_text": source,
        }))
    if not promoted:
        return patches
    return [p for p in patches if id(p) not in absorbed] + promoted


def apply_patches(strategy: StrategySpec, patches: List[PatchOp]) -> StrategySpec:
    """패치를 적용한 새 StrategySpec을 반환한다(원본 불변). 실패 시 PatchError."""
    _reject_state_ops(patches)
    doc = copy.deepcopy(strategy.model_dump())
    patches = _promote_patches_on_absent_condition(doc, patches)
    before = copy.deepcopy(doc)
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

    _drop_stale_parameters(doc, _changed_factor_conditions(before, doc, patches))

    try:
        return StrategySpec.model_validate(doc)
    except Exception as exc:
        raise PatchError(f"패치 적용 결과가 스키마를 위반합니다: {str(exc)[:300]}")
