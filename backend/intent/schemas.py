"""Query intent 분류 결과 스키마."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    STRATEGY_ADVICE = "STRATEGY_ADVICE"
    # 특정 종목의 매수·매도·전망 질문 — 판단·추천 대신 그 종목에서 출발한 전략 설계로
    # 전환하는 안내를 suggested_reply로 동반한다(종목 분석 기능은 제거됨).
    STOCK_ANALYSIS = "STOCK_ANALYSIS"
    # 특정 종목을 골라/추천해 달라는 열린 요청 — 추천 대신 전략 설계로 전환(suggested_reply).
    STOCK_PICK = "STOCK_PICK"
    # 어떤 전략이 좋은지 골라/추천해 달라는 열린 요청 — 우열 판단 대신 전략 빌더로 유도(suggested_reply).
    STRATEGY_PICK = "STRATEGY_PICK"
    # 무엇을 해야 할지 모르는 막연한 도움 요청('어떻게 시작하지?') — 전략 빌더로 유도(suggested_reply).
    ONBOARDING = "ONBOARDING"
    # [규제 안전] 나이·자산·직업 등 개인 상황 기반 맞춤 추천 요청 — 맞춤 조언 불가 안내 + 빌더 유도.
    # 레거시 원문 정규식(is_personal_advice_request)이 담당하던 판정을 LLM 라벨로 승격한 것.
    PERSONAL_ADVICE = "PERSONAL_ADVICE"
    # [기능 범위] 실계좌 자동매매·대리 투자 요청 — 미제공 안내(가상계좌 모의투자로 유도).
    # 레거시 원문 정규식(is_live_trading_request)이 담당하던 판정을 LLM 라벨로 승격한 것.
    LIVE_TRADING = "LIVE_TRADING"
    # 뉴스·공시 분석처럼 플랫폼이 제공하지 않는 기능을 근거로 한 요청 — 빌더로 새지 않고
    # 미제공 안내 + 다른 아이디어 유도(suggested_reply).
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"
    GENERAL_INVESTMENT = "GENERAL_INVESTMENT"
    GREETING = "GREETING"
    OFF_TOPIC = "OFF_TOPIC"
    UNKNOWN = "UNKNOWN"


class DetectedSymbol(BaseModel):
    symbol: str
    name: str
    overseas: bool = False


class IntentResult(BaseModel):
    intent: QueryIntent
    symbols: List[DetectedSymbol] = Field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    # 결정적 규칙으로 끝났는지(테스트/디버깅용). LLM 폴백을 거쳤으면 False.
    deterministic: bool = True
    # GREETING/OFF_TOPIC처럼 곧바로 보여줄 정해진 응답 문구(없으면 None).
    suggested_reply: Optional[str] = None


class ChatTurn(BaseModel):
    """대화 맥락 한 턴. 후속 질문('다른 예는 없어?')을 직전 주제의 연속으로 분류하기 위한
    참고용 컨텍스트다 — 분류 대상은 항상 최신 입력(query) 하나뿐이다."""

    role: str  # "user" | "assistant"
    text: str


class IntentRequest(BaseModel):
    query: str
    # 직전 분석 종목 등 anaphora('이 종목') 해석을 돕는 보조 컨텍스트.
    last_symbol: Optional[str] = None
    # 최근 대화 턴(오래된 것부터). 분류 LLM이 후속 질문을 맥락으로 판단하게 한다.
    history: List[ChatTurn] = Field(default_factory=list)
    # 화면에 진행 중인 전략이 떠 있는지. 짧고 모호한 발화('원자력 업종만 테스트 하고 싶어')를
    # 역할 밖 잡담이 아니라 전략 수정 요청으로 읽을 근거를 LLM에 준다.
    active_strategy: bool = False
