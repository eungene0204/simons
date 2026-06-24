"""
Query Intent 분류기 — 결정적 우선 하이브리드.

원칙(feedback_nl_parser_hybrid): 핵심은 결정적 규칙으로 처리하고, 애매한 긴 꼬리만
LLM에 위임한다. phrasing마다 regex를 늘리지 않는다.

분류 우선순위:
  1. STRATEGY_ADVICE  — '전략/백테스트/유니버스/리밸런싱' 등 전략 설계 키워드
  2. STOCK_ANALYSIS   — 특정 종목명/코드 + 매수·매도·보유·전망·리스크 질문
  3. GENERAL_INVESTMENT — 'X가 뭐야/뜻/설명/차이' 정의형 질문
  4. (애매) LLM 폴백 → 실패 시 UNKNOWN
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from stock_analysis.symbol_resolver import StockRef, find_in_text, resolve_by_symbol

from .schemas import DetectedSymbol, IntentResult, QueryIntent
from .scope import (
    ONBOARDING_REPLY,
    OFFTOPIC_REFUSAL,
    greeting_reply,
    has_finance_cue,
    is_greeting_only,
    is_offtopic,
    is_onboarding_help_request,
    is_stock_pick_request,
    stock_pick_reply,
)

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]  # (system_prompt, user_msg) -> raw text

# 전략 설계를 가리키는 강한 신호. 이게 있으면 종목명이 섞여 있어도 STRATEGY_ADVICE.
_STRATEGY_KEYWORDS = re.compile(
    r"전략|백테스트|back\s*test|유니버스|리밸런|포트폴리오\s*구성|매매\s*규칙|"
    r"진입\s*조건|청산\s*조건|손절|익절|트레일링|스크리닝|종목\s*선정|분산\s*투자|"
    r"리스크\s*관리|최적화|워크포워드",
    re.IGNORECASE,
)

# 펀더멘털/지표 스크리닝은 이 플랫폼 전략의 핵심 카테고리다 — 특정 종목이 아니라
# '조건에 맞는 종목 바스켓'을 고르는 전략 설계 신호다(phrasing 긴 꼬리가 아니라
# 카테고리 단위 신호이므로 결정적으로 처리, feedback_nl_parser_hybrid 부합).
#   · 지표+숫자 필터: "PBR 1 이하", "PER 10", "ROE 15 이상"
#   · 가치/배당/규모 스크리닝 + 바스켓 명사: "저평가 종목", "고배당주", "우량주"
#   · 비교 필터 + 종목: "~이하인 종목", "거래량 ~이상 종목"
_SCREENING_SIGNAL = re.compile(
    r"(?:per|pbr|psr|roe|roa|eps|bps|배당수익률|배당률|시가총액|시총|부채비율|거래량|거래대금)\s*\d"
    r"|(?:저평가|고평가|고배당|우량|가치|성장|배당|소형|대형|중소형)\s*(?:된|인)?\s*(?:종목|주식|주)"
    r"|(?:이하|이상|미만|초과)\s*(?:인|의)?\s*종목",
    re.IGNORECASE,
)

# 개별 종목에 대한 행동/판단 질문 동사.
_STOCK_QUESTION = re.compile(
    r"사도|살까|사야|매수|들어가|들어가도|진입|팔아|팔까|매도|손절|"
    r"들고|보유|계속\s*가져|전망|어때|어떨까|괜찮|괜찮을까|분석|"
    r"오를까|내릴까|상승|하락|리스크|위험|목표가|적정\s*주가",
    re.IGNORECASE,
)

# 일반 투자 지식(정의형) 질문.
_DEFINITION_QUESTION = re.compile(
    r"(?:뭐야|뭔가요|무엇|뜻이|뜻은|의미가|의미는|차이가|차이는|설명해|"
    r"어떻게\s*계산|왜\s*중요|개념)",
    re.IGNORECASE,
)

# anaphora — 직전 종목을 가리키는 표현('이 종목', '얘', '저 주식').
_ANAPHORA = re.compile(r"이\s*종목|이\s*주식|그\s*종목|저\s*종목|얘|이거", re.IGNORECASE)

_CLASSIFIER_SYSTEM_PROMPT = (
    "너는 투자 챗봇 입력을 의도로 분류한다. "
    "STRATEGY_ADVICE(투자 전략·지표 조합·백테스트·매매 규칙, 그리고 "
    "'PBR 1 이하·PER 10 이하·저평가/고배당 종목'처럼 조건에 맞는 종목을 고르는 스크리닝), "
    "STOCK_ANALYSIS(이름이 명시된 '특정 한 종목'의 매수·매도·보유·전망·리스크·분석), "
    "STOCK_PICK(특정 종목명도 정량 조건도 없이 '무엇을 사야 하나·종목 추천·살 만한 종목·돈 될 종목'처럼 "
    "매수 대상을 골라 달라는 열린 추천 요청), "
    "ONBOARDING(구체적인 전략·지표·종목 없이 '어떻게 시작하지·뭐부터 해야 해·처음인데 어떻게 써'처럼 "
    "무엇을 해야 할지 막막해 도움을 청하는 요청), "
    "GENERAL_INVESTMENT(일반 투자 지식·용어 정의), "
    "GREETING(인사·짧은 사회적 표현), "
    "OFF_TOPIC(투자와 무관한 잡담·사적 대화·일반 상식·날씨·건강·프로그래밍·정치 등 역할 밖 질문), "
    "UNKNOWN(투자 관련이지만 위 어디에도 안 맞아 분류 불가). "
    "특정 종목명이 없는 '조건/필터로 종목 고르기'는 STOCK_ANALYSIS가 아니라 STRATEGY_ADVICE다. "
    "투자와 직접 관련이 없으면 STRATEGY_ADVICE나 UNKNOWN으로 추측하지 말고 OFF_TOPIC으로 분류하라. "
    '반드시 {"intent": "..."} JSON 한 줄로만 답하라.'
)


def _to_detected(refs: list[StockRef]) -> list[DetectedSymbol]:
    return [DetectedSymbol(symbol=r.symbol, name=r.name, overseas=r.overseas) for r in refs]


def _classify_deterministic(query: str, last_symbol: Optional[str]) -> Optional[IntentResult]:
    text = query or ""

    # 0) 역할 범위 가드 — 인사/역할 밖 질문은 전략으로 파싱하지 않고 정해진 응답으로 안내한다.
    if is_greeting_only(text):
        return IntentResult(
            intent=QueryIntent.GREETING,
            suggested_reply=greeting_reply(text),
            confidence=0.95,
            reason="인사 감지",
        )
    if is_offtopic(text):
        return IntentResult(
            intent=QueryIntent.OFF_TOPIC,
            suggested_reply=OFFTOPIC_REFUSAL,
            confidence=0.9,
            reason="역할 밖 질문 감지",
        )

    refs = find_in_text(text)
    has_strategy_kw = bool(_STRATEGY_KEYWORDS.search(text))
    has_screening = bool(_SCREENING_SIGNAL.search(text))
    has_stock_q = bool(_STOCK_QUESTION.search(text))
    has_def_q = bool(_DEFINITION_QUESTION.search(text))

    # 1) 전략 키워드 또는 스크리닝 조건이 있으면 전략 설계로 본다(종목명이 섞여 있어도).
    if has_strategy_kw or has_screening:
        return IntentResult(
            intent=QueryIntent.STRATEGY_ADVICE,
            symbols=_to_detected(refs),
            confidence=0.9,
            reason="전략 설계 키워드 감지" if has_strategy_kw else "종목 스크리닝 조건 감지",
        )

    # 1-b) [규제 안전] 특정 종목명·조건 없이 '무엇을 사야 하나'라는 열린 추천 요청 → 추천하지 않고
    #      전략 설계로 대화를 전환한다. 종목명이 특정됐으면 종목 분석(아래)으로 흘려보낸다.
    if not refs and is_stock_pick_request(text):
        return IntentResult(
            intent=QueryIntent.STOCK_PICK,
            suggested_reply=stock_pick_reply(text),
            confidence=0.9,
            reason="열린 종목 추천 요청 감지 — 전략 설계로 전환",
        )

    # 2) 특정 종목 + 행동/판단 질문 → 종목 분석.
    if refs and has_stock_q:
        return IntentResult(
            intent=QueryIntent.STOCK_ANALYSIS,
            symbols=_to_detected(refs),
            confidence=0.92,
            reason="종목명 + 매수/매도/전망 질문 감지",
        )

    # 2-b) anaphora('이 종목 팔까?') + 직전 종목 컨텍스트 → 종목 분석.
    if has_stock_q and _ANAPHORA.search(text):
        carried = resolve_by_symbol(last_symbol) if last_symbol else None
        return IntentResult(
            intent=QueryIntent.STOCK_ANALYSIS,
            symbols=_to_detected([carried]) if carried else [],
            confidence=0.7 if carried else 0.55,
            reason="직전 종목 참조('이 종목') + 행동 질문",
        )

    # 3) 정의형 질문 → 일반 투자 지식. 단, 투자 신호가 있어야 한다
    #    ('너 이름이 뭐야'처럼 투자 맥락 없는 '뭐야'는 잡담이므로 LLM 폴백으로 넘긴다).
    if has_def_q and not refs and has_finance_cue(text):
        return IntentResult(
            intent=QueryIntent.GENERAL_INVESTMENT,
            confidence=0.85,
            reason="용어 정의형 질문 감지",
        )

    # 4) [온보딩] 위 어디에도 안 맞은(구체 전략·종목·조건이 없는) 막연한 도움 요청
    #    ('어떻게 시작하지?')은 빈 전략 카드를 띄우거나 LLM에 넘기지 않고, 전략 빌더로
    #    유도한다. has_finance_cue가 있으면 구체 질문이므로 여기서 잡지 않는다(위 게이트).
    if is_onboarding_help_request(text):
        return IntentResult(
            intent=QueryIntent.ONBOARDING,
            suggested_reply=ONBOARDING_REPLY,
            confidence=0.85,
            reason="막연한 도움 요청 감지 — 전략 빌더로 유도",
        )

    # 종목명만 단독 등장(행동 동사 없음, 예: '삼성전자 전망' 은 위 2에서 처리됨).
    # 행동 동사도 정의형도 없으면 결정 불가 → LLM 폴백.
    return None


def _classify_with_llm(query: str, llm: LLMFn) -> Optional[IntentResult]:
    try:
        raw = llm(_CLASSIFIER_SYSTEM_PROMPT, query)
    except Exception:
        logger.exception("intent LLM 폴백 실패")
        return None
    match = re.search(
        r'"intent"\s*:\s*"(STRATEGY_ADVICE|STOCK_ANALYSIS|STOCK_PICK|ONBOARDING|GENERAL_INVESTMENT|GREETING|OFF_TOPIC|UNKNOWN)"',
        raw or "",
    )
    if not match:
        return None
    intent = QueryIntent(match.group(1))
    suggested_reply = None
    if intent == QueryIntent.GREETING:
        suggested_reply = greeting_reply(query)
    elif intent == QueryIntent.OFF_TOPIC:
        suggested_reply = OFFTOPIC_REFUSAL
    elif intent == QueryIntent.STOCK_PICK:
        suggested_reply = stock_pick_reply(query)
    elif intent == QueryIntent.ONBOARDING:
        suggested_reply = ONBOARDING_REPLY
    refs = find_in_text(query) if intent == QueryIntent.STOCK_ANALYSIS else []
    return IntentResult(
        intent=intent,
        symbols=_to_detected(refs),
        suggested_reply=suggested_reply,
        confidence=0.6,
        reason="LLM 폴백 분류",
        deterministic=False,
    )


def classify(query: str, *, last_symbol: Optional[str] = None, llm: Optional[LLMFn] = None) -> IntentResult:
    """입력을 QueryIntent로 분류한다. 결정적 규칙 우선, 애매하면 llm 폴백."""
    deterministic = _classify_deterministic(query, last_symbol)
    if deterministic is not None:
        return deterministic

    if llm is not None:
        llm_result = _classify_with_llm(query, llm)
        if llm_result is not None:
            return llm_result

    return IntentResult(
        intent=QueryIntent.UNKNOWN,
        symbols=_to_detected(find_in_text(query or "")),
        confidence=0.3,
        reason="결정적 규칙·LLM 모두 분류 실패",
        deterministic=False,
    )
