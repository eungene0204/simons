"""2026-08-02 Agent Architecture Audit #3 결함 수정 회귀.

감사 하니스(프론트 무상태 에코 계약 재현, 25턴 실측)가 찾은 결함들의 재현 절차를
그대로 테스트로 고정한다. 각 테스트 머리에 감사 시나리오 id를 남긴다.

#1 B1-T2: 유니버스 전환(코스피+PER → ETF)이 capability 오류로 레인 전체 폴백
   → "해석하지 못했어요" 오보고. 검증기 문구를 되묻기로 전달해야 한다.
#2 C1-T6: "초기 자금 5천만원"의 정당한 패치가 복합 수사 단위(천만) 미해석으로
   환각 게이트에서 거부 → 미반영.
#5 D1: Artifact 상태 레인이 라이브 경로(model_dump dict)에서 항상 None.
#6 비-SSE /strategy/parse 응답 모델에 field_states 부재 → 에코 계약 성립 불가.
#7 C1-T6: 미반영(notices-only) 응답이 열려 있던 되묻기 질문을 화면에서 지움.
"""

from engine.nl_parser import ParsedStrategy
from strategy_conversation import primary
from strategy_conversation.interpreter.models import PatchOp, StrategyIntent


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _kospi_per_strategy() -> ParsedStrategy:
    """감사 B1-T1 상태: 코스피 + PER 10 이하 스크리닝."""
    return ParsedStrategy.model_validate({
        "description": "코스피에서 PER 10 이하 종목 매수 전략 만들어줘",
        "universe": ["KOSPI"],
        "fundamental_filters": [{"metric": "per", "operator": "<=", "value": 10.0}],
        "max_positions": 10,
        "rebalancing_period": "monthly",
        "backtest_period": "5y",
        "initial_capital": 10_000_000.0,
    })


class _StubInterpreter:
    def __init__(self, intent_data):
        from strategy_conversation.interpreter.llm_strategy_interpreter import (
            InterpreterResult,
        )
        self._result = InterpreterResult(
            intent=StrategyIntent.model_validate(intent_data),
            raw_output="{}", repair_attempts=0, latency_ms=1.0, model_name="stub",
            unreflected_numbers=None,
        )

    def interpret(self, user_input, draft=None, pending_question=None, on_stage=None):
        return self._result


def _stub(monkeypatch, intent_data):
    monkeypatch.setattr(primary, "_interpreter_singleton", _StubInterpreter(intent_data))


def _provenance(patch, user_input: str) -> bool:
    from engine.nl_parser import _compact

    return primary._patch_provenance_supported(
        patch, _compact(user_input), primary._input_number_candidates(user_input)
    )


# ── #2 환각 게이트 복합 수사 단위 ────────────────────────────────────────────

def test_compound_korean_amount_units_pass_provenance_gate():
    """C1-T6 재현: LLM이 정확한 값(5천만원=5e7)+인용을 냈는데 '5천'(5,000)으로
    잘려 자릿수 모순 판정 → 거부되던 결함. 복합 단위는 환산표의 표기 변환이다."""
    cases = [
        ("초기 자금 5천만원", 50_000_000),
        ("초기 자금 3백만원", 3_000_000),
        ("초기 자금 50만원", 500_000),
    ]
    for utter, value in cases:
        patch = PatchOp(op="replace", path="/backtest/initial_capital",
                        value=value, source_text=utter)
        assert _provenance(patch, utter) is True, utter
        assert primary._quote_contradicts_value(utter, value) is False, utter


def test_digit_error_detection_still_works_after_unit_fix():
    """복합 단위 추가가 게이트의 존재 이유(자릿수 오류 검출)를 무디게 하면 안 된다 —
    '1000억원'에 1e10(10배 오차)은 여전히 모순이다(2026-08-02 실측 사고)."""
    assert primary._quote_contradicts_value("1000억원", 10_000_000_000) is True
    # 복합 단위에서도 자릿수 오류는 잡는다: 5천만원에 5억(10배)은 모순
    assert primary._quote_contradicts_value("초기 자금 5천만원", 500_000_000) is True


def test_recall_validator_reflects_compound_units():
    from strategy_conversation.validation.recall_validator import (
        _candidates,
        _input_anchors,
    )

    anchors = _input_anchors("초기 자금 5천만원")
    assert [(label, unit) for label, _v, unit in anchors] == [("5천만", "천만")]
    assert 50_000_000.0 in _candidates(5, "천만")
    assert 1_000_000.0 in _candidates(1, "백만")
    assert 100_000.0 in _candidates(1, "십만")


