"""분위(퀀타일) 그룹 비교·비율 선정(FR-BT-060) — 해석 레인 결정론 계층 검증.

'PER 낮은 순 정렬 → 종목 수 동일 10개 그룹 → 그룹별 편입/비교' 요청과
'상위 X% 편입' 요청이 LLM 출력(StrategyIntent)에서 ParsedStrategy·백테스트 요청까지
소실 없이 왕복하는지 확인한다(LLM 없이 결정론 계층만).
"""

from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _quantile_intent_dict(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI"], "sectors": []},
        "entry_conditions": [],
        "exit_conditions": [],
        "ranking": [
            {"metric": "fundamental.per", "direction": "bottom", "quantile_groups": 10,
             "source_text": "PER 가장 낮은 종목부터 10개 그룹으로 나눠"}
        ],
        "portfolio": {"selection_count": None, "rebalance_frequency": "monthly"},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return {
        "intent": "CREATE_STRATEGY",
        "status": "READY",
        "confidence": 0.9,
        "strategy": strategy,
    }


def test_quantile_groups_compile_to_parsed_strategy():
    """quantile_groups=10 랭킹이 ParsedStrategy.ranking_quantile_groups로 컴파일된다."""
    validated, report = run_validation(
        StrategyIntent.model_validate(_quantile_intent_dict())
    )
    parsed = compile_strategy(validated, report, "PER 십분위 그룹 비교")
    assert parsed.ranking_metric == "per"
    assert parsed.ranking_direction == "bottom"
    assert parsed.ranking_quantile_groups == 10


def test_quantile_groups_do_not_ask_selection_count():
    """그룹이 편입 규모를 정의하므로 '상위 몇 종목?' 되묻기가 나가면 안 된다."""
    _, report = run_validation(
        StrategyIntent.model_validate(_quantile_intent_dict())
    )
    assert "strategy.portfolio.selection_count" not in report.missing_fields, (
        f"분위 그룹 전략에 종목 수 되묻기가 나감: {report.missing_fields}"
    )


def test_selection_percent_compiles_and_suppresses_count_question():
    """'상위 10%만 편입'(selection_percent)이 max_positions_pct로 컴파일되고
    종목 수 되묻기를 만들지 않는다."""
    data = _quantile_intent_dict(
        ranking=[{"metric": "fundamental.per", "direction": "bottom",
                  "source_text": "PER 낮은 순"}],
        portfolio={"selection_count": None, "selection_percent": 10,
                   "rebalance_frequency": "monthly"},
    )
    validated, report = run_validation(StrategyIntent.model_validate(data))
    assert "strategy.portfolio.selection_count" not in report.missing_fields
    parsed = compile_strategy(validated, report, "PER 낮은 상위 10% 편입")
    assert parsed.max_positions_pct == 10


def test_quantile_group_range_validated():
    """분위 그룹 수는 2~10 — 범위 밖이면 검증 에러로 잡힌다(조용한 보정 금지)."""
    _, report = run_validation(
        StrategyIntent.model_validate(_quantile_intent_dict(
            ranking=[{"metric": "fundamental.per", "direction": "bottom",
                      "quantile_groups": 50}],
        ))
    )
    assert any("분위 그룹" in e for e in report.errors), report.errors


def test_quantile_fields_roundtrip_decompile_compile():
    """수정 턴 라운드트립: parsed → decompile → 재compile에서 분위·비율 필드가 소실되지
    않는다(소실되면 라운드트립 가드가 모든 수정을 레거시 레인으로 떨어뜨린다)."""
    validated, report = run_validation(
        StrategyIntent.model_validate(_quantile_intent_dict())
    )
    parsed = compile_strategy(validated, report, "PER 십분위 그룹 비교")
    draft = decompile_strategy(parsed)
    assert draft.ranking[0].quantile_groups == 10
    revalidated, rereport = run_validation(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=draft, confidence=1.0)
    )
    recompiled = compile_strategy(revalidated, rereport, parsed.description)
    assert recompiled.ranking_quantile_groups == parsed.ranking_quantile_groups
    assert recompiled.ranking_metric == parsed.ranking_metric
    assert recompiled.ranking_direction == parsed.ranking_direction


def test_selection_percent_roundtrip_decompile_compile():
    parsed_fields = {"max_positions_pct": 10.0}
    from engine.nl_parser import ParsedStrategy

    parsed = ParsedStrategy(
        description="PER 낮은 상위 10% 편입",
        universe=["KOSPI"],
        ranking_metric="per",
        ranking_direction="bottom",
        rebalancing_period="monthly",
        **parsed_fields,
    )
    draft = decompile_strategy(parsed)
    assert draft.portfolio.selection_percent == 10.0
    revalidated, rereport = run_validation(
        StrategyIntent(intent="CREATE_STRATEGY", strategy=draft, confidence=1.0)
    )
    recompiled = compile_strategy(revalidated, rereport, parsed.description)
    assert recompiled.max_positions_pct == 10.0


def test_converter_carries_quantile_fields_to_backtest_request():
    """to_backtest_request risk에 새 필드가 실리고, BacktestRequest 스키마의
    model_dump에서도 살아남는다(extra=ignore 조용한 소실 함정 회귀)."""
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request
    from schemas import BacktestRequest

    parsed = ParsedStrategy(
        description="PER 십분위",
        universe=["KOSPI"],
        ranking_metric="per",
        ranking_direction="bottom",
        ranking_quantile_groups=10,
        max_positions_pct=10.0,
        rebalancing_period="monthly",
    )
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["ranking_quantile_groups"] == 10
    assert req["risk"]["max_positions_pct"] == 10.0

    dumped = BacktestRequest(
        symbols=[], entry={"conditions": []}, exit={"conditions": []},
        risk={**req["risk"], "position_size_pct": 10.0},
    ).model_dump()
    assert dumped["risk"]["ranking_quantile_groups"] == 10
    assert dumped["risk"]["max_positions_pct"] == 10.0


