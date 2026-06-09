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

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]  # (system_prompt, user_msg) -> raw text

# 전략 설계를 가리키는 강한 신호. 이게 있으면 종목명이 섞여 있어도 STRATEGY_ADVICE.
_STRATEGY_KEYWORDS = re.compile(
    r"전략|백테스트|back\s*test|유니버스|리밸런|포트폴리오\s*구성|매매\s*규칙|"
    r"진입\s*조건|청산\s*조건|손절|익절|트레일링|스크리닝|종목\s*선정|분산\s*투자|"
    r"리스크\s*관리|최적화|워크포워드",
    re.IGNORECASE,
)

# 개별 종목에 대한 행동/판단 질문 동사.
_STOCK_QUESTION = re.compile(
    r"사도|살까|사야|매수|들어가|들어가도|진입|팔아|팔까|매도|손절|"
    r"들고|보유|계속\s*가져|전망|어때|어떨까|괜찮|괜찮을까|"
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
    "너는 투자 챗봇 입력을 4가지 의도로 분류한다. "
    "STRATEGY_ADVICE(투자 전략·지표 조합·백테스트·매매 규칙), "
    "STOCK_ANALYSIS(특정 종목의 매수·매도·보유·전망·리스크), "
    "GENERAL_INVESTMENT(일반 투자 지식·용어 정의), "
    "UNKNOWN(분류 불가). "
    '반드시 {"intent": "..."} JSON 한 줄로만 답하라.'
)


def _to_detected(refs: list[StockRef]) -> list[DetectedSymbol]:
    return [DetectedSymbol(symbol=r.symbol, name=r.name, overseas=r.overseas) for r in refs]


def _classify_deterministic(query: str, last_symbol: Optional[str]) -> Optional[IntentResult]:
    text = query or ""
    refs = find_in_text(text)
    has_strategy_kw = bool(_STRATEGY_KEYWORDS.search(text))
    has_stock_q = bool(_STOCK_QUESTION.search(text))
    has_def_q = bool(_DEFINITION_QUESTION.search(text))

    # 1) 전략 키워드가 있으면 전략 설계 질문으로 본다(종목명이 섞여 있어도).
    if has_strategy_kw:
        return IntentResult(
            intent=QueryIntent.STRATEGY_ADVICE,
            symbols=_to_detected(refs),
            confidence=0.9,
            reason="전략 설계 키워드 감지",
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

    # 3) 정의형 질문 → 일반 투자 지식.
    if has_def_q and not refs:
        return IntentResult(
            intent=QueryIntent.GENERAL_INVESTMENT,
            confidence=0.85,
            reason="용어 정의형 질문 감지",
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
    match = re.search(r'"intent"\s*:\s*"(STRATEGY_ADVICE|STOCK_ANALYSIS|GENERAL_INVESTMENT|UNKNOWN)"', raw or "")
    if not match:
        return None
    intent = QueryIntent(match.group(1))
    refs = find_in_text(query) if intent == QueryIntent.STOCK_ANALYSIS else []
    return IntentResult(
        intent=intent,
        symbols=_to_detected(refs),
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
