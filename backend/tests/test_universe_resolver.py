"""Universe Resolver 계약 — LLM이 뽑은 표현을 정본 유니버스 값으로 해석한다.

핵심: 입력은 사용자 원문이 아니라 **LLM이 추출한 짧은 문자열**이다
(docs/nl_interpretation_contract.md § 3, 1a+4 마이그레이션).
"""

from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import (
    BacktestSpec,
    StrategyCondition,
    StrategyIntent,
    StrategySpec,
    UniverseSpec,
    ValidationReport,
)
from strategy_conversation.registry.universe_resolver import resolve_sectors, resolve_symbols


# ── 업종/테마 해석 ────────────────────────────────────────────────────────────

def test_resolve_sectors_canonical_and_synonym():
    value, unresolved = resolve_sectors(["반도체"])
    assert value == "반도체"
    assert unresolved == []


def test_resolve_sectors_multiple_returns_list():
    value, unresolved = resolve_sectors(["반도체", "로봇"])
    assert isinstance(value, list) and len(value) == 2
    assert unresolved == []


def test_resolve_sectors_dedup_preserves_order():
    value, _ = resolve_sectors(["반도체", "반도체"])
    assert value == "반도체"


def test_resolve_sectors_reports_unresolved_instead_of_silent_drop():
    value, unresolved = resolve_sectors(["도저히없는업종이름123"])
    assert value is None
    assert unresolved == ["도저히없는업종이름123"]


def test_resolve_sectors_ignores_blank_and_non_string():
    value, unresolved = resolve_sectors(["", "   ", None])
    assert value is None
    assert unresolved == []


# ── 지정 종목 해석 ────────────────────────────────────────────────────────────

def test_resolve_symbols_by_name():
    codes, unresolved = resolve_symbols(["삼성전자"])
    assert codes == ["005930"]
    assert unresolved == []


def test_resolve_symbols_by_code():
    codes, unresolved = resolve_symbols(["005930"])
    assert codes == ["005930"]
    assert unresolved == []


def test_resolve_symbols_multiple_dedup():
    codes, _ = resolve_symbols(["삼성전자", "005930", "SK하이닉스"])
    assert codes == ["005930", "000660"]


def test_resolve_symbols_reports_unresolved():
    codes, unresolved = resolve_symbols(["존재하지않는회사명입니다"])
    assert codes == []
    assert unresolved == ["존재하지않는회사명입니다"]


def test_resolve_symbols_rejects_overseas():
    """해외 종목은 백테스트 OHLCV가 없어 지정해도 실행 불가 — 조용히 통과시키지 않는다."""
    codes, unresolved = resolve_symbols(["AAPL"])
    assert codes == []
    assert unresolved == ["AAPL"]


# ── 컴파일 배선 (FR-STR-068 — LLM이 종목을 지목하면 target_symbols로) ──────────

def _intent(universe: UniverseSpec) -> StrategyIntent:
    return StrategyIntent(
        intent="CREATE_STRATEGY",
        status="READY",
        strategy=StrategySpec(universe=universe),
    )


def _valid_report() -> ValidationReport:
    return ValidationReport(is_valid=True, status="READY")


def test_compile_maps_llm_symbols_to_target_symbols():
    parsed = compile_strategy(
        _intent(UniverseSpec(markets=["KOSPI"], symbols=["삼성전자"])),
        _valid_report(),
        "삼성전자로 백테스트",
    )
    assert parsed.target_symbols == ["005930"]


def test_compile_canonicalizes_llm_sector_terms():
    """LLM이 낸 업종 표현은 정본화 후 sector에 들어간다(원문 재해석 없이)."""
    parsed = compile_strategy(
        _intent(UniverseSpec(markets=["KOSPI", "KOSDAQ"], sectors=["반도체"])),
        _valid_report(),
        "반도체 업종 전략",
    )
    assert parsed.sector == "반도체"


def test_compile_without_symbols_keeps_target_symbols_empty():
    parsed = compile_strategy(
        _intent(UniverseSpec(markets=["KOSPI200"])),
        _valid_report(),
        "코스피200 전략",
    )
    assert parsed.target_symbols == []


def test_decompile_roundtrips_target_symbols():
    """수정 요청 초안에서 지정 종목이 소실되면 지정이 풀린다."""
    parsed = compile_strategy(
        _intent(UniverseSpec(markets=["KOSPI"], symbols=["삼성전자"])),
        _valid_report(),
        "삼성전자로 백테스트",
    )
    spec = decompile_strategy(parsed)
    assert spec.universe.symbols == ["005930"]


# ── 스키마 드리프트 정규화 ────────────────────────────────────────────────────

def test_universe_spec_coerces_single_string_symbols():
    spec = UniverseSpec.model_validate({"markets": ["KOSPI"], "symbols": "삼성전자"})
    assert spec.symbols == ["삼성전자"]


def test_universe_spec_drops_non_string_symbol_items():
    spec = UniverseSpec.model_validate({"markets": ["KOSPI"], "symbols": ["삼성전자", 5930]})
    assert spec.symbols == ["삼성전자"]