# ── #1 유니버스 전환 capability 오류 → 되묻기 ────────────────────────────────

def test_universe_switch_capability_error_returns_clarification(monkeypatch):
    """B1-T2 재현: '유니버스를 ETF로 바꿔줘' 패치는 정확했고 검증이 거부했다.
    폴백('해석하지 못했어요' 오보고) 대신 전략 무변경 + 검증기 문구 되묻기여야 한다."""
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    _stub(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.9,
        "patches": [{"op": "replace", "path": "/universe/markets", "value": ["ETF"],
                     "source_text": "유니버스를 ETF로 바꿔줘"}],
    })
    prev = _kospi_per_strategy()
    result = primary.run_primary_modification("유니버스를 ETF로 바꿔줘", prev.model_dump())

    assert result is not None, "검증 거부가 폴백(None)으로 위장되면 안 된다"
    assert result["interpreter"]["mode"] == "primary_modify_capability_conflict"
    assert result["parsed"].model_dump() == prev.model_dump()  # 전략 무변경
    question = result["clarification_question"] or ""
    assert "ETF" in question and "PER" in question  # 검증기 문구가 사용자에게 도달
    assert result["clarification_priority"] == "modify_unapplied"
    chips = result["clarification_suggestions"] or []
    assert any("조건을 빼고 ETF로 바꿔줘" in c for c in chips)


def test_capability_conflict_without_universe_change_has_no_removal_chip():
    """유니버스가 그대로인 오류(기존 ETF 전략에 재무 조건 추가)는 제거 칩이 성립하지
    않는다 — 질문만 낸다."""
    from strategy_conversation.interpreter.models import StrategySpec, ValidationReport

    spec = StrategySpec.model_validate({"universe": {"markets": ["ETF"]}})
    report = ValidationReport(
        is_valid=False, status="NEEDS_CLARIFICATION",
        errors=["ETF는 여러 종목을 묶은 상품이라 진입 조건 'PER(주가수익비율)'(기업 재무지표)을 사용할 수 없습니다"],
        unsupported_features=["ETF 유니버스 × PER(주가수익비율)"],
    )
    question, chips, _ask = primary._capability_conflict_clarification(
        report, spec, spec, None)
    assert question and "사용할 수 없습니다" in question
    assert chips is None


# ── #7 미반영 턴 열린 질문 재표시 ────────────────────────────────────────────

_OPEN_ASK = {"topic": "리스크 관리",
             "question": "익절 — 목표 수익 비율을 정해주세요",
             "chips": ["익절 20%", "익절 10%"]}


def test_rejected_patches_turn_reattaches_open_question(monkeypatch):
    """C1-T6 재현: 전량 거부(미반영 안내) 턴이 답을 기다리던 익절 질문을 화면에서
    지웠다 — 에코된 pending_ask를 그대로 되붙여야 한다."""
    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    _stub(monkeypatch, {
        "intent": "MODIFY_STRATEGY", "status": "READY", "confidence": 0.9,
        # 인용도 수치도 없는 환각 패치 — 게이트가 전량 거부한다
        "patches": [{"op": "replace", "path": "/portfolio/rebalance_frequency",
                     "value": "monthly"}],
    })
    prev = _kospi_per_strategy()
    result = primary.run_primary_modification(
        "다른 예는 없어?", prev.model_dump(), pending_ask=dict(_OPEN_ASK),
        pending_question=_OPEN_ASK["question"])

    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify_rejected_patches"
    assert result["notices"], "미반영 안내는 유지된다"
    assert result["clarification_question"] == _OPEN_ASK["question"]
    assert result["clarification_suggestions"] == _OPEN_ASK["chips"]
    assert (result["pending_ask"] or {}).get("topic") == "리스크 관리"


