"""필드 상태 축 오버라이드(설계 스펙 § 5) — 검증 판정을 슬롯 상태로 환산한다.

여기서 고정하는 계약: 이 모듈은 **판정을 새로 하지 않는다**. 이미 검증기가 내린
판정(미지원 지표·ETF 비호환·조건 모순)을 슬롯에 붙이는 일만 한다 — 같은 규칙의 두
번째 구현을 만들면 반드시 갈라진다(strategy_slots 모듈이 생긴 이유).
"""

from __future__ import annotations
import pytest


from engine.strategy_slots import ENTRY, EXIT, DerivedStatus
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategySpec,
    UniverseSpec,
    ValidationReport,
)
from strategy_conversation.validation.field_state import slot_status_overrides


def _cond(factor: str, operator: str = "<=", value: float = 10.0) -> StrategyCondition:
    return StrategyCondition(factor=factor, operator=operator, value=value)


def test_no_findings_leaves_slots_untouched():
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    assert slot_status_overrides(spec, ValidationReport()) == {}


def test_missing_strategy_is_not_an_error():
    assert slot_status_overrides(None, ValidationReport()) == {}


def test_unknown_indicator_marks_slot_invalid():
    """Registry에 없는 지표가 값으로 남아 있으면 그 슬롯은 실행할 수 없다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("완전히.없는지표")],
    )
    assert slot_status_overrides(spec, ValidationReport())[ENTRY] is DerivedStatus.INVALID


def test_etf_universe_marks_fundamental_conditions_not_applicable():
    """ETF는 여러 종목을 묶은 상품이라 기업 재무지표가 성립하지 않는다.

    지표 자체는 지원되므로 INVALID가 아니라 NOT_APPLICABLE이다 — 둘의 구분이
    '지표를 바꿔라'와 '유니버스를 바꿔라'라는 서로 다른 해결책을 가리킨다.
    """
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    assert slot_status_overrides(spec, ValidationReport())[ENTRY] is (
        DerivedStatus.NOT_APPLICABLE
    )


def test_etf_trading_value_is_allowed():
    """거래대금은 가격·거래량 파생이라 ETF에서도 쓸 수 있다(capability_validator와 동일)."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.trading_value", ">=", 2_000_000_000)],
    )
    assert ENTRY not in slot_status_overrides(spec, ValidationReport())