def test_strategy_id_unchanged_for_existing_strategies():
    """새 필드가 None인 기존 전략의 canonical DSL에는 새 키가 들어가지 않는다
    (strategy_id 해시 불변 — 캐시·기록 호환)."""
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_canonical_strategy_dsl

    parsed = ParsedStrategy(
        description="기존 전략",
        universe=["KOSPI"],
        ranking_metric="per",
        rebalancing_period="monthly",
    )
    canonical = to_canonical_strategy_dsl(parsed)
    assert "ranking_quantile_groups" not in canonical
    assert "max_positions_pct" not in canonical


# ─── 그룹당 보유 상한 (FR-BT-060b) ───────────────────────────────────────────

def test_quantile_selection_count_compiles_to_group_cap():
    """분위 그룹 전략에서 사용자가 말한 종목 수는 그룹당 보유 상한으로 컴파일된다."""
    data = _quantile_intent_dict(
        portfolio={"selection_count": 15, "rebalance_frequency": "quarterly"},
    )
    validated, report = run_validation(StrategyIntent.model_validate(data))
    parsed = compile_strategy(validated, report, "PER 십분위 그룹당 15종목")
    assert parsed.ranking_group_cap == 15
    assert parsed.ranking_quantile_groups == 10


def test_group_cap_roundtrip_decompile_compile():
    """cap 있는/없는 분위 전략 모두 라운드트립에서 필드가 보존된다 — 어긋나면 모든
    수정이 레거시 레인으로 폴백한다(라운드트립 가드)."""
    for count in (15, None):
        data = _quantile_intent_dict(
            portfolio={"selection_count": count, "rebalance_frequency": "quarterly"},
        )
        validated, report = run_validation(StrategyIntent.model_validate(data))
        parsed = compile_strategy(validated, report, "PER 십분위")
        draft = decompile_strategy(parsed)
        revalidated, rereport = run_validation(
            StrategyIntent(intent="CREATE_STRATEGY", strategy=draft, confidence=1.0)
        )
        recompiled = compile_strategy(revalidated, rereport, parsed.description)
        assert recompiled.ranking_group_cap == parsed.ranking_group_cap == count
        assert recompiled.max_positions == parsed.max_positions


def test_converter_carries_group_cap():
    from engine.nl_parser import ParsedStrategy
    from engine.strategy_converter import to_backtest_request
    from schemas import BacktestRequest

    parsed = ParsedStrategy(
        description="PER 십분위 그룹당 10종목",
        universe=["KOSPI"],
        ranking_metric="per",
        ranking_direction="bottom",
        ranking_quantile_groups=10,
        ranking_group_cap=10,
        rebalancing_period="quarterly",
    )
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["ranking_group_cap"] == 10
    dumped = BacktestRequest(
        symbols=[], entry={"conditions": []}, exit={"conditions": []},
        risk={**req["risk"], "position_size_pct": 10.0},
    ).model_dump()
    assert dumped["risk"]["ranking_group_cap"] == 10


def test_quantile_chip_answer_sets_group_cap():
    """'그룹당 10종목' 칩 답변(결정 레인)이 그룹당 상한과 종목 수를 함께 채운다."""
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    base = ParsedStrategy(
        description="PER 십분위",
        universe=["KOSPI"],
        ranking_metric="per",
        ranking_direction="bottom",
        ranking_quantile_groups=10,
        rebalancing_period="quarterly",
    )
    after = _apply_prompt_overrides(base, "그룹당 10종목", skip_signal_validation=True)
    assert after.ranking_group_cap == 10
    assert after.max_positions == 10


def test_non_quantile_chip_answer_leaves_group_cap_none():
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    base = ParsedStrategy(
        description="일반 랭킹",
        universe=["KOSPI"],
        ranking_metric="per",
        rebalancing_period="monthly",
    )
    after = _apply_prompt_overrides(base, "최대 10종목", skip_signal_validation=True)
    assert after.ranking_group_cap is None
    assert after.max_positions == 10


def test_quantile_slot_ask_uses_dedicated_question_and_chips():
    """분위 그룹 전략의 '최대 보유' 되묻기는 전용 질문·칩(그룹당 10종목~)으로 나간다."""
    from engine import strategy_slots
    from engine.nl_parser import ParsedStrategy

    parsed = ParsedStrategy(
        description="PER 십분위",
        universe=["KOSPI"],
        ranking_metric="per",
        ranking_direction="bottom",
        ranking_quantile_groups=10,
        rebalancing_period="quarterly",
    )
    statuses = {
        s.field: s for s in strategy_slots.evaluate(parsed, require_explicit=True)
    }
    mp = statuses[strategy_slots.MAX_POSITIONS]
    assert not mp.filled, "cap 미답변인데 최대 보유가 충족으로 판정됨"
    assert "분위 그룹" in mp.question
    assert mp.suggestions == ("그룹당 10종목", "그룹당 20종목", "그룹당 30종목")
    # 정본 칩 조회 경로(suggestions_for_topic)도 같은 칩을 낸다.
    assert strategy_slots.suggestions_for_topic(
        "최대 보유", parsed=parsed
    ) == ["그룹당 10종목", "그룹당 20종목", "그룹당 30종목"]

    # cap을 답하면 provenance 없이도 충족된다(물질화 기본값이 없는 필드).
    answered = parsed.model_copy(update={"ranking_group_cap": 10})
    statuses = {
        s.field: s for s in strategy_slots.evaluate(answered, require_explicit=True)
    }
    assert statuses[strategy_slots.MAX_POSITIONS].filled
