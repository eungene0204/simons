"""랭킹이 이미 담은 지표의 '값 없는 조건' 껍데기 정리 회귀 (2026-09-19 사고).

"PER, PBR, EV/EBITDA가 낮고 …" 한 문장을 인터프리터가 지표마다 조건("PER이 낮은")으로 쪼개고
같은 지표를 종합 점수 랭킹에도 냈다. 조건 쪽은 방향 연산자(<=·>=)만 있고 값이 없었는데
① 검증기 거울 정리가 연산자가 있으면 거울로 못 봐 "EV/EBITDA 기준값을 얼마로?"가 물어졌고
② 쪼갠 인용이 입력에 없어 출처 대조가 "요청 문장에서 확인되지 않아 반영하지 않았어요"라는
거짓 안내를 냈다(랭킹이 반영하는 조건인데). ③ FCF Yield를 FCF 마진 랭킹으로 바꿔 넣어도
별칭 예외표 때문에 대체 안내가 나가지 않았다.
"""

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.primary import _approximation_notices, _drop_fabricated_conditions
from strategy_conversation.validation.capability_validator import validate_capability

USER_INPUT = "PER, PBR, EV/EBITDA가 낮고 잉여현금흐름수익률(FCF Yield)이 높은 저평가 기업을 골라 종합 점수 상위 25개"


def _intent(conditions, ranking):
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "status": "READY", "confidence": 0.9,
        "strategy": {
            "universe": {"markets": ["KOSPI"], "sectors": []},
            "entry_conditions": conditions,
            "exit_conditions": [],
            "ranking": ranking,
            "portfolio": {"selection_count": 25, "rebalance_frequency": "monthly"},
            "risk_management": {"stop_loss": 8},
            "backtest": {},
        },
    })


def _cond(factor, operator, quote):
    return {"factor": factor, "operator": operator, "value": None, "source_text": quote}


def test_direction_only_valueless_condition_mirroring_ranking_is_removed_by_validator():
    intent = _intent(
        [_cond("fundamental.ev_ebitda", "<=", "EV/EBITDA가 낮은")],
        [{"metric": "fundamental.ev_ebitda", "direction": "bottom"}],
    )
    validate_capability(intent)
    assert intent.strategy.entry_conditions == []


def test_condition_against_ranking_direction_is_kept():
    intent = _intent(
        [_cond("fundamental.per", ">=", "PER이 높은")],
        [{"metric": "fundamental.per", "direction": "bottom"}],
    )
    validate_capability(intent)
    assert len(intent.strategy.entry_conditions) == 1


def test_valued_condition_is_never_a_mirror():
    intent = _intent(
        [{"factor": "fundamental.per", "operator": "<=", "value": 10, "source_text": "PER 10 이하"}],
        [{"metric": "fundamental.per", "direction": "bottom"}],
    )
    validate_capability(intent)
    assert len(intent.strategy.entry_conditions) == 1


def test_split_quote_mirror_gets_no_unconfirmed_notice():
    """쪼갠 인용('PER이 낮은')이 입력에 없어도 랭킹이 반영하는 조건에는 거짓 안내를 내지 않는다."""
    intent = _intent(
        [_cond("fundamental.per", "<=", "PER이 낮은"), _cond("fundamental.pbr", "<=", "PBR이 낮은")],
        [{"metric": "fundamental.per", "direction": "bottom"},
         {"metric": "fundamental.pbr", "direction": "bottom"}],
    )
    notices = _drop_fabricated_conditions(intent, USER_INPUT)
    assert notices == []
    assert intent.strategy.entry_conditions == []


def test_fabricated_condition_without_ranking_still_gets_notice():
    intent = _intent([_cond("fundamental.per", "<=", "PER이 낮은")], [])
    notices = _drop_fabricated_conditions(intent, USER_INPUT)
    assert len(notices) == 1 and "확인되지 않아" in notices[0]


