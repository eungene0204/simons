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

from . import clarify_targets
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
    "4-1. [답을 기다리는 질문]이 주어지면 최신 입력은 **그 질문에 대한 답일 가능성이 높다**.\n"
    "   '아니야'·'응'·'그건 아니고'처럼 짧은 답이라도 인사(GREETING)나 잡담(OFF_TOPIC)이\n"
    "   아니다 — 진행 중인 전략을 다듬는 대화의 일부이므로 STRATEGY_ADVICE로 본다.\n"
    "   GREETING은 대화를 여는 인사일 때만 쓴다.\n"
    "4-2. [진행 중인 전략]이 있을 때 그 **작업 자체를 제어**하는 발화 — '잠깐 멈춰',\n"
    "   '그만할래', '처음부터 다시 만들자', '아까 바꾼 거 되돌려줘' — 는 실계좌 매매\n"
    "   (LIVE_TRADING)도, 열린 추천(STOCK_PICK/STRATEGY_PICK)도 아니다. 라벨은\n"
    "   STRATEGY_ADVICE로 두고 아래 workflow_effect에 해당 제어 값을 실어라.\n"
    "   '멈춰'는 매매 중지 요청이 아니라 이 대화의 진행을 멈추는 것이고, '처음부터\n"
    "   다시 만들자'는 전략을 골라 달라는 것이 아니라 지금 전략을 버리고 새로 시작하는\n"
    "   것이다.\n"
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
    "CORRECT — 직전에 잘못 알아들었다고 정정하면서 **올바른 지시를 함께 주는** 발화\n"
    "  ('아니, 그런 뜻이 아니라 ~야', '그게 아니고 ~로 해줘').\n"
    "\n"
    "제어 판단 규칙:\n"
    "5. 확실할 때만 NONE이 아닌 값을 고른다. 애매하면 NONE이다 — 잘못된 취소·초기화는\n"
    "   사용자가 쌓아온 전략을 잃게 만든다.\n"
    "6. 조건을 지우는 것(UPDATE)과 작업을 되돌리는 것(ROLLBACK)은 다르다.\n"
    "   'PER 조건 빼줘'는 UPDATE이고, 'PER 조건 지운 거 되돌려'는 ROLLBACK이다.\n"
    "7. 전체를 버리는 것(RESTART)과 일부를 바꾸는 것(UPDATE)은 다르다.\n"
    "   '유니버스만 다시 정하자'는 UPDATE이고, '전략 다 지우고 새로 하자'는 RESTART다.\n"
    "8. 되돌리기만 원하는 것(ROLLBACK)과 정정(CORRECT)은 다르다. 판단 기준은\n"
    "   **올바른 지시가 함께 있는가**다. '아까 바꾼 거 취소해'는 ROLLBACK,\n"
    "   '아니 ETF로 바꾸라는 게 아니라 관련 ETF를 후보에 추가하라는 거야'는 CORRECT다.\n"
    "9. 단순히 조건을 바꾸는 것(UPDATE)과 정정(CORRECT)도 다르다. 직전 해석이\n"
    "   틀렸다고 지적하는 표현이 있어야 CORRECT다 — 그냥 '손절 -5%로 바꿔줘'는 UPDATE다.\n"
    "\n"
    "\n"
    "마지막으로, **바꾸려는 대상은 말했지만 값을 말하지 않은 경우** 그 대상을 고른다.\n"
    "값이 없으면 무엇으로 바꿀지 알 수 없어 되물어야 하기 때문이다.\n"
    "대상이 없거나 값이 함께 있으면 null이다(기본값).\n"
    "\n" + clarify_targets.prompt_target_lines() + "\n"
    "\n"
    "대상 판단 규칙:\n"
    "10. **값이 함께 있으면 null이다** — '손절 -8%로 바꿔줘'는 값이 있으니 null,\n"
    "    '손절 바꿔줘'는 값이 없으니 stop_loss다.\n"
    "11. 지우거나 빼 달라는 요청은 null이다 — 뺄 때는 값이 필요 없다('PER 조건 빼줘').\n"
    "12. 뜻을 묻는 질문·결과를 묻는 질문은 null이다('익절이 뭐야?', '왜 안 돼?').\n"
    "13. 이미 설정돼 있는지 확인하는 질문도 null이다('익절 설정돼 있어?').\n"
    "14. 구체 필드를 말했으면 필드를, 영역만 말했으면 영역을 고른다.\n"
    "    '손절 바꿔줘'는 stop_loss, '진입 신호를 바꾸고 싶어'는 entry_signal,\n"
    "    '조건을 변경할 수 있어?'처럼 영역도 없으면 condition이다.\n"
    "15. 재무 지표를 값 없이 추가·적용하겠다는 요청은 그 지표의 키를 고른다\n"
    "    ('영업이익률을 추가해 볼까?' → operating_margin).\n"
    "\n"
    "출력 형식(JSON 한 줄, 다른 말 금지):\n"
    '{"intent": "<라벨>", "stock_name": "<원문에 나온 종목명 또는 null>", '
    '"refers_to_last_stock": <직전에 다루던 종목을 \'이 종목\'처럼 가리키면 true, 아니면 false>, '
    '"workflow_effect": "<제어 값>", "clarify_target": "<대상 또는 null>"}'
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
    # 값 없이 지목된 수정 대상(닫힌 목록). 목록 밖 표기·미출력은 None으로 떨어진다 —
    # 되묻기는 부가 축이고, None이 기존 흐름(파싱으로 통과)이라 안전 방향이다.
    clarify_target: Optional[str] = None


