"""JSON Patch 적용기 — MODIFY_STRATEGY 패치를 StrategySpec에 안전하게 적용.

적용 전에 경로 유효성을 검증하고, 적용 후 결과 전체를 StrategySpec으로 재검증한다.
잘못된 경로/값은 PatchError로 거부한다(조용한 무시 금지).
"""

from __future__ import annotations

import copy
from typing import Any, List

from strategy_conversation.interpreter.models import ALLOWED_PATCH_OPS, PatchOp, StrategySpec, scale_in_view


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
                index = int(token)
                if not 0 <= index < len(node):
                    raise IndexError(index)
                node = node[index]
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


def _condition_patch_groups(doc: dict, patches: List[PatchOp]):
    """Yield sequential operations together with their original approval members."""
    lengths = {field: len(doc[field]) for field in _CONDITION_LIST_FIELDS}
    consumed = set()
    for ordinal, patch in enumerate(patches):
        if ordinal in consumed:
            continue
        tokens = patch.path.split("/")[1:]
        if not tokens:
            raise PatchError(f"JSON Pointer 경로가 아닙니다: {patch.path!r}")
        field = tokens[0]
        if field not in lengths:
            yield patch, [patch]
            continue
        if len(tokens) == 1:
            lengths[field] = len(patch.value) if isinstance(patch.value, list) else 0
        elif len(tokens) == 2:
            if patch.op == "add" or tokens[1] == "-":
                lengths[field] += 1
            elif patch.op == "remove":
                lengths[field] -= 1
        elif len(tokens) == 3 and tokens[1] == str(lengths[field]) and patch.op == "replace":
            # Recover field-wise creation only at the next index. A structural
            # operation changes identity, so never collect siblings across it.
            members = [patch]
            indices = []
            prefix = tokens[:2]
            for index in range(ordinal + 1, len(patches)):
                other = patches[index]
                path = other.path.split("/")[1:]
                if not path or path[0] != field:
                    continue
                if len(path) <= 2 or path[:2] != prefix or len(path) != 3 or other.op != "replace":
                    break
                members.append(other)
                indices.append(index)
            value = {item.path.rsplit("/", 1)[1]: item.value for item in members}
            if value.get("factor"):
                consumed.update(indices)
                lengths[field] += 1
                source = next((item.source_text for item in members if item.source_text), None)
                yield PatchOp(op="add", path=f"/{field}/-", value=value, source_text=source), members
                continue
        yield patch, [patch]


def unchanged_replace_indices(strategy: StrategySpec, patches: List[PatchOp]) -> set[int]:
    """값이 초안의 현재 값과 같은 replace 패치의 인덱스 — 적용해도 전략이 달라지지 않는다.

    입력은 LLM 패치와 초안뿐인 구조화 값 비교다(§ 3-2). 경로를 풀 수 없는 패치는 세지 않는다.
    """
    doc = scale_in_view(copy.deepcopy(strategy.model_dump()))
    unchanged: set[int] = set()
    for index, patch in enumerate(patches):
        if patch.op != "replace":
            continue
        try:
            parent, last = _resolve_parent(doc, patch.path)
            current = parent[int(last)] if isinstance(parent, list) else parent[last]
        except (PatchError, ValueError, IndexError, KeyError, TypeError):
            continue
        if current == patch.value:
            unchanged.add(index)
    return unchanged


# 거부가 성립하는 설정(DeclinableField)의 패치 경로.
DECLINABLE_PATHS = {
    "/risk_management/stop_loss": "stop_loss",
    "/risk_management/take_profit": "take_profit",
    "/portfolio/rebalance_frequency": "rebalancing",
    "/exit_conditions": "exit",
}


def _record_null_declines(doc: dict, before: dict, patches: List[PatchOp]) -> None:
    """거부 가능 설정을 인용과 함께 비운 패치를 '안 함'(declined)으로 기록한다(2026-11-13 사용자 결정).

    수정 LLM은 '익절 안 함'을 /declined 패치 대신 take_profit=null로만 내기도 한다 — 그러면 값도
    거부도 없어 게이트가 같은 질문을 반복했다(가상 사용자 QA: 최대 6회). LLM 출력의 구조만 본다.
    """
    declined = doc.get("declined")
    if not isinstance(declined, list):
        return
    for patch in patches:
        field = DECLINABLE_PATHS.get(patch.path)
        if field is None or not str(patch.source_text or "").strip() or not _is_clear(patch):
            continue
        # 있던 매도 조건을 지우는 것은 '안 함'이 아니라 삭제다 — 비어 있던 칸을 비운 것만 거부로 읽는다.
        if field == "exit" and before.get("exit_conditions"):
            continue
        parent, last = _resolve_parent(doc, patch.path)
        if isinstance(parent, dict) and parent.get(last) in (None, []) and field not in declined:
            declined.append(field)


