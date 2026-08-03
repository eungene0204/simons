"""레드팀 QA(docs/qa_redteam_validation_report.md)에서 발견한 24개 FAIL의 회귀 테스트.

각 테스트는 결정적 계층(분류기·파서·검증 agent·리졸버)만 검증한다 — LLM 왕복이 필요한
부분(오개념 교정 문구 등)은 라우팅/사실주입까지만 확인한다.
"""

from __future__ import annotations

import pytest

from intent.classifier import classify
from intent.schemas import QueryIntent


@pytest.fixture(autouse=True)
def _legacy_lane(monkeypatch):
    """분류기 라우팅 검증은 [레거시 레인](원문 정규식) 대상이다 — 롤백 경로 보증용.
    계약 레인에서 같은 요구사항(맞춤 조언·실계좌 매매 안내 등)이 지켜지는지는
    tests/test_intent_interpreter.py가 라벨→정책 매핑으로 검증한다."""
    monkeypatch.setenv("INTENT_CLASSIFIER_MODE", "legacy")


# ── 분류기 라우팅(심각도 1·5) ────────────────────────────────────────────────

def test_personal_advice_is_not_general_llm_answer():
    """22-10: 나이 기반 맞춤 조언 요청은 LLM 일반답변이 아니라 맞춤 추천 불가 안내."""
    r = classify("40대 직장인인데 나한테 맞는 전략 뭐야?")
    assert r.intent == QueryIntent.STRATEGY_PICK
    assert r.suggested_reply and "맞춘" in r.suggested_reply


@pytest.mark.parametrize("query", [
    "PER이 높을수록 싸다는 거지? 그럼 PER 높은 걸로 사줘",
    "MACD가 100 넘으면 무조건 사면 된대",
    "부채비율 높을수록 레버리지 효과로 무조건 수익 좋아지잖아",
    "골든크로스 나오면 100% 오르는 거 맞지?",
])
def test_misconception_routes_to_knowledge_answer(query):
    """7-1/3/5/6: 오개념 단정/확인 발화는 지식 답변 경로(교정 기회)로."""
    assert classify(query).intent == QueryIntent.GENERAL_INVESTMENT


def test_strategy_pick_superlative_still_detected():
    """22-8: '어떤 전략이 제일 좋아?'는 STRATEGY_PICK(추천 불가 + 빌더)."""
    assert classify("어떤 전략이 제일 좋아?").intent == QueryIntent.STRATEGY_PICK


@pytest.mark.parametrize("query", [
    "자동으로 실전 매매까지 해줘",
    "내 돈 3천만원 대신 투자해줘",
])
def test_live_trading_is_unsupported(query):
    """22-7/22-3: 실계좌 자동매매·대리 투자는 미제공 안내."""
    r = classify(query)
    assert r.intent == QueryIntent.UNSUPPORTED_FEATURE
    assert r.suggested_reply and "가상계좌" in r.suggested_reply


def test_virtual_autotrade_is_not_unsupported():
    """회귀: 가상계좌 모의 자동매매는 미제공으로 막지 않는다."""
    from intent.scope import is_live_trading_request
    assert not is_live_trading_request("가상계좌로 자동매매 돌려줘")


@pytest.mark.parametrize("query", [
    "맥디 데드크로스에 팔아줘",
    "알에스아이 30 밑이면 매수",
])
def test_indicator_typo_is_strategy_not_stock(query):
    """16-4/16-6: 지표 발음 표기 + 매매 동사는 종목 오인 없이 전략 설계."""
    assert classify(query).intent == QueryIntent.STRATEGY_ADVICE


def test_greeting_downgrade_keeps_pure_greeting():
    """15-2 회귀: 순수 인사는 GREETING 유지, 요청 어미가 붙으면 ONBOARDING."""
    from intent.classifier import _classify_with_llm
    greeting = _classify_with_llm("어이~ 반가워이", lambda s, u: '{"intent": "GREETING"}')
    assert greeting.intent == QueryIntent.GREETING
    request = _classify_with_llm("엄청 안전한 걸로 부탁해", lambda s, u: '{"intent": "GREETING"}')
    assert request.intent == QueryIntent.ONBOARDING


# ── 해외 종목(심각도 1) ──────────────────────────────────────────────────────

