"""
Query Intent 분류기 — 결정적 우선 하이브리드.

원칙(feedback_nl_parser_hybrid): 핵심은 결정적 규칙으로 처리하고, 애매한 긴 꼬리만
LLM에 위임한다. phrasing마다 regex를 늘리지 않는다.

분류 우선순위:
  1. STRATEGY_ADVICE  — '전략/백테스트/유니버스/리밸런싱' 등 전략 설계 키워드
  2. STOCK_ANALYSIS   — 특정 종목명/코드 + 매수·매도·보유·전망·리스크 질문.
     [규제 안전] 판단·추천을 제공하지 않고 suggested_reply로 전략 설계 전환을 안내한다.
  3. GENERAL_INVESTMENT — 'X가 뭐야/뜻/설명/차이' 정의형 질문
  4. (애매) LLM 폴백 → 실패 시 UNKNOWN
"""

from __future__ import annotations

import json
import logging
import re
from typing import Callable, Optional

from stock_analysis.symbol_resolver import StockRef, find_in_text, resolve_by_symbol

from . import platform_defaults
from .schemas import ChatTurn, DetectedSymbol, IntentResult, QueryIntent
from .scope import (
    METRIC_NUM_GAP,
    ONBOARDING_REPLY,
    OFFTOPIC_REFUSAL,
    UNSUPPORTED_FEATURE_REPLY,
    greeting_reply,
    has_finance_cue,
    is_greeting_only,
    is_offtopic,
    is_onboarding_help_request,
    is_stock_pick_request,
    is_strategy_pick_request,
    is_unsupported_feature_request,
    STRATEGY_PICK_REPLY,
    stock_pick_reply,
    stock_question_redirect,
)

logger = logging.getLogger(__name__)

LLMFn = Callable[[str, str], str]  # (system_prompt, user_msg) -> raw text

# '5게'·'120게'처럼 숫자 뒤 '게'는 종목 수 단위 '개'의 흔한 오타다(파서 _compact와 동일 규칙).
# 분류 전에 보정해 "종목은 5게" 같은 전략 수정 입력이 OFF_TOPIC으로 새는 것을 막는다.
# 게로 시작하는 단어(게임·게시)는 건드리지 않도록 문장 끝/조사/공백 앞에서만 바꾼다.
_COUNT_TYPO_RE = re.compile(r"(\d)\s*게(?=$|[\s은는이가을를로도만씩요])")


def _correct_count_typo(text: str) -> str:
    return _COUNT_TYPO_RE.sub(r"\1개", text or "")

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

    refs = find_in_text(text)
    has_strategy_kw = bool(_STRATEGY_KEYWORDS.search(text))
    has_screening = bool(_SCREENING_SIGNAL.search(text))
    has_modify = bool(_MODIFY_VERB.search(text) and _ADJUST_TARGET.search(text))
    has_stock_q = bool(_STOCK_QUESTION.search(text))
    has_def_q = bool(_DEFINITION_QUESTION.search(text))

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
    if (
        (has_strategy_kw or has_screening or has_modify or has_stock_test)
        and not pure_definition
        and not stock_question_overrides_strategy
    ):
        reason = (
            "전략 설계 키워드 감지" if has_strategy_kw
            else "종목 스크리닝 조건 감지" if has_screening
            else "전략 수정/조정 명령 감지" if has_modify
            else "종목 지정 테스트 요청 감지"
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

    # 2) [규제 안전] 특정 종목 + 행동/판단 질문 → 매수·매도 판단을 제공하지 않고
    #    그 종목에서 출발한 전략 설계로 대화를 전환한다(suggested_reply).
    if refs and has_stock_q:
        return IntentResult(
            intent=QueryIntent.STOCK_ANALYSIS,
            symbols=_to_detected(refs),
            suggested_reply=stock_question_redirect(refs[0].name, refs[0].market, refs[0].sector),
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
        return None
    intent = QueryIntent(match.group(1))
    # [안전망] LLM이 OFF_TOPIC으로 분류해도 입력에 금융 신호(PER/PBR/ROE/CAGR 등)가 있으면
    # 거절하지 않는다. 'roe를 5% 이상으로'처럼 짧은 전략 수정은 문맥이 적어 작은 모델이 자주
    # 역할 밖으로 오판하는데, 금융 용어가 있으면 전략 흐름으로 넘겨 파싱이 처리하게 한다.
    if intent == QueryIntent.OFF_TOPIC and has_finance_cue(query):
        intent = QueryIntent.STRATEGY_ADVICE
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
        )
    return IntentResult(
        intent=intent,
        symbols=_to_detected(refs),
        suggested_reply=suggested_reply,
        confidence=0.6,
        reason="LLM 폴백 분류",
        deterministic=False,
    )


def classify(
    query: str,
    *,
    last_symbol: Optional[str] = None,
    llm: Optional[LLMFn] = None,
    history: Optional[list[ChatTurn]] = None,
) -> IntentResult:
    """입력을 QueryIntent로 분류한다. 결정적 규칙 우선, 애매하면 llm 폴백.
    history(최근 대화 턴)는 LLM 폴백에서만 쓴다 — 결정적 규칙은 현재 입력만 본다."""
    query = _correct_count_typo(query)
    deterministic = _classify_deterministic(query, last_symbol)
    if deterministic is not None:
        return deterministic

    if llm is not None:
        llm_result = _classify_with_llm(query, llm, history)
        if llm_result is not None:
            return llm_result

    return IntentResult(
        intent=QueryIntent.UNKNOWN,
        symbols=_to_detected(find_in_text(query or "")),
        confidence=0.3,
        reason="결정적 규칙·LLM 모두 분류 실패",
        deterministic=False,
    )
