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

    def chat(self, _system_prompt, _user_message, max_tokens=512):
        self.chat_calls += 1
        self.last_user_message = _user_message
        self.user_messages.append(_user_message)
        assert max_tokens == 400
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
    assert "익절 비율을 설정할까요?" in msg
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

    assert response.message == "익절 비율을 30%로 설정할까요? 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."


def test_parse_llm_response_does_not_repeat_known_trailing_stop_explanation():
    response = coach_routes._parse_llm_response(
        "{\"message\": \"트레일링 스탑(주가가 오른 뒤 최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건)을 추가해 보시겠어요? 예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주시면 바로 추가하겠습니다.\"}",
        explained_terms={"trailing_stop"},
    )

    assert response.message == "트레일링 스탑을 추가해 보시겠어요? 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."


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

    assert response.message.count("바로 백테스트") == 1


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
    assert "'익절 비율을 설정할까요?'처럼 추가 여부를 묻는 표현" in msg


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
    assert "트레일링 스탑 같은 전문 용어" in prompt
    assert "뜻을 쉬운 말로 덧붙이십시오" in prompt
    assert "수치가 필요한 조건" in prompt
    assert "몇 %로 설정할지 먼저 물어보십시오" in prompt
    assert "strategy_memory_context" in prompt
    assert "data_sufficiency가 insufficient" in prompt
    assert "꾸며내지 마라" in prompt
    assert "백테스트 결과가 없으면" in prompt
    assert "제공되지 않은 백테스트 사례" in prompt
    assert "검색/계산/판정 엔진이 아니라" in prompt
    assert "과거 데이터 검색" in prompt
    assert "지금 바로 할 수 없는 행동" in prompt
    assert "비교 테스트를 진행해 보시겠어요?" in prompt
    assert "익절 비율을 설정할까요?" in prompt
    assert "트레일링 스탑을 모든 전략의 기본 개선안처럼 제안하지 마십시오" in prompt
    assert "정확한 수치를 말한 경우에만" in prompt
    assert "익절 비율과 트레일링 스탑은 서로 다른 전문 용어" in prompt
    assert "익절 비율은 매수가 대비 정한 수익률에 도달하면 매도하는 고정 목표 수익 조건" in prompt
    assert "트레일링 스탑은 보유 중 최고가에서 정한 비율만큼 내려오면 매도" in prompt
    assert "트레일링 스탑을 뜻하면서 익절 비율이라고 부르지 말고" in prompt
    assert "보유 기간을 개선안으로 제안할 때" in prompt
    assert "보유 기간을 설정할까요?" in prompt
    assert "익절 비율을 개선안으로 제안할 때" in prompt
    assert "익절 비율을 설정할까요?" in prompt
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
