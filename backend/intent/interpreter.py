"""의도 분류 LLM 인터프리터 — 자연어 해석 계약 준수 레인.

    원문 → LLM(의미 해석) → 제한된 구조화 출력 → 형식 정규화 → Schema → Domain(정책)

이 모듈의 정규식은 **LLM 출력에만** 걸린다(JSON 경계 추출·코드펜스 제거·enum 표기 정규화).
사용자 원문에는 어떤 패턴 매칭도 하지 않는다 — 원문의 의미는 전적으로 LLM이 정한다
(CLAUDE.md 자연어 해석 구조 원칙, docs/nl_interpretation_contract.md).

종목명도 원문 스캔으로 찾지 않는다. LLM이 뽑은 짧은 문자열을 registry(symbol_resolver)에
넘겨 정본 매핑한다(금지 사항 5 — 지식 조회를 원문에서 수행하지 않는다).
"""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

from pydantic import BaseModel, ValidationError

from .schemas import ChatTurn, QueryIntent, WorkflowEffect

INTENT_SCHEMA_VERSION = "1.0"

LLMFn = Callable[[str, str], str]

# LLM에 넘기는 대화 맥락 상한 — 후속 질문 판단에는 최근 몇 턴이면 충분하고,
# 작은 분류 모델의 입력이 길어질수록 오분류가 늘어난다.
_HISTORY_MAX_TURNS = 6
_HISTORY_TEXT_MAX = 240