def test_universe_spec_symbols_default_empty():
    assert UniverseSpec().symbols == []


# ── 표준값 있는 파라미터는 조건을 드롭시키지 않는다 (A/B 실측 2026-07-26) ──────────

def test_missing_defaultable_param_keeps_condition():
    """'데드크로스에 청산'을 기간 미언급 이유로 버리면 사용자가 준 정보를 잃는다.

    Registry 표준값(20/60)으로 컴파일하고 되묻기 질문은 유지한다.
    """
    from strategy_conversation.compiler.strategy_compiler import compile_partial
    from strategy_conversation.validation.pipeline import run_validation

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY",
        "strategy": {
            "universe": {"markets": ["KOSPI"]},
            "entry_conditions": [
                {"factor": "technical.ma_crossover", "operator": "crosses_above", "value": None},
            ],
            "exit_conditions": [
                {"factor": "technical.ma_crossover", "operator": "crosses_below", "value": None},
            ],
        },
    })
    validated, report = run_validation(intent)
    parsed, dropped = compile_partial(validated, report, "골든크로스 매수 데드크로스 매도")

    assert dropped == []
    assert [(s.indicator, s.signal_type, s.short_period, s.long_period)
            for s in parsed.entry_signals] == [("ma_crossover", "buy", 20, 60)]
    assert [(s.indicator, s.signal_type) for s in parsed.exit_signals] == [("ma_crossover", "sell")]
    # 되묻기는 유지된다 — 표준값 적용이 질문을 삼키지 않는다(무단 확정 금지).
    assert any(q.field.endswith(".parameters.short_period")
               for q in report.clarification_questions)


def test_missing_threshold_still_drops_condition():
    """임계값(value) 누락은 전략의 의미 자체가 미정 — 기존대로 제외한다(경계 유지)."""
    from strategy_conversation.compiler.strategy_compiler import compile_partial
    from strategy_conversation.validation.pipeline import run_validation

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY",
        "strategy": {
            "universe": {"markets": ["KOSPI"]},
            "entry_conditions": [
                {"factor": "fundamental.per", "operator": "<=", "value": None},
            ],
        },
    })
    validated, report = run_validation(intent)
    parsed, dropped = compile_partial(validated, report, "PER이 낮은 종목")
    assert dropped
    assert parsed.fundamental_filters == []


# ── execution_timing 스키마 공백 해소 ─────────────────────────────────────────

def test_compile_maps_execution_timing():
    parsed = compile_strategy(
        StrategyIntent(
            intent="CREATE_STRATEGY", status="READY",
            strategy=StrategySpec(
                universe=UniverseSpec(markets=["KOSPI"]),
                backtest=BacktestSpec(execution_timing="current_close"),
            ),
        ),
        _valid_report(),
        "당일 종가로 체결",
    )
    assert parsed.execution_timing == "current_close"


def test_compile_defaults_execution_timing_to_next_open():
    parsed = compile_strategy(
        _intent(UniverseSpec(markets=["KOSPI"])), _valid_report(), "전략",
    )
    assert parsed.execution_timing == "next_open"


def test_decompile_roundtrips_execution_timing():
    """수정 초안이 체결 시점을 잃으면 '당일 종가로 바꿔줘'가 삼켜진다."""
    parsed = compile_strategy(
        StrategyIntent(
            intent="CREATE_STRATEGY", status="READY",
            strategy=StrategySpec(
                universe=UniverseSpec(markets=["KOSPI"]),
                backtest=BacktestSpec(execution_timing="current_close"),
            ),
        ),
        _valid_report(),
        "당일 종가로 체결",
    )
    assert decompile_strategy(parsed).backtest.execution_timing == "current_close"


# ── AI 임계값: 사용자 값이 Registry 기본값보다 우선 ──────────────────────────

def _ai_intent(value):
    return StrategyIntent(
        intent="CREATE_STRATEGY", status="READY",
        strategy=StrategySpec(
            universe=UniverseSpec(markets=["KOSPI"]),
            entry_conditions=[StrategyCondition(
                factor="technical.ai_model", operator=">=", value=value)],
        ),
    )


def test_ai_threshold_uses_user_value_not_registry_default():
    """'상승 확률 80% 이상'이 조용히 70%로 백테스트되던 버그(2026-07-26 A/B 실측).

    Registry 기본값(70)이 cond.value를 덮어쓰고 있었다 — 사용자가 말한 값이 항상 우선한다.
    """
    parsed = compile_strategy(_ai_intent(80), _valid_report(), "AI 상승 확률 80% 이상 매수")
    assert [s.threshold for s in parsed.entry_signals] == [80.0]


def test_ai_threshold_falls_back_to_registry_default_when_unstated():
    """임계 언급이 없으면 Registry 표준값을 쓴다(경계 유지)."""
    parsed = compile_strategy(_ai_intent(None), _valid_report(), "AI 상승 예측이 뜨면 매수")
    assert [s.threshold for s in parsed.entry_signals] == [70.0]
