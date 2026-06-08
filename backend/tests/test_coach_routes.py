import os
import sys
import types
import logging

import pytest
from fastapi import Response

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from api import coach_routes
from api.coach_routes import CoachRequest
from advisor.schemas import NewsArticleSignal, NewsContext


class _DummyLock:
    def priority(self, _priority):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _DummyParser:
    def __init__(self):
        self.chat_calls = 0
        self.last_user_message = ""
        self.user_messages = []

    def chat(self, _system_prompt, _user_message, max_tokens=512, temperature=0.0, top_p=1.0):
        self.chat_calls += 1
        self.last_user_message = _user_message
        self.user_messages.append(_user_message)
        assert max_tokens == 400
        # 코치는 표현 다양화를 위해 샘플링 온도를 준다.
        assert temperature > 0
        return '{"message":"캐시된 코치 응답"}'


class _FailingParser:
    def chat(self, *_args, **_kwargs):
        raise RuntimeError("mlx chat failed for test")


class _DummyAdvisorResponse:
    def model_dump(self, mode="json"):
        return {
            "strategy_score": 62,
            "risk_score": 71,
            "overfit_risk": "medium",
            "response_sections": [
                {"title": "핵심 진단", "body": "손절 기준이 없어 손실 관리가 약합니다."}
            ],
            "advice": [
                {
                    "severity": "high",
                    "title": "손절 기준 보강",
                    "body": "먼저 손실을 어디서 멈출지 정해야 합니다.",
                }
            ],
            "suggested_experiments": ["손절 8% 후보를 비교"],
            "ai_model_recommendation": {"recommended": False, "reason": "규칙 검증이 먼저 필요"},
        }


class _DummyAdvisor:
    calls = 0

    def review(self, req):
        self.__class__.calls += 1
        assert req.user_prompt
        assert req.parsed_strategy
        return _DummyAdvisorResponse()


def _install_dummy_main(monkeypatch):
    records = []

    def _record_ai_runtime(stage, runtime):
        records.append({"stage": stage, "runtime": runtime})

    def get_ai_runtime_metrics():
        coach_records = [record for record in records if record["stage"] == "coach"]
        return {
            "stages": {
                "coach": {
                    "count": len(coach_records),
                    "cache_hits": sum(1 for record in coach_records if record["runtime"].get("cache_hit") is True),
                }
            }
        }

    dummy_main = types.SimpleNamespace(
        _mlx_inference_lock=_DummyLock(),
        _record_ai_runtime=_record_ai_runtime,
        get_ai_runtime_metrics=get_ai_runtime_metrics,
    )
    monkeypatch.setitem(sys.modules, "main", dummy_main)


def _install_dummy_main_with_parser(monkeypatch, parser):
    records = []

    def _record_ai_runtime(stage, runtime):
        records.append({"stage": stage, "runtime": runtime})

    dummy_main = types.SimpleNamespace(
        _mlx_inference_lock=_DummyLock(),
        _record_ai_runtime=_record_ai_runtime,
        _nl_parsers={"mlx": parser},
    )
    monkeypatch.setitem(sys.modules, "main", dummy_main)


def _make_request(**overrides):
    payload = {
        "user_prompt": "PBR 1 이하 전략",
        "parsed_strategy": {
            "description": "large prompt metadata should not be repeated",
            "universe": ["KOSPI200"],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "entry_signals": [],
            "exit_signals": [],
            "max_positions": 10,
            "hold_period_days": 252,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "initial_capital": 10_000_000,
            "canonical_strategy_dsl": {"irrelevant": True},
            "symbols": ["005930", "000660"],
        },
        "advisor_insight": {
            "strategy_score": 70,
            "risk_score": 55,
            "overfit_risk": "low",
            "issues": [
                {"severity": "high", "message": "첫 이슈"},
                {"severity": "medium", "message": "둘째 이슈"},
                {"severity": "low", "message": "잘려야 하는 이슈"},
            ],
            "recommendations": [
                {"priority": 1, "title": "첫 제안", "reason": "핵심"},
                {"priority": 2, "title": "둘째 제안", "reason": "잘림"},
            ],
        },
    }
    payload.update(overrides)
    return CoachRequest(**payload)


def setup_function():
    coach_routes._reset_coach_cache_for_tests()
    coach_routes.set_parser(None)
    _DummyAdvisor.calls = 0
    if "main" in sys.modules and hasattr(sys.modules["main"], "_reset_ai_runtime_metrics_for_tests"):
        sys.modules["main"]._reset_ai_runtime_metrics_for_tests()


def test_build_user_message_compacts_strategy_context():
    msg = coach_routes._build_user_message(_make_request())

    assert "canonical_strategy_dsl" not in msg
    assert "symbols" not in msg
    assert "large prompt metadata" not in msg
    assert "잘려야 하는 이슈" not in msg
    assert "둘째 제안" not in msg
    assert "[코칭 행동 제약]" in msg
    assert "과거 데이터 검색" in msg
    assert "비교 테스트를 진행해 보시겠어요?" in msg
    assert "추상적으로 묻지 말고" in msg
    assert "익절 비율 설정을 추천드립니다" in msg
    assert "트레일링 스탑은 모든 전략의 기본 개선안이 아니므로" in msg
    assert '"fundamental_filters":[{"metric":"pbr","operator":"<=","value":1}]' in msg


def test_build_user_message_does_not_mark_take_profit_missing_when_exit_signal_exists():
    req = _make_request(
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "max_positions": 10,
            "hold_period_days": 252,
            "stop_loss_pct": 10,
            "take_profit_pct": None,
            "initial_capital": 10_000_000,
        },
    )

    msg = coach_routes._build_user_message(req)

    assert '"exit_signals":[{"indicator":"rsi","operator":">=","threshold":70}]' in msg
    assert "미정의 항목: 익절 비율" not in msg
    assert "청산 기준이 존재합니다" in msg
    assert "언제 팔아야 할지 기준이 없다" in msg
    assert "명확한 매도 신호가 이미 있습니다" in msg
    assert "트레일링 스탑을 최종 다음 행동으로 고르지 마십시오" in msg


