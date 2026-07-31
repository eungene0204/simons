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


class WorkflowEffect(str, Enum):
    """입력이 진행 중인 전략 작성 워크플로에 일으키는 효과.

    QueryIntent와 직교하는 축이다 — 라벨은 "무엇에 대한 발화인가"를, 이 값은 "그
    발화가 워크플로를 어떻게 제어하는가"를 말한다. 한 발화가 전략 요청이면서 동시에
    취소일 수는 없으므로 두 축은 겹치지 않는다(설계 스펙 §4).

    기본값 NONE은 안전 방향이다 — LLM이 이 필드를 채우지 못하면 워크플로 제어가
    일어나지 않고 기존 동작 그대로 흐른다.
    """

    # 워크플로에 영향 없음. 부가 질문·잡담이어도 진행 중인 전략 State는 유지된다.
    # 스펙 §4 예시는 용어 설명을 PAUSE로 적었으나, 같은 스펙 §21이 "부가 질문은 기존
    # 워크플로를 유지한다"고 규정한다. 설명마다 워크플로를 멈추면 명시적 RESUME이
    # 있어야 진행되므로 §21을 따르고, PAUSE는 명시적 중지 요청에만 쓴다.
    NONE = "NONE"
    # 전략 State를 갱신하는 요청(조건 추가·변경·삭제).
    UPDATE = "UPDATE"
    # 사용자가 명시적으로 진행을 멈춘 상태. 전략 State는 보존된다.
    PAUSE = "PAUSE"
    # 멈춘 워크플로를 다시 진행한다.
    RESUME = "RESUME"
    # 전략 작성을 그만둔다. State를 버린다.
    CANCEL = "CANCEL"
    # 전략을 버리고 처음부터 다시 시작한다.
    RESTART = "RESTART"
    # 직전 변경을 되돌린다. 어디로 되돌릴지는 /strategy/rollback/resolve가 정하고,
    # 복원은 변경 이력을 들고 있는 프론트가 결정론으로 수행한다(설계 스펙 § 19).
    ROLLBACK = "ROLLBACK"
    # 직전 해석이 틀렸다는 정정. 되돌린 **뒤** 이 발화로 다시 해석한다(설계 스펙 § 20).
    # ROLLBACK과의 차이는 새 지시가 함께 있는지다 — '아까 거 취소해'는 되돌리고 끝이고,
    # '아니 그런 뜻이 아니라 X야'는 되돌린 자리에 X를 적용해야 한다.
    CORRECT = "CORRECT"


class WorkflowStatus(str, Enum):
    """전략 작성 워크플로의 현재 진행 상태.

    백엔드는 세션을 갖지 않는다 — 프론트가 previous_explicit_fields·pending_ask와 같은
    무상태 에코 계약으로 이 값을 매 턴 돌려준다. PAUSE 없이는 RESUME이 성립하지 않으므로
    효과 판정에는 직전 상태가 필요하다.
    """

    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"


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
    # 워크플로 제어 효과(QueryIntent와 직교). 규제 게이트 라벨에서는 항상 NONE으로
    # 강제된다 — 정형 안내가 워크플로 제어로 우회되지 않게 한다.
    workflow_effect: WorkflowEffect = WorkflowEffect.NONE
    # 이 턴 이후의 워크플로 상태. 프론트가 다음 요청에 그대로 에코한다.
    workflow_status: WorkflowStatus = WorkflowStatus.IDLE
    # 값 없이 지목된 수정 대상(닫힌 목록, intent/clarify_targets.py). 무엇을 되물을지는
    # 프론트의 문구·선택지 표가 이 라벨을 키로 고른다 — 문구를 LLM이 짓지 않는다.
    # 규제 게이트 라벨·진행 중인 전략 없음에서는 항상 None으로 강등된다.
    clarify_target: Optional[str] = None


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
    # 지금 화면에서 **답을 기다리고 있는 질문**(무상태 에코). 이게 없으면 그 답인 짧은
    # 발화("아니야", "응")가 문맥 없는 잡담으로 보여 인사로 오분류된다(2026-07-31 실측).
    # 답인지 아닌지의 판정은 LLM 몫이고, 여기서는 판정 재료만 전달한다.
    pending_question: Optional[str] = None
    # 직전 턴의 워크플로 상태(무상태 에코 계약). PAUSED일 때만 RESUME이 성립하므로
    # 효과 판정의 입력으로 쓴다. 프론트가 응답의 workflow_status를 그대로 돌려준다.
    workflow_status: WorkflowStatus = WorkflowStatus.IDLE
