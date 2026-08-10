"""
Query Intent 분류기.

기본(contract) 레인 — CLAUDE.md 자연어 해석 구조 원칙 준수:

    원문 → LLM 의미 해석(interpreter) → 제한된 구조화 출력
         → 형식 정규화 → Schema 검증 → Domain 정책(라벨 → 정형 응답)

원문에는 정규식을 걸지 않는다. 종목 정본 매핑도 원문 스캔이 아니라 LLM이 뽑은
짧은 문자열을 registry에 넘겨 수행한다. 해석 실패는 UNKNOWN 실패 보고로 끝나며,
정규식이 재해석자로 나서는 폴백은 없다(계약 § 8-1).

--- 아래 `_classify_deterministic` / `_classify_with_llm`과 그 정규식들은 레거시다 ---
INTENT_CLASSIFIER_MODE=legacy 롤백 경로에서만 실행된다. 원문을 패턴 매칭해 의도·지표·
업종을 추출하므로 계약 위반 상태이며, 보존만 하고 기본 경로로 되돌리지 않는다.
새 판정 규칙은 여기 추가하지 말고 interpreter.SYSTEM_PROMPT와 도메인 정책에 넣는다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from engine.console_logging import console_logger
from stock_analysis.symbol_resolver import StockRef, find_in_text, resolve_by_symbol

from . import interpreter, platform_defaults, stock_facts, stock_lists
from .config import classifier_mode
from .schemas import (
    ChatTurn,
    DetectedSymbol,
    IntentResult,
    QueryIntent,
    WorkflowEffect,
    WorkflowStatus,
)
from .scope import (
    LIVE_TRADING_REPLY,
    METRIC_NUM_GAP,
    ONBOARDING_REPLY,
    OFFTOPIC_REFUSAL,
    PERSONAL_ADVICE_REPLY,
    UNSUPPORTED_FEATURE_REPLY,
    greeting_reply,
    has_finance_cue,
    is_greeting_only,
    is_live_trading_request,
    is_misconception_assertion,
    is_offtopic,
    is_onboarding_help_request,
    is_personal_advice_request,
    is_stock_pick_request,
    is_strategy_pick_request,
    is_unsupported_feature_request,
    STRATEGY_PICK_REPLY,
    stock_pick_reply,
    stock_question_redirect,
)

# 분류 판정 경로를 콘솔에 상시 노출한다 — 어떤 결정 규칙이 잡았는지/LLM 폴백이 무엇을
# 뱉었는지/안전망이 걸렸는지가 안 보이면, 정상 요청이 OFF_TOPIC 거절로 새도 원인을 추적할
# 수 없다(2026-07-30 '원자력 업종만 테스트 하고 싶어' 거절 제보).
logger = console_logger(__name__, "INTENT")

LLMFn = Callable[[str, str], str]  # (system_prompt, user_msg) -> raw text

# '5게'·'120게'처럼 숫자 뒤 '게'는 종목 수 단위 '개'의 흔한 오타다(파서 _compact와 동일 규칙).
# 분류 전에 보정해 "종목은 5게" 같은 전략 수정 입력이 OFF_TOPIC으로 새는 것을 막는다.
# 게로 시작하는 단어(게임·게시)는 건드리지 않도록 문장 끝/조사/공백 앞에서만 바꾼다.
_COUNT_TYPO_RE = re.compile(r"(\d)\s*게(?=$|[\s은는이가을를로도만씩요])")

# 지표명의 흔한 구어·발음 표기(파서 _compact와 동일 규칙 유지). '맥디'가 종목명으로,
# '알에스아이'가 ai_model로 오인되던 실측 사고(레드팀 QA 16-4/16-6) 보정.
_INDICATOR_TYPO_SUBS = (
    (re.compile(r"알에스아이", re.IGNORECASE), "RSI"),
    (re.compile(r"맥디|엠에이씨디", re.IGNORECASE), "MACD"),
)


def _correct_count_typo(text: str) -> str:
    text = _COUNT_TYPO_RE.sub(r"\1개", text or "")
    for pattern, repl in _INDICATOR_TYPO_SUBS:
        text = pattern.sub(repl, text)
    return text

# 전략 설계를 가리키는 강한 신호. 이게 있으면 종목명이 섞여 있어도 STRATEGY_ADVICE.
_STRATEGY_KEYWORDS = re.compile(
    r"전략|백테스트|back\s*test|유니버스|리밸런|포트폴리오\s*구성|매매\s*규칙|"
    r"진입\s*조건|청산\s*조건|손절|익절|트레일링|스크리닝|종목\s*선정|분산\s*투자|"
    r"리스크\s*관리|최적화|워크포워드",
    re.IGNORECASE,
)

# 종목명과 함께 쓰인 '테스트'는 그 종목을 백테스트하려는 요청이다(FR-STR-068 —
# "삼성전자 단일 종목만 테스트 해보자"). 단독 '테스트'는 잡담일 수 있어 종목명이
# 특정된 경우로 한정한다 — LLM 폴백이 STOCK_ANALYSIS로 오판해 매수·매도 판단
# 거절 안내로 새는 것을 결정 규칙이 막는다.
_TEST_CUE = re.compile(r"테스트", re.IGNORECASE)

# 테마/업종 '관련 투자' 언급("ess 관련 투자"·"2차전지 관련주"·"원자로 테마주") — 전략
# 동사가 없어도 투자 아이디어 제시이므로 전략 설계로 라우팅한다(빌더 시드 → 섹터/용어
# 그라운딩 체인 FR-STR-069/070 관통). LLM 일반답변으로 새면 낯선 용어(ESS)를 아는 척
# 환각 정의하는 사고 실측(2026-07-24 스크린샷: ESS를 '에너지 효율성·저탄소'로 오답).
_THEME_INVEST_CUE = re.compile(
    r"관련\s*(?:주식|주|투자|종목|산업|테마)|테마\s*(?:주|투자)", re.IGNORECASE
)

# 펀더멘털/지표 스크리닝은 이 플랫폼 전략의 핵심 카테고리다 — 특정 종목이 아니라
# '조건에 맞는 종목 바스켓'을 고르는 전략 설계 신호다(phrasing 긴 꼬리가 아니라
# 카테고리 단위 신호이므로 결정적으로 처리, feedback_nl_parser_hybrid 부합).
#   · 지표+숫자 필터: "PBR 1 이하", "PER 10", "ROE 15 이상"
#   · 가치/배당/규모 스크리닝 + 바스켓 명사: "저평가 종목", "고배당주", "우량주"
#   · 비교 필터 + 종목: "~이하인 종목", "거래량 ~이상 종목"
# 지표명과 숫자 사이에 조사('roe를 5')·연산자가 끼어도 인식하도록 METRIC_NUM_GAP을 쓴다.
_SCREENING_SIGNAL = re.compile(
    r"(?:per|pbr|psr|roe|roa|eps|bps|배당수익률|배당률|시가총액|시총|부채비율|거래량|거래대금)"
    + METRIC_NUM_GAP + r"\d"
    r"|(?:저평가|고평가|고배당|우량|가치|성장|배당|소형|대형|중소형)\s*(?:된|인)?\s*(?:종목|주식|주)"
    r"|(?:이하|이상|미만|초과)\s*(?:인|의)?\s*종목",
    re.IGNORECASE,
)

# 기존 전략의 파라미터를 바꾸려는 '수정/조정' 명령. 종목 추천이 아니라 전략 설계(수정)다.
# 예: "종목을 10개로 늘려줘", "손절 추가해줘", "보유기간 바꿔줘", "백테스트 5년으로 변경".
# 조정 동사 + 조정 대상(전략 필드/수량)이 함께 있을 때만 잡아 '추천' 요청 오인을 피한다.
_MODIFY_VERB = re.compile(
    r"늘려|늘리|줄여|줄이|바꿔|바꾸|변경|교체|높여|높이|낮춰|낮추|"
    r"추가|제거|조정|수정|고쳐|설정\s*해|로\s*해\s*줘|으로\s*해\s*줘",
    re.IGNORECASE,
)
_ADJUST_TARGET = re.compile(
    r"종목|보유|비중|손절|익절|트레일링|손익|기간|유니버스|리밸런|포트폴리오|자금|조건|"
    r"\d+\s*(?:개|종목|%|년|개월|주|일)",
    re.IGNORECASE,
)

# 개별 종목에 대한 행동/판단 질문 동사.
_STOCK_QUESTION = re.compile(
    r"사도|살까|사야|사볼|매수|들어가|들어가도|진입|팔아|팔까|팔아볼|매도|손절|"
    r"들고|보유|계속\s*가져|전망|어때|어떨까|괜찮|괜찮을까|분석|"
    r"오를까|내릴까|상승|하락|리스크|위험|목표가|적정\s*주가",
    re.IGNORECASE,
)

# 무언가를 해 달라는 요청 어미/동사(인사가 아니라 요청임을 가르는 신호).
_REQUEST_CUE = re.compile(
    r"부탁|해\s*줘|해\s*주세요|만들|짜\s*줘|골라|추천|하고\s*싶|원해|원합니다|"
    r"가자|가고\s*싶|해\s*보자|알려\s*줘|찾아|구성",
    re.IGNORECASE,
)

# 기술 지표 신호(종목명 오인 방지용 — 지표 + 매매 동사는 전략 설계다).
_INDICATOR_CUE = re.compile(
    r"rsi|macd|볼린저|이동\s*평균|이평|골든\s*크로스|데드\s*크로스|크로스오버|"
    r"스토캐스틱|cci|adx|mfi|모멘텀|신고가|돌파|과매도|과매수",
    re.IGNORECASE,
)

# 일반 투자 지식(정의형) 질문.
_DEFINITION_QUESTION = re.compile(
    r"(?:뭐야|뭔가요|무엇|뜻이|뜻은|의미가|의미는|차이가|차이는|설명해|"
    r"어떻게\s*계산|왜\s*중요|개념)",
    re.IGNORECASE,
)

# 전략을 실제로 '구성/실행'하려는 동사. 정의형 질문에 이게 섞이면 단순 지식 질문이 아니다
# ('모멘텀 전략이 뭔지 설명하고 만들어줘'는 설계 요청). 없으면 순수 정의형으로 본다.
_CONSTRUCT_VERB = re.compile(r"만들|짜\s*줘|구성|돌려\s*줘|돌려줘", re.IGNORECASE)


def is_definition_question(text: str) -> bool:
    """순수 정의형 투자 질문("PBR이 뭐야?") 여부 — 결정적 GENERAL_INVESTMENT 규칙과 동일 cue.

    전략 수정 경로로 오라우팅된 정의형 질문을 백엔드가 판별할 때 쓴다(FR-SA-002c-4).
    구성/실행 동사가 섞이면(설계 요청) 정의형으로 보지 않는다.
    """
    text = text or ""
    return bool(
        _DEFINITION_QUESTION.search(text)
        and has_finance_cue(text)
        and not _CONSTRUCT_VERB.search(text)
    )

# anaphora — 직전 종목을 가리키는 표현('이 종목', '얘', '저 주식').
_ANAPHORA = re.compile(r"이\s*종목|이\s*주식|그\s*종목|저\s*종목|얘|이거", re.IGNORECASE)

# 리스크 관리 단어(손절/익절/트레일링)는 전략 키워드이면서 동시에 개별 종목 행동 질문
# ("삼성전자 지금 손절해야 할까?")에도 흔히 등장한다. 종목명+행동 질문에서 전략 증거가
# 이 단어들뿐이면 전략 설계가 아니라 종목 분석이다 — 이를 판별하기 위한 제거용 패턴.
_RISK_ONLY_KW = re.compile(r"손절|익절|트레일링", re.IGNORECASE)

_CLASSIFIER_SYSTEM_PROMPT = (
    "너는 투자 챗봇 입력을 의도로 분류한다. "
    "STRATEGY_ADVICE(투자 전략·지표 조합·백테스트·매매 규칙, 그리고 "
    "'PBR 1 이하·PER 10 이하·저평가/고배당 종목'처럼 조건에 맞는 종목을 고르는 스크리닝), "
    "STOCK_ANALYSIS(이름이 명시된 '특정 한 종목'의 매수·매도·보유·전망·리스크·분석), "
    "STOCK_PICK(특정 종목명도 정량 조건도 없이 '무엇을 사야 하나·종목 추천·살 만한 종목·돈 될 종목'처럼 "
    "매수 대상을 골라 달라는 열린 추천 요청), "
    "STRATEGY_PICK(구체적인 지표·전략 유형 없이 '어떤 전략이 좋을까·전략 추천해줘·무슨 전략을 써야 해'처럼 "
    "어떤 전략이 우수한지 골라 달라는 열린 추천 요청 — 특정 유형(모멘텀·RSI 등)이 명시되면 STRATEGY_ADVICE다), "
    "ONBOARDING(구체적인 전략·지표·종목 없이 '어떻게 시작하지·뭐부터 해야 해·처음인데 어떻게 써'처럼 "
    "무엇을 해야 할지 막막해 도움을 청하는 요청), "
    "UNSUPPORTED_FEATURE(뉴스·공시·SNS 여론·애널리스트 리포트처럼 플랫폼에 없는 데이터 분석을 "
    "근거로 종목을 고르거나 전략을 만들어 달라는 요청 — 단, RSI·이동평균·PER 같은 지원 지표가 "
    "함께 있으면 STRATEGY_ADVICE다), "
    "GENERAL_INVESTMENT(일반 투자 지식·용어 정의), "
    "GREETING(인사·짧은 사회적 표현), "
    "OFF_TOPIC(투자와 무관한 잡담·사적 대화·일반 상식·날씨·건강·프로그래밍·정치 등 역할 밖 질문), "
    "UNKNOWN(투자 관련이지만 위 어디에도 안 맞아 분류 불가). "
    "특정 종목명이 없는 '조건/필터로 종목 고르기'는 STOCK_ANALYSIS가 아니라 STRATEGY_ADVICE다. "
    "투자와 직접 관련이 없으면 STRATEGY_ADVICE나 UNKNOWN으로 추측하지 말고 OFF_TOPIC으로 분류하라. "
    "단, 입력에는 오타·맞춤법 오류가 섞일 수 있으니 글자 표면이 아니라 의미로 판단하라. "
    "종목 수·기간·비율 등 전략 파라미터를 바꾸는 표현(예: '종목은 5게'='종목 5개로')은 "
    "오타가 있어도 전략 수정이므로 STRATEGY_ADVICE이며 절대 OFF_TOPIC이 아니다. "
    "입력 앞에 [대화 맥락]이 함께 주어질 수 있다. 맥락은 참고용일 뿐 분류 대상은 [최신 입력] 하나다. "
    "'다른 예는 없어?', '더 알려줘', '그럼 어떻게 해?'처럼 직전 챗봇 답변에 이어지는 후속 질문은 "
    "직전 주제의 연속으로 분류하라 — 직전 주제가 투자라면 OFF_TOPIC이 아니다. "
    "직전 답변이 보여준 예시·설명을 더 요청하는 후속 질문은 GENERAL_INVESTMENT다. "
    '반드시 {"intent": "..."} JSON 한 줄로만 답하라.'
)

# LLM 폴백에 넘기는 대화 맥락 상한 — 후속 질문 판단에는 최근 몇 턴이면 충분하고,
# 작은 분류 모델의 입력이 길어질수록 오분류가 늘어난다.
_HISTORY_MAX_TURNS = 6
_HISTORY_TEXT_MAX = 240


def format_history_context(history: Optional[list[ChatTurn]]) -> str:
    """대화 맥락을 LLM 프롬프트용 텍스트로 만든다(없으면 빈 문자열).
    intent 분류 폴백과 /query/general 답변이 공유한다."""
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

    # 0-a) 백테스트 설정 기본값 질문("슬리피지는 몇 %가 기본이지?") → LLM이 값을 지어내지
    #      않도록 실제 코드 기본값으로 결정적 답변한다. '수수료'가 전략 키워드와 섞인
    #      문장("백테스트 수수료 기본값은?")이 아래 규칙 1(STRATEGY_ADVICE)로 새기 전에 잡는다.
    if platform_defaults.is_default_question(text):
        return IntentResult(
            intent=QueryIntent.GENERAL_INVESTMENT,
            suggested_reply=platform_defaults.reply(text),
            confidence=0.95,
            reason="백테스트 설정 기본값 질문 감지 — 실제 기본값으로 답변",
        )

    # 0-a-1) [규제 안전] 나이·자산·직업 기반 맞춤 추천 요청("40대인데 나한테 맞는 전략?") →
    #        LLM 일반답변이 맞춤 조언을 생성하기 전에 결정적으로 가로채, 맞춤 추천 불가를
    #        안내하고 조건은 직접 고르는 빌더로 유도한다(STRATEGY_PICK과 동일한 흐름).
    if is_personal_advice_request(text):
        return IntentResult(
            intent=QueryIntent.STRATEGY_PICK,
            suggested_reply=PERSONAL_ADVICE_REPLY,
            confidence=0.92,
            reason="개인 맞춤형 조언 요청 감지 — 맞춤 추천 불가 안내 + 빌더 유도",
        )

    refs = find_in_text(text)
    has_strategy_kw = bool(_STRATEGY_KEYWORDS.search(text))
    has_screening = bool(_SCREENING_SIGNAL.search(text))
    has_modify = bool(_MODIFY_VERB.search(text) and _ADJUST_TARGET.search(text))
    has_stock_q = bool(_STOCK_QUESTION.search(text))
    has_def_q = bool(_DEFINITION_QUESTION.search(text))

    # 0-a-2) 오개념 단정/확인 발화("PER이 높을수록 싸다는 거지?") → 파싱으로 흐르면 교정
    #        기회 없이 조건 되묻기만 나간다. 지식 답변 경로로 보내 먼저 바로잡는다.
    #        구성/수정 동사가 있으면 설계 요청이므로 가로채지 않는다.
    if (
        has_finance_cue(text)
        and is_misconception_assertion(text)
        and not has_modify
        and not _CONSTRUCT_VERB.search(text)
    ):
        return IntentResult(
            intent=QueryIntent.GENERAL_INVESTMENT,
            confidence=0.85,
            reason="금융 오개념 단정/확인 발화 감지 — 지식 답변으로 교정",
        )

    # 0-a-3) [기능 범위] 실계좌 자동매매·대리 투자 요청 → 미제공 안내(가상계좌 모의투자 안내).
    if is_live_trading_request(text) and not has_screening:
        return IntentResult(
            intent=QueryIntent.UNSUPPORTED_FEATURE,
            symbols=_to_detected(refs),
            suggested_reply=LIVE_TRADING_REPLY,
            confidence=0.9,
            reason="실전 매매/대리 투자 요청 감지 — 미제공 안내",
        )

    # 순수 정의형 질문('리밸런싱이 뭔가요?')은 '리밸런' 같은 전략 키워드가 있어도 설계 요청이
    #    아니라 지식 질문이다. 수정/구성 동사가 없을 때만 전략 키워드 게이트를 건너뛰어
    #    아래 정의형 규칙(GENERAL_INVESTMENT)이 처리하게 한다.
    pure_definition = has_def_q and not has_modify and not _CONSTRUCT_VERB.search(text)

    # [예외] 종목명 + 행동/판단 질문인데 전략 증거가 리스크 단어(손절/익절/트레일링)뿐이면
    # "삼성전자 지금 손절해야 할까?" 같은 개별 종목 질문이다 — 전략 설계로 가로채지 않고
    # 아래 규칙 2(STOCK_ANALYSIS)로 흘려보낸다. 수정 명령·스크리닝·구성 동사가 있으면 제외.
    risk_word_only_strategy_kw = (
        has_strategy_kw
        and not has_screening
        and not has_modify
        and not _STRATEGY_KEYWORDS.search(_RISK_ONLY_KW.sub("", text))
    )
    stock_question_overrides_strategy = bool(
        refs and has_stock_q and risk_word_only_strategy_kw and not _CONSTRUCT_VERB.search(text)
    )

    # 0-c) [기능 범위] 뉴스·공시 등 제공하지 않는 재료 분석을 근거로 한 요청("최근 뉴스가
    #      좋은 종목을 사는 전략") → '전략' 키워드로 STRATEGY_ADVICE에 새서 빈 전략 파싱 →
    #      빌더 자동 전환으로 이어지지 않도록 먼저 잡아 미제공 안내로 답한다.
    #      순수 정의형 질문("공시가 뭐야?")은 지식 질문, 종목명(또는 anaphora)+행동 질문
    #      ("삼성전자 악재 떴는데 팔까?")은 종목 질문이므로 아래 규칙에 맡긴다.
    if (
        is_unsupported_feature_request(text)
        and not pure_definition
        and not (has_stock_q and (refs or _ANAPHORA.search(text)))
    ):
        return IntentResult(
            intent=QueryIntent.UNSUPPORTED_FEATURE,
            symbols=_to_detected(refs),
            suggested_reply=UNSUPPORTED_FEATURE_REPLY,
            confidence=0.9,
            reason="미제공 기능(뉴스·공시 분석) 기반 요청 감지",
        )

    # 0-b) [규제 안전] "어떤 전략이 좋을까?"처럼 어떤 전략이 우수한지 골라/추천해 달라는 열린 요청 →
    #      전략 우열을 판단·추천하지 않고, 함께 만들어 백테스트하는 전략 빌더로 유도한다. '전략'이
    #      들어 있어 아래 STRATEGY_ADVICE로 새기 전에 먼저 잡는다. 구체 지표·유형·수정·종목명이
    #      섞였으면(=설계 요청) is_strategy_pick_request/게이트에서 제외돼 일반 흐름으로 넘어간다.
    if (
        is_strategy_pick_request(text)
        and not refs
        and not has_screening
        and not has_modify
        and not pure_definition
    ):
        return IntentResult(
            intent=QueryIntent.STRATEGY_PICK,
            suggested_reply=STRATEGY_PICK_REPLY,
            confidence=0.9,
            reason="열린 전략 추천 요청 감지 — 전략 빌더로 유도",
        )

    # 1) 전략 키워드/스크리닝 조건/전략 수정 명령이 있으면 전략 설계로 본다(종목명이 섞여 있어도).
    #    "종목을 10개로 늘려줘"처럼 기존 전략을 다듬는 요청을 '종목 추천(STOCK_PICK)'으로
    #    오분류해 빌더로 새로 진입하는 일을 막는다.
    has_stock_test = bool(refs and _TEST_CUE.search(text))
    # 테마 관련 투자 언급 — 열린 추천 요청("AI 관련주 추천해 주세요")은 기존 STOCK_PICK
    # 리다이렉트(1-b)에 맡기고, 종목명+행동 질문("삼성전자 관련주 살까?")도 가로채지 않는다.
    has_theme_invest = bool(
        _THEME_INVEST_CUE.search(text)
        and not (refs and has_stock_q)
        and not is_stock_pick_request(text)
    )
    if (
        (has_strategy_kw or has_screening or has_modify or has_stock_test or has_theme_invest)
        and not pure_definition
        and not stock_question_overrides_strategy
    ):
        reason = (
            "전략 설계 키워드 감지" if has_strategy_kw
            else "종목 스크리닝 조건 감지" if has_screening
            else "전략 수정/조정 명령 감지" if has_modify
            else "종목 지정 테스트 요청 감지" if has_stock_test
            else "테마 관련 투자 언급 감지 — 전략 설계로 전환"
        )
        return IntentResult(
            intent=QueryIntent.STRATEGY_ADVICE,
            symbols=_to_detected(refs),
            confidence=0.9,
            reason=reason,
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

    # 1-c) 종목명 없이 지표 + 매매 동사("MACD 데드크로스에 팔아줘")는 전략 설계다 — LLM
    #      폴백이 지표명을 종목으로 오인해 STOCK_ANALYSIS 안내로 새던 사고(레드팀 QA 16-4) 방지.
    if not refs and has_stock_q and _INDICATOR_CUE.search(text):
        return IntentResult(
            intent=QueryIntent.STRATEGY_ADVICE,
            confidence=0.85,
            reason="지표 + 매매 동사 감지 — 전략 설계",
        )

    # 2) [규제 안전] 특정 종목 + 행동/판단 질문 → 매수·매도 판단을 제공하지 않고
    #    그 종목에서 출발한 전략 설계로 대화를 전환한다(suggested_reply).
    if refs and has_stock_q:
        return IntentResult(
            intent=QueryIntent.STOCK_ANALYSIS,
            symbols=_to_detected(refs),
            suggested_reply=stock_question_redirect(
                refs[0].name, refs[0].market, refs[0].sector, overseas=refs[0].overseas
            ),
            confidence=0.92,
            reason="종목명 + 매수/매도/전망 질문 감지 — 전략 설계로 전환",
        )

    # 2-b) anaphora('이 종목 팔까?') + 직전 종목 컨텍스트 → 동일하게 전략 설계로 전환.
    if has_stock_q and _ANAPHORA.search(text):
        carried = resolve_by_symbol(last_symbol) if last_symbol else None
        return IntentResult(
            intent=QueryIntent.STOCK_ANALYSIS,
            symbols=_to_detected([carried]) if carried else [],
            suggested_reply=stock_question_redirect(
                carried.name if carried else None,
                carried.market if carried else None,
                carried.sector if carried else None,
            ),
            confidence=0.7 if carried else 0.55,
            reason="직전 종목 참조('이 종목') + 행동 질문 — 전략 설계로 전환",
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


def _classify_with_llm(
    query: str, llm: LLMFn, history: Optional[list[ChatTurn]] = None
) -> Optional[IntentResult]:
    # 대화 맥락이 있으면 함께 넘긴다 — "다른 예는 없어?" 같은 후속 질문은 문장만 보면
    # 투자 신호가 없어 OFF_TOPIC으로 오판되지만, 직전 턴이 있으면 주제의 연속으로 판단된다.
    context = format_history_context(history)
    user_msg = f"[대화 맥락]\n{context}\n[최신 입력]\n{query}" if context else query
    try:
        raw = llm(_CLASSIFIER_SYSTEM_PROMPT, user_msg)
    except Exception:
        logger.exception("intent LLM 폴백 실패")
        return None
    match = re.search(
        r'"intent"\s*:\s*"(STRATEGY_ADVICE|STOCK_ANALYSIS|STOCK_PICK|STRATEGY_PICK|ONBOARDING|UNSUPPORTED_FEATURE|GENERAL_INVESTMENT|GREETING|OFF_TOPIC|UNKNOWN)"',
        raw or "",
    )
    if not match:
        logger.info("  LLM 폴백 파싱 실패 raw=%r", (raw or "")[:200])
        return None
    intent = QueryIntent(match.group(1))
    logger.info("  LLM 폴백 → %s (history=%d턴, raw=%r)",
                intent.value, len(history or []), (raw or "").strip()[:120])
    # [안전망] LLM이 OFF_TOPIC으로 분류해도 입력에 금융 신호(PER/PBR/ROE/CAGR 등)가 있으면
    # 거절하지 않는다. 'roe를 5% 이상으로'처럼 짧은 전략 수정은 문맥이 적어 작은 모델이 자주
    # 역할 밖으로 오판하는데, 금융 용어가 있으면 전략 흐름으로 넘겨 파싱이 처리하게 한다.
    if intent == QueryIntent.OFF_TOPIC and has_finance_cue(query):
        logger.info("  안전망: 금융 신호 있음 → OFF_TOPIC을 STRATEGY_ADVICE로 강등")
        intent = QueryIntent.STRATEGY_ADVICE
    elif intent == QueryIntent.OFF_TOPIC:
        logger.info("  안전망 미적용(finance_cue=False) → OFF_TOPIC 유지, 정형 거절 응답")
    # [안전망] LLM이 GREETING으로 분류했지만 인사가 아니라 요청 어미("엄청 안전한 걸로
    # 부탁해")면 인사말로 요청을 무시하게 된다 — 막연한 요청으로 보고 빌더 유도(ONBOARDING)로
    # 강등한다(레드팀 QA 15-2). 순수 인사("어이~ 반가워이")는 요청 cue가 없어 그대로 둔다.
    if (
        intent == QueryIntent.GREETING
        and not is_greeting_only(query)
        and _REQUEST_CUE.search(query)
    ):
        intent = QueryIntent.ONBOARDING
    suggested_reply = None
    if intent == QueryIntent.GREETING:
        suggested_reply = greeting_reply(query)
    elif intent == QueryIntent.OFF_TOPIC:
        suggested_reply = OFFTOPIC_REFUSAL
    elif intent == QueryIntent.STOCK_PICK:
        suggested_reply = stock_pick_reply(query)
    elif intent == QueryIntent.STRATEGY_PICK:
        suggested_reply = STRATEGY_PICK_REPLY
    elif intent == QueryIntent.ONBOARDING:
        suggested_reply = ONBOARDING_REPLY
    elif intent == QueryIntent.UNSUPPORTED_FEATURE:
        suggested_reply = UNSUPPORTED_FEATURE_REPLY
    refs = find_in_text(query) if intent == QueryIntent.STOCK_ANALYSIS else []
    if intent == QueryIntent.STOCK_ANALYSIS:
        suggested_reply = stock_question_redirect(
            refs[0].name if refs else None,
            refs[0].market if refs else None,
            refs[0].sector if refs else None,
            overseas=refs[0].overseas if refs else False,
        )
    return IntentResult(
        intent=intent,
        symbols=_to_detected(refs),
        suggested_reply=suggested_reply,
        confidence=0.6,
        reason="LLM 폴백 분류",
        deterministic=False,
    )


# ── Domain 정책 (입력이 LLM 출력이므로 결정론 코드 소관) ──────────────────────
# 라벨 → 정형 응답 매핑. 원문을 다시 읽지 않는다 — LLM이 정한 의미만 소비한다.
# [규제 안전] 추천·맞춤 조언·미제공 기능 안내 문구는 LLM에 맡기지 않고 여기서 확정한다.
_LABEL_REPLIES: dict[QueryIntent, str] = {
    QueryIntent.OFF_TOPIC: OFFTOPIC_REFUSAL,
    QueryIntent.STRATEGY_PICK: STRATEGY_PICK_REPLY,
    QueryIntent.PERSONAL_ADVICE: PERSONAL_ADVICE_REPLY,
    QueryIntent.LIVE_TRADING: LIVE_TRADING_REPLY,
    QueryIntent.ONBOARDING: ONBOARDING_REPLY,
    QueryIntent.UNSUPPORTED_FEATURE: UNSUPPORTED_FEATURE_REPLY,
}


# 워크플로 제어 효과 → 정형 안내 문구. 라벨을 키로 정해진 문구를 고르는 결정론 매핑이다
# (원문을 다시 읽지 않는다). RESUME은 안내 없이 이어서 진행하므로 문구가 없다.
_EFFECT_REPLIES: dict[WorkflowEffect, str] = {
    WorkflowEffect.PAUSE: (
        "전략 작성을 잠시 멈췄습니다. 지금까지 정한 조건은 그대로 유지돼요. "
        "이어서 하시려면 말씀해 주세요."
    ),
    WorkflowEffect.CANCEL: (
        "전략 작성을 취소했습니다. 새로 만들고 싶으실 때 언제든 말씀해 주세요."
    ),
    WorkflowEffect.RESTART: (
        "지금까지의 전략을 지우고 처음부터 시작할게요. 어떤 조건으로 만들어 볼까요?"
    ),
    # ROLLBACK·CORRECT는 여기 없다 — 안내 문구가 **결과**에 달려 있고(어느 변경을
    # 되돌렸는지·되물어야 하는지), 그 결과는 변경 이력을 들고 있는 프론트가 복원을
    # 마친 뒤에야 정해진다(설계 스펙 § 19, /strategy/rollback/resolve).
    # CORRECT는 되돌린 자리에 재해석 결과가 그대로 답이 된다 — 정정을 사과하거나
    # 설명하지 않는다(설계 스펙 § 20 "잘못 해석한 내용을 변명하지 마라").
}

# 제어 효과를 인정하지 않는 라벨 — 규제·범위 게이트라 정형 안내가 반드시 나가야 한다.
# 여기에 제어를 허용하면 "그만할래" 한마디로 맞춤 조언·실계좌 매매 안내가 삼켜진다.
# 제어가 유효한 라벨은 전략 대화 맥락인 STRATEGY_ADVICE·GENERAL_INVESTMENT·UNKNOWN뿐이다.
#
# STRATEGY_STATUS·RESULT_EXPLAIN도 여기 든다. 이유는 규제가 아니라 **읽기 전용**이라서다 —
# 상태를 묻기만 하는 발화가 상태를 바꾸면 안 된다. '아까 손절 몇 퍼센트로 했었지?'가
# ROLLBACK으로 새면 묻기만 한 사용자의 전략이 되감긴다.
_EFFECT_BLOCKED_INTENTS = frozenset({
    QueryIntent.STOCK_ANALYSIS,
    QueryIntent.STOCK_PICK,
    QueryIntent.STRATEGY_PICK,
    QueryIntent.ONBOARDING,
    QueryIntent.PERSONAL_ADVICE,
    QueryIntent.LIVE_TRADING,
    QueryIntent.UNSUPPORTED_FEATURE,
    QueryIntent.GREETING,
    QueryIntent.OFF_TOPIC,
    QueryIntent.STRATEGY_STATUS,
    QueryIntent.RESULT_EXPLAIN,
})

# 진행 중인 전략이 있어야 성립하는 효과 — 없으면 되돌리거나 멈출 대상이 없다.
# CORRECT도 여기 든다: 정정은 직전 해석을 겨냥하므로 되돌릴 State가 있어야 한다
# (없으면 그냥 새 요청이므로 NONE으로 강등돼 일반 파스로 흐른다).
_REQUIRES_ACTIVE_STRATEGY = frozenset({
    WorkflowEffect.PAUSE,
    WorkflowEffect.CANCEL,
    WorkflowEffect.RESTART,
    WorkflowEffect.ROLLBACK,
    WorkflowEffect.CORRECT,
})

# 효과 → 이 턴 이후의 워크플로 상태. ROLLBACK은 실행되지 않으므로 상태를 바꾸지 않는다.
_EFFECT_TRANSITIONS: dict[WorkflowEffect, WorkflowStatus] = {
    WorkflowEffect.UPDATE: WorkflowStatus.ACTIVE,
    # 정정은 되돌린 자리에 새 해석을 적용하므로 작업이 계속된다.
    WorkflowEffect.CORRECT: WorkflowStatus.ACTIVE,
    WorkflowEffect.PAUSE: WorkflowStatus.PAUSED,
    WorkflowEffect.RESUME: WorkflowStatus.ACTIVE,
    WorkflowEffect.CANCEL: WorkflowStatus.CANCELLED,
    WorkflowEffect.RESTART: WorkflowStatus.IDLE,
}


def _resolve_workflow(
    interp: interpreter.IntentInterpretation,
    active_strategy: bool,
    workflow_status: WorkflowStatus,
) -> tuple[WorkflowEffect, WorkflowStatus]:
    """LLM이 제안한 제어 효과를 결정론으로 검증하고 다음 상태를 계산한다.

    LLM은 효과를 제안만 하고, 성립 여부는 코드가 정한다(스펙 §18 — LLM이 State를 직접
    바꾸지 않는다). 성립하지 않는 효과는 거부가 아니라 NONE 강등이다 — 제어가 사라져도
    기존 대화 흐름은 그대로 이어진다."""
    effect = interp.workflow_effect
    if interp.intent in _EFFECT_BLOCKED_INTENTS:
        # 규제·범위 게이트가 제어보다 우선한다.
        return WorkflowEffect.NONE, workflow_status
    if effect in _REQUIRES_ACTIVE_STRATEGY and not active_strategy:
        return WorkflowEffect.NONE, workflow_status
    if effect is WorkflowEffect.RESUME and workflow_status is not WorkflowStatus.PAUSED:
        # 멈춘 적이 없으면 이어갈 것도 없다.
        return WorkflowEffect.NONE, workflow_status
    return effect, _EFFECT_TRANSITIONS.get(effect, workflow_status)


def _resolve_clarify_target(
    interp: interpreter.IntentInterpretation, active_strategy: bool
) -> Optional[str]:
    """LLM이 지목한 되묻기 대상을 결정론으로 검증한다(성립하지 않으면 None 강등).

    _resolve_workflow와 같은 계약이다 — LLM은 대상을 제안만 하고 성립 여부는 코드가 정한다.
    None 강등은 거부가 아니라 기존 흐름(전략 파싱으로 통과) 유지이므로 안전 방향이다."""
    if interp.clarify_target is None:
        return None
    if interp.intent in _EFFECT_BLOCKED_INTENTS:
        # 규제·범위 게이트 안내가 되묻기로 삼켜지지 않게 한다(제어 축과 같은 이유).
        return None
    if not active_strategy:
        # 진행 중인 전략이 없으면 바꿀 대상도 없다 — 첫 발화는 파싱으로 흐른다.
        return None
    return interp.clarify_target


def _resolve_stock_fact(
    interp: interpreter.IntentInterpretation, ref: Optional[StockRef]
) -> tuple[Optional[str], Optional[str]]:
    """지표 조회가 성립하는지 결정론으로 판정하고, 성립하면 사실 문장까지 만든다.

    [규제 안전] 이 축이 여는 것은 **결정론 조회**뿐이다 — 답변 문장은 stock_facts가
    데이터에서 읽어 정해진 틀에 채우고, LLM은 개입하지 않는다. 그래서 축이 오판돼도
    최악은 '숫자를 보여준다'이지 '사도 된다고 말한다'가 아니다.

    성립 조건 셋을 모두 만족해야 한다:
      ① 라벨이 STOCK_ANALYSIS — 특정 한 종목에 대한 발화
      ② LLM이 닫힌 목록의 지표를 골랐다(목록 밖은 normalize에서 이미 None)
      ③ 종목 정본 매핑에 성공했고 국내 종목이다 — 해외 종목은 보유 데이터가 없다

    하나라도 어긋나면 (None, None)이고 기존 거절 안내가 그대로 나간다(안전 방향).
    """
    metric = interp.fact_metric
    if metric is None or interp.intent != QueryIntent.STOCK_ANALYSIS:
        return None, None
    if ref is None or ref.overseas:
        return None, None

    reading = stock_facts.read_metric(ref.symbol, metric)
    if reading is None:
        # 지표는 알겠는데 그 종목 값이 없다 — 지어내지 않고 없다고 밝힌다.
        return metric, stock_facts.metric_unavailable(ref.name, metric)
    return metric, stock_facts.metric_answer(ref.name, reading)


# 소속 목록 조회가 성립할 수 있는 라벨 — 목록 질문은 STOCK_PICK(열린 추천 오분류),
# GENERAL_INVESTMENT(일반 지식), UNKNOWN('코스피200에 몇 종목?' — 라벨이 마땅치 않아
# 분류 불가로 떨어진 구성 질문, 2026-08-11 프로브 실측)으로 떨어진다. 나머지 라벨에서는
# 축을 무시한다 — 특히 STRATEGY_ADVICE에서 열면 스크리닝 조건이 목록 표시로 새고,
# 규제 거절 라벨(PERSONAL_ADVICE 등)에서 열면 정형 안내가 목록으로 우회된다.
# UNKNOWN을 허용해도 안전한 이유: 성립하려면 추출 표기가 정본(시장 사전·섹터 사전·KG)에
# 매핑돼야 하고, 답은 결정론 목록뿐이다 — 오판의 최악은 '소속 목록 표시'다.
_LISTING_INTENTS = frozenset({
    QueryIntent.STOCK_PICK,
    QueryIntent.GENERAL_INVESTMENT,
    QueryIntent.UNKNOWN,
})


def _resolve_stock_listing(
    interp: interpreter.IntentInterpretation,
) -> tuple[Optional[str], Optional[str]]:
    """업종·테마 소속 목록 조회의 성립을 결정론으로 판정한다(FR-SA-002c-11).

    _resolve_stock_fact와 같은 계약 — LLM은 범위 표기를 제안만 하고, 정본 성립
    (섹터 사전·지식그래프 매핑)은 코드가 정한다. 미해석이면 (None, None)으로 기존
    안내(열린 추천 전환 등)가 그대로 나간다 — 목록을 지어내지 않는다.
    """
    term = interp.list_scope
    if term is None or interp.intent not in _LISTING_INTENTS:
        return None, None
    listing = stock_lists.resolve_listing(term)
    if listing is None:
        return None, None
    return listing.scope, stock_lists.listing_answer(
        listing, count_only=interp.list_count_only
    )


def _resolve_stock(
    interp: interpreter.IntentInterpretation, last_symbol: Optional[str]
) -> Optional[StockRef]:
    """LLM이 뽑은 종목 표기를 registry 정본으로 매핑한다.

    입력은 원문이 아니라 LLM 출력(짧은 문자열)이다 — 지식 조회를 원문에서 수행하지
    말라는 금지 사항 5의 규정 방식 그대로다. 지시어('이 종목')는 LLM이
    refers_to_last_stock으로 알려주고, 실제 종목은 직전 컨텍스트에서 가져온다."""
    if interp.stock_name:
        refs = find_in_text(interp.stock_name)
        if refs:
            return refs[0]
    if interp.refers_to_last_stock and last_symbol:
        return resolve_by_symbol(last_symbol)
    return None


# 종목 정본 매핑이 의미 있는 라벨만 registry를 조회한다(불필요한 조회 방지).
_STOCK_BEARING_INTENTS = frozenset({QueryIntent.STOCK_ANALYSIS, QueryIntent.STRATEGY_ADVICE})


def _apply_domain_policy(
    interp: interpreter.IntentInterpretation,
    last_symbol: Optional[str],
    query: str,
    active_strategy: bool = False,
    workflow_status: WorkflowStatus = WorkflowStatus.IDLE,
) -> IntentResult:
    """구조화 출력에 도메인 정책을 적용해 최종 IntentResult를 만든다.

    query는 여러 문안 중 하나를 고르는 해시 씨앗으로만 쓴다(같은 입력에 같은 문구 —
    캐시 친화). 원문에서 의미를 읽지 않으므로 해석이 아니다."""
    intent = interp.intent
    effect, next_status = _resolve_workflow(interp, active_strategy, workflow_status)
    clarify_target = _resolve_clarify_target(interp, active_strategy)
    ref = _resolve_stock(interp, last_symbol) if intent in _STOCK_BEARING_INTENTS else None
    fact_metric, fact_answer = _resolve_stock_fact(interp, ref)
    list_scope, list_answer = _resolve_stock_listing(interp)
    if fact_answer is not None:
        suggested_reply = fact_answer
    elif list_answer is not None:
        suggested_reply = list_answer
    elif intent == QueryIntent.STOCK_ANALYSIS:
        suggested_reply = stock_question_redirect(
            ref.name if ref else None,
            ref.market if ref else None,
            ref.sector if ref else None,
            overseas=ref.overseas if ref else False,
        )
    elif intent == QueryIntent.GREETING:
        suggested_reply = greeting_reply(query)
    elif intent == QueryIntent.STOCK_PICK:
        suggested_reply = stock_pick_reply(query)
    else:
        suggested_reply = _LABEL_REPLIES.get(intent)
    # 워크플로 제어가 성립하면 그 안내가 라벨 안내를 대신한다 — 제어는 라벨과 직교하지만
    # 사용자에게 보일 문장은 하나뿐이고, 제어 결과를 알리는 쪽이 우선이다. 규제 게이트
    # 라벨은 _resolve_workflow가 이미 NONE으로 강등했으므로 여기 도달하지 않는다.
    if effect in _EFFECT_REPLIES:
        suggested_reply = _EFFECT_REPLIES[effect]
    return IntentResult(
        intent=intent,
        symbols=_to_detected([ref] if ref else []),
        suggested_reply=suggested_reply,
        confidence=0.8,
        reason="LLM 의미 해석",
        deterministic=False,
        workflow_effect=effect,
        workflow_status=next_status,
        clarify_target=clarify_target,
        fact_metric=fact_metric,
        list_scope=list_scope,
    )


def classify(
    query: str,
    *,
    last_symbol: Optional[str] = None,
    llm: Optional[LLMFn] = None,
    history: Optional[list[ChatTurn]] = None,
    active_strategy: bool = False,
    workflow_status: WorkflowStatus = WorkflowStatus.IDLE,
    pending_question: Optional[str] = None,
) -> IntentResult:
    """입력을 QueryIntent로 분류한다.

    계약 레인(기본): 원문 → LLM 의미 해석 → 구조화 출력 → 형식 정규화 → 도메인 정책.
    원문에 정규식을 걸지 않는다. 해석 실패는 UNKNOWN 실패 보고로 끝나며, 정규식이
    재해석자로 나서는 폴백은 없다(계약 § 8-1).

    workflow_status는 직전 턴의 워크플로 상태다(무상태 에코). 해석에 실패해도 이 값을
    잃지 않는다 — 분류 실패가 사용자의 '멈춤' 상태를 조용히 해제하면 안 된다.

    롤백(INTENT_CLASSIFIER_MODE=legacy): 아래 원문 정규식 레인. 계약 위반 상태로
    보존만 하며 기본 경로가 아니다. 워크플로 제어는 지원하지 않고 상태만 통과시킨다."""
    if classifier_mode() == "legacy":
        legacy = _classify_legacy(query, last_symbol, llm, history)
        return legacy.model_copy(update={"workflow_status": workflow_status})

    logger.info("query=%r active_strategy=%s workflow_status=%s pending_question=%r",
                query, active_strategy, workflow_status.value, pending_question)
    if llm is None:
        return _log_result(IntentResult(
            intent=QueryIntent.UNKNOWN,
            confidence=0.0,
            reason="LLM 미가용 — 해석 실패 보고",
            deterministic=False,
            workflow_status=workflow_status,
            interpretation_failed=True,
        ))
    try:
        interp = interpreter.interpret(
            query, llm, history, active_strategy, pending_question,
        )
    except Exception:
        logger.exception("의도 해석 LLM 호출 실패")
        raise
    if interp is None:
        return _log_result(IntentResult(
            intent=QueryIntent.UNKNOWN,
            confidence=0.0,
            reason="LLM 구조화 출력 해석 실패",
            deterministic=False,
            workflow_status=workflow_status,
            interpretation_failed=True,
        ))
    logger.info("  LLM 해석 → %s stock_name=%r refers_to_last=%s effect=%s",
                interp.intent.value, interp.stock_name, interp.refers_to_last_stock,
                interp.workflow_effect.value)
    return _log_result(_apply_domain_policy(
        interp, last_symbol, query, active_strategy, workflow_status,
    ))


def _classify_legacy(
    query: str,
    last_symbol: Optional[str],
    llm: Optional[LLMFn],
    history: Optional[list[ChatTurn]],
) -> IntentResult:
    """[레거시·롤백 전용] 원문 정규식 우선 레인 — 자연어 해석 계약 위반 상태.

    INTENT_CLASSIFIER_MODE=legacy 로만 진입한다. 삭제하지 않고 보존하는 것은
    롤백 경로를 남기기 위함이며, 기본 경로로 되돌리지 않는다."""
    query = _correct_count_typo(query)
    logger.info("[legacy] query=%r", query)
    deterministic = _classify_deterministic(query, last_symbol)
    if deterministic is not None:
        return _log_result(deterministic)

    if llm is not None:
        llm_result = _classify_with_llm(query, llm, history)
        if llm_result is not None:
            return _log_result(llm_result)

    return _log_result(IntentResult(
        intent=QueryIntent.UNKNOWN,
        symbols=_to_detected(find_in_text(query or "")),
        confidence=0.3,
        reason="결정적 규칙·LLM 모두 분류 실패",
        deterministic=False,
    ))


def _log_result(result: IntentResult) -> IntentResult:
    """최종 판정을 한 줄로 남긴다. canned=정형 응답을 붙여 보냈다는 뜻 —
    프론트가 이 문구를 그대로 띄우고 전략 파싱(인터프리터)에는 도달하지 않는다."""
    logger.info(
        "→ intent=%s deterministic=%s reason=%s canned=%s effect=%s status=%s",
        result.intent.value, result.deterministic, result.reason,
        bool(result.suggested_reply),
        result.workflow_effect.value, result.workflow_status.value,
    )
    return result