SYSTEM_PROMPT = (
    "너는 한국 주식 전략 연구 플랫폼의 사용자 입력을 의도로 분류한다.\n"
    "아래 라벨 중 정확히 하나를 고른다.\n"
    "\n"
    "STRATEGY_ADVICE — 투자 전략 설계·수정 요청. 지표 조합, 매매 규칙, 백테스트,\n"
    "  조건 스크리닝('PBR 1 이하', '저평가 종목'), 유니버스·업종·테마 지정,\n"
    "  진행 중인 전략의 파라미터 변경('종목 5개로', '손절 -9%로', '원자력 업종만').\n"
    "STOCK_ANALYSIS — 이름이 명시된 특정 한 종목의 매수·매도·보유·전망·리스크 판단 질문.\n"
    "STOCK_PICK — 종목명도 정량 조건도 없이 '무엇을 사야 하나·종목 추천해줘'처럼\n"
    "  매수 대상을 골라 달라는 열린 추천 요청.\n"
    "STRATEGY_PICK — 구체적 지표·유형 없이 '어떤 전략이 좋을까·전략 추천해줘'처럼\n"
    "  어떤 전략이 우수한지 골라 달라는 열린 요청(특정 유형이 명시되면 STRATEGY_ADVICE).\n"
    "PERSONAL_ADVICE — 나이·자산·소득·직업·위험성향 등 개인 상황에 맞춘 전략·종목 추천 요청\n"
    "  ('40대인데 나한테 맞는 전략 뭐야?').\n"
    "LIVE_TRADING — 실제 계좌로 매매를 실행하거나 자금을 대신 운용해 달라는 요청\n"
    "  (가상계좌·모의투자 요청은 해당 없음 — 그건 STRATEGY_ADVICE).\n"
    "ONBOARDING — 구체적 전략·지표·종목 없이 '어떻게 시작하지·뭐부터 해야 해·처음인데'처럼\n"
    "  무엇을 해야 할지 막막해 도움을 청하는 요청.\n"
    "UNSUPPORTED_FEATURE — 뉴스·공시·SNS 여론·애널리스트 리포트처럼 플랫폼에 없는 데이터를\n"
    "  근거로 종목을 고르거나 전략을 만들어 달라는 요청(RSI·이동평균·PER 등 지원 지표가\n"
    "  함께 있으면 STRATEGY_ADVICE).\n"
    "GENERAL_INVESTMENT — 일반 투자 지식·용어 정의·설정 기본값 질문, 그리고 잘못된 금융\n"
    "  상식을 확인하는 발화('PER이 높을수록 싸다는 거지?').\n"
    "GREETING — 인사·짧은 사회적 표현만 있는 입력.\n"
    "OFF_TOPIC — 투자와 무관한 잡담·일반 상식·날씨·건강·프로그래밍·정치.\n"
    "UNKNOWN — 투자 관련이지만 위 어디에도 안 맞아 분류 불가.\n"
    "\n"
    "판단 규칙:\n"
    "1. 글자 표면이 아니라 의미로 판단하라. 오타·구어·줄임말이 섞일 수 있다.\n"
    "2. 업종·테마·섹터를 지정하거나 좁히는 표현('원자력 업종만', '2차전지 관련주로')은\n"
    "   전략의 유니버스 지정이다 — STRATEGY_ADVICE이며 OFF_TOPIC이 아니다.\n"
    "3. 입력 앞에 [대화 맥락]과 [진행 중인 전략]이 주어질 수 있다. 분류 대상은\n"
    "   [최신 입력] 하나지만, 진행 중인 전략이 있으면 짧고 모호한 입력도 그 전략을\n"
    "   다듬는 요청일 가능성이 높다 — 함부로 OFF_TOPIC으로 보내지 마라.\n"
    "4. 투자와 무관함이 분명할 때만 OFF_TOPIC을 쓴다. 애매하면 UNKNOWN이다.\n"
    "\n"
    "라벨과 별개로, 이 입력이 진행 중인 전략 작성을 어떻게 제어하는지도 고른다.\n"
    "\n"
    "NONE — 워크플로를 제어하지 않는다. 용어 질문·잡담·일반 질문처럼 전략을 그대로\n"
    "  두는 입력은 전부 NONE이다(기본값).\n"
    "UPDATE — 전략의 조건을 추가·변경·삭제하는 요청.\n"
    "PAUSE — 진행을 잠시 멈춰 달라는 명시적 요청('잠깐 멈춰', '이따 이어서 할게').\n"
    "RESUME — 멈춘 작업을 다시 이어 달라는 요청('아까 하던 거 계속하자').\n"
    "CANCEL — 전략 작성을 그만두겠다는 요청('그만할래', '취소').\n"
    "RESTART — 지금 전략을 버리고 처음부터 다시 하겠다는 요청('처음부터 다시 하자').\n"
    "ROLLBACK — 직전 변경을 되돌려 달라는 요청('아까 바꾼 거 취소해', '그 전으로').\n"
    "\n"
    "제어 판단 규칙:\n"
    "5. 확실할 때만 NONE이 아닌 값을 고른다. 애매하면 NONE이다 — 잘못된 취소·초기화는\n"
    "   사용자가 쌓아온 전략을 잃게 만든다.\n"
    "6. 조건을 지우는 것(UPDATE)과 작업을 되돌리는 것(ROLLBACK)은 다르다.\n"
    "   'PER 조건 빼줘'는 UPDATE이고, 'PER 조건 지운 거 되돌려'는 ROLLBACK이다.\n"
    "7. 전체를 버리는 것(RESTART)과 일부를 바꾸는 것(UPDATE)은 다르다.\n"
    "   '유니버스만 다시 정하자'는 UPDATE이고, '전략 다 지우고 새로 하자'는 RESTART다.\n"
    "\n"
    "출력 형식(JSON 한 줄, 다른 말 금지):\n"
    '{"intent": "<라벨>", "stock_name": "<원문에 나온 종목명 또는 null>", '
    '"refers_to_last_stock": <직전에 다루던 종목을 \'이 종목\'처럼 가리키면 true, 아니면 false>, '
    '"workflow_effect": "<제어 값>"}'
)


class IntentInterpretation(BaseModel):
    """LLM이 내놓는 제한된 구조화 출력. 이 모델을 통과한 값만 도메인 정책이 소비한다."""

    intent: QueryIntent
    # 원문에 등장한 종목 표기. registry 정본 매핑의 입력으로만 쓴다(원문 스캔 대체).
    stock_name: Optional[str] = None
    refers_to_last_stock: bool = False
    # 워크플로 제어 효과. 표기 불량·미출력은 NONE으로 떨어진다 — 라벨 분류를 실패로
    # 만들지 않는다(효과는 부가 축이고, NONE이 기존 동작 그대로라 안전 방향이다).
    workflow_effect: WorkflowEffect = WorkflowEffect.NONE


# ── 형식 정규화 (입력이 LLM 출력이므로 결정론 코드 소관) ─────────────────────

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
# 소형 모델이 붙이는 사고 흔적 블록. JSON 경계 추출 전에 걷어낸다.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LABEL_SEPARATORS = re.compile(r"[\s\-]+")