def test_build_user_message_includes_memory_context_when_supplied():
    req = _make_request(
        user_prompt="PBR 1 이하 RSI 30 이하",
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
        memory_strategy_cases=[
            {
                "strategy_id": "case_rsi_pbr",
                "user_prompt": "과매도 PBR 저평가 전략",
                "strategy_summary": "PBR + RSI 평균회귀",
                "strategy_dsl": {
                    "universe": ["KOSPI200"],
                    "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 31}],
                    "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 69}],
                    "fundamental_filters": [{"metric": "pbr", "operator": "<=", "value": 1}],
                    "max_positions": 10,
                    "initial_capital": 10_000_000,
                },
            }
        ],
        memory_experiences=[
            {
                "strategy_id": "case_rsi_pbr",
                "before_backtest": {"cagr": 0.04, "mdd": -0.22, "sharpe": 0.4},
                "after_backtest": {"cagr": 0.07, "mdd": -0.16, "sharpe": 0.7},
                "evaluation": {"advice_success": True},
                "lesson": "PBR + RSI 전략은 추세 필터와 비용 민감도 검증이 필요하다.",
            }
        ],
    )

    msg = coach_routes._build_user_message(req)

    assert "[strategy_memory_context" in msg
    assert "confidence:" in msg
    assert "similar_strategy_ids: case_rsi_pbr" in msg
    assert "score=" in msg
    assert "case=case_rsi_pbr" in msg
    assert 'before={"cagr":0.04,"mdd":-0.22,"sharpe":0.4}' in msg
    assert 'after={"cagr":0.07,"mdd":-0.16,"sharpe":0.7}' in msg
    assert "비용 민감도 검증" in msg


def test_build_user_message_directs_concrete_example_for_indicator_setup_question():
    req = _make_request(
        user_prompt="rsi 몇으로 설정 할까?",
        parsed_strategy={
            "universe": ["KOSDAQ"],
            "entry_signals": [],
            "exit_signals": [],
            "stop_loss_pct": 9,
            "max_positions": 6,
            "initial_capital": 10_000_000,
        },
    )

    msg = coach_routes._build_user_message(req)

    assert "[지표 조건 설정 — 구체적 예시 필수]" in msg
    assert "구체적인 예시를 1~2개 제시" in msg
    assert "조건을 먼저 확정해 주세요" in msg  # 떠넘기지 말라는 부정 지침으로 포함
    assert "RSI가 30 이하로 떨어졌을 때 매수" in msg


def test_asks_indicator_setup_detection():
    assert coach_routes._asks_indicator_setup("rsi 몇으로 설정 할까?") is True
    assert coach_routes._asks_indicator_setup("골든크로스는 어떻게 잡아요?") is True
    assert coach_routes._asks_indicator_setup("macd 추천해줘") is True
    # 손절 비율은 리스크 조건이라 구체적 예시 강제 대상이 아니다.
    assert coach_routes._asks_indicator_setup("손절 몇 %로 할까?") is False
    # 이미 구체적으로 진술한 경우(질문 의도 없음)는 발동하지 않는다.
    assert coach_routes._asks_indicator_setup("RSI 30 이하에서 매수") is False


def test_parse_llm_response_extracts_message_from_incomplete_json():
    response = coach_routes._parse_llm_response(
        '{"message": "청산 신호가 있으므로 그 기준을 먼저 백테스트로 확인하세요."'
    )

    assert response.message == "청산 신호가 있으므로 그 기준을 먼저 백테스트로 확인하세요."


def test_parse_llm_response_extracts_nested_message_json():
    response = coach_routes._parse_llm_response(
        '{"message": "{\\"message\\": \\"안쪽 문장만 보여주세요.\\"}"}'
    )

    assert response.message == "안쪽 문장만 보여주세요."


def test_parse_llm_response_explains_trailing_stop_term_when_missing():
    response = coach_routes._parse_llm_response(
        '{"message": "수익을 자동 확정해 주는 트레일링 스탑을 추가해 보시겠어요?"}'
    )

    assert "트레일링 스탑(" in response.message
    assert "최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건" in response.message
    assert "추가해 보시겠어요?" in response.message
    assert "예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주시면 바로 추가하겠습니다." in response.message


def test_parse_llm_response_explains_take_profit_term_when_missing():
    response = coach_routes._parse_llm_response(
        '{"message": "현재 전략은 손절 기준만 있어 주가가 크게 오르면 언제 팔아야 할지 기준이 없습니다. 수익을 자동 확정해 주는 익절 비율을 추가해 보시겠어요?"}'
    )

    assert "익절 비율(" in response.message
    assert "매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건" in response.message
    assert "트레일링 스탑" not in response.message


def test_parse_llm_response_does_not_repeat_known_take_profit_explanation():
    response = coach_routes._parse_llm_response(
        '{"message": "익절 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건)을 30%로 설정할까요?"}',
        explained_terms={"take_profit"},
    )

    assert response.message == "익절 비율 30% 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."


def test_parse_llm_response_converts_tentative_take_profit_question_to_recommendation():
    # '익절 비율 … 설정하는 것이 좋을까요?' 같은 망설이는 질문은 확실한 조언형으로 바꾼다.
    response = coach_routes._parse_llm_response(
        '{"message": "수익을 확정하기 위한 \'익절 비율\'(목표 수익)을 함께 설정하는 것이 좋을까요? '
        '아니면 지금 손절 -12% 조건만 유지하고 바로 백테스트를 진행하시겠습니까?"}',
        explained_terms={"take_profit"},
    )

    assert "설정하는 것이 좋습니다." in response.message
    assert "설정하는 것이 좋을까요?" not in response.message


def test_prefer_take_profit_recommendation_wording_handles_geunda_question_form():
    assert (
        coach_routes._prefer_take_profit_recommendation_wording(
            "'익절 비율'(목표 수익)을 함께 설정하는 것이 좋을까요?"
        )
        == "'익절 비율'(목표 수익)을 함께 설정하는 것이 좋습니다."
    )


def test_fix_awkward_affirmation_opening_replaces_bare_good():
    assert coach_routes._parse_llm_response(
        '{"message": "좋습니다. 손절 조건이 있어 손실 방어에 도움이 됩니다."}'
    ).message.startswith("좋아 보이는 전략입니다.")


def test_remove_meaningless_filler_drops_unknown_phrase():
    out = coach_routes._remove_meaningless_filler(
        "손절 조건이 있습니다. 모르는 부분은 없으니 그대로 사용하셔도 됩니다. 익절을 추가해 보세요."
    )
    assert "모르는 부분" not in out
    assert "손절 조건이 있습니다." in out
    assert "익절을 추가해 보세요." in out


def test_simplify_set_condition_restatement_shortens_definition_echo():
    out = coach_routes._simplify_set_condition_restatement(
        "손절 10%는 매수가 대비 10% 하락 시 자동으로 파는 조건으로 설정해 계신군요. 손실 제한에 도움이 됩니다."
    )
    assert out.startswith("손절 10%로 설정하셨군요.")
    assert "매수가 대비" not in out
    assert "손실 제한에 도움이 됩니다." in out


def test_simplify_set_condition_restatement_keeps_already_simple_confirmation():
    # 이미 간결한 확인 문장은 건드리지 않는다.
    text = "손절 10%로 설정하셨군요. 좋은 안전장치입니다."
    assert coach_routes._simplify_set_condition_restatement(text) == text


def test_set_condition_dedup_collapses_parenthetical_and_followup_definition():
    # 괄호 풀이 + '이는 …조건입니다' 후속 문장으로 같은 정의를 두 번 말하는 중복을 제거.
    ex = (
        "손절 비율(매수가 대비 정한 비율만큼 손실이 나면 자동으로 파는 손실 제한 조건) 10%로 설정하셨군요. "
        "이는 매수가 대비 10% 하락 시 자동으로 매도하는 손실 제한 조건입니다."
    )
    out = coach_routes._apply_coach_postprocessing(ex, set())
    assert out == "손절 10%로 설정하셨군요."


