"""지표 온톨로지 시드 무결성 + 프롬프트 어휘 생성 계약.

시드(data/indicator-ontology.json)는 파일 수정만으로 성장한다 — 오타·미분류·전개 위반은
여기서 CI가 잡는다(knowledge_graph의 test_seed_integrity_no_issues와 같은 패턴).
"""

from strategy_conversation.registry.concept_ontology import (
    concept_prompt_lines,
    get_ontology,
    ontology_graph,
    ontology_prompt_sections,
)
from strategy_conversation.registry.indicator_registry import _SPECS, REGISTRY


def test_seed_integrity_no_issues():
    """시드 무결성 위반 0 — 미존재 참조·순환·미분류 잎·전개 위반이 없어야 한다.

    이 테스트가 깨지면 issues 메시지가 곧 수정 지시다(어느 항목이 왜 위반인지).
    새 지표를 _SPECS에 추가하면 '미분류 잎'으로 여기서 잡힌다 — 시드 members에
    분류를 등록해야 한다.
    """
    assert list(get_ontology().issues) == []


def test_every_spec_classified_exactly_once():
    """전 잎 완전 분류 — Registry의 모든 지표(미지원 포함)가 클래스 하나에 속한다."""
    ontology = get_ontology()
    spec_ids = {spec.id for spec in _SPECS}
    assert set(ontology.members.keys()) == spec_ids


def test_class_tree_reaches_root():
    """모든 클래스는 부모 체인을 따라 최상위(class.indicator)에 닿는다."""
    ontology = get_ontology()
    for cls in ontology.classes.values():
        cur = cls
        hops = 0
        while cur.parent is not None:
            cur = ontology.classes[cur.parent]
            hops += 1
            assert hops <= len(ontology.classes), f"순환 의심: {cls.id}"
        assert cur.id == "class.indicator", f"{cls.id}가 루트에 닿지 않음({cur.id})"


def test_concept_expansions_are_valid_conditions():
    """합성 개념 전개는 지원 잎 + 허용 연산자 + 실존 파라미터만 가리킨다.

    이 선언이 유효해야 Phase C(전개 위임)에서 결정적 물질화가 안전하다.
    """
    ontology = get_ontology()
    assert len(ontology.concepts) >= 4  # golden/dead cross, price_vs_ma, macd_cross
    for concept in ontology.concepts.values():
        if concept.expansion is None:
            continue
        spec = REGISTRY[concept.expansion["factor"]]
        assert spec.supported != "UNSUPPORTED"
        operator = concept.expansion.get("operator")
        if operator is not None:
            assert operator in spec.allowed_operators
        for param in (concept.expansion.get("default_parameters") or {}):
            assert param in spec.parameters


def test_golden_cross_canonical_periods():
    """골든크로스 정본 5/20 — 프롬프트 예시 3-0·규칙 5-3과 같은 값이어야 한다.

    온톨로지가 표기 정본의 SOT다: 이 값을 바꾸려면 프롬프트 규칙과 함께 바꿔야
    하고(드리프트 금지), 여기서 어긋나면 먼저 어느 쪽이 옳은지 규명한다.
    """
    concept = get_ontology().concepts["concept.golden_cross"]
    assert concept.expansion["operator"] == "crosses_above"
    assert concept.expansion["default_parameters"] == {"short_period": 5, "long_period": 20}


def test_prompt_sections_cover_all_supported_leaves():
    """계층 어휘는 지원 잎을 하나도 빠뜨리지 않는다(평면 목록과 같은 커버리지).

    어휘에서 빠진 잎은 LLM이 출력할 수 없다(출력 형태가 규칙보다 강하다) —
    지원 지표가 프롬프트에서 사라지는 회귀를 막는다.
    """
    rendered = "\n".join(ontology_prompt_sections())
    for spec in _SPECS:
        if spec.supported == "UNSUPPORTED":
            assert spec.id not in rendered, f"미지원 잎이 어휘에 노출: {spec.id}"
        else:
            assert spec.id in rendered, f"지원 잎이 어휘에서 누락: {spec.id}"


def test_concept_lines_match_seed_expansion():
    """합성 개념 프롬프트 줄은 시드 전개 선언에서 생성된다(손 규칙과 드리프트 방지).

    llm_output 개념(골든/데드크로스)은 개념 ID 출력 계약 줄로, 나머지는 표기 정본
    참고 줄로 렌더링된다(프롬프트 3.0).
    """
    lines = "\n".join(concept_prompt_lines())
    assert 'factor="concept.golden_cross"' in lines
    assert 'factor="concept.dead_cross"' in lines
    assert 'factor="concept.macd_golden_cross"' in lines
    assert 'factor="concept.macd_dead_cross"' in lines
    assert "short_period=5, long_period=20" in lines
    # 정본 기간이 없는 개념(MACD 고정 12/26/9)은 'parameters 항상 비움' 계약 줄
    assert "parameters는 항상 비움" in lines
    # 미계약 개념(가격 vs 한 선)은 여전히 표기 정본 참고 형식
    assert "= technical.ma_crossover" in lines


def test_llm_output_concepts_have_deterministic_expansion():
    """llm_output 개념은 전개가 완전 결정적이어야 한다(연산자 선언 필수) —
    아니면 물질화가 방향을 지어내야 하므로 무결성 검증이 막는다."""
    ontology = get_ontology()
    flagged = [c for c in ontology.concepts.values() if c.llm_output]
    assert {c.id for c in flagged} == {
        "concept.golden_cross", "concept.dead_cross",
        "concept.macd_golden_cross", "concept.macd_dead_cross",
    }
    for concept in flagged:
        assert concept.expansion["operator"] is not None


def test_graph_dump_shape():
    """콘솔 시각화 덤프 — 노드 3종(kind)과 엣지 참조 무결성."""
    graph = ontology_graph()
    node_ids = {n["id"] for n in graph["nodes"]}
    kinds = {n["kind"] for n in graph["nodes"]}
    assert kinds == {"class", "leaf", "concept"}
    for edge in graph["edges"]:
        assert edge["source"] in node_ids, f"엣지 source 미존재: {edge}"
        assert edge["target"] in node_ids, f"엣지 target 미존재: {edge}"
        assert edge["type"] in ("is_a", "expands_to", "requires")
    assert graph["issues"] == []