def _is_clear(patch: PatchOp) -> bool:
    return patch.op == "remove" or (patch.op == "replace" and patch.value in (None, [], {}))


def _relocate_declined_patches(patches: List[PatchOp]) -> List[PatchOp]:
    """다른 칸 아래에 쓴 declined 패치(/risk_management/declined)를 제자리(/declined)로 옮긴다.

    declined는 전략 최상위에만 있는 이름이라 옮길 자리가 하나뿐이다 — 값은 건드리지 않는 경로 정규화다.
    옮기지 않으면 '존재하지 않는 필드'로 수정 전체가 "해석하지 못했어요"로 끝난다(2026-11-13 실측).
    """
    out: List[PatchOp] = []
    for patch in patches:
        tokens = patch.path.split("/")[1:]
        tail = tokens[-2:] if tokens[-1:] == ["-"] else tokens[-1:]
        if tail[:1] == ["declined"] and len(tokens) > len(tail):
            patch = patch.model_copy(update={"path": "/" + "/".join(tail)})
        out.append(patch)
    return out


def patch_document(strategy: StrategySpec) -> dict:
    """패치 경로가 가리키는 문서 — 사다리 단계는 수정 LLM이 보는 초안과 같은 모양(scale_in_buys)이다."""
    return scale_in_view(copy.deepcopy(strategy.model_dump()))


def is_noop_clear(doc: dict, patch: PatchOp) -> bool:
    """이미 비어 있거나 없는 설정을 다시 비우는 패치인가(경로·값 형태만 본다)."""
    if not _is_clear(patch):
        return False
    try:
        parent, last = _resolve_parent(doc, patch.path)
    except PatchError:
        return False
    return isinstance(parent, dict) and parent.get(last) in (None, [], {})


def apply_patches(strategy: StrategySpec, patches: List[PatchOp]) -> StrategySpec:
    """패치를 적용한 새 StrategySpec을 반환한다(원본 불변). 실패 시 PatchError."""
    _reject_state_ops(patches)
    doc = patch_document(strategy)
    patches = _relocate_declined_patches(patches)
    patches = [patch for patch, _ in _condition_patch_groups(doc, patches)]
    check_extra_fields = False
    before = copy.deepcopy(doc)
    for patch in patches:
        parent, last = _resolve_parent(doc, patch.path)
        if isinstance(parent, list):
            if last == "-" and patch.op in ("add", "replace"):
                # JSON Pointer의 "-"(배열 끝)는 add 전용이지만, 4B가 추가 의도를
                # replace로 내는 드리프트 실측(2026-07-17) — 의미가 유일하므로 append로 수용
                parent.append(copy.deepcopy(patch.value))
                continue
            try:
                index = int(last)
            except ValueError:
                raise PatchError(f"배열에 문자열 키를 쓸 수 없습니다: {patch.path!r}")
            if patch.op == "add":
                if not (0 <= index <= len(parent)):
                    raise PatchError(f"배열 인덱스 범위 밖입니다: {patch.path!r}")
                parent.insert(index, copy.deepcopy(patch.value))
            elif not (0 <= index < len(parent)):
                raise PatchError(f"배열 인덱스 범위 밖입니다: {patch.path!r}")
            elif patch.op == "replace":
                parent[index] = copy.deepcopy(patch.value)
            else:  # remove
                del parent[index]
        elif isinstance(parent, dict):
            if patch.op == "add" and last not in parent:
                check_extra_fields = True
            if patch.op in ("replace", "remove") and last not in parent:
                if _is_clear(patch):
                    continue          # 없는 설정을 비우는 패치 — 바뀌는 것이 없다
                raise PatchError(f"존재하지 않는 필드입니다: {patch.path!r}")
            if patch.op == "remove":
                # 스키마 필드 삭제는 null 초기화로 해석한다(필드 자체는 계약상 존재)
                parent[last] = None
            else:
                parent[last] = copy.deepcopy(patch.value)
        else:
            raise PatchError(f"경로가 컨테이너를 가리키지 않습니다: {patch.path!r}")

    _drop_stale_parameters(doc, _changed_factor_conditions(before, doc, patches))
    _record_null_declines(doc, before, patches)

    try:
        return StrategySpec.model_validate(doc, extra="forbid" if check_extra_fields else None)
    except Exception as exc:
        raise PatchError(f"패치 적용 결과가 스키마를 위반합니다: {str(exc)[:300]}")