# ── 형식 정규화 (입력이 LLM 출력이므로 결정론 코드 소관) ─────────────────────

_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
# 소형 모델이 붙이는 사고 흔적 블록. JSON 경계 추출 전에 걷어낸다.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_LABEL_SEPARATORS = re.compile(r"[\s\-]+")
# 4B 모델이 enum 값을 따옴표 없이 내놓는 형식 결함("workflow_effect": NONE — 실측
# 2026-08-03 '면역항암제 관련주 투자 전략' 6/20). 값 자리의 대문자 bare 토큰만 감싼다
# (true/false/null은 소문자라 안 걸린다).
_BARE_ENUM_VALUE = re.compile(r"(:\s*)([A-Z][A-Z0-9_]*)(?=\s*[,}\]])")


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
        try:
            parsed = json.loads(_BARE_ENUM_VALUE.sub(r'\1"\2"', match.group(0)))
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
    pending_question: Optional[str] = None,
) -> str:
    """분류 LLM에 보낼 사용자 메시지를 만든다.

    진행 중인 전략 여부를 함께 알린다 — 전략 카드가 떠 있는 상태의 짧은 발화는
    그 전략을 다듬는 요청일 확률이 높다는 맥락을 LLM이 쓸 수 있게 한다(원문 정규식으로
    '수정 요청'을 판별하던 레거시 규칙의 계약 준수 대체물)."""
    parts = []
    if active_strategy:
        parts.append("[진행 중인 전략] 있음")
    if pending_question and pending_question.strip():
        parts.append(f"[답을 기다리는 질문]\n{pending_question.strip()}")
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
    pending_question: Optional[str] = None,
) -> Optional[IntentInterpretation]:
    """원문을 LLM에 넘겨 제한된 구조화 출력으로 해석한다.

    반환 None = 해석 실패(실패 보고). 정규식으로 원문을 재해석하는 폴백은 두지 않는다
    (계약 § 8-1 "폴백은 자연어 재해석이 아니라 실패 보고"). LLM 호출 예외는 그대로
    올려 호출부가 연결 오류(503)와 구분할 수 있게 한다."""
    raw = llm(
        SYSTEM_PROMPT,
        build_user_message(query, history, active_strategy, pending_question),
    )
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
            clarify_target=clarify_targets.normalize_clarify_target(
                payload.get("clarify_target")
            ),
        )
    except ValidationError:
        return None