def extract_json_object(raw: str) -> Optional[dict]:
    """LLM 출력에서 JSON 객체 하나를 꺼낸다. 실패하면 None(임의 보정 금지)."""
    text = _THINK_BLOCK.sub("", raw or "")
    text = _CODE_FENCE.sub("", text.strip())
    match = _JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_intent_label(value: object) -> Optional[str]:
    """라벨 표기를 enum 값으로 정규화한다('off topic'·'off-topic'·소문자 → OFF_TOPIC)."""
    if not isinstance(value, str):
        return None
    label = _LABEL_SEPARATORS.sub("_", value.strip()).upper()
    return label if label in QueryIntent.__members__ else None


def normalize_workflow_effect(value: object) -> WorkflowEffect:
    """제어 값 표기를 enum으로 정규화한다('roll back'·소문자 → ROLLBACK).

    입력이 LLM 출력이므로 표기 정규화는 결정론 코드 소관이다. 목록 밖 표기는 NONE —
    모르는 값을 제어 동작으로 승격하지 않는다."""
    if not isinstance(value, str):
        return WorkflowEffect.NONE
    label = _LABEL_SEPARATORS.sub("_", value.strip()).upper()
    # 값이 전부 한 단어라 구분자를 밑줄로 바꾸면 오히려 안 맞는다('roll back' → ROLL_BACK).
    # 밑줄을 지운 형태도 대조한다.
    for candidate in (label, label.replace("_", "")):
        if candidate in WorkflowEffect.__members__:
            return WorkflowEffect[candidate]
    return WorkflowEffect.NONE


def _clean_stock_name(value: object) -> Optional[str]:
    """LLM이 채운 종목명 필드를 정리한다. 빈 값·null 표기는 None."""
    if not isinstance(value, str):
        return None
    name = value.strip().strip("\"'")
    if not name or name.lower() in ("null", "none", "n/a", "없음"):
        return None
    return name


def format_history_context(history: Optional[list[ChatTurn]]) -> str:
    """대화 맥락을 LLM 프롬프트용 텍스트로 만든다(없으면 빈 문자열)."""
    if not history:
        return ""
    lines = []
    for turn in history[-_HISTORY_MAX_TURNS:]:
        text = (turn.text or "").strip()
        if not text:
            continue
        if len(text) > _HISTORY_TEXT_MAX:
            text = text[:_HISTORY_TEXT_MAX] + "…"
        speaker = "사용자" if turn.role == "user" else "챗봇"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def build_user_message(
    query: str,
    history: Optional[list[ChatTurn]] = None,
    active_strategy: bool = False,
) -> str:
    """분류 LLM에 보낼 사용자 메시지를 만든다.

    진행 중인 전략 여부를 함께 알린다 — 전략 카드가 떠 있는 상태의 짧은 발화는
    그 전략을 다듬는 요청일 확률이 높다는 맥락을 LLM이 쓸 수 있게 한다(원문 정규식으로
    '수정 요청'을 판별하던 레거시 규칙의 계약 준수 대체물)."""
    parts = []
    if active_strategy:
        parts.append("[진행 중인 전략] 있음")
    context = format_history_context(history)
    if context:
        parts.append(f"[대화 맥락]\n{context}")
    parts.append(f"[최신 입력]\n{query}")
    return "\n".join(parts)


def interpret(
    query: str,
    llm: LLMFn,
    history: Optional[list[ChatTurn]] = None,
    active_strategy: bool = False,
) -> Optional[IntentInterpretation]:
    """원문을 LLM에 넘겨 제한된 구조화 출력으로 해석한다.

    반환 None = 해석 실패(실패 보고). 정규식으로 원문을 재해석하는 폴백은 두지 않는다
    (계약 § 8-1 "폴백은 자연어 재해석이 아니라 실패 보고"). LLM 호출 예외는 그대로
    올려 호출부가 연결 오류(503)와 구분할 수 있게 한다."""
    raw = llm(SYSTEM_PROMPT, build_user_message(query, history, active_strategy))
    payload = extract_json_object(raw)
    if payload is None:
        return None
    label = normalize_intent_label(payload.get("intent"))
    if label is None:
        return None
    try:
        return IntentInterpretation(
            intent=QueryIntent(label),
            stock_name=_clean_stock_name(payload.get("stock_name")),
            refers_to_last_stock=bool(payload.get("refers_to_last_stock")),
            workflow_effect=normalize_workflow_effect(payload.get("workflow_effect")),
        )
    except ValidationError:
        return None