def test_overseas_stock_redirect_does_not_offer_backtest():
    """10-2: 해외 종목 안내는 그 종목 백테스트를 예시로 제안하지 않는다."""
    from intent.scope import stock_question_redirect
    reply = stock_question_redirect("애플", None, None, overseas=True)
    assert "지원하지 않아요" in reply
    assert "애플에 골든크로스" not in reply


@pytest.mark.parametrize("prompt", [
    "QQQ만 투자하는 전략",
    "엔비디아 백테스트",
    "애플만 골든크로스 전략",
])
def test_overseas_symbols_get_unsupported_notice(prompt):
    """9-1/10-3: 해외 종목은 조용히 드롭하지 않고 미지원 안내."""
    from engine.nl_parser import build_unsupported_concept_notice
    notice = build_unsupported_concept_notice(prompt)
    assert notice is not None and "해외" in notice


# ── 파서 오귀속(심각도 2) ────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,expected", [
    ("최근 3년으로 골든크로스 전략", "3y"),
    ("골든크로스 전략 최근 1년만", "1y"),
])
def test_recent_years_is_backtest_period(prompt, expected):
    """11-1: '최근 N년'은 백테스트 기간(MA 기간 오귀속 아님)."""
    from engine.nl_parser import _extract_backtest_period
    assert _extract_backtest_period(prompt) == expected


@pytest.mark.parametrize("prompt", [
    "최근 3개월 수익률 상위 10종목",
    "최근 1년 오른 종목 위주로",
])
def test_recent_years_guard_excludes_momentum(prompt):
    """11-1 회귀: 모멘텀 룩백·상승 표현은 백테스트 기간으로 오인하지 않는다."""
    from engine.nl_parser import _extract_backtest_period
    assert _extract_backtest_period(prompt) is None


def test_rsi_phonetic_not_ai_model():
    """16-6: '알에스아이'는 rsi 신호로 추출(ai_model 오인 아님)."""
    from engine.nl_parser import _extract_technical_signals
    entry, _ = _extract_technical_signals("알에스아이 30 밑이면 매수")
    assert entry and entry[0].indicator == "rsi"


def test_market_cap_trillion_unit():
    """24-2: '시총 100조'는 1,000,000억(조×10000)으로 변환."""
    from engine.nl_parser import _extract_fundamental_filters
    filters = _extract_fundamental_filters("시총 100조 이상")
    cap = next(f for f in filters if f.metric == "market_cap")
    assert cap.value == 1_000_000.0


def test_preferred_stock_not_swapped_to_common():
    """10-6: 우선주 지정은 보통주로 바꿔치지 않고 미지원 안내에 맡긴다."""
    from engine.nl_parser import _extract_target_symbols, build_unsupported_concept_notice
    assert _extract_target_symbols("삼성전자 우선주로만 골든크로스 전략") is None
    notice = build_unsupported_concept_notice("삼성전자 우선주로만 골든크로스 전략")
    assert notice and "우선주" in notice


def test_english_input_no_phantom_symbol():
    """17-3: 영어 입력의 부분 문자열이 짧은 영문 종목명으로 오매칭되지 않는다."""
    from stock_analysis.symbol_resolver import find_in_text
    assert find_in_text("Make me a value strategy for Korean stocks") == []


def test_korean_short_symbol_still_matches():
    """17-3 회귀: 정상 종목 인식은 유지."""
    from stock_analysis.symbol_resolver import find_in_text
    assert any(r.name == "삼성전자" for r in find_in_text("삼성전자만 RSI 전략"))


# ── 설정값 방어(심각도 3) ────────────────────────────────────────────────────

def test_max_positions_clamped_not_error():
    """13-4: 500종목은 ValidationError 없이 100으로 클램프."""
    from engine.nl_parser import ParsedStrategy
    assert ParsedStrategy(description="x", max_positions=500).max_positions == 100


def test_stop_loss_over_100_dropped_with_notice():
    """14-4: 손절 300%는 반영하지 않고 안내."""
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums
    ps = ParsedStrategy(description="x", stop_loss_pct=300.0)
    notices = enforce_strategy_minimums(ps)
    assert ps.stop_loss_pct is None
    assert any("범위" in n for n in notices)


def test_tiny_take_profit_warns():
    """14-5: 극소 익절은 경고 안내(무언 드롭 아님)."""
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums
    ps = ParsedStrategy(description="x", take_profit_pct=0.0001)
    notices = enforce_strategy_minimums(ps)
    assert ps.take_profit_pct == 0.0001
    assert any("비용" in n for n in notices)


