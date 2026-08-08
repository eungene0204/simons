"""지표 온톨로지 — 전략 언어(지표·합성 개념)의 분류 계층(is_a)과 전개 선언.

잎(leaf) 정본은 indicator_registry._SPECS이고, 이 모듈은 그 위에 두 축을 얹는다:
  1. is_a 계층 — 잎 → 클래스(이동평균/오실레이터/밸류에이션 …) → 최상위(지표)
  2. 합성 개념 — 관용 표현(골든크로스 등)의 정본 전개(expands_to/requires) 선언

시드는 data/indicator-ontology.json(git 추적)이며 파일 수정만으로 새 지식이 편입된다
(mtime 자동 재로드 — engine/knowledge_graph.get_graph와 같은 패턴). 무결성 위반은
issues 채널에 쌓이고 test_concept_ontology.py가 위반 0을 CI에서 단언한다.

소비 지점:
  - interpreter/prompts.py — 계층 어휘 섹션 생성(ontology_prompt_sections)
  - /ontology/graph — 관리자 콘솔 시각화·검색용 노드/엣지 덤프(ontology_graph)

이 모듈은 사용자 원문을 읽지 않는다 — 입력은 항상 LLM 구조화 출력 또는 정본 ID다
(자연어 해석 구조 원칙).
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from strategy_conversation.registry.indicator_registry import REGISTRY, _SPECS

_BASE_DIR = Path(__file__).resolve().parents[3]  # 레포 루트(data/의 부모)
_SEED_PATH = _BASE_DIR / "data" / "indicator-ontology.json"

# 지표값의 자연 방향 — '관례적으로 어느 쪽을 선호하는가'이지 우열 판정이 아니다.
# none은 "보편적 선호 방향 없음"의 **명시적 선언**이다(선언 누락과 구별된다).
LOWER_BETTER = "lower_better"
HIGHER_BETTER = "higher_better"
POLARITY_NONE = "none"
_POLARITIES = (LOWER_BETTER, HIGHER_BETTER, POLARITY_NONE)


@dataclass(frozen=True)
class OntologyClass:
    id: str                    # "class.oscillator"
    name: str                  # "모멘텀/오실레이터"
    parent: Optional[str]      # "class.technical" (루트는 None)
    description: str = ""


@dataclass(frozen=True)
class ConceptSpec:
    id: str                    # "concept.golden_cross"
    name: str                  # "골든크로스"
    supported: str             # SUPPORTED / UNSUPPORTED
    synonyms: Tuple[str, ...] = ()
    # 전개 선언: {"factor": canonical ID, "operator": str|None, "default_parameters": {...}}
    expansion: Optional[dict] = None
    requires: Tuple[str, ...] = ()
    description: str = ""
    # True면 LLM이 이 개념 ID를 factor로 출력하는 계약(프롬프트 3.0) — 전개(연산자·
    # 정본 기간)는 capability_validator가 결정론으로 물질화한다. 완전 결정 전개
    # (operator 선언 필수)만 플래그를 켤 수 있다(무결성 검증).
    llm_output: bool = False
    # 엔진이 고정해 둔 파라미터(예: MACD 12/26/9) — 전개 대상 잎에 선언되지 않은
    # 파라미터가 조건에 실려 오면 전개가 정리하는데, 값이 이 고정값과 **다르면**
    # 사용자가 커스텀 기간을 말한 것이므로 조용히 버리지 않고 안내한다(침묵 왜곡 방지).
    fixed_parameters: Optional[Dict[str, float]] = None


@dataclass(frozen=True)
class Ontology:
    classes: Dict[str, OntologyClass]
    members: Dict[str, str]            # 잎 canonical ID → 클래스 ID (전 잎 완전 분류)
    concepts: Dict[str, ConceptSpec]
    # 잎 canonical ID → 자연 방향(lower_better/higher_better/none). 지원 잎 전수 명시.
    polarity: Dict[str, str] = field(default_factory=dict)
    issues: Tuple[str, ...] = field(default_factory=tuple)

    def class_members(self, class_id: str) -> List[str]:
        """클래스 직속 잎 목록(시드 members 선언 순)."""
        return [leaf for leaf, cls in self.members.items() if cls == class_id]

    def child_classes(self, class_id: Optional[str]) -> List[OntologyClass]:
        return [c for c in self.classes.values() if c.parent == class_id]


def _validate(
    classes: Dict[str, OntologyClass],
    members: Dict[str, str],
    concepts: Dict[str, ConceptSpec],
    polarity: Dict[str, str],
) -> List[str]:
    issues: List[str] = []

    # 자연 방향 — 지원 잎은 **전수 명시**해야 한다. 침묵을 허용하면 "선언을 잊은 것"과
    # "방향이 없는 것"을 구별할 수 없고, 방향 기본값 경로가 조용히 top으로 떨어진다
    # (PER이면 가장 비싼 종목 선정 = 전략 반전). none도 명시적 선언이다.
    for leaf, value in polarity.items():
        if leaf not in REGISTRY:
            issues.append(f"polarity 잎 미존재(Registry에 없음): {leaf}")
        if value not in _POLARITIES:
            issues.append(f"polarity 값 오류: {leaf} → {value!r} ∉ {_POLARITIES}")
    for spec in _SPECS:
        if spec.supported != "UNSUPPORTED" and spec.id not in polarity:
            issues.append(f"polarity 미선언(지원 잎): {spec.id}")

    for cls in classes.values():
        if not cls.id.startswith("class."):
            issues.append(f"클래스 id 접두 오류: {cls.id}")
        if cls.parent is not None and cls.parent not in classes:
            issues.append(f"클래스 부모 미존재: {cls.id} → {cls.parent}")
        # 순환 검사 — 부모 체인을 따라 루트까지(클래스 수 초과 시 순환)
        seen, cur = set(), cls.parent
        while cur is not None:
            if cur in seen or len(seen) > len(classes):
                issues.append(f"클래스 계층 순환: {cls.id}")
                break
            seen.add(cur)
            cur = classes[cur].parent if cur in classes else None

    for leaf, cls_id in members.items():
        if leaf not in REGISTRY:
            issues.append(f"멤버 잎 미존재(Registry에 없음): {leaf}")
        if cls_id not in classes:
            issues.append(f"멤버 클래스 미존재: {leaf} → {cls_id}")

    # 완전 분류 — 새 지표가 _SPECS에 추가되면 여기서 잡혀 시드 등록을 강제한다
    for spec in _SPECS:
        if spec.id not in members:
            issues.append(f"미분류 잎(시드 members에 없음): {spec.id}")

    # 잎이 하나도 없고 자식 클래스도 없는 클래스 — 탐색에 잡히지 않는 고아
    child_parents = {c.parent for c in classes.values() if c.parent}
    used_classes = set(members.values()) | child_parents
    for cls in classes.values():
        if cls.id not in used_classes:
            issues.append(f"고아 클래스(잎·자식 없음): {cls.id}")

    for concept in concepts.values():
        if not concept.id.startswith("concept."):
            issues.append(f"개념 id 접두 오류: {concept.id}")
        for req in concept.requires:
            if req not in REGISTRY:
                issues.append(f"개념 requires 미존재: {concept.id} → {req}")
        exp = concept.expansion
        if exp is None:
            continue
        factor = exp.get("factor")
        spec = REGISTRY.get(factor or "")
        if spec is None:
            issues.append(f"개념 전개 factor 미존재: {concept.id} → {factor}")
            continue
        if spec.supported == "UNSUPPORTED":
            issues.append(f"개념 전개가 미지원 잎을 가리킴: {concept.id} → {factor}")
        operator = exp.get("operator")
        if operator is not None and operator not in spec.allowed_operators:
            issues.append(
                f"개념 전개 연산자 위반: {concept.id} {operator} ∉ {factor}의 허용 연산자"
            )
        for param in (exp.get("default_parameters") or {}):
            if param not in spec.parameters:
                issues.append(
                    f"개념 전개 파라미터 미존재: {concept.id} {param} ∉ {factor}의 parameters"
                )
        if concept.llm_output and operator is None:
            # LLM 출력 계약 개념은 전개가 완전 결정적이어야 한다 — 연산자가 비면
            # 물질화가 방향을 지어내야 하므로 금지(무단 확정 방지).
            issues.append(f"llm_output 개념의 전개 연산자 미선언: {concept.id}")
    return issues


def _build() -> Ontology:
    raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    classes = {
        c["id"]: OntologyClass(
            id=c["id"], name=c["name"], parent=c.get("parent"),
            description=c.get("description", ""),
        )
        for c in raw.get("classes", [])
    }
    members = dict(raw.get("members", {}))
    concepts = {
        c["id"]: ConceptSpec(
            id=c["id"], name=c["name"], supported=c.get("supported", "SUPPORTED"),
            synonyms=tuple(c.get("synonyms", [])), expansion=c.get("expansion"),
            requires=tuple(c.get("requires", [])), description=c.get("description", ""),
            llm_output=bool(c.get("llm_output", False)),
            fixed_parameters=c.get("fixed_parameters"),
        )
        for c in raw.get("concepts", [])
    }
    # 시드의 "_doc"은 사람용 주석이라 잎 매핑에서 제외한다(밑줄 접두 = 비-데이터 관례).
    polarity = {
        k: v for k, v in (raw.get("polarity") or {}).items() if not k.startswith("_")
    }
    issues = _validate(classes, members, concepts, polarity)
    return Ontology(
        classes=classes, members=members, concepts=concepts,
        polarity=polarity, issues=tuple(issues),
    )


_CACHE_LOCK = threading.Lock()
_CACHED: Optional[tuple[float, Ontology]] = None


def get_ontology() -> Ontology:
    """온톨로지(캐시). 시드 파일이 바뀌면 자동 재로드된다."""
    global _CACHED
    try:
        stamp = os.path.getmtime(_SEED_PATH)
    except OSError:
        stamp = 0.0
    with _CACHE_LOCK:
        if _CACHED is not None and _CACHED[0] == stamp:
            return _CACHED[1]
        ontology = _build()
        _CACHED = (stamp, ontology)
        return ontology


# ─── 클래스 발화 되묻기 (Phase B) ───────────────────────────────────────────────


def is_class_id(factor: Optional[str]) -> bool:
    """factor가 온톨로지 분류 ID(class.*)인가 — 입력은 LLM 구조화 출력이다."""
    return bool(factor) and factor in get_ontology().classes


def class_choice(factor: str) -> Optional[Tuple[str, List[str]]]:
    """분류 발화 되묻기 재료 — (분류 표시명, 선택지 표시명 목록).

    직속 지원 잎이 있으면 잎 표시명(괄호 설명 제거 — 칩 표기 관례), 없으면(중간
    분류) 지원 잎을 품은 자식 분류명. 미지 분류면 None.
    """
    ontology = get_ontology()
    cls = ontology.classes.get(factor)
    if cls is None:
        return None
    leaves = [
        REGISTRY[leaf].display_name.split("(")[0].strip()
        for leaf in ontology.class_members(cls.id)
        if leaf in REGISTRY and REGISTRY[leaf].supported != "UNSUPPORTED"
    ]
    if leaves:
        return cls.name, leaves
    children = [
        c.name for c in ontology.child_classes(cls.id) if _has_supported(c.id, ontology)
    ]
    return cls.name, children


def class_display_name(factor: str) -> Optional[str]:
    """분류 ID의 한글 표시명 — 라벨·안내에서 내부 식별자 노출 방지."""
    cls = get_ontology().classes.get(factor)
    return cls.name if cls else None


# ─── 합성 개념 전개 (Phase C) ───────────────────────────────────────────────────


def polarity_of(factor: Optional[str]) -> Optional[str]:
    """지표의 자연 방향(lower_better/higher_better/none). 미선언이면 None.

    입력은 canonical ID(LLM 출력을 검증기가 정규화한 값)다 — 원문을 읽지 않는다.
    """
    if not factor:
        return None
    return get_ontology().polarity.get(factor)


def natural_ranking_direction(metric: Optional[str]) -> Optional[str]:
    """랭킹 방향을 사용자가 말하지 않았을 때 쓸 자연 방향(top/bottom). 없으면 None.

    "PER 기준 20종목"처럼 방향이 빠진 요청에서 무조건 top(높은 순)으로 떨어지면
    저평가 지표가 **가장 비싼 종목 선정**으로 뒤집힌다. 방향 없는 지표(none)와
    미선언은 None을 반환해 기존 동작을 그대로 둔다 — 억지 방향을 만들지 않는다.
    """
    pol = polarity_of(metric)
    if pol == LOWER_BETTER:
        return "bottom"
    if pol == HIGHER_BETTER:
        return "top"
    return None


def concept_spec(factor: Optional[str]) -> Optional[ConceptSpec]:
    """factor가 합성 개념 ID(concept.*)면 그 선언을 반환 — 입력은 LLM 구조화 출력."""
    if not factor:
        return None
    return get_ontology().concepts.get(factor)


# ─── 프롬프트 어휘 생성 ─────────────────────────────────────────────────────────


def _leaf_line(leaf_id: str) -> Optional[str]:
    """잎 한 줄 요약 — 구 평면 목록(supported_factor_lines, 2.7까지)과 동일 표기."""
    spec = REGISTRY.get(leaf_id)
    if spec is None or spec.supported == "UNSUPPORTED":
        return None
    ops = "/".join(spec.allowed_operators) if spec.allowed_operators else "-"
    unit = spec.value_type or "-"
    line = f"- {spec.id} ({spec.display_name}) 단위={unit} 연산자={ops}"
    # 자연 방향 병기 — 정성 표현("저평가된", "수익성 좋은")을 랭킹 방향으로 옮길 때
    # 9B가 참조할 근거다. none은 병기하지 않는다(방향이 없다는 사실은 침묵으로 족하고,
    # 줄마다 붙이면 어휘가 길어져 형태 학습을 방해한다).
    pol = get_ontology().polarity.get(spec.id)
    if pol == LOWER_BETTER:
        line += " [낮을수록 선호]"
    elif pol == HIGHER_BETTER:
        line += " [높을수록 선호]"
    if spec.notes:
        line += f" — {spec.notes}"
    return line


def ontology_prompt_sections() -> List[str]:
    """LLM 프롬프트에 주입할 계층 어휘 — 분류(클래스) 아래 잎을 묶어 렌더링한다.

    구 평면 목록(supported_factor_lines, 2.7까지)을 대체한다: 같은 잎·같은 줄 표기를
    유지하되, 분류 헤더가 '무엇이 같은 계열인지'(오실레이터=임계값 비교만 등)를
    구조로 전달한다. UNSUPPORTED 잎은 기존과 동일하게 어휘에서 제외한다(미지원
    개념은 규칙 3의 unsupported_features 경로가 담당).
    """
    ontology = get_ontology()
    lines: List[str] = []

    def render(class_id: str, depth: int) -> None:
        cls = ontology.classes[class_id]
        leaf_lines = [
            line for leaf in ontology.class_members(class_id)
            if (line := _leaf_line(leaf)) is not None
        ]
        children = ontology.child_classes(class_id)
        # 지원 잎이 없고 자식도 렌더링할 게 없는 분기(미지원 라우팅 전용)는 생략
        if not leaf_lines and not any(
            _has_supported(c.id, ontology) for c in children
        ):
            return
        header = "#" * min(depth + 3, 6)
        desc = f" — {cls.description}" if cls.description else ""
        lines.append(f"{header} {cls.name} ({cls.id}){desc}")
        lines.extend(leaf_lines)
        for child in children:
            render(child.id, depth + 1)

    # 재무 → 기술 → AI → 랭킹 순(기존 평면 목록의 _SPECS 순서와 동일한 큰 흐름 유지)
    ordered_roots = ["class.fundamental", "class.technical", "class.ai", "class.ranking"]
    for root_id in ordered_roots:
        if root_id in ontology.classes:
            render(root_id, 0)
    # 위 순서에 없는 나머지 최상위 분기(위험·수급 등 미지원 전용)는 _has_supported가
    # 걸러 자동 생략되지만, 지원 잎이 생기면 여기서 함께 렌더링된다
    for cls in ontology.child_classes("class.indicator"):
        if cls.id not in ordered_roots:
            render(cls.id, 0)
    return lines


def _has_supported(class_id: str, ontology: Ontology) -> bool:
    if any(
        REGISTRY[leaf].supported != "UNSUPPORTED"
        for leaf in ontology.class_members(class_id)
        if leaf in REGISTRY
    ):
        return True
    return any(_has_supported(c.id, ontology) for c in ontology.child_classes(class_id))


def concept_prompt_lines() -> List[str]:
    """합성 개념 프롬프트 줄 — 온톨로지가 SOT.

    llm_output 개념: 개념 ID를 factor로 출력하는 계약 줄(전개는 시스템 물질화 —
    프롬프트 3.0). 그 외: 규칙 5-3과 정합하는 표기 정본 참고 줄.
    """
    ontology = get_ontology()
    lines: List[str] = []
    for concept in ontology.concepts.values():
        if concept.supported == "UNSUPPORTED" or concept.expansion is None:
            continue
        exp = concept.expansion
        params = exp.get("default_parameters") or {}
        if concept.llm_output:
            if params:
                params_txt = ", ".join(f"{k}={v}" for k, v in params.items())
                tail = (
                    f"전개는 시스템이 합니다 — 정본 {params_txt}). 사용자가 기간을 "
                    f"말했으면 그 값만 parameters에 담으세요."
                )
            else:
                tail = "parameters는 항상 비움 — 전개는 시스템이 합니다)."
            lines.append(
                f'- {concept.name} 발화 → factor="{concept.id}" (operator·value는 null, '
                f"{tail} {concept.description}"
            )
            continue
        op = exp.get("operator") or "crosses_above/crosses_below(방향에 따라)"
        params_txt = (
            " 기본 " + ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
        )
        lines.append(
            f"- {concept.name} = {exp.get('factor')} {op}{params_txt} — {concept.description}"
        )
    return lines


# ─── 콘솔 시각화 덤프 ───────────────────────────────────────────────────────────


def ontology_graph() -> dict:
    """관리자 콘솔 시각화·검색용 노드/엣지 덤프 — 읽기 전용 뷰.

    노드: 클래스 + 잎(Registry 전체, 미지원 포함) + 합성 개념.
    엣지: 잎 –is_a→ 클래스, 클래스 –is_a→ 부모 클래스,
          개념 –expands_to→ 잎, 개념 –requires→ 잎.
    """
    ontology = get_ontology()
    nodes: List[dict] = []
    edges: List[dict] = []

    for cls in ontology.classes.values():
        nodes.append({
            "id": cls.id, "name": cls.name, "kind": "class",
            "description": cls.description,
        })
        if cls.parent:
            edges.append({"source": cls.id, "type": "is_a", "target": cls.parent})

    for spec in _SPECS:
        nodes.append({
            "id": spec.id, "name": spec.display_name, "kind": "leaf",
            "supported": spec.supported, "category": spec.category,
            "data_source": spec.data_source, "unit": spec.value_type,
            "operators": list(spec.allowed_operators),
            "description": spec.notes or "",
        })
        cls_id = ontology.members.get(spec.id)
        if cls_id:
            edges.append({"source": spec.id, "type": "is_a", "target": cls_id})

    for concept in ontology.concepts.values():
        nodes.append({
            "id": concept.id, "name": concept.name, "kind": "concept",
            "supported": concept.supported, "synonyms": list(concept.synonyms),
            "description": concept.description,
        })
        if concept.expansion and concept.expansion.get("factor") in REGISTRY:
            edges.append({
                "source": concept.id, "type": "expands_to",
                "target": concept.expansion["factor"],
            })
        for req in concept.requires:
            # expands_to와 중복되는 requires는 시각적 노이즈라 생략
            if req in REGISTRY and req != (concept.expansion or {}).get("factor"):
                edges.append({"source": concept.id, "type": "requires", "target": req})

    return {"nodes": nodes, "edges": edges, "issues": list(ontology.issues)}