def test_partial_incompatibility_leaves_slot_usable():
    """쓸 수 있는 조건이 하나라도 남으면 그 슬롯은 여전히 유효한 규칙을 갖는다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[
            _cond("fundamental.per"),
            _cond("fundamental.trading_value", ">=", 2_000_000_000),
        ],
    )
    assert ENTRY not in slot_status_overrides(spec, ValidationReport())


def test_conflicted_slot_wins_over_condition_level_findings():
    """모순은 조건 조합의 문제라 개별 조건의 지원 여부보다 먼저 해결해야 한다."""
    spec = StrategySpec(
        universe=UniverseSpec(markets=["ETF"]),
        entry_conditions=[_cond("fundamental.per")],
    )
    report = ValidationReport(conflicted_slots=[ENTRY])
    assert slot_status_overrides(spec, report)[ENTRY] is DerivedStatus.CONFLICTED


def test_exit_slot_is_evaluated_independently():
    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per")],
        exit_conditions=[_cond("완전히.없는지표")],
    )
    overrides = slot_status_overrides(spec, ValidationReport())
    assert overrides == {EXIT: DerivedStatus.INVALID}


# ── 모순 앵커 (conflict_validator → report.conflicted_slots) ────────────────────
# 오류 문장만으로는 어느 필드가 모순인지 알 수 없어 CONFLICTED를 붙일 수 없다.
# 판정한 자리에서 슬롯을 함께 기록하는 것이 계약이다.


def test_conflict_validator_anchors_contradiction_to_its_slot():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        # PER <= 5 AND PER >= 20 — 만족하는 종목이 없다
        entry_conditions=[
            _cond("fundamental.per", "<=", 5.0),
            _cond("fundamental.per", ">=", 20.0),
        ],
    )
    errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert errors
    assert conflicted == [ENTRY]


def test_crossover_period_order_conflict_is_anchored():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        exit_conditions=[
            StrategyCondition(
                factor="technical.ma_crossover",
                operator="crosses_below",
                parameters={"short_period": 60, "long_period": 20},
            )
        ],
    )
    _errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert conflicted == [EXIT]


def test_no_conflict_reports_no_slots():
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.conflict_validator import validate_conflicts

    spec = StrategySpec(
        universe=UniverseSpec(markets=["KOSPI"]),
        entry_conditions=[_cond("fundamental.per", "<=", 10.0)],
    )
    _errors, _warnings, conflicted = validate_conflicts(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec)
    )
    assert conflicted == []


# ── 하이브리드 상태 모델 (2026-07-30 설계 결정) ────────────────────────────────
# 파생 상태는 저장하지 않는다. 이 성질이 실제로 성립하는지 — 값은 보존되고, 유니버스를
# 되돌리면 역방향 패치 없이 판정도 되돌아오는지 — 를 고정한다.

def _value_strategy(markets):
    from engine.nl_parser import FundamentalFilter, ParsedStrategy

    return ParsedStrategy(
        description="저평가 전략", universe=list(markets),
        fundamental_filters=[FundamentalFilter(metric="per", operator="<=", value=10)],
    )


def test_derived_status_is_reversible_without_a_reverse_patch():
    """ETF로 바꾸면 NOT_APPLICABLE, 코스피로 되돌리면 APPLICABLE — 저장하지 않기 때문이다.

    상태를 저장했다면 ③에서 누군가(=LLM) 역방향 패치를 발행해야 하고, 빠뜨리면 멀쩡한
    PER 조건에 '적용 불가'가 영구히 남는다. 그 실패 모드가 없다는 것이 이 테스트다.
    """
    from strategy_conversation.primary import derive_field_states

    def entry_state(parsed):
        return derive_field_states(parsed, ["universe"])["매수 조건"]

    assert entry_state(_value_strategy(["KOSPI"]))["derived"] == "APPLICABLE"
    assert entry_state(_value_strategy(["ETF"]))["derived"] == "NOT_APPLICABLE"
    assert entry_state(_value_strategy(["KOSPI"]))["derived"] == "APPLICABLE"


def test_original_value_survives_a_not_applicable_universe():
    """원본 값은 삭제하지도 상태를 덮어쓰지도 않는다 — 값 축은 파생 축과 독립이다."""
    from strategy_conversation.primary import derive_field_states

    parsed = _value_strategy(["ETF"])
    state = derive_field_states(parsed, ["universe"])["매수 조건"]
    assert state["derived"] == "NOT_APPLICABLE"
    # 값 축은 '사용자가 말한 값'을 계속 사실대로 말한다.
    assert state["value"] == "CONFIRMED"
    assert parsed.fundamental_filters[0].value == 10.0


def test_derived_state_never_carries_over_from_a_previous_turn():
    """파이프라인 불변조건 — 응답 조립은 항상 이번 턴의 State로 파생 상태를 계산한다.

    계산하는 레인이 일부뿐이면 값이 비는 게 아니라 프론트가 직전 턴 사본을 계속 쓴다.
    """
    from engine.nl_parser import ParsedStrategy
    from main import _ensure_field_states

    turn1 = ParsedStrategy(description="전략", universe=["KOSPI"], max_positions=10)
    turn2 = turn1.model_copy(update={"max_positions": 5})
    stale = {"parsed": turn1, "explicit_fields": []}
    _ensure_field_states(stale)
    fresh = {"parsed": turn2, "explicit_fields": ["max_positions"]}
    _ensure_field_states(fresh)
    # 직전 턴은 기본값 물질화라 미확인, 이번 턴은 사용자가 고른 값이라 확정이다.
    assert stale["field_states"]["최대 보유"]["value"] == "PROVISIONAL"
    assert fresh["field_states"]["최대 보유"]["value"] == "CONFIRMED"


def test_existing_computation_is_reused_not_recomputed():
    """인터프리터 레인이 이미 계산했으면 덮어쓰지 않는다(재사용이지 생략이 아니다)."""
    from main import _ensure_field_states

    already = {"parsed": None, "field_states": {"유니버스": {"value": "CONFIRMED"}}}
    _ensure_field_states(already)
    assert already["field_states"] == {"유니버스": {"value": "CONFIRMED"}}


# ── Patch 허용목록 불변조건 (2026-07-30) ───────────────────────────────────────

def test_patch_allowlist_has_no_state_operations():
    """상태를 쓰는 연산은 계약상 존재하지 않는다 — 없는 것이 설계다.

    파생 상태를 패치로 기록하면 같은 판정이 evaluator와 저장값 두 곳에서 갈라진다.
    허용목록을 늘리는 것이 곧 그 계약을 깨는 일이므로 목록 자체를 고정한다.
    """
    from strategy_conversation.interpreter.models import ALLOWED_PATCH_OPS

    assert ALLOWED_PATCH_OPS == {"add", "replace", "remove"}
    for banned in ("MARK_NOT_APPLICABLE", "MARK_INVALID", "MARK_CONFLICT", "REVALIDATE"):
        assert banned not in ALLOWED_PATCH_OPS


def test_state_marking_patch_is_rejected_by_the_applier():
    from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
    from strategy_conversation.interpreter.models import StrategySpec

    class _Op:  # Pydantic Literal을 우회해 도달한 연산도 적용기가 막는다
        op = "MARK_NOT_APPLICABLE"
        path = "/entry_conditions"
        value = None

    with pytest.raises(PatchError, match="허용되지 않은 패치 연산"):
        apply_patches(StrategySpec(), [_Op()])


# ── 비권위 메타데이터 (2026-07-30 사용자 결정) ─────────────────────────────────

def _request(**over):
    from main import NLParseRequest

    return NLParseRequest(**{"prompt": "테스트", **over})


def test_metadata_records_source_and_time_for_changed_fields_only():
    from main import _ensure_field_metadata

    result = {
        "parsed": None, "changed_fields": ["max_positions"],
        "runtime": {"interpreter": {"confidence": 0.9}},
    }
    _ensure_field_metadata(result, _request(previous_field_metadata={
        "stop_loss_pct": {"source": "USER", "updated_at": "2026-07-29T00:00:00+00:00"},
    }))
    meta = result["field_metadata"]
    assert meta["max_positions"]["source"] == "USER"
    assert meta["max_positions"]["confidence"] == 0.9
    assert meta["max_positions"]["updated_at"]
    # 바뀌지 않은 필드의 기록은 그대로 남는다(무상태 누적).
    assert meta["stop_loss_pct"]["updated_at"] == "2026-07-29T00:00:00+00:00"


def test_theme_derived_symbols_are_not_recorded_as_user_provided():
    """지식 조회가 채운 종목 목록을 '사용자가 말한 값'으로 기록하지 않는다."""
    from engine.nl_parser import ParsedStrategy
    from main import _ensure_field_metadata

    parsed = ParsedStrategy(
        description="테마", target_symbols=["005930"], theme_universe="쿠팡(coupang)")
    result = {
        "parsed": parsed, "changed_fields": ["target_symbols", "max_positions"],
        "runtime": {},
    }
    _ensure_field_metadata(result, _request())
    assert result["field_metadata"]["target_symbols"]["source"] == "KNOWLEDGE_GRAPH"
    assert result["field_metadata"]["max_positions"]["source"] == "USER"


def test_metadata_is_carried_over_when_nothing_changed():
    from main import _ensure_field_metadata

    previous = {"universe": {"source": "USER", "updated_at": "2026-07-29T00:00:00+00:00"}}
    result = {"parsed": None, "changed_fields": []}
    _ensure_field_metadata(result, _request(previous_field_metadata=previous))
    assert result["field_metadata"] == previous


def test_metadata_is_never_read_by_a_decision_path():
    """비권위 계약 — 판정 코드가 이 채널을 읽지 않는다(읽으면 권위가 생긴다).

    소비자가 생기면 그때 권위를 부여할지 따로 판단한다. 그 전까지는 판정 경로에서
    이름이 등장하는 것 자체가 계약 위반이다.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    decision_paths = [
        root / "engine" / "strategy_slots.py",
        root / "strategy_conversation" / "validation" / "field_state.py",
        root / "strategy_conversation" / "validation" / "pipeline.py",
        root / "strategy_conversation" / "validation" / "completeness_validator.py",
    ]
    for path in decision_paths:
        assert "field_metadata" not in path.read_text(encoding="utf-8"), (
            f"{path.name}이 비권위 메타데이터를 읽는다 — 판정은 값과 explicit_fields만 본다"
        )


