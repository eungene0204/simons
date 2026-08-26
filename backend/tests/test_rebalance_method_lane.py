"""리밸런싱 방식(FR-BT-067) — 대화 레인에서 엔진까지의 배선 계약.

리밸런싱에는 종목을 교체하는 방식(reconstitute)과 같은 종목의 비중만 균등으로 되돌리는
방식(weights_only)이 있다. 사용자가 고른 값이 **대화 → 스펙 → ParsedStrategy → 엔진
risk_params**의 어느 이음매에서도 사라지지 않는다는 것이 여기서 고정하는 계약이다
(스키마에 칸이 없으면 model_dump가 조용히 버려 엔진이 못 받는다 — ranking_metric
0거래 사고와 동일 함정).
"""

from engine.nl_parser import ParsedStrategy
from engine.strategy_slots import REBALANCE_METHOD_CHIP_VALUES
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.response.provenance import (
    explicit_fields_from_patches, explicit_fields_from_spec,
)


def _parsed(method: str = "reconstitute") -> ParsedStrategy:
    return ParsedStrategy(
        description="월간 리밸런싱 전략",
        universe=["KOSPI"],
        entry_signals=[{"indicator": "ma_crossover", "signal_type": "buy",
                        "short_period": 5, "long_period": 20}],
        exit_signals=[{"indicator": "ma_crossover", "signal_type": "sell",
                       "short_period": 5, "long_period": 20}],
        max_positions=10,
        rebalancing_period="monthly",
        rebalance_method=method,
    )


def test_default_is_the_previous_behavior():
    """방식을 말하지 않은 기존 전략은 종전 동작(종목 교체)이다 — 결과값 불변."""
    assert ParsedStrategy(description="x").rebalance_method == "reconstitute"


def test_converter_passes_method_to_the_engine():
    from engine.strategy_converter import to_backtest_request

    request = to_backtest_request(_parsed("weights_only"), resolve_symbols=False)
    assert request["risk"]["rebalance_method"] == "weights_only"


def test_backtest_request_schema_keeps_the_method():
    """전송 스키마에 칸이 없으면 model_dump가 버려 엔진이 못 받는다."""
    from schemas import RiskManagement

    risk = RiskManagement(position_size_pct=10, rebalance_method="weights_only")
    assert risk.model_dump()["rebalance_method"] == "weights_only"


def test_strategy_id_is_unchanged_for_strategies_without_a_method():
    """방식이 생기기 전 저장된 전략의 해시가 흔들리면 캐시·기록이 갈라진다."""
    from engine.strategy_converter import compute_strategy_id

    legacy = _parsed().model_dump()
    legacy.pop("rebalance_method")     # 방식이 없던 시절의 전략
    assert compute_strategy_id(_parsed("reconstitute")) == compute_strategy_id(
        ParsedStrategy.model_validate(legacy)
    )
    # 방식을 바꾸면 다른 전략이다(결과가 달라지므로 캐시를 나눠야 한다).
    assert compute_strategy_id(_parsed("weights_only")) != compute_strategy_id(
        _parsed("reconstitute")
    )


def test_spec_roundtrip_keeps_the_method():
    """수정 턴은 이전 전략을 디컴파일한 초안 위에 패치를 얹는다 — 여기서 방식이 빠지면
    수정할 때마다 비중 유지 전략이 종목 교체로 되돌아간다."""
    from strategy_conversation.compiler.strategy_compiler import compile_strategy
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.pipeline import run_validation

    spec = decompile_strategy(_parsed("weights_only"))
    assert spec.portfolio.rebalance_method == "weights_only"
    validated, report = run_validation(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0)
    )
    recompiled = compile_strategy(validated, report, "월간 리밸런싱 전략")
    assert recompiled.rebalance_method == "weights_only"

    # 종목 교체(기본)는 스펙에서 null로 남는다 — 사용자가 말했다는 근거가 아니기 때문이다.
    assert decompile_strategy(_parsed("reconstitute")).portfolio.rebalance_method is None


def test_provenance_counts_the_method_only_when_the_llm_extracted_it():
    spec = decompile_strategy(_parsed("weights_only"))
    assert "rebalance_method" in explicit_fields_from_spec(spec)
    assert "rebalance_method" not in explicit_fields_from_spec(
        decompile_strategy(_parsed("reconstitute"))
    )
    assert explicit_fields_from_patches(
        [{"path": "/portfolio/rebalance_method", "value": "weights_only"}]
    ) == ["rebalance_method"]


def test_unsupported_method_value_is_dropped_with_an_error():
    """LLM이 목록 밖 값을 내면 오류로 안내하고 값을 비운다 — 값을 남기면 부분 컴파일이
    ParsedStrategy Literal에서 크래시해 해석 실패(빈 전략)로 둔갑한다(주기와 같은 계약)."""
    from strategy_conversation.interpreter.models import StrategyIntent
    from strategy_conversation.validation.capability_validator import validate_capability

    spec = decompile_strategy(_parsed())
    spec.portfolio.rebalance_method = "equal_weight"
    errors, *_ = validate_capability(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0)
    )
    assert any("리밸런싱 방식" in e for e in errors), errors
    assert spec.portfolio.rebalance_method is None


def test_chip_binding_applies_the_method_without_reading_free_text():
    """칩=값 결속 계약 — 칩 문구는 정본 표로 값이 되고, 원문 보정 파서를 타지 않는다."""
    from strategy_conversation.primary import _bind_chips

    chips = list(REBALANCE_METHOD_CHIP_VALUES)
    bound, bindings, _confirms, _declines = _bind_chips(chips, _parsed(), "리밸런싱 방식")
    assert bound == chips, "정본 칩이 노출에서 탈락하면 사용자가 답할 방법이 사라진다"
    assert bindings["비중 조정 리밸런싱 (균등 유지)"] == {"rebalance_method": "weights_only"}
    assert bindings["종목 교체 리밸런싱"] == {"rebalance_method": "reconstitute"}
