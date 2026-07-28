"""수치 반영 대조(Recall Validator) 계약.

이 검사는 원문을 **해석하지 않는다** — 숫자가 출력 어딘가에 반영됐는지만 대조하고,
누락 시 유일한 동작은 LLM 재생성 요청이다(docs/nl_interpretation_contract.md § 3-1).
오탐이 잦으면 무의미한 왕복만 늘어나므로, 단위 환산·부호·날짜 표현을 폭넓게 인정한다.
"""

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.recall_validator import find_unreflected_numbers


def _intent(strategy: dict, **kw) -> StrategyIntent:
    return StrategyIntent.model_validate(
        {"intent": "CREATE_STRATEGY", "status": "READY", "strategy": strategy, **kw}
    )


# ── 누락 감지 (동기가 된 실측 실패 유형) ──────────────────────────────────────

def test_detects_dropped_fundamental_conditions():
    """A/B 실측: '부채비율 80% 이하이고 시총 5000억 이상'을 4B가 통째로 빠뜨렸다."""
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "technical.rsi", "operator": "<=", "value": 35}],
    })
    missing = find_unreflected_numbers(
        "부채비율 80% 이하이고 시가총액 5000억 이상인 종목 중 RSI 35 이하에서 매수", intent
    )
    assert missing == ["80%", "5000억"]


def test_source_text_echo_does_not_count_as_reflected():
    """조건은 버리고 원문만 인용한 경우를 반영으로 인정하면 검사가 무력해진다."""
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "technical.rsi", "operator": "<=", "value": None,
             "source_text": "부채비율 80% 이하"},
        ],
    })
    assert "80%" in find_unreflected_numbers("부채비율 80% 이하인 종목 매수", intent)


def test_unsupported_features_count_as_reflected():
    """'표현할 수 없다'고 명시하는 것은 정당한 처리 결과다."""
    intent = _intent(
        {"universe": {"markets": ["KOSPI"]}},
        unsupported_features=["변동성 20% 이하"],
    )
    assert find_unreflected_numbers("변동성 20% 이하인 종목", intent) == []


# ── 오탐 방지 ────────────────────────────────────────────────────────────────

def test_negative_threshold_is_not_false_positive():
    """'CCI가 -100 밑으로' → 앵커는 100, 출력은 -100. 부호는 대조 대상이 아니다."""
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [{"factor": "technical.cci", "operator": "<=", "value": -100}],
    })
    assert find_unreflected_numbers("CCI가 -100 밑으로 내려가면 진입", intent) == []


def test_unit_conversion_billion_won():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "fundamental.market_cap", "operator": ">=", "value": 5000},
        ],
    })
    assert find_unreflected_numbers("시가총액 5000억 이상", intent) == []


def test_unit_conversion_trillion_to_billion_field():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "fundamental.market_cap", "operator": ">=", "value": 10000},
        ],
    })
    assert find_unreflected_numbers("시가총액 1조 이상", intent) == []


def test_initial_capital_in_won():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "backtest": {"initial_capital": 100_000_000},
    })
    assert find_unreflected_numbers("초기 자금 1억으로 백테스트", intent) == []


def test_weeks_to_trading_days():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "technical.breakout", "operator": "crosses_above",
             "value": None, "parameters": {"lookback_period": 252}},
        ],
    })
    assert find_unreflected_numbers("52주 신고가 돌파 매수", intent) == []


def test_months_to_trading_days_in_ranking():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "ranking": [{"metric": "return", "lookback_days": 63}],
    })
    assert find_unreflected_numbers("최근 3개월 수익률 상위", intent) == []


def test_explicit_dates_reflected_via_iso_strings():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "backtest": {"start_date": "2020-01-01", "end_date": "2025-12-31"},
    })
    assert find_unreflected_numbers("2020년 1월부터 2025년 12월까지 백테스트", intent) == []


def test_backtest_period_bucket_string():
    intent = _intent({"universe": {"markets": ["KOSPI"]}, "backtest": {"period": "3y"}})
    assert find_unreflected_numbers("3년 백테스트", intent) == []


def test_moving_average_periods_in_parameters():
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "technical.ma_crossover", "operator": "crosses_above", "value": None,
             "parameters": {"short_period": 20, "long_period": 60}},
        ],
    })
    assert find_unreflected_numbers("20일선과 60일선의 골든크로스", intent) == []