# ── 영속 Artifact 상태 (2026-07-30) ────────────────────────────────────────────
# 파생 상태와 반대로 **저장한다** — 지식그래프 조회 결과가 아직 맞는지 확인하려고
# 다시 조회할 수는 없으므로, 근거(source_key)를 남기고 대조만 한다.

def _theme_strategy(theme, sector, symbols=("005930",)):
    from engine.nl_parser import ParsedStrategy

    return ParsedStrategy(
        description="테마 전략", sector=sector,
        target_symbols=list(symbols), theme_universe=theme,
    )


def test_artifact_is_valid_while_its_source_key_still_matches():
    from strategy_conversation.conversation.artifacts import THEME_SYMBOLS, evaluate_artifacts

    got = evaluate_artifacts(_theme_strategy("반도체", "반도체"))
    assert got[THEME_SYMBOLS]["status"] == "VALID"
    assert got[THEME_SYMBOLS]["produced_by"] == "kg_theme_companies"
    assert got[THEME_SYMBOLS]["source_key"] == "반도체"
    assert got[THEME_SYMBOLS]["basis_verified"] is True


def test_artifact_goes_stale_when_the_requested_theme_changes():
    """근거가 바뀌면 재조회 없이 대조만으로 알 수 있다 — 이 모듈의 존재 이유다."""
    from strategy_conversation.conversation.artifacts import THEME_SYMBOLS, evaluate_artifacts

    # 사용자가 요구하는 업종은 반도체인데 종목은 아직 이차전지 조회 결과다.
    got = evaluate_artifacts(_theme_strategy("이차전지", "반도체"))
    assert got[THEME_SYMBOLS]["status"] == "STALE"