def test_simplify_set_condition_does_not_eat_multi_clause_sentence():
    text = "손절 10%로 설정하셨고, 익절은 20%로 설정하셨습니다."
    assert coach_routes._simplify_set_condition_restatement(text) == text


def test_remove_redundant_definition_keeps_evaluative_sentence():
    text = "손절 10%로 설정하셨군요. 이는 위험을 줄이는 좋은 조건입니다."
    assert coach_routes._remove_redundant_definition_followup(text) == text


def test_removes_monte_carlo_suggestion_but_keeps_backtest_offer():
    ex = (
        "익절 30%로 설정하셨군요. 안정적 종목 위주로 천천히 투자하시는 방향과 잘 맞습니다. "
        "현재 조건으로 바로 백테스트를 진행해 보시겠어요? "
        "아니면 AI 예측 신호 추가나 몬테카를로 시뮬레이션 같은 다른 조건을 더 추가해 비교해 볼까요?"
    )
    out = coach_routes._apply_coach_postprocessing(ex, set())
    assert "몬테카를로" not in out
    assert "백테스트를 진행해 보시겠어요?" in out


def test_removes_solo_monte_carlo_suggestion_and_falls_back_to_backtest():
    out = coach_routes._remove_unsupported_technique_suggestion(
        "좋은 전략입니다. 몬테카를로 시뮬레이션을 돌려서 검증해 보시겠어요?"
    )
    assert "몬테카를로" not in out
    assert "바로 백테스트를 진행하셔도 됩니다" in out


def test_unsupported_technique_remover_is_noop_without_technique():
    text = "손절 8% 설정을 추천드립니다."
    assert coach_routes._remove_unsupported_technique_suggestion(text) == text


def test_system_prompt_forbids_unsupported_techniques():
    assert "몬테카를로" in coach_routes.COACH_SYSTEM_PROMPT
    assert "앱에서" not in coach_routes.COACH_SYSTEM_PROMPT