def test_explain_turn_reattaches_open_question(monkeypatch):
    """설명(EXPLAIN_INDICATOR) 턴도 같은 증상 — 답변 notices에 더해 열린 질문을 되붙인다."""
    import api.intent_routes as intent_routes

    monkeypatch.setenv("STRATEGY_MODIFY_INTERPRETER_MODE", "llm_first")
    monkeypatch.setattr(intent_routes, "generate_general_answer",
                        lambda _q: "PER은 주가수익비율입니다.")
    _stub(monkeypatch, {
        "intent": "EXPLAIN_INDICATOR", "status": "READY", "confidence": 0.9,
    })
    prev = _kospi_per_strategy()
    result = primary.run_primary_modification(
        "PER이 뭐야?", prev.model_dump(), pending_ask=dict(_OPEN_ASK))

    assert result is not None
    assert result["interpreter"]["mode"] == "primary_modify_explain"
    assert result["clarification_question"] == _OPEN_ASK["question"]
    assert (result["pending_ask"] or {}).get("question") == _OPEN_ASK["question"]


def test_reattach_noop_without_open_question():
    assert primary._reattach_open_question(None, None) == {}
    assert primary._reattach_open_question({}, "") == {}


# ── #4 후속: 후보 1개 표현의 해석 완료 전파 ─────────────────────────────────

def test_single_candidate_source_term_marked_resolved(monkeypatch):
    """'ESS' 후보 조회가 '전력저장장치(ESS)' 하나를 내고 그 정본 표기가 테마로
    적용됐으면 원 표현도 해석 완료다 — 전파하지 않으면 term-in 체인이 같은 표현에
    kg_resolve_sector를 또 돌려 섹터를 이중 병합한다(실측: artifacts STALE 오염)."""
    from strategy_conversation.planner.dag import DagNode
    from strategy_conversation.planner.dag_planner import ExecutedNode

    import engine.nl_parser as nl

    applied = []
    monkeypatch.setattr(nl, "apply_theme_companies",
                        lambda parsed, term: applied.append(term) or True)

    class _Result:
        executed = {
            "cand": ExecutedNode(
                DagNode(id="cand", type="tool", tool="list_concept_candidates",
                        args={"text": "ESS"}),
                {"candidates": [{"term": "전력저장장치(ESS)", "companies": 60}]},
            ),
        }
        auto_steps = [{
            "id": "auto:0", "tool": "kg_theme_companies",
            "args": {"text": "전력저장장치(ESS)"},
            "observation": {"found": True, "term": "전력저장장치(ESS)",
                            "companies": [{"symbol": "006400", "name": "삼성SDI"}]},
        }]

    parsed = ParsedStrategy.model_validate({"description": "x", "universe": ["KOSPI200"]})
    resolved, unresolved = primary._apply_planner_first_universe(_Result(), parsed, [])
    assert applied == ["전력저장장치(ESS)"]
    assert "ESS" in resolved and "전력저장장치(ESS)" in resolved
    assert unresolved == set()


# ── #5 Artifact 레인 dict 수용 ───────────────────────────────────────────────

def test_artifacts_accept_model_dump_dict():
    """D1 재현: 라이브 경로는 직렬화된 dict를 넘긴다 — getattr만 쓰면 테마 전략의
    25턴 전부 artifacts=null이었다. 인스턴스와 dict가 같은 판정을 내야 한다."""
    from strategy_conversation.conversation.artifacts import evaluate_artifacts

    parsed = ParsedStrategy.model_validate({
        "description": "ESS 관련주로 전략 만들어줘",
        "universe": ["KOSPI200"],
        "target_symbols": ["006400", "373220"],
        "theme_universe": "ESS",
    })
    from_instance = evaluate_artifacts(parsed, None)
    from_dict = evaluate_artifacts(parsed.model_dump(), None)
    assert from_instance == from_dict
    assert from_dict["universe.symbols"]["status"] == "VALID"
    assert from_dict["universe.symbols"]["source_key"] == "ESS"

    # 근거 소멸(INVALIDATED)도 dict에서 판정돼야 한다
    dropped = parsed.model_dump()
    dropped["theme_universe"] = None
    dropped["target_symbols"] = []
    prior = dict(from_dict)
    result = evaluate_artifacts(dropped, prior)
    assert result["universe.symbols"]["status"] == "INVALIDATED"


# ── #6 field_states 응답 모델 ────────────────────────────────────────────────

def test_nl_parse_response_exposes_field_states():
    """비-SSE 라우트는 response_model이 없는 키를 잘라낸다 — field_states가 모델에
    없으면 previous_field_states 에코 계약이 그 라우트에서 영원히 성립 불가다."""
    from main import NLParseResponse

    assert "field_states" in NLParseResponse.model_fields