def test_unknown_theme_cannot_be_compared_and_says_so():
    """미지 테마는 요청이 어디에도 저장되지 않아 대조 상대가 없다.

    그때 VALID는 '확인했다'가 아니라 '반증이 없다'는 뜻이며, 그 차이를 basis_verified로
    드러낸다 — 드러내지 않으면 검증되지 않은 산출물이 검증된 것처럼 보인다.
    """
    from strategy_conversation.conversation.artifacts import THEME_SYMBOLS, evaluate_artifacts

    # sector 검증이 '토스'를 통과시키지 않아 parsed.sector는 None이 된다.
    got = evaluate_artifacts(_theme_strategy("쿠팡", "토스"))
    assert got[THEME_SYMBOLS]["status"] == "VALID"
    assert got[THEME_SYMBOLS]["basis_verified"] is False


def test_artifact_is_invalidated_when_its_basis_disappears():
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.conversation.artifacts import THEME_SYMBOLS, evaluate_artifacts

    direct = ParsedStrategy(description="직접 지정", target_symbols=["005930"])
    previous = {THEME_SYMBOLS: {"status": "VALID", "source_key": "쿠팡"}}
    got = evaluate_artifacts(direct, previous)
    assert got[THEME_SYMBOLS]["status"] == "INVALIDATED"
    # 테마 이력이 없으면 추적할 산출물 자체가 없다.
    assert evaluate_artifacts(direct, None) is None


def test_artifact_records_a_failed_lookup():
    from strategy_conversation.conversation.artifacts import THEME_SYMBOLS, evaluate_artifacts

    got = evaluate_artifacts(_theme_strategy("리센즈", "리센즈", symbols=()))
    assert got[THEME_SYMBOLS]["status"] == "FAILED"


def test_artifact_evaluation_never_triggers_a_lookup(monkeypatch):
    """판정과 실행을 섞지 않는다 — 표시용 호출이 네트워크를 타면 실패가 파스를 깬다."""
    import engine.knowledge_graph as kg
    from strategy_conversation.conversation.artifacts import evaluate_artifacts

    def _fail(*a, **k):
        raise AssertionError("Artifact 판정이 지식그래프를 조회했다")

    monkeypatch.setattr(kg, "listed_companies", _fail, raising=False)
    evaluate_artifacts(_theme_strategy("쿠팡", "토스"))