def test_fcf_yield_swapped_for_fcf_margin_ranking_is_flagged_as_substitution():
    """FCF Yield는 v16.15부터 지원 지표(fundamental.fcf_yield)다. 그래도 LLM이 FCF 마진 랭킹으로
    바꿔 내면 — 조건 껍데기가 걷히면서 인용이 랭킹으로 옮겨가 — 인용↔지표 대조가 대체를 잡아
    근사 안내로 드러낸다(조용한 대체 금지). 종전(미지원 시절)엔 랭킹을 지우고 미지원으로 알렸다."""
    intent = _intent(
        [_cond("fundamental.fcf_margin", ">=", "잉여현금흐름수익률(FCF Yield)이 높은")],
        [{"metric": "fundamental.fcf_margin", "direction": "top"}],
    )
    _drop_fabricated_conditions(intent, USER_INPUT)
    validate_capability(intent)
    assert intent.strategy.entry_conditions == []
    assert [(r.metric, r.approximated) for r in intent.strategy.ranking] == [("fundamental.fcf_margin", True)]
    notices = _approximation_notices(intent.strategy)
    assert notices and "FCF Yield" in notices[0] and "FCF 마진" in notices[0]


def test_fcf_margin_named_exactly_is_not_an_approximation():
    intent = _intent(
        [_cond("fundamental.fcf_margin", ">=", "잉여현금흐름(FCF) 마진이 높은")],
        [{"metric": "fundamental.fcf_margin", "direction": "top"}],
    )
    validate_capability(intent)
    assert _approximation_notices(intent.strategy) == []


def test_condition_metric_placed_in_ranking_slot_still_mirrors_after_normalization():
    """랭킹 technical.volatility→ranking.volatility 정규화 뒤에도 같은 개념의 값 없는 조건은 거울이다."""
    intent = _intent(
        [_cond("technical.volatility", "<=", "변동성이 낮은")],
        [{"metric": "technical.volatility", "direction": "bottom"}],
    )
    validate_capability(intent)
    assert [r.metric for r in intent.strategy.ranking] == ["ranking.volatility"]
    assert intent.strategy.entry_conditions == []


def test_mirrored_condition_period_carries_into_ranking_lookback():
    """[회귀 2026-09-20] '최근 60일 주가 변동성이 낮은'을 값 없는 조건(period=60)과 랭킹(기간
    없음)에 함께 낸 120B 출력 — 거울 정리가 조건을 걷으며 60을 버려 이미 말한 산정 기간을
    되물었다. 조건의 기간은 랭킹 산정 기간으로 옮겨져야 하고, 완결성 검증은 묻지 않아야 한다."""
    from strategy_conversation.validation.completeness_validator import validate_completeness

    intent = _intent(
        [{"factor": "technical.volatility", "operator": "<=", "value": None,
          "parameters": {"period": 60}, "source_text": "최근 60일 주가 변동성이 낮은"}],
        [{"metric": "technical.volatility", "direction": "bottom"}],
    )
    validate_capability(intent)
    assert intent.strategy.entry_conditions == []
    assert [(r.metric, r.lookback_days) for r in intent.strategy.ranking] == [("ranking.volatility", 60)]
    missing, _questions = validate_completeness(intent)
    assert not any(field.endswith("lookback_days") for field in missing)


def test_mirrored_fundamental_period_is_not_a_ranking_lookback():
    """재무 지표의 period(연 단위 평균 등)는 거래일 산정 기간이 아니다 — 옮기지 않는다."""
    intent = _intent(
        [{"factor": "fundamental.roe_or_gpa", "operator": ">=", "value": None,
          "parameters": {"period": 3}, "source_text": "3년 평균 ROE가 높은"}],
        [{"metric": "fundamental.roe_or_gpa", "direction": "top"}],
    )
    validate_capability(intent)
    assert intent.strategy.entry_conditions == []
    assert [r.lookback_days for r in intent.strategy.ranking] == [None]
