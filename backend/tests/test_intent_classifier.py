"""Query Intent 분류기 테스트 — 스펙 예시 + 결정적 규칙 + LLM 폴백."""

from __future__ import annotations

import pytest

from intent.classifier import classify, format_history_context, _correct_count_typo
from intent.schemas import ChatTurn, QueryIntent


@pytest.mark.parametrize(
    "query, expected",
    [
        ("RSI 30 이하에서 매수하는 전략 어때?", QueryIntent.STRATEGY_ADVICE),
        ("지금 삼성전자 사도 될까요?", QueryIntent.STOCK_ANALYSIS),
        ("PER이 뭐야?", QueryIntent.GENERAL_INVESTMENT),
        ("SK하이닉스 전망 어때?", QueryIntent.STOCK_ANALYSIS),
        ("엔비디아 지금 들어가도 돼?", QueryIntent.STOCK_ANALYSIS),
        ("카카오 계속 들고 있어도 될까?", QueryIntent.STOCK_ANALYSIS),
    ],
)
def test_spec_examples(query, expected):
    assert classify(query).intent == expected


@pytest.mark.parametrize(
    "query",
    [
        "PBR 1 이하, PER 10 이하 저평가 종목",  # 실제 버그 재현 케이스
        "저평가 종목",
        "고배당주 추천해줘",
        "ROE 15 이상 우량주",
        "거래량 100만 이상 종목",
        "시총 1조 이상인 종목",
        # 지표와 숫자 사이에 목적격 조사(을/를)가 끼는 수정 표현도 전략으로 잡혀야 한다.
        "roe를 5% 이상으로 해줘",
        "pbr을 1.2 이하로 바꿔줘",
        "per를 10 이하로",
        "부채비율을 50% 미만으로",
    ],
)
def test_fundamental_screening_is_strategy(query):
    # 특정 종목명 없는 '조건/필터로 종목 고르기'는 전략 설계(스크리닝)다.
    # 종목 분석(STOCK_ANALYSIS)으로 빠지면 "어떤 종목?" 막다른 길이 된다.
    result = classify(query)  # llm 없이도 결정적으로 잡혀야 한다
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.deterministic is True


@pytest.mark.parametrize(
    "query",
    [
        "어떤 주식을 사야 할까요?",
        "어떤 종목을 사야 하나요?",
        "추천 종목이 있나요?",
        "지금 살 만한 종목이 있나요?",
        "뭐를 사면 좋을까요?",
        "AI 관련주 추천해 주세요.",
        "수익이 잘 날 종목이 있나요?",
    ],
)
def test_open_stock_pick_is_redirected(query):
    # [규제 안전] 특정 종목명·조건 없이 '무엇을 사야 하나'라는 열린 추천 요청은
    # 추천하지 않고 전략 설계로 전환하는 안내(STOCK_PICK + suggested_reply)로 잡혀야 한다.
    result = classify(query)  # llm 없이도 결정적으로
    assert result.intent == QueryIntent.STOCK_PICK
    assert result.deterministic is True
    assert result.suggested_reply
    assert "전략" in result.suggested_reply


@pytest.mark.parametrize(
    "query",
    [
        "종목을 10개로 늘려줘",      # 실제 버그 재현: '종목' 때문에 STOCK_PICK으로 빌더 진입하던 케이스
        "보유 종목을 5개로 줄여줘",
        "손절 추가해줘",
        "보유 기간 바꿔줘",
        "백테스트 5년으로 변경해줘",
        "익절을 30%로 높여줘",
        "비중을 조정해줘",
    ],
)
def test_strategy_modification_is_strategy_not_pick(query):
    # 기존 전략을 다듬는 수정/조정 명령은 종목 추천(STOCK_PICK)이 아니라 전략 설계로
    # 결정적으로 잡혀, 빌더로 새로 진입해 기존 전략을 버리지 않아야 한다.
    result = classify(query)  # llm 없이도 결정적으로
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.deterministic is True


@pytest.mark.parametrize(
    "raw,corrected",
    [
        ("종목은 5게", "종목은 5개"),
        ("종목은 120게", "종목은 120개"),
        ("5게 이상", "5개 이상"),
        ("120게임 만들기", "120게임 만들기"),  # 게로 시작하는 단어는 보존
    ],
)
def test_correct_count_typo_ge_to_gae(raw, corrected):
    # [회귀] 숫자 뒤 '게'(개 오타)를 분류 전에 보정해 OFF_TOPIC 오분류를 막는다.
    assert _correct_count_typo(raw) == corrected


