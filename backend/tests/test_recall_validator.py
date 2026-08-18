"""수치 반영 대조(Recall Validator) 계약.

이 검사는 원문을 **해석하지 않는다** — 숫자가 출력 어딘가에 반영됐는지만 대조하고,
누락 시 유일한 동작은 LLM 재생성 요청이다(docs/nl_interpretation_contract.md § 3-1).
오탐이 잦으면 무의미한 왕복만 늘어나므로, 단위 환산·부호·날짜 표현을 폭넓게 인정한다.
"""

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.recall_validator import (
    drop_ungrounded_condition_periods,
    find_unreflected_numbers,
)


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


def test_patch_source_text_echo_does_not_count_as_reflected():
    """[회귀 2026-07-31] 수정 패치의 인용문(source_text)은 사용자 원문 조각이라 값이 틀려도
    입력의 숫자를 포함한다 — 반영으로 인정하면 단위 오차가 검사를 통과한다.

    실측: 되묻기 답변 '3억원'에 9B가 value=30000000(10배 축소) + source_text='3억원'을
    출력했고, 인용의 3이 앵커 '3억'의 후보 3과 맞아 검사가 침묵 → 3천만원이 조용히 확정."""
    intent = StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY", "status": "READY", "strategy": None,
        "patches": [{"op": "replace", "path": "/backtest/initial_capital",
                     "value": 30000000, "source_text": "3억원"}],
    })
    assert find_unreflected_numbers("3억원", intent) == ["3억"]


def test_correct_unit_conversion_in_patch_passes():
    """올바른 환산(3억원=300000000)은 인용을 빼도 값 자체가 앵커와 맞아 통과한다."""
    intent = StrategyIntent.model_validate({
        "intent": "MODIFY_STRATEGY", "status": "READY", "strategy": None,
        "patches": [{"op": "replace", "path": "/backtest/initial_capital",
                     "value": 300000000, "source_text": "3억원"}],
    })
    assert find_unreflected_numbers("3억원", intent) == []


# ── 근거 없는 기간 파라미터 제거 (2026-08-07 '60일 신고가' 사고) ─────────────

def test_ungrounded_period_is_cleared_not_confirmed():
    """'60일 신고가'에 9B가 lookback_period=252를 냈다(프롬프트의 '52주=252' 예시 오적용).

    재요청도 같은 값을 반복했고 검증은 READY·미지원 0으로 통과해, 사용자가 말한 적
    없는 252가 조용히 확정됐다. 값을 만들어 채우지 않고 **비워** 되묻기로 보낸다.
    """
    intent = _intent({
        "universe": {"markets": ["KOSDAQ"]},
        "entry_conditions": [
            {"factor": "technical.breakout", "operator": "crosses_above",
             "parameters": {"lookback_period": 252},
             "source_text": "60일 신고가를 만든 뒤"},
        ],
    })
    missing = find_unreflected_numbers(
        "KOSDAQ에서 60일 신고가를 만든 뒤 5거래일 안에 거래량이 다시 증가한 종목을 매수", intent
    )
    assert "60일" in missing

    cleared = drop_ungrounded_condition_periods(
        "KOSDAQ에서 60일 신고가를 만든 뒤 5거래일 안에 거래량이 다시 증가한 종목을 매수",
        intent, missing,
    )

    assert cleared == ["entry_conditions.lookback_period=252"]
    # 비우기만 한다 — 60을 대신 채워 넣지 않는다(값 확정은 되묻기의 몫).
    assert intent.strategy.entry_conditions[0].parameters["lookback_period"] is None


def test_unit_converted_period_is_kept():
    """'52주 신고가'→252는 정당한 단위 환산이다 — 입력에 252가 없다고 비우면 오탐이다."""
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "technical.breakout", "operator": "crosses_above",
             "parameters": {"lookback_period": 252},
             "source_text": "52주 신고가"},
        ],
    })
    cleared = drop_ungrounded_condition_periods(
        "52주 신고가 돌파하고 거래대금 50억 이상", intent, ["50억"],
    )
    assert cleared == []
    assert intent.strategy.entry_conditions[0].parameters["lookback_period"] == 252