def test_extreme_slippage_reset_with_notice():
    """24-10: 슬리피지 500%는 기본값 복원 + 안내."""
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums
    ps = ParsedStrategy(description="x", slippage_rate=500.0)
    notices = enforce_strategy_minimums(ps)
    assert ps.slippage_rate == 0.05
    assert any("슬리피지" in n for n in notices)


def test_pre_1996_start_date_gets_coverage_notice():
    """11-4: 1985년 시작일은 데이터 커버리지 안내."""
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums
    ps = ParsedStrategy(description="x", backtest_start_date="1985-01-01")
    notices = enforce_strategy_minimums(ps)
    assert any("1996" in n for n in notices)


# ── 미지원 개념(심각도 4) ────────────────────────────────────────────────────

@pytest.mark.parametrize("prompt,keyword", [
    ("골든크로스 전략 ATR 스탑으로 해줘", "ATR"),
    ("골든크로스 전략에 물타기 기능 넣어줘", "물타기"),
    ("장중에 실시간으로 리밸런싱하는 전략", "실시간"),
])
def test_risk_execution_concepts_get_notice(prompt, keyword):
    """14-3/14-6/12-5: 리스크/실행 방식 미지원 개념은 조용히 드롭하지 않는다."""
    from engine.nl_parser import build_unsupported_concept_notice
    notice = build_unsupported_concept_notice(prompt)
    assert notice is not None and keyword in notice


# ── 검증 agent(심각도 3) ─────────────────────────────────────────────────────

def test_contradictory_filters_flagged():
    """23-4: PER ≤10 AND PER ≥20 모순 필터를 검증 agent가 잡는다."""
    from ai.strategy_validation_agent import StrategyValidationAgent
    from api.coach_routes import _validation_payload
    from engine.nl_parser import ParsedStrategy, FundamentalFilter
    ps = ParsedStrategy(
        description="x",
        fundamental_filters=[
            FundamentalFilter(metric="per", operator="<=", value=10.0),
            FundamentalFilter(metric="per", operator=">=", value=20.0),
        ],
        rebalancing_period="monthly",
    )
    result = StrategyValidationAgent().validate(_validation_payload(ps.model_dump()))
    assert any(i["category"] == "logical_conflict" for i in result["issues"])


# ── 수정 경로(심각도 1) ──────────────────────────────────────────────────────

def test_signal_removal_preserves_other_fields():
    """19-3: 'RSI 조건 빼줘'는 RSI만 제거하고 PER·손절을 보존한다."""
    from engine.nl_parser import _modify_rule_based, ParsedStrategy
    prev = ParsedStrategy(
        description="x", universe=["KOSPI"],
        fundamental_filters=[{"metric": "per", "operator": "<=", "value": 10.0}],
        entry_signals=[{"indicator": "rsi", "signal_type": "buy", "period": 14,
                        "operator": "<=", "value": 30.0}],
        exit_signals=[{"indicator": "rsi", "signal_type": "sell", "period": 14,
                       "operator": ">=", "value": 70.0}],
        stop_loss_pct=5.0, max_positions=10,
    ).model_dump()
    r = _modify_rule_based("RSI 조건 빼줘", prev)
    assert r is not None
    assert r.entry_signals == [] and r.exit_signals == []
    assert [f.metric for f in r.fundamental_filters] == ["per"]
    assert r.stop_loss_pct == 5.0


def test_full_rewrite_asks_direction():
    """19-4: '완전 다르게 해줘'는 임의 재작성이 아니라 방향 되묻기."""
    from engine.nl_parser import full_rewrite_clarification
    assert full_rewrite_clarification("그거 말고 완전 다르게 해줘") is not None
    assert full_rewrite_clarification("손절 10%로 바꿔줘") is None


# ── primary 경로: 내부명 치환 + 패치 환각 게이트 ──────────────────────────────

def test_internal_feature_name_humanized():
    """20-5: 미지원 안내에 내부 식별자(strategy_evaluation)를 노출하지 않는다."""
    from strategy_conversation.primary import _humanize_features
    assert _humanize_features(["strategy_evaluation"]) == ["전략 우열 평가"]
    # 매핑에 없는 토큰(FCF·technical.beta)은 그대로 둔다(정보 손실 방지).
    assert _humanize_features(["FCF"]) == ["FCF"]
    assert _humanize_features(["technical.beta"]) == ["technical.beta"]