def test_symbol_code_is_not_an_anchor():
    """6자리 종목코드는 universe.symbols가 문자열로 담는다 — 수치 대조 대상이 아니다."""
    intent = _intent({"universe": {"markets": ["KOSPI"], "symbols": ["005930"]}})
    assert find_unreflected_numbers("005930에 골든크로스 전략", intent) == []


def test_no_numbers_no_gap():
    intent = _intent({"universe": {"markets": ["KOSPI"]}})
    assert find_unreflected_numbers("골든크로스가 나오면 매수", intent) == []


def test_trillion_unit_misconversion_is_caught():
    """실측 미탐(2026-07-26): 시총 '1조'를 100000억으로 오변환했는데 '1'이 다른 필드와
    우연히 맞아 통과했다. 조 단위는 맨값을 후보에서 제외한다."""
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "fundamental.market_cap", "operator": ">=", "value": 100000},
            {"factor": "fundamental.per", "operator": "<=", "value": 1},
        ],
    })
    assert "1조" in find_unreflected_numbers("시가총액 1조 이상", intent)


def test_assumptions_narration_does_not_count_as_reflected():
    """실측(2026-07-26): 거래대금 조건을 조건 배열이 아니라 assumptions 서술에 적고
    빠져나갔다. 자유 서술은 반영이 아니다(source_text와 동일 취급)."""
    intent = _intent(
        {"universe": {"markets": ["KOSPI200"]},
         "entry_conditions": [{"factor": "technical.stochastic", "operator": "<=", "value": 20}]},
        assumptions=["거래대금 300억 이상은 종목 선정 기준으로 해석하여 기본 필터로 적용함"],
    )
    assert "300억" in find_unreflected_numbers(
        "거래대금 300억 이상 종목을 대상으로 스토캐스틱 과매도에서 매수", intent
    )


def test_clarification_question_echo_does_not_count_as_reflected():
    """실측 사고(2026-07-27): "거래대금 50억 이상"을 조건 대신 "추가해 드릴까요?" 질문
    + recommended_value로 돌려주자 검사가 반영으로 인정했다. 검증 파이프라인은 READY
    상태에서 LLM 자체 질문을 폐기하므로 하류 채널이 없다 — 조건이 조용히 사라진다."""
    intent = _intent(
        {"universe": {"markets": ["KOSPI"]},
         "entry_conditions": [{"factor": "fundamental.roe_or_gpa", "operator": ">=", "value": 10}]},
        missing_fields=["strategy.entry_conditions[1].factor"],
        clarification_questions=[{
            "field": "strategy.entry_conditions[1]",
            "question": "일평균 거래대금이 50억 원 이상인 조건을 추가해 드릴까요?",
            "recommended_value": {"factor": "fundamental.trading_value",
                                  "operator": ">=", "value": 50, "unit": "억원"},
        }],
    )
    assert "50억" in find_unreflected_numbers(
        "ROE 10% 이상이면서 일평균 거래대금이 50억 원 이상인 종목 매수", intent
    )


# ── 최종 전략 대조(labels_absent_from) ────────────────────────────────────────

def test_labels_absent_from_keeps_only_truly_missing_labels():
    """인터프리터 단계의 미반영 목록을 컴파일·결정적 보정까지 끝난 결과로 다시 거른다 —
    이미 되살아난 값까지 '반영하지 못했다'고 알리면 안내가 전략과 모순된다."""
    from strategy_conversation.validation.recall_validator import labels_absent_from

    payload = {"fundamental_filters": [{"metric": "roe_or_gpa", "value": 10.0}],
               "stop_loss_pct": 8.0}
    assert labels_absent_from(["10%", "8%"], payload) == []
    assert labels_absent_from(["50억"], payload) == ["50억"]


def test_recall_repair_prompt_demands_full_strategy_on_create_turn():
    """초기 파스 재요청에서 patches만 돌려주면 정상 해석이 통째로 버려진다 —
    프롬프트가 형식을 명시해야 한다(2026-07-27 사고)."""
    from strategy_conversation.validation.recall_validator import build_recall_repair_prompt

    create = build_recall_repair_prompt("거래대금 50억 이상", ["50억"], "{}")
    assert "strategy를 통째로 다시 담으세요" in create
    assert "CREATE_STRATEGY" in create
    # 수정 턴은 반대로 patches 형식을 유지해야 한다.
    modify = build_recall_repair_prompt("거래대금 50억 이상", ["50억"], "{}", draft={"universe": {}})
    assert "patches" in modify and "strategy는 null" in modify