def test_remove_meta_suggestion_sentence_drops_instruction_echo():
    out = coach_routes._remove_meta_suggestion_sentence(
        "익절 비율 설정을 추천드립니다. 익절 비율을 추가하고 싶으시다면 "
        "'익절 비율 설정을 추천드립니다'와 같이 제안할 수 있습니다. "
        "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    )
    assert "와 같이 제안할 수 있습니다" not in out
    assert "익절 비율 설정을 추천드립니다." in out
    assert "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다." in out


def test_remove_meta_suggestion_sentence_keeps_normal_suggestion():
    # '와 같이/처럼/라고 제안' 메타 표현이 없는 정상 제안 문장은 유지한다.
    text = "익절 비율 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    assert coach_routes._remove_meta_suggestion_sentence(text) == text


def test_parse_llm_response_flattens_nested_term_explanation_parentheses():
    # '수익 실현 비율(익절 비율(설명))' 이중 괄호 → '수익 실현 비율(설명)' 한 겹으로 평탄화.
    response = coach_routes._parse_llm_response(
        '{"message": "수익 실현 비율(익절 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건))을 '
        '설정하는 것이 좋습니다."}',
    )

    assert "((" not in response.message
    assert "익절 비율(매수가" not in response.message
    assert "수익 실현 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건)" in response.message


def test_prefer_take_profit_recommendation_handles_synonym_and_setting_verb():
    # '수익 실현 비율 … 몇 %로 세팅할까요?' → 확신형 추천. 막연한 '몇 %'는 제거.
    out = coach_routes._prefer_take_profit_recommendation_wording(
        "수익 실현 비율을 몇 %로 세팅할까요?"
    )
    assert out == "수익 실현 비율 설정을 추천드립니다."


def test_remove_redundant_keep_condition_question_drops_awkward_alternative():
    out = coach_routes._remove_redundant_keep_condition_question(
        "익절 비율 설정을 추천드립니다. 아니면 지금 손절 조건만 사용하세요? "
        "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    )
    assert "손절 조건만 사용하세요?" not in out
    assert "익절 비율 설정을 추천드립니다." in out
    assert "지금 조건으로 바로 백테스트를 진행하셔도 됩니다." in out


def test_parse_llm_response_does_not_repeat_known_trailing_stop_explanation():
    response = coach_routes._parse_llm_response(
        "{\"message\": \"트레일링 스탑(주가가 오른 뒤 최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건)을 추가해 보시겠어요? 예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주시면 바로 추가하겠습니다.\"}",
        explained_terms={"trailing_stop"},
    )

    assert response.message == "트레일링 스탑을 추가해 보시겠어요? 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."


def test_parse_llm_response_explains_stop_loss_term_when_missing():
    """'손절 비율'도 최초 1회는 뜻을 풀이한다 (glossary 일반화)."""
    response = coach_routes._parse_llm_response(
        '{"message": "현재 전략에 손절 비율을 추가하면 어떨까요?"}'
    )

    assert "손절 비율(" in response.message
    assert "손실" in response.message


def test_parse_llm_response_does_not_force_inject_non_action_jargon():
    """지표/성과 용어(RSI·최대 낙폭 등)는 강제 주입하지 않는다 — 응답 길이 보호.

    최초 풀이는 LLM이 직접 하고, 코드는 반복만 막는다. (force_explain=False)
    """
    response = coach_routes._parse_llm_response(
        '{"message": "이 전략은 RSI가 높고 최대 낙폭 관리가 필요합니다."}'
    )

    assert "RSI(" not in response.message
    assert "최대 낙폭(" not in response.message


def test_parse_llm_response_strips_repeated_non_action_jargon_explanation():
    """이미 설명한 지표 용어(RSI)는 이어지는 대화에서 풀이를 떼고 용어만 남긴다."""
    response = coach_routes._parse_llm_response(
        '{"message": "RSI(상대강도지수, 과열 여부를 보는 지표)가 70을 넘었습니다."}',
        explained_terms={"rsi"},
    )

    assert "RSI(" not in response.message
    assert "RSI" in response.message


def test_parse_llm_response_does_not_repeat_known_stop_loss_explanation():
    """이미 설명한 '손절 비율'은 이어지는 대화에서 풀이 없이 용어만 남긴다."""
    response = coach_routes._parse_llm_response(
        '{"message": "손절 비율(매수가 대비 정한 비율만큼 손실이 나면 자동으로 파는 손실 제한 조건)을 8%로 설정할까요?"}',
        explained_terms={"stop_loss"},
    )

    assert "손절 비율(" not in response.message
    assert "손절 비율" in response.message


def test_coach_glossary_is_collision_safe():
    """용어 추가 시 깨지면 안 되는 불변식 — 라벨 충돌/중첩 주입/자기 감지 보장."""
    import re

    glossary = coach_routes._COACH_GLOSSARY
    for a in glossary:
        for b in glossary:
            if a.key == b.key:
                continue
            # 라벨이 다른 라벨의 부분문자열이면 replace가 잘못된 곳을 건드린다.
            assert a.label not in b.label, f"label collision: {a.label} ⊂ {b.label}"
            # 풀이에 다른 라벨이 들어 있으면 주입이 풀이 안쪽에 중첩될 수 있다.
            assert b.label not in a.explanation, f"{b.label} appears in {a.key} explanation"
    for term in glossary:
        # keywords는 자기 풀이에서 검출되어야 한다(감지/중복 방지가 동작).
        assert re.search(term.keywords, term.explanation), f"keywords miss own explanation: {term.key}"
        if term.force_explain and not term.special_injection:
            injected = f"{term.label}({term.explanation})"
            assert re.search(term.inline_pattern, injected), f"not self-detectable: {term.key}"


def test_explained_terms_from_context_detects_broad_jargon():
    """청산 용어뿐 아니라 지표/재무 용어도 이전 대화에서 설명되면 감지한다."""
    context = [
        {"role": "assistant", "content": "PER(주가수익비율, 주가가 한 해 순이익의 몇 배인지)이 낮습니다."},
        {"role": "assistant", "content": "골든크로스는 단기 이동평균선이 장기 이동평균선을 아래에서 위로 뚫는 신호입니다."},
    ]

    explained = coach_routes._explained_terms_from_context(context)

    assert "per" in explained
    assert "golden_cross" in explained


def test_explained_terms_from_context_detects_all_glossary_terms():
    context = [
        {"role": "assistant", "content": "샤프 지수(감수한 변동성 대비 얼마나 효율적으로 수익을 냈는지 보여주는 지표)가 낮습니다."},
        {"role": "assistant", "content": "손절 비율은 매수가 대비 손실이 나면 파는 조건입니다."},
    ]

    explained = coach_routes._explained_terms_from_context(context)

    assert "sharpe" in explained
    assert "stop_loss" in explained


def test_parse_llm_response_adds_backtest_option_when_suggesting_extra_condition():
    response = coach_routes._parse_llm_response(
        '{"message": "현재 전략은 이동평균선 교차로 매도하는 방식입니다. 이 조건을 유지하면서, 보유 기간을 설정해 볼까요?"}',
    )

    assert "보유 기간을 설정해 볼까요?" in response.message
    assert "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다." in response.message


def test_parse_llm_response_does_not_duplicate_existing_backtest_option():
    response = coach_routes._parse_llm_response(
        '{"message": "익절 비율을 설정할까요? 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."}',
    )

    assert response.message.startswith("익절 비율(")
    assert "설정할까요?" not in response.message
    assert "설정을 추천드립니다." in response.message
    assert response.message.count("바로 백테스트") == 1


def test_parse_llm_response_does_not_duplicate_run_as_is_offer_phrased_differently():
    # '기존 조건으로 바로 실험해 볼까요?'는 '바로 백테스트' 안내와 같은 뜻이므로 중복 추가하지 않는다.
    response = coach_routes._parse_llm_response(
        '{"message": "수익 실현 기준이 없습니다. 기존 조건으로 바로 실험해 볼까요? '
        '아니면 익절 비율을 몇 %로 설정하고 비교해 볼까요?"}',
    )

    assert "기존 조건으로 바로 실험해 볼까요?" in response.message
    assert "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다." not in response.message


def test_parse_llm_response_removes_past_backtest_comparison_clause():
    # '과거 백테스트 결과를 바탕으로 비교'는 사용자가 과거 데이터를 갖고 있다고 가정하므로 제거한다.
    response = coach_routes._parse_llm_response(
        '{"message": "익절 비율(정해진 수익률에 도달하면 팔기)을 추가하거나, '
        '과거 백테스트 결과를 바탕으로 비교해 보는 것이 좋겠습니다. '
        '익절 비율을 추가하시거나 지금 조건으로 바로 진행하시겠습니까?"}',
    )

    assert "과거 백테스트 결과를 바탕으로 비교" not in response.message
    assert "과거 데이터" not in response.message
    assert "익절 비율" in response.message
    assert "추가하는 것이 좋겠습니다" in response.message


def test_strip_past_backtest_comparison_keeps_in_app_backtest_offer():
    # 과거 언급 없는 '바로 백테스트 진행' 안내는 그대로 유지한다.
    kept = "지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    assert coach_routes._strip_past_backtest_comparison(kept) == kept
    # 독립 문장으로 과거 데이터 비교만 권하면 통째로 제거한다.
    stripped = coach_routes._strip_past_backtest_comparison(
        "익절 비율을 추가하세요. 과거 데이터를 참고해 비교해 보세요."
    )
    assert stripped == "익절 비율을 추가하세요."


def test_parse_llm_response_fixes_contradictory_deliberation_then_backtest():
    # '고민해보고 싶으시다면, 지금 조건으로 바로 백테스트' 는 모순 → 두 개의 별개 선택지로 분리한다.
    response = coach_routes._parse_llm_response(
        '{"message": "익절 비율을 몇 %로 설정할지 고민해보고 싶으시다면, '
        '지금 조건으로 바로 백테스트를 진행하셔도 됩니다."}',
    )

    assert "고민해보고 싶으시다면, 지금 조건으로 바로 백테스트" not in response.message
    assert "고민해보셔도 됩니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다." in response.message


def test_fix_contradictory_backtest_option_keeps_clean_alternative():
    # 이미 '아니면'으로 분리된 정상 문장은 건드리지 않는다.
    clean = "익절 비율 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    assert coach_routes._fix_contradictory_backtest_option(clean) == clean


def test_already_offers_run_as_is_detects_paraphrased_offers():
    assert coach_routes._already_offers_run_as_is("기존 조건으로 바로 실험해 볼까요?")
    assert coach_routes._already_offers_run_as_is("지금 조건 그대로 바로 돌려보시겠어요?")
    assert coach_routes._already_offers_run_as_is("지금 조건으로 바로 백테스트를 진행하셔도 됩니다.")
    # 단순히 익절 비율만 제안하는 문장은 as-is 제안이 아니다 → 안내를 덧붙여야 한다.
    assert not coach_routes._already_offers_run_as_is("익절 비율 30% 설정을 추천드립니다.")


def test_parse_llm_response_does_not_duplicate_trailing_stop_explanation():
    response = coach_routes._parse_llm_response(
        '{"message": "트레일링 스탑은 최고가에서 일정 비율 하락하면 파는 조건입니다. 추가해 보시겠어요?"}'
    )

    assert "(" not in response.message
    assert response.message.count("최고가에서 일정 비율 하락하면 파는 조건") == 1
    assert "예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주시면 바로 추가하겠습니다." in response.message


def test_parse_llm_response_does_not_duplicate_trailing_stop_example():
    response = coach_routes._parse_llm_response(
        '{"message": "트레일링 스탑은 최고가에서 일정 비율 하락하면 파는 조건입니다. 예를 들면 트레일링 스탑 15% 설정이라고 말해 주세요."}'
    )

    assert response.message.count("예를 들면") == 1


def test_align_response_does_not_suggest_adding_existing_trailing_stop():
    response = coach_routes._parse_llm_response(
        '{"message": "트레일링 스탑 15% 조건을 추가해 보시겠어요? 예를 들면 트레일링 스탑 15% 설정이라고 말씀해주시면 바로 추가하겠습니다."}'
    )

    aligned = coach_routes._align_response_with_strategy(
        response,
        {"trailing_stop_pct": 15},
    )

    assert "전략에 반영했습니다" in aligned.message
    assert "15% 조건" in aligned.message
    assert "주가가 오른 뒤" not in aligned.message
    assert "자동으로 파는 조건" not in aligned.message
    assert "추가해 보시겠어요" not in aligned.message
    assert "바로 추가하겠습니다" not in aligned.message
    assert "예를 들면" not in aligned.message


def test_align_response_acknowledges_take_profit_when_already_set():
    """익절 비율이 이미 설정됐는데 또 추천하면, 반영 완료 안내로 바꾼다."""
    aligned = coach_routes._align_response_with_strategy(
        coach_routes.CoachResponse(message="익절 비율 30% 설정을 추천드립니다. 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."),
        {"take_profit_pct": 30.0},
    )

    assert "전략에 반영했습니다" in aligned.message
    assert "익절 비율 30%" in aligned.message  # 30.0%가 아니라 30%
    assert "추천드립니다" not in aligned.message


def test_align_response_acknowledges_hold_period_when_already_set():
    """보유 기간이 이미 설정됐는데 또 설정을 권하면, 반영 완료 안내로 바꾼다(스크린샷 버그)."""
    aligned = coach_routes._align_response_with_strategy(
        coach_routes.CoachResponse(
            message="보유 기간을 설정하면 변동성 관리에 도움이 됩니다. 보유 기간을 설정할까요? "
            "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
        ),
        {"hold_period_days": 30},
    )

    assert "보유 기간 30일 조건을 전략에 반영했습니다" in aligned.message
    assert "설정할까요" not in aligned.message


def test_align_response_keeps_hold_period_advice_when_not_set():
    message = "보유 기간을 설정할까요?"
    aligned = coach_routes._align_response_with_strategy(
        coach_routes.CoachResponse(message=message), {"hold_period_days": None}
    )
    assert aligned.message == message


def test_already_set_topics_flags_only_fields_with_values():
    assert coach_routes._already_set_topics(["보유 기간", "익절 비율"], {"hold_period_days": 30}) == ["보유 기간"]
    assert coach_routes._already_set_topics(["보유 기간"], {"hold_period_days": None}) == []
    assert coach_routes._already_set_topics(["종목 수"], {"max_positions": 8}) == []  # 종목 수는 대상 아님


def test_align_response_acknowledges_take_profit_from_risk_dict():
    aligned = coach_routes._align_response_with_strategy(
        coach_routes.CoachResponse(message="익절 비율 30% 설정을 추천드립니다."),
        {"risk": {"take_profit_pct": 30.0}},
    )

    assert "전략에 반영했습니다" in aligned.message


def test_align_response_keeps_take_profit_recommendation_when_not_set():
    """아직 설정되지 않았으면 추천을 그대로 둔다."""
    message = "익절 비율 설정을 추천드립니다."
    aligned = coach_routes._align_response_with_strategy(
        coach_routes.CoachResponse(message=message),
        {"take_profit_pct": None},
    )

    assert aligned.message == message


def test_align_response_detects_nested_risk_trailing_stop():
    response = coach_routes.CoachResponse(
        message="트레일링 스탑 15% 조건을 추가해 보시겠어요?"
    )

    aligned = coach_routes._align_response_with_strategy(
        response,
        {"risk": {"trailing_stop_pct": 15}},
    )

    assert "전략에 반영했습니다" in aligned.message


def test_align_response_does_not_prioritize_trailing_stop_when_exit_signal_exists():
    response = coach_routes.CoachResponse(
        message=(
            "현재 전략은 이동평균선 교차로 매수/매도하는 방식인데, "
            "트레일링 스탑을 추가해 보시겠어요?"
        )
    )

    aligned = coach_routes._align_response_with_advisor_priority(
        response,
        {
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "stop_loss_pct": 8,
            "take_profit_pct": None,
            "trailing_stop_pct": None,
        },
        {
            "advice": [
                {
                    "title": "전략 실험 근거 기반 개선",
                    "body": "이동평균 기간과 손절 폭을 각각 바꿔 테스트해 보세요.",
                }
            ],
            "suggested_experiments": ["트레일링 스탑 15% 추가 후 MDD/Sharpe 변화 비교"],
        },
    )

    assert "트레일링 스탑" not in aligned.message
    assert "이동평균 기간과 손절 폭" in aligned.message


def test_align_response_allows_trailing_stop_when_primary_advice_recommends_it():
    response = coach_routes.CoachResponse(message="트레일링 스탑을 추가해 보시겠어요?")

    aligned = coach_routes._align_response_with_advisor_priority(
        response,
        {"exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}]},
        {
            "advice": [
                {
                    "title": "트레일링 스탑 추가",
                    "body": "이벤트 변동성이 커서 트레일링 스탑을 비교하세요.",
                }
            ],
        },
    )

    assert aligned.message == response.message


def test_build_user_message_includes_advisor_result_and_conversation_context():
    req = _make_request(
        advisor_insight=None,
        advisor_result=_DummyAdvisorResponse().model_dump(),
        conversation_context=[
            {"role": "user", "content": "쉽게 설명해줘"},
            {"role": "assistant", "content": "손실 관리부터 봐야 합니다."},
        ],
    )

    msg = coach_routes._build_user_message(req)

    assert "[advisor_result" in msg
    assert "손절 기준이 없어 손실 관리가 약합니다." in msg
    assert "[conversation_context" in msg
    assert "쉽게 설명해줘" in msg


def test_detect_question_topics_identifies_holding_period_question():
    # 사용자가 보유 기간만 물으면 익절 등 다른 주제는 감지되지 않아야 한다.
    assert coach_routes._detect_question_topics("보유 기간을 얼마로 설정할까?") == ["보유 기간"]
    assert coach_routes._detect_question_topics("익절은 몇 %가 좋을까?") == ["익절 비율"]
    assert coach_routes._detect_question_topics("그냥 안녕") == []


def test_build_user_message_anchors_to_current_question_topic():
    # '보유 기간'을 물었으면 그 주제로 직접 답하라는 최우선 지시가 들어가야 한다 (동문서답 방지).
    req = _make_request(
        user_prompt="보유 기간을 얼마로 설정할까?",
        advisor_result=_DummyAdvisorResponse().model_dump(),
        conversation_context=[
            {"role": "assistant", "content": "익절 비율을 추가해 보시겠어요?"},
        ],
    )

    msg = coach_routes._build_user_message(req)

    assert "[현재 질문 우선 — 최우선 반영]" in msg
    assert "'보유 기간'을(를) 다루고 있습니다" in msg
    assert "주제를 바꾸지 마십시오" in msg


def test_build_user_message_filters_legacy_experiment_learning_copy():
    legacy_body = (
        "백테스트 학습 사례 2496건 기준으로 제안 주신 전략과 비슷한 전략의 결과가 "
        "CAGR 중앙값 4.80%, Sharpe 중앙값 0.62, MDD 중앙값 -9.22%, "
        "Profit Factor 중앙값 1.24, 거래 수 중앙값 725회로 나왔습니다. "
        "이 전략에서 PBR 기준은 0.8배/1.0배, 최대 보유기간은 10일, "
        "보유 종목 수는 20개로 각각 바꿔 테스트해 보세요. "
        "테스트 후에는 MDD와 Sharpe가 동시에 좋아지는 설정만 남기세요."
    )
    req = _make_request(
        advisor_insight=None,
        advisor_result={
            "strategy_score": 70,
            "risk_score": 50,
            "overfit_risk": "medium",
            "advice": [{"severity": "medium", "title": "전략 실험 근거 기반 개선", "body": legacy_body}],
            "response_sections": [{"title": "학습 사례", "body": legacy_body}],
            "strategy_experiment_learning": {
                "similar_strategy_count": 2496,
                "confidence": "medium",
                "median_cagr": 4.8,
                "median_sharpe": 0.62,
                "median_mdd": -9.22,
            },
        },
    )

    msg = coach_routes._build_user_message(req)

    assert legacy_body not in msg
    assert "백테스트 학습 사례 2496건" not in msg
    assert "CAGR 중앙값" not in msg
    assert "PBR 기준은 0.8배/1.0배" not in msg
    assert '"strategy_experiment_learning"' in msg
    assert '"confidence":"medium"' in msg


def test_parse_llm_response_blocks_legacy_experiment_learning_copy():
    response = coach_routes._parse_llm_response(
        '{"message": "백테스트 학습 사례 2496건 기준으로 제안 주신 전략과 비슷한 전략의 결과가 CAGR 중앙값 4.80%, Sharpe 중앙값 0.62, MDD 중앙값 -9.22%, Profit Factor 중앙값 1.24, 거래 수 중앙값 725회로 나왔습니다. 이 전략에서 PBR 기준은 0.8배/1.0배, 최대 보유기간은 10일, 보유 종목 수는 20개로 각각 바꿔 테스트해 보세요. 테스트 후에는 MDD와 Sharpe가 동시에 좋아지는 설정만 남기세요."}'
    )

    assert "백테스트 학습 사례" not in response.message
    assert "중앙값" not in response.message
    assert "PBR 기준은 0.8배/1.0배" not in response.message
    assert "유사 사례 지표를 그대로 나열하는 조언은 생략" in response.message


def test_build_user_message_marks_already_explained_terms():
    req = _make_request(
        conversation_context=[
            {
                "role": "assistant",
                "content": "익절 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건)을 설정할까요?",
            },
            {
                "role": "assistant",
                "content": "트레일링 스탑(주가가 오른 뒤 최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건)을 추가할까요?",
            },
        ],
    )

    msg = coach_routes._build_user_message(req)

    assert "[전문용어 설명 반복 금지]" in msg
    assert "이미 설명한 용어: 익절 비율, 트레일링 스탑" in msg
    assert "다시 뜻을 풀이하지 말고" in msg


def test_build_user_message_requires_trailing_stop_percentage_before_suggesting_value():
    req = _make_request(
        user_prompt="트레일링 스탑을 추가해줘",
        advisor_insight=None,
        advisor_result={
            "advice": [
                {
                    "severity": "medium",
                    "title": "트레일링 스탑 추가",
                    "body": "트레일링 스탑 15% 후보를 비교하세요.",
                }
            ],
        },
    )

    msg = coach_routes._build_user_message(req)

    assert "[필수 확인 질문]" in msg
    assert "트레일링 스탑 수치를 말하지 않았습니다" in msg
    assert "15% 같은 후보가 있어도 임의 수치를 제안하지 말고" in msg
    assert "몇 %로 설정할지 먼저 물어보십시오" in msg


def test_build_user_message_allows_trailing_stop_when_percentage_is_present():
    req = _make_request(user_prompt="트레일링 스탑 15% 추가해줘")

    msg = coach_routes._build_user_message(req)

    assert "[필수 확인 질문]" not in msg


def test_build_user_message_does_not_require_exact_holding_days_for_advice():
    req = _make_request(
        user_prompt=(
            "KOSPI 종목 중 골든크로스가 나오면 매수하고, "
            "데드크로스가 나오면 매도해 주세요. 손절은 -8%입니다."
        ),
        parsed_strategy={
            "universe": ["KOSPI"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [{"indicator": "ma_crossover", "signal_type": "sell"}],
            "max_positions": 10,
            "stop_loss_pct": 8,
            "hold_period_days": None,
        },
    )

    msg = coach_routes._build_user_message(req)

    assert "보유 기간은 개선안으로만 제안하십시오" in msg
    assert "'몇 일로 설정할까요?'처럼 정확한 일수를 요구하지 말고" in msg
    assert "'보유 기간을 설정할까요?'처럼 추가 여부를 묻는 표현" in msg


def test_build_user_message_does_not_require_exact_take_profit_pct_for_advice():
    req = _make_request(
        user_prompt="KOSPI 대형주를 사고 손절은 -8%로 해주세요.",
        parsed_strategy={
            "universe": ["KOSPI"],
            "entry_signals": [{"indicator": "ma_crossover", "signal_type": "buy"}],
            "exit_signals": [],
            "max_positions": 10,
            "stop_loss_pct": 8,
            "take_profit_pct": None,
        },
    )

    msg = coach_routes._build_user_message(req)

    assert "익절 비율은 개선안으로만 제안하십시오" in msg
    assert "'몇 %로 설정할까요?'처럼 정확한 비율을 요구하지 말고" in msg
    assert "'익절 비율 설정을 추천드립니다'처럼 추천/조언 표현" in msg


def test_require_parser_logs_debug_state_when_model_is_unavailable(monkeypatch, caplog):
    _install_dummy_main_with_parser(monkeypatch, None)
    sys.modules["main"]._nl_parsers.clear()
    coach_routes.set_parser(None)

    with caplog.at_level(logging.ERROR, logger="api.coach_routes"):
        with pytest.raises(Exception) as exc_info:
            coach_routes._require_parser()

    assert getattr(exc_info.value, "status_code", None) == 503
    assert "coach parser unavailable" in caplog.text
    assert "main_parser_keys" in caplog.text
    assert "main_mlx_parser_loaded" in caplog.text


def test_generate_coach_response_logs_parser_chat_failure(monkeypatch, caplog):
    _install_dummy_main(monkeypatch)
    coach_routes.set_parser(_FailingParser())
    req = _make_request(advisor_result=_DummyAdvisorResponse().model_dump())

    with caplog.at_level(logging.ERROR, logger="api.coach_routes"):
        with pytest.raises(RuntimeError, match="mlx chat failed for test"):
            coach_routes._generate_coach_response(req, 0.0, request_id="testreq")

    assert "coach parser.chat failed" in caplog.text
    assert "request_id=testreq" in caplog.text
    assert "parser_state" in caplog.text


def test_system_prompt_requires_memory_evidence_discipline():
    prompt = coach_routes.COACH_SYSTEM_PROMPT

    assert "사용자를 주식 초보자라고 생각" in prompt
    assert "주식 전문 용어를 처음 쓸 때는" in prompt
    assert "괄호 안에 한 번만 짧게 뜻을 덧붙이십시오" in prompt
    assert "이미 설명한 전문 용어는 다시 설명하지 말고" in prompt
    assert "수치가 필요한 조건" in prompt
    assert "몇 %로 설정할지 먼저 물어보십시오" in prompt
    assert "strategy_memory_context" in prompt
    assert "data_sufficiency가 insufficient" in prompt
    assert "꾸며내지 마라" in prompt
    assert "백테스트 결과가 없으면" in prompt
    assert "제공되지 않은 백테스트 사례" in prompt
    assert "검색/계산/판정 엔진이 아니라" in prompt
    assert "백테스트 학습 사례 N건 기준" in prompt
    assert "CAGR 중앙값" in prompt
    assert "그대로 인용하거나 요약하지 마십시오" in prompt
    assert "표본 수/중앙값/여러 파라미터 후보를 나열" in prompt
    assert "과거 데이터 검색" in prompt
    assert "지금 바로 할 수 없는 행동" in prompt
    assert "비교 테스트를 진행해 보시겠어요?" in prompt
    assert "익절 비율 설정을 추천드립니다" in prompt
    assert "트레일링 스탑을 모든 전략의 기본 개선안처럼 제안하지 마십시오" in prompt
    assert "정확한 수치를 말한 경우에만" in prompt
    assert "익절 비율과 트레일링 스탑은 서로 다른 전문 용어" in prompt
    assert "익절 비율은 매수가 대비 정한 수익률에 도달하면 매도하는 고정 목표 수익 조건" in prompt
    assert "트레일링 스탑은 보유 중 최고가에서 정한 비율만큼 내려오면 매도" in prompt
    assert "트레일링 스탑을 뜻하면서 익절 비율이라고 부르지 말고" in prompt
    assert "보유 기간을 개선안으로 제안할 때" in prompt
    assert "보유 기간을 설정할까요?" in prompt
    assert "익절 비율을 개선안으로 제안할 때" in prompt
    assert "익절 비율 설정을 추천드립니다" in prompt
    assert "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다." in prompt
    assert "앱에서" not in prompt


@pytest.mark.asyncio
async def test_coach_strategy_reuses_backend_cache(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    req = _make_request()
    first = await coach_routes.coach_strategy(req)
    second = await coach_routes.coach_strategy(req)

    assert first.message == "캐시된 코치 응답"
    assert second.message == "캐시된 코치 응답"
    assert parser.chat_calls == 1

    metrics = sys.modules["main"].get_ai_runtime_metrics()
    assert metrics["stages"]["coach"]["count"] == 2
    assert metrics["stages"]["coach"]["cache_hits"] == 1


@pytest.mark.asyncio
async def test_coach_strategy_builds_advisor_result_once_when_missing(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)
    monkeypatch.setattr(coach_routes, "StrategyAdvisorAgent", _DummyAdvisor)
    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    req = _make_request(advisor_insight=None, advisor_result=None)
    first = await coach_routes.coach_strategy(req)
    second = await coach_routes.coach_strategy(req)

    assert first.model_dump() == {"message": "캐시된 코치 응답"}
    assert second.model_dump() == {"message": "캐시된 코치 응답"}
    assert _DummyAdvisor.calls == 1
    assert parser.chat_calls == 1
    assert "[advisor_result" in parser.last_user_message
    assert "손절 기준이 없어 손실 관리가 약합니다." in parser.last_user_message


@pytest.mark.asyncio
async def test_coach_session_stores_advisor_result_and_returns_only_message(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)
    monkeypatch.setattr(coach_routes, "StrategyAdvisorAgent", _DummyAdvisor)
    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    response = Response()
    result = await coach_routes.create_coach_session(
        coach_routes.CoachSessionRequest(
            user_prompt="RSI 전략",
            parsed_strategy={
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi"}],
                "max_positions": 10,
            },
        ),
        response,
    )

    session_id = response.headers["X-Coach-Session-Id"]
    assert result.model_dump() == {"message": "캐시된 코치 응답"}
    assert session_id in coach_routes._coach_sessions
    assert "advisor_result" in coach_routes._coach_sessions[session_id]
    assert _DummyAdvisor.calls == 1


@pytest.mark.asyncio
async def test_coach_session_uses_lazy_parser_from_main_when_not_preloaded(monkeypatch):
    parser = _DummyParser()
    _install_dummy_main_with_parser(monkeypatch, parser)
    coach_routes.set_parser(None)
    monkeypatch.setattr(coach_routes, "StrategyAdvisorAgent", _DummyAdvisor)
    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    response = Response()
    result = await coach_routes.create_coach_session(
        coach_routes.CoachSessionRequest(
            user_prompt="RSI 전략",
            parsed_strategy={
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi"}],
                "max_positions": 10,
            },
        ),
        response,
    )

    assert result.model_dump() == {"message": "캐시된 코치 응답"}
    assert parser.chat_calls == 1
    assert response.headers["X-Coach-Session-Id"]


@pytest.mark.asyncio
async def test_create_session_threads_prior_conversation_for_explained_terms(monkeypatch):
    """전략 수정으로 세션을 새로 만들 때, 직전 코치 대화를 받아 이미 설명한 용어를 다시 설명하지 않는다."""
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)
    monkeypatch.setattr(coach_routes, "StrategyAdvisorAgent", _DummyAdvisor)
    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    prior = [
        {"role": "user", "content": "익절 알려줘"},
        {
            "role": "assistant",
            "content": "익절 비율(매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건)을 추천드립니다.",
        },
    ]
    response = Response()
    await coach_routes.create_coach_session(
        coach_routes.CoachSessionRequest(
            user_prompt="익절 비율 30% 설정",
            parsed_strategy={"universe": ["KOSPI"], "max_positions": 8, "take_profit_pct": 30.0},
            conversation_context=prior,
        ),
        response,
    )

    # 직전 대화에서 익절 비율이 설명됐음을 인지해 '재설명 금지' 지시가 프롬프트에 들어가야 한다.
    assert "이미 설명한 용어" in parser.last_user_message
    assert "익절 비율" in parser.last_user_message
    # 새 세션에도 직전 대화가 보존되어 이후 follow-up에서도 재설명을 막는다.
    session_id = response.headers["X-Coach-Session-Id"]
    stored = coach_routes._coach_sessions[session_id]["conversation_context"]
    assert stored[0]["content"] == "익절 알려줘"
    assert any("익절 비율(" in item["content"] for item in stored)


@pytest.mark.asyncio
async def test_coach_session_requires_startup_loaded_parser(monkeypatch):
    _install_dummy_main_with_parser(monkeypatch, None)
    sys.modules["main"]._nl_parsers.clear()
    coach_routes.set_parser(None)

    response = Response()
    with pytest.raises(Exception) as exc_info:
        await coach_routes.create_coach_session(
            coach_routes.CoachSessionRequest(
                user_prompt="RSI 전략",
                parsed_strategy={
                    "universe": ["KOSPI200"],
                    "entry_signals": [{"indicator": "rsi"}],
                    "max_positions": 10,
                },
            ),
            response,
        )

    assert getattr(exc_info.value, "status_code", None) == 503
    assert "Coach model not loaded yet" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_coach_session_follow_up_reuses_stored_advisor_result(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)
    monkeypatch.setattr(coach_routes, "StrategyAdvisorAgent", _DummyAdvisor)
    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    response = Response()
    await coach_routes.create_coach_session(
        coach_routes.CoachSessionRequest(
            user_prompt="RSI 전략",
            parsed_strategy={
                "universe": ["KOSPI200"],
                "entry_signals": [{"indicator": "rsi"}],
                "max_positions": 10,
            },
        ),
        response,
    )
    session_id = response.headers["X-Coach-Session-Id"]

    follow_up = await coach_routes.continue_coach_session(
        coach_routes.CoachSessionFollowUpRequest(
            session_id=session_id,
            user_prompt="초보자도 이해하게 설명해줘",
        )
    )

    assert follow_up.model_dump() == {"message": "캐시된 코치 응답"}
    assert _DummyAdvisor.calls == 1
    assert parser.chat_calls == 2
    assert "[conversation_context" in parser.last_user_message
    assert "RSI 전략" in parser.last_user_message
    assert "손절 기준이 없어 손실 관리가 약합니다." in parser.last_user_message


@pytest.mark.asyncio
async def test_coach_strategy_auto_injects_news_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(
        coach_routes,
        "build_news_context_from_strategy",
        lambda _parsed: [
            NewsContext(
                symbol="005930",
                latest_alpha=-0.12,
                risk_alert_level="high",
                articles=[
                    NewsArticleSignal(
                        event_type="earnings_miss",
                        sentiment="negative",
                        impact_direction="down",
                        impact_score=-0.8,
                        confidence_score=0.9,
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())

    req = _make_request(advisor_insight=None, news_agent_insight=None)
    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[news_agent_insight" in parser.last_user_message
    assert "risk_alert=high" in parser.last_user_message
    assert "earnings_miss" in parser.last_user_message


@pytest.mark.asyncio
async def test_coach_strategy_auto_injects_memory_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])
    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", lambda *_args, **_kwargs: _empty_memory())
    monkeypatch.setattr(
        coach_routes,
        "load_advisor_memory",
        lambda: (
            [
                {
                    "strategy_id": "case_auto_memory",
                    "user_prompt": "RSI 평균회귀",
                    "strategy_summary": "RSI 평균회귀",
                    "strategy_dsl": {
                        "universe": ["KOSPI200"],
                        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                        "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
                        "max_positions": 10,
                        "initial_capital": 10_000_000,
                    },
                }
            ],
            [
                {
                    "strategy_id": "case_auto_memory",
                    "before_backtest": {"cagr": 0.03, "mdd": -0.25, "sharpe": 0.3},
                    "after_backtest": {"cagr": 0.06, "mdd": -0.18, "sharpe": 0.6},
                    "evaluation": {"advice_success": True},
                    "lesson": "RSI 평균회귀는 장기 추세 필터 검증이 필요하다.",
                }
            ],
        ),
    )

    req = _make_request(
        user_prompt="RSI 30 이하 매수, 70 이상 매도",
        advisor_insight=None,
        news_agent_insight=None,
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "exit_signals": [{"indicator": "rsi", "operator": ">=", "threshold": 70}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[strategy_memory_context" in parser.last_user_message
    assert "case=case_auto_memory" in parser.last_user_message
    assert "장기 추세 필터" in parser.last_user_message


async def _empty_memory():
    return [], []


@pytest.mark.asyncio
async def test_coach_strategy_prefers_vector_memory_context(monkeypatch):
    _install_dummy_main(monkeypatch)
    parser = _DummyParser()
    coach_routes.set_parser(parser)

    monkeypatch.setattr(coach_routes, "build_news_context_from_strategy", lambda _parsed: [])

    async def _vector_memory(_user_prompt, _parsed_strategy):
        return (
            [
                {
                    "strategy_id": "vector_case",
                    "user_prompt": "RSI vector memory",
                    "strategy_summary": "Vector RSI memory",
                    "strategy_dsl": {
                        "universe": ["KOSPI200"],
                        "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
                        "max_positions": 10,
                        "initial_capital": 10_000_000,
                    },
                }
            ],
            [
                {
                    "strategy_id": "vector_case",
                    "before_backtest": {"cagr": 0.02, "mdd": -0.30, "sharpe": 0.2},
                    "after_backtest": {"cagr": 0.05, "mdd": -0.18, "sharpe": 0.6},
                    "evaluation": {"advice_success": True},
                    "lesson": "Vector DB 검색 사례는 변동성 필터 검증이 필요하다.",
                    "retrieval_categories": ["similar", "successful_low_risk"],
                }
            ],
        )

    monkeypatch.setattr(coach_routes, "load_vector_advisor_memory", _vector_memory)
    monkeypatch.setattr(
        coach_routes,
        "load_advisor_memory",
        lambda: pytest.fail("load_advisor_memory should not run when vector memory is available"),
    )

    req = _make_request(
        user_prompt="RSI 30 이하 매수",
        advisor_insight=None,
        news_agent_insight=None,
        parsed_strategy={
            "universe": ["KOSPI200"],
            "entry_signals": [{"indicator": "rsi", "operator": "<=", "threshold": 30}],
            "max_positions": 10,
            "initial_capital": 10_000_000,
        },
    )

    response = await coach_routes.coach_strategy(req)

    assert response.message == "캐시된 코치 응답"
    assert "[strategy_memory_context" in parser.last_user_message
    assert "case=vector_case" in parser.last_user_message
    assert "변동성 필터 검증" in parser.last_user_message