def test_classify_normalizes_count_typo_before_llm():
    # 오타 입력 "종목은 5게"는 LLM에 보정된 "종목은 5개"로 전달돼야 한다.
    seen = {}

    def fake_llm(_system, query):
        seen["query"] = query
        return '{"intent": "STRATEGY_ADVICE"}'

    classify("종목은 5게", llm=fake_llm)
    assert seen["query"] == "종목은 5개"


def test_classifier_prompt_has_typo_tolerance_guidance():
    # [회귀] 결정적 정규화가 못 잡는 미지의 오타도 LLM이 의미로 분류하도록 프롬프트가 안내해야 한다.
    from intent.classifier import _CLASSIFIER_SYSTEM_PROMPT
    assert "오타" in _CLASSIFIER_SYSTEM_PROMPT
    assert "OFF_TOPIC이 아니다" in _CLASSIFIER_SYSTEM_PROMPT


def test_named_stock_is_not_pick_redirect():
    # 종목명이 특정된 매수 질문은 열린 추천(STOCK_PICK)이 아니라 STOCK_ANALYSIS로 잡혀
    # 그 종목에서 출발한 전략 전환 안내(suggested_reply)를 받는다.
    result = classify("삼성전자 사야 할까요?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS


@pytest.mark.parametrize(
    "query",
    [
        "삼성전자를 사볼까?",       # 실사용 문구 — '사볼까'도 결정적으로 잡혀야 한다
        "지금 삼성전자 사도 될까요?",
        "SK하이닉스 전망 어때?",
    ],
)
def test_stock_question_redirects_to_strategy_building(query):
    # [규제 안전] 종목 분석 기능 제거 — 특정 종목 매수·매도 질문에는 판단·추천을 제공하지
    # 않고, 그 종목에서 출발한 전략 설계 전환 안내를 suggested_reply로 동반해야 한다.
    result = classify(query)
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert result.deterministic is True
    reply = result.suggested_reply or ""
    assert "추천은 제공하지 않아요" in reply
    assert "전략" in reply
    # 언급한 종목명이 안내에 포함돼 '그 종목에서 출발한' 전환임이 드러나야 한다.
    assert result.symbols and result.symbols[0].name in reply


def test_stock_question_redirect_tailors_universe_by_market():
    # 예시 전략의 유니버스는 언급 종목의 시장에 맞춘다(KOSPI→코스피200 대형주, KOSDAQ→코스닥).
    from intent.scope import stock_question_redirect
    kospi = stock_question_redirect("삼성전자", "KOSPI")
    assert "코스피200" in kospi
    kosdaq = stock_question_redirect("에코프로", "KOSDAQ")
    assert "코스닥" in kosdaq
    generic = stock_question_redirect()
    assert "추천은 제공하지 않아요" in generic


def test_stock_question_redirect_has_no_action_directives():
    # 안내 문구 자체가 매수·매도 지시/추천 표현을 담으면 안 된다(유사투자자문 회피).
    from stock_analysis.guardrails import contains_forbidden
    from intent.scope import stock_question_redirect
    assert contains_forbidden(stock_question_redirect("삼성전자", "KOSPI")) is False


def test_llm_fallback_stock_analysis_sets_redirect_reply():
    # LLM 폴백으로 STOCK_ANALYSIS가 분류돼도 전환 안내가 채워져야 한다(프론트가 그대로 표시).
    result = classify("삼성전자 물타기 괜찮은 생각일까요 흠", llm=lambda s, u: '{"intent": "STOCK_ANALYSIS"}')
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert "추천은 제공하지 않아요" in (result.suggested_reply or "")


def test_screening_basket_recommend_is_strategy():
    # '고배당주 추천'은 열린 추천이 아니라 스크리닝 전략 설계로 분류돼야 한다.
    assert classify("고배당주 추천해줘").intent == QueryIntent.STRATEGY_ADVICE


def test_stock_question_extracts_symbol():
    result = classify("지금 삼성전자 사도 될까요?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "005930" for s in result.symbols)


def test_strategy_keyword_beats_stock_name():
    # 종목명이 섞여 있어도 '전략/백테스트'가 있으면 전략 설계로 분류.
    result = classify("삼성전자로 백테스트하는 전략 만들어줘")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


@pytest.mark.parametrize(
    "query",
    [
        "삼성전자 단일 종목만 테스트 해보자",
        "삼성전자 골든크로스 테스트를 해보자",
    ],
)
def test_stock_name_with_test_cue_is_strategy(query):
    # [회귀] FR-STR-068 — 종목명+'테스트'는 그 종목 백테스트 요청이다. 결정 규칙이 없어
    # LLM 폴백이 STOCK_ANALYSIS로 오판, 매수·매도 판단 거절 안내로 새던 버그.
    result = classify(query)
    assert result.intent == QueryIntent.STRATEGY_ADVICE
    assert result.deterministic is True


@pytest.mark.parametrize(
    "query",
    [
        "삼성전자 지금 손절해야 할까?",
        "삼성전자 익절 타이밍 어때?",
        "카카오 손절할까 계속 들고 갈까?",
    ],
)
def test_stock_question_with_risk_word_only_is_stock_analysis(query):
    # [회귀] 손절/익절은 전략 키워드이지만, 종목명+행동 질문에서 전략 증거가 그 단어들뿐이면
    # 전략 설계가 아니라 개별 종목 질문이다. 예전엔 '손절' 키워드가 선점해 전략 파싱으로
    # 오라우팅됐다(→빈 전략 카드/빌더 진입 막다른 길).
    result = classify(query)
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert result.deterministic is True


@pytest.mark.parametrize(
    "query",
    [
        "삼성전자 손절 10%로 백테스트해줘",       # 다른 전략 키워드(백테스트) 있음
        "삼성전자 넣고 손절 8% 전략 만들어줘",     # 구성 동사 있음
        "손절 추가해줘",                          # 종목명 없음(수정 명령)
    ],
)
def test_risk_word_with_other_strategy_evidence_stays_strategy(query):
    # 리스크 단어 외의 전략 증거(백테스트/전략/구성 동사/수정 명령)가 있으면 전략 설계 유지.
    assert classify(query).intent == QueryIntent.STRATEGY_ADVICE


def test_anaphora_uses_last_symbol():
    result = classify("이 종목 팔아야 할까?", last_symbol="005930")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "005930" for s in result.symbols)


def test_overseas_alias_detected_but_marked_overseas():
    result = classify("엔비디아 지금 들어가도 돼?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.overseas for s in result.symbols)


def test_definition_question_is_general():
    assert classify("골든크로스가 무엇인가요?").intent == QueryIntent.GENERAL_INVESTMENT


@pytest.mark.parametrize(
    "query",
    [
        "리밸런싱이 뭔가요?",       # 실제 버그 재현: '리밸런' 전략 키워드에 가로채여 STRATEGY로 오분류되던 케이스
        "모멘텀 전략이 뭐야?",
        "손절이 무엇인가요?",
        "트레일링 스탑이 무슨 뜻이야?",
    ],
)
def test_definition_beats_strategy_keyword(query):
    # [회귀] 전략 키워드('리밸런/전략/손절/트레일링')가 섞여도, 구성/수정 동사 없는 순수 정의형
    # 질문('~이 뭔가요?')은 전략 설계가 아니라 일반 투자 지식(GENERAL_INVESTMENT)으로 잡혀야 한다.
    result = classify(query)
    assert result.intent == QueryIntent.GENERAL_INVESTMENT
    assert result.deterministic is True


def test_definition_with_construct_verb_stays_strategy():
    # 정의형 표지가 있어도 '만들어줘' 같은 구성 동사가 붙으면 설계 요청이다.
    assert classify("모멘텀 전략이 뭔지 설명하고 만들어줘").intent == QueryIntent.STRATEGY_ADVICE


def test_virtual_account_is_in_scope_not_offtopic():
    # [회귀] '가상계좌/모의투자'는 이 플랫폼의 핵심 기능이므로 역할 밖(OFF_TOPIC) 신호가 아니다.
    from intent.scope import is_offtopic, has_finance_cue
    assert has_finance_cue("가상계좌 만들어줘") is True
    assert is_offtopic("가상계좌 만들어줘") is False
    assert is_offtopic("모의투자 하고 싶어요") is False
    # '가상현실 게임'처럼 '가상'만 들어간 잡담은 여전히 역할 밖으로 걸러야 한다.
    assert is_offtopic("가상현실 게임 추천해줘") is True


def test_ambiguous_without_llm_is_unknown():
    # 종목명·전략 키워드·정의형·행동 동사가 모두 없는 입력 → 결정 불가 → UNKNOWN.
    result = classify("음 글쎄요 그냥 궁금해서요")
    assert result.intent == QueryIntent.UNKNOWN
    assert result.deterministic is False


def test_llm_fallback_used_when_deterministic_fails():
    captured = {}

    def fake_llm(system, user):
        captured["called"] = True
        return '{"intent": "GENERAL_INVESTMENT"}'

    result = classify("요즘 시장 분위기 어떤 느낌이에요", llm=fake_llm)
    assert captured.get("called") is True
    assert result.intent == QueryIntent.GENERAL_INVESTMENT
    assert result.deterministic is False


def test_substring_match_bug_sk_hynix_not_confused_with_inix():
    # 이닉스(452400)은 SK하이닉스(000660)에 substring으로 포함되지만,
    # 단어 경계를 고려해 정확히 구분해야 한다.
    result = classify("SK하이닉스 사도 될까?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert any(s.symbol == "000660" for s in result.symbols), \
        f"SK하이닉스 코드는 000660이어야 하는데, 찾은 symbol: {[s.symbol for s in result.symbols]}"
    assert not any(s.symbol == "452400" for s in result.symbols), \
        "이닉스(452400)이 잘못 매칭되면 안 된다"


@pytest.mark.parametrize(
    "query",
    ["안녕", "안녕하세요", "좋은 아침", "하이!", "ㅎㅇ"],
)
def test_greeting_is_detected(query):
    result = classify(query)
    assert result.intent == QueryIntent.GREETING
    assert result.deterministic is True
    assert result.suggested_reply  # 곧바로 보여줄 인사 문구가 채워진다


def test_greeting_with_strategy_question_is_strategy():
    # 인사 + 전략 질문이 섞이면 인사로 가로채지 않고 전략 설계로 분류한다.
    result = classify("안녕하세요 RSI 30 이하 매수 전략 어때요?")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


@pytest.mark.parametrize(
    "query",
    ["오늘 날씨 어때?", "파이썬 코드를 작성해줘.", "대통령이 누구야?", "감기에 좋은 약 알려줘"],
)
def test_offtopic_is_refused(query):
    result = classify(query)
    assert result.intent == QueryIntent.OFF_TOPIC
    assert result.deterministic is True
    assert "투자 전략 및 투자 분석 전용" in (result.suggested_reply or "")


def test_offtopic_with_finance_cue_is_not_refused():
    # 금융 신호가 있으면 역할 밖으로 보지 않는다(오탐 방지).
    result = classify("이 전략은 변동성이 날씨처럼 들쭉날쭉해요")
    assert result.intent != QueryIntent.OFF_TOPIC


def test_llm_fallback_offtopic_sets_refusal_reply():
    # 결정적 cue로 못 잡는 잡담('없어 그냥 너랑 놀려고')은 LLM이 OFF_TOPIC으로 잡고
    # 곧바로 보여줄 거절 문구가 채워진다 — 전략 생성으로 새지 않는다.
    result = classify("없어 그냥 너랑 놀려고", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC
    assert "투자 전략 및 투자 분석 전용" in (result.suggested_reply or "")


def test_llm_fallback_offtopic_overridden_when_finance_cue_present():
    # [안전망] 결정 규칙이 못 잡아 LLM 폴백으로 갔는데 LLM이 OFF_TOPIC으로 오판해도,
    # 입력에 금융 신호(cagr 등)가 있으면 거절하지 않고 전략 흐름으로 넘긴다.
    # ('cagr'은 스크리닝 지표가 아니라 결정 규칙엔 안 잡혀 LLM 폴백 경로를 실제로 탄다.)
    result = classify("cagr 위주로 평가해줘", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent != QueryIntent.OFF_TOPIC
    assert result.suggested_reply is None


def test_llm_fallback_greeting_sets_reply():
    result = classify("어이~ 반가워이", llm=lambda s, u: '{"intent": "GREETING"}')
    assert result.intent == QueryIntent.GREETING
    assert result.suggested_reply


def test_definition_without_finance_cue_is_not_general_investment():
    # 투자 맥락 없는 '뭐야'('너 이름이 뭐야')는 결정적으로 GENERAL_INVESTMENT가 되지 않고
    # LLM 폴백으로 넘어가 OFF_TOPIC으로 분류된다.
    result = classify("너 이름이 뭐야", llm=lambda s, u: '{"intent": "OFF_TOPIC"}')
    assert result.intent == QueryIntent.OFF_TOPIC


@pytest.mark.parametrize(
    "query",
    [
        "어떻게 시작하지?",
        "뭐부터 해야 해?",
        "처음인데 어떻게 써요?",
        "어디서부터 시작해야 할지 모르겠어요",
        "사용법 알려줘",
        "초보인데 도와주세요",
    ],
)
def test_onboarding_help_is_routed_to_builder(query):
    # [온보딩] 무엇을 해야 할지 막막한 도움 요청은 거절하거나 빈 전략 카드를 띄우지 않고
    # 전략 빌더로 유도한다(ONBOARDING + suggested_reply). LLM 없이 결정적으로 잡혀야 한다.
    result = classify(query)
    assert result.intent == QueryIntent.ONBOARDING
    assert result.deterministic is True
    assert result.suggested_reply


def test_onboarding_with_finance_cue_is_not_onboarding():
    # 구체적인 지표가 섞인 '어떻게' 질문은 막연한 요청이 아니므로 ONBOARDING으로 잡지 않는다
    # (기존 전략/코칭 흐름이 더 잘 처리한다).
    result = classify("RSI 어떻게 설정해?")
    assert result.intent != QueryIntent.ONBOARDING


def test_onboarding_does_not_steal_strategy_question():
    # '전략 어떻게 만들어?'처럼 전략 키워드가 있으면 전략 설계로 분류된다(온보딩보다 우선).
    result = classify("골든크로스 전략 어떻게 만들어?")
    assert result.intent == QueryIntent.STRATEGY_ADVICE


def test_llm_fallback_onboarding_sets_reply():
    # 결정적 cue로 못 잡는 막막한 입력도 LLM이 ONBOARDING으로 잡으면 안내 문구가 채워진다.
    result = classify("나 이런 거 잘 못하는데", llm=lambda s, u: '{"intent": "ONBOARDING"}')
    assert result.intent == QueryIntent.ONBOARDING
    assert result.suggested_reply


@pytest.mark.parametrize(
    "query",
    [
        "지금 어떤 전략이 좋을까?",
        "어떤 전략이 좋아요?",
        "무슨 전략을 써야 하나요?",
        "전략 추천해줘",
        "좋은 전략 있어?",
        "어떤 전략을 골라야 할지 모르겠어요",
    ],
)
def test_open_strategy_pick_is_routed_to_builder(query):
    # [규제 안전] 어떤 전략이 우수한지 골라 달라는 열린 요청은 우열을 판단·추천하지 않고
    # 전략 빌더로 유도하는 안내(STRATEGY_PICK + suggested_reply)로 잡혀야 한다.
    result = classify(query)  # llm 없이도 결정적으로
    assert result.intent == QueryIntent.STRATEGY_PICK
    assert result.deterministic is True
    assert result.suggested_reply
    assert "백테스트" in result.suggested_reply


@pytest.mark.parametrize(
    "query",
    [
        "모멘텀 전략 추천해줘",       # 특정 유형 명시 → 설계 요청
        "RSI 30 이하에서 매수하는 전략 어때?",
        "골든크로스 전략 만들어줘",
        "이 전략이 좋을까?",         # 기존 전략 지시어 → 다듬기 흐름
        "PBR 낮은 저평가 가치 전략이 좋을까?",
    ],
)
def test_specific_strategy_is_not_pick(query):
    # 구체적인 지표·유형이 명시됐거나 기존 전략을 가리키면 열린 추천이 아니라 설계 요청이다.
    result = classify(query)
    assert result.intent == QueryIntent.STRATEGY_ADVICE


def test_llm_fallback_strategy_pick_sets_reply():
    # 결정적 cue로 못 잡는 애매한 전략 추천 요청도 LLM이 STRATEGY_PICK으로 잡으면 안내가 채워진다.
    result = classify("나한테 맞는 게 뭘까", llm=lambda s, u: '{"intent": "STRATEGY_PICK"}')
    assert result.intent == QueryIntent.STRATEGY_PICK
    assert result.suggested_reply


def test_stock_question_redirect_first_example_uses_stock_sector():
    # 섹터 전략이 지원되면서, 언급 종목이 속한 업종 전략이 첫 예시가 된다(삼성전자→반도체).
    result = classify("삼성전자를 사볼까?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS
    assert "반도체 업종" in (result.suggested_reply or "")


def test_stock_question_redirect_sector_example_is_parseable():
    # 전환 안내의 업종 예시 문구는 실제로 파싱·실행 가능한 전략이어야 한다(막다른 길 방지).
    from intent.scope import stock_question_redirect
    from engine.nl_parser import _parse_rule_based_strategy

    reply = stock_question_redirect("삼성전자", "KOSPI", "반도체")
    example = next(line for line in reply.splitlines() if line.startswith("• ") and "업종" in line)
    parsed = _parse_rule_based_strategy(example.removeprefix("• "))
    assert parsed is not None
    assert parsed.sector == "반도체"
    assert parsed.ranking_metric == "return"


@pytest.mark.parametrize(
    "query",
    [
        "최근 뉴스가 좋은 종목을 사는 전략을 만들어줘",  # 실제 버그 재현: 빌더로 진입하던 케이스
        "호재 있는 종목 골라줘",
        "공시 보고 매매하는 전략 만들어줘",
        "악재 없는 종목만 사는 전략",
        "뉴스 기반으로 종목 골라주는 전략 짜줘",
    ],
)
def test_unsupported_feature_request_is_declined_not_built(query):
    # [기능 범위] 뉴스·공시 분석처럼 제공하지 않는 기능을 근거로 한 요청은 전략 빌더로
    # 유도하지 않고 미제공 안내(UNSUPPORTED_FEATURE + suggested_reply)로 답해야 한다.
    result = classify(query)  # llm 없이도 결정적으로
    assert result.intent == QueryIntent.UNSUPPORTED_FEATURE
    assert result.deterministic is True
    assert result.suggested_reply
    assert "제공하고 있지 않아요" in result.suggested_reply
    assert "아이디어" in result.suggested_reply  # 다른 아이디어 유도


@pytest.mark.parametrize(
    "query",
    [
        # 지원 지표가 섞인 혼합 요청 → 가로채지 않고 일반 전략 흐름(파서 notice가 처리).
        "RSI 30 이하에서 매수하고 호재 뉴스 있으면 익절하는 전략",
        "PBR 1 이하 저평가 종목 중 악재 없는 종목 매수",
        # 뉴스 단어가 있어도 지원 유형이 명시된 설계 요청.
        "뉴스에서 봤는데 골든크로스 전략 만들어줘",
    ],
)
def test_mixed_news_request_stays_strategy(query):
    # 지원 지표·유형이 함께 있으면 미제공 안내로 막지 않고 전략 설계로 흘려보낸다
    # (파서가 지원 부분을 살리고 미지원 개념 notice로 알린다).
    assert classify(query).intent == QueryIntent.STRATEGY_ADVICE


def test_named_stock_news_question_is_stock_analysis():
    # 종목명 + 행동 질문은 뉴스 단어가 섞여도 종목 질문 안내(전략 전환)가 우선한다.
    result = classify("삼성전자 악재 떴는데 팔까?")
    assert result.intent == QueryIntent.STOCK_ANALYSIS


def test_news_definition_question_is_not_declined():
    # 순수 정의형 질문("공시가 뭐야?")은 미제공 안내로 가로채지 않는다(지식 질문).
    result = classify("공시가 뭐야?")
    assert result.intent != QueryIntent.UNSUPPORTED_FEATURE


def test_llm_fallback_unsupported_feature_sets_reply():
    # 결정적 cue로 못 잡는 긴 꼬리 phrasing도 LLM이 UNSUPPORTED_FEATURE로 잡으면 안내가 채워진다.
    result = classify(
        "요즘 화제성 높은 걸로 부탁해", llm=lambda s, u: '{"intent": "UNSUPPORTED_FEATURE"}'
    )
    assert result.intent == QueryIntent.UNSUPPORTED_FEATURE
    assert result.suggested_reply
    assert "제공하고 있지 않아요" in result.suggested_reply


# ─── 대화 맥락(history) 기반 후속 질문 분류 ──────────────────────────────────────
# 실제 사고 재현: 직전 답변이 전략 예시를 보여준 뒤 "다른 예는 없어?"라고 물으면,
# 문장만 보면 투자 신호가 없어 LLM 폴백이 OFF_TOPIC으로 오판 → 거절 문구가 나갔다.
# 최근 대화 턴을 LLM 폴백에 함께 넘겨 직전 주제의 연속으로 분류하게 한다.

_EXAMPLES_SHOWN_HISTORY = [
    ChatTurn(role="user", text="삼성전자 지금 사도 될까?"),
    ChatTurn(
        role="assistant",
        text="삼성전자에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요. "
        "예를 들어 이렇게 시작해볼 수 있어요: RSI 과매도 반등 전략, 골든크로스 추세 전략",
    ),
]


def test_followup_with_history_passes_context_to_llm():
    captured = {}

    def fake_llm(system, user):
        captured["system"] = system
        captured["user"] = user
        return '{"intent": "GENERAL_INVESTMENT"}'

    result = classify("다른 예는 없어?", llm=fake_llm, history=_EXAMPLES_SHOWN_HISTORY)
    # 맥락과 최신 입력이 구분되어 LLM에 전달된다.
    assert "[대화 맥락]" in captured["user"]
    assert "챗봇:" in captured["user"]
    assert "매수·매도 판단이나 종목 추천은 제공하지 않아요" in captured["user"]
    assert "[최신 입력]\n다른 예는 없어?" in captured["user"]
    # 시스템 프롬프트가 후속 질문 판단 규칙을 담는다.
    assert "후속 질문" in captured["system"]
    assert result.intent == QueryIntent.GENERAL_INVESTMENT


def test_no_history_keeps_plain_query_for_llm():
    captured = {}

    def fake_llm(system, user):
        captured["user"] = user
        return '{"intent": "UNKNOWN"}'

    classify("다른 예는 없어?", llm=fake_llm)
    assert captured["user"] == "다른 예는 없어?"


def test_history_does_not_affect_deterministic_rules():
    # 결정적 규칙은 현재 입력만 본다 — 투자 맥락이 있어도 명백한 역할 밖 질문은 거절된다.
    result = classify("오늘 날씨 어때?", history=_EXAMPLES_SHOWN_HISTORY)
    assert result.intent == QueryIntent.OFF_TOPIC
    assert result.deterministic is True


def test_format_history_context_truncates_and_caps_turns():
    long_text = "가" * 500
    history = [ChatTurn(role="assistant", text=long_text)] + [
        ChatTurn(role="user", text=f"turn-{i}") for i in range(10)
    ]
    context = format_history_context(history)
    # 최근 6턴만 남는다 → 긴 첫 턴은 잘려 나간다.
    assert "가" not in context
    assert "turn-9" in context and "turn-4" in context
    assert "turn-3" not in context
    # 개별 턴 텍스트는 240자로 잘린다.
    truncated = format_history_context([ChatTurn(role="assistant", text=long_text)])
    assert len(truncated) < 260
    assert truncated.endswith("…")


def test_format_history_context_empty_and_blank_turns():
    assert format_history_context(None) == ""
    assert format_history_context([]) == ""
    assert format_history_context([ChatTurn(role="user", text="   ")]) == ""


def test_general_query_user_msg_includes_history():
    from api.intent_routes import GeneralQueryRequest, _build_general_user_msg

    req = GeneralQueryRequest(query="다른 예는 없어?", history=_EXAMPLES_SHOWN_HISTORY)
    msg = _build_general_user_msg(req)
    assert "[대화 맥락]" in msg
    assert "[질문]\n다른 예는 없어?" in msg
    # 맥락이 없으면 질문만 그대로.
    assert _build_general_user_msg(GeneralQueryRequest(query="PER이 뭐야?")) == "PER이 뭐야?"