def test_patch_provenance_gate_rejects_hallucinated_field():
    """20-3: 출처 인용도 수치 근거도 없는 패치는 환각으로 거부(대조, § 3-1).

    2026-07-26 계약 전환: 필드별 어휘 큐 스캔(원문 어휘 스캔)은 폐기 — 판정은
    LLM 인용(source_text)의 실재 여부와 패치 수치의 입력 수치 일치로만 한다.
    """
    from engine.nl_parser import _compact
    from strategy_conversation.interpreter.models import PatchOp
    from strategy_conversation.primary import (
        _input_number_candidates,
        _patch_provenance_supported,
    )

    def gate(patch, utter):
        return _patch_provenance_supported(
            patch, _compact(utter), _input_number_candidates(utter))

    # "다른 예는 없어?"에는 10이라는 수치도, 손절 관련 인용도 없다 → 환각 거부
    assert not gate(
        PatchOp(op="replace", path="/risk_management/stop_loss", value=10),
        "다른 예는 없어?")
    # 지어낸 인용(입력에 없는 문구)도 거부
    assert not gate(
        PatchOp(op="replace", path="/risk_management/stop_loss", value=10,
                source_text="손절 10%로"),
        "다른 예는 없어?")
    # 정상: 발화의 수치 10과 일치하는 손절 패치는 통과(수치 대조)
    assert gate(
        PatchOp(op="replace", path="/risk_management/stop_loss", value=10),
        "손절 10%로 바꿔줘")


# ── 일반답변 사실 주입(심각도 6) ─────────────────────────────────────────────

@pytest.mark.parametrize("query,term", [
    ("PER 써줘", "주가수익비율"),
    ("RSI 90 이하면 과매도라며?", "과매수"),
])
def test_glossary_facts_injected(query, term):
    """6-1/7-4: 기초 용어 정의 사실이 프롬프트에 주입된다."""
    from intent import glossary_facts
    block = glossary_facts.facts_block(query)
    assert block is not None and term in block


# ── 추가 오귀속/UX(심각도 2·5) ───────────────────────────────────────────────

def test_fundamental_top_n_is_not_return_ranking():
    """13-1: 'PER 낮은 상위 20종목'의 '상위'는 선정 개수일 뿐 모멘텀 랭킹이 아니다."""
    from engine.nl_parser import _apply_prompt_overrides, ParsedStrategy
    llm_out = ParsedStrategy(
        description="PER 낮은 상위 20종목 동일비중으로",
        ranking_metric="return", ranking_lookback_days=60, max_positions=20,
    )
    fixed = _apply_prompt_overrides(llm_out, "PER 낮은 상위 20종목 동일비중으로")
    assert fixed.ranking_metric is None
    assert fixed.max_positions == 20


def test_real_momentum_ranking_preserved():
    """13-1 회귀: 실제 모멘텀 요청의 return 랭킹은 유지."""
    from engine.nl_parser import _apply_prompt_overrides, ParsedStrategy
    llm_out = ParsedStrategy(
        description="최근 3개월 수익률 상위 20종목",
        ranking_metric="return", ranking_lookback_days=63, max_positions=20,
    )
    fixed = _apply_prompt_overrides(llm_out, "최근 3개월 수익률 상위 20종목")
    assert fixed.ranking_metric == "return"


def test_fundamental_factor_ranking_survives_qualitative_override():
    """13-1 가드는 'return' 오귀속 전용 — 재무 팩터 랭킹(2026-08-03 지원)은 정확히
    그 정성 표현('PER 낮은 상위 N')의 의도된 표현형이라 비우면 기능이 소거된다."""
    from engine.nl_parser import _apply_prompt_overrides, ParsedStrategy
    llm_out = ParsedStrategy(
        description="PER 낮은 상위 20종목 동일비중으로",
        ranking_metric="per", ranking_direction="bottom", max_positions=20,
    )
    fixed = _apply_prompt_overrides(llm_out, "PER 낮은 상위 20종목 동일비중으로")
    assert fixed.ranking_metric == "per"
    assert fixed.ranking_direction == "bottom"


@pytest.mark.parametrize("query", ["형 돈 벌고 싶어", "부자 되고 싶어"])
def test_vague_money_desire_routes_to_onboarding(query):
    """15-1: 막연한 '돈 벌고 싶다'는 거절이 아니라 빌더 유도."""
    assert classify(query).intent == QueryIntent.ONBOARDING