def test_system_canonical_period_without_quoted_number_is_kept():
    """기간을 말하지 않은 '골든크로스'의 정본 5/20은 건드리지 않는다.

    인용(source_text)에 수치가 없으면 '모델이 그 수치에서 나왔다고 적어 놓고 다른 값을
    넣은' 경우가 아니다 — 판정 조건 ②가 이 경우를 걸러낸다.
    """
    intent = _intent({
        "universe": {"markets": ["KOSPI"]},
        "entry_conditions": [
            {"factor": "technical.ma_crossover", "operator": "crosses_above",
             "parameters": {"short_period": 5, "long_period": 20},
             "source_text": "골든크로스"},
        ],
    })
    cleared = drop_ungrounded_condition_periods(
        "골든크로스 나면 매수하고 거래대금 50억 이상", intent, ["50억"],
    )
    assert cleared == []
    assert intent.strategy.entry_conditions[0].parameters["short_period"] == 5




# ── 재요청 폐지 + 체크리스트 선주입 (2026-08-07) ──────────────────────────────

def test_first_call_prompt_carries_the_number_checklist():
    """1차 호출이 입력 수치 목록을 받는다 — 폐지된 재요청의 유일한 무기를 앞당긴 것.

    재요청이 1차보다 더 알던 정보는 '어느 수치가 빠졌나' 하나뿐이었고, 그 목록은 출력
    없이 입력만으로 계산된다. 그래서 두 번째 호출 대신 첫 호출에 싣는다. 이 주입이
    사라지면 "RSI 30 이하에서 매수"가 entry_conditions를 통째로 비운 채 나가던 실측
    실패에 안전망이 없어진다.
    """
    from strategy_conversation.interpreter.prompts import build_user_prompt

    prompt = build_user_prompt("KOSDAQ에서 60일 신고가, 최대 8종목, 손절 -8%")

    assert "입력에 등장한 수치" in prompt
    for label in ("60일", "8종목", "8%"):
        assert label in prompt
    # 값이 아닌 표현을 임계값으로 채워 넣지 말라는 계약도 함께 간다 — 이 문구가 빠지면
    # 폐지된 재요청이 저지른 훼손(PER≤1·PBR≤1)을 1차가 그대로 재현한다.
    assert "끼워 넣지 마세요" in prompt


def test_checklist_is_empty_when_input_has_no_numbers():
    """수치가 없으면 체크리스트 블록 자체를 붙이지 않는다(프롬프트 잡음 금지)."""
    from strategy_conversation.interpreter.prompts import build_user_prompt

    assert "입력에 등장한 수치" not in build_user_prompt("골든크로스 나면 매수")


def test_input_number_labels_dedupes_in_order():
    from strategy_conversation.validation.recall_validator import input_number_labels

    assert input_number_labels("60일 신고가 뒤 5거래일, 최대 8종목, 60일 재확인") == [
        "60일", "5", "8종목",
    ]


def test_prompt_states_eok_unit_conversion_for_amount_factors():
    """단위=억원 지표의 '조' 환산 계약(프롬프트 11-2-1).

    사고(2026-08-18): "시가총액 1조 원 이상"에 9B가 value=100000을 냈다. market_cap의
    정본 단위는 억원이라 100000은 10조 — 사용자가 말한 조건의 10배가 조용히 확정됐고
    요약 카드에도 '시총 >= 10조'로 표시됐다. 수치 대조는 이 오변환을 잡아내지만
    (test_trillion_unit_misconversion_is_caught) 재생성 요청은 2026-08-07 폐지됐으므로
    막는 곳은 1차 프롬프트뿐이다.
    """
    from strategy_conversation.interpreter.prompts import PROMPT_VERSION, build_system_prompt

    assert PROMPT_VERSION >= "3.8"
    prompt = build_system_prompt()
    assert "단위=억원" in prompt and "×10,000" in prompt
    assert '"1조"=10000' in prompt
    # 초기자금(원 단위) 규칙과 혼동하지 않도록 단위가 다르다는 사실을 명시한다.
    assert "원 단위로 쓰지 말고" in prompt
