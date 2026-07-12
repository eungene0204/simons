"""코칭/챗봇 역할 범위 판정 — 인사·역할 밖(off-topic) 감지와 정해진 응답 문구.

intent.classifier(입력 게이트)와 api.coach_routes(코치 가드)가 공유한다.
[feedback_nl_parser_hybrid] 원칙대로 명확한 인사/역할 밖만 결정적으로 잡고,
애매한 긴 꼬리는 가로채지 않아 일반 흐름(전략 파싱·LLM)으로 넘긴다.
"""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Optional

# 인사 토큰. 입력 전체가 이것들로만 이뤄졌을 때만 '인사'로 본다.
_GREETING_RE = re.compile(
    r"안녕(?:하세요|하십니까|하셨어요|하신가요)?|반(?:가워요?|갑습니다|갑네요)|"
    r"하이|헬로|hello|hi|좋은\s*(?:아침|하루|저녁)|굿\s*모닝|good\s*morning|ㅎㅇ|방가+",
    re.IGNORECASE,
)
GREETING_REPLIES = (
    "안녕하세요. 어떤 투자 아이디어를 가지고 계신가요?",
    "안녕하세요. 오늘은 어떤 전략을 연구해 볼까요?",
    "반갑습니다. 백테스트해 보고 싶은 전략이 있으신가요?",
)
OFFTOPIC_REFUSAL = (
    "저는 투자 전략 및 투자 분석 전용 모델입니다. "
    "현재 질문에는 도움을 드릴 수 없습니다. "
    "대신 투자 전략, 백테스트와 관련된 질문은 도와드릴 수 있습니다."
)
# [규제 안전] 특정 종목 매수·매도·보유 추천 금지. "무엇을 사야 하나"라는 열린 추천 요청은
# 거절만 하지 않고, 바로 만들어볼 수 있는 전략 예시를 보여주며 "어떤 조건에서 투자할 것인가"를
# 정의·검증하는 전략 구성 대화로 자연스럽게 이끈다(예시는 추천이 아니라 출발점 안내).
# 프론트는 infoText를 whitespace-pre-line으로 렌더하므로 줄바꿈/불릿이 그대로 보인다.
STOCK_PICK_REDIRECT = (
    "특정 종목을 추천하거나 지금 무엇을 사야 하는지는 안내하지 않지만, "
    "어떤 조건에서 사고팔지를 전략으로 정의해 백테스트해볼 수 있어요.\n\n"
    "예를 들어 이렇게 시작해볼 수 있어요:\n"
    "• RSI가 30 이하로 떨어지면 매수하고 70 이상에서 파는 '과매도 반등' 전략\n"
    "• 20일 이동평균이 60일 이동평균을 위로 뚫는 골든크로스에서 매수하는 추세 전략\n"
    "• PBR은 낮고 ROE는 높은 저평가 우량주를 고르는 가치 전략\n\n"
    "이 중 끌리는 아이디어가 있으신가요? 평소 관심 있던 매매 방식이 있다면 말씀해 주세요 "
    "— 손절·익절이나 보유 기간 같은 조건도 함께 더해 백테스트로 확인해 드릴게요.",

    "무엇을 사야 할지 알려드릴순 없지만, 투자 아이디어를 전략으로 만들어 함께 "
    "백테스트해볼 수 있어요.\n\n"
    "예를 들면 이런 전략을 만들 수 있어요:\n"
    "• 최근 3개월 수익률이 가장 높은 상위 종목을 매수하는 모멘텀 전략\n"
    "• 주가가 박스권 상단(전고점)을 돌파할 때 매수하는 돌파 전략\n"
    "• 거래량이 평소보다 급증한 종목을 포착하는 전략\n\n"
    "관심 가는 방식이 있으면 알려주세요. 어떤 시장(코스피·코스닥 등)을 대상으로 할지도 함께 정해 "
    "바로 백테스트해 볼 수 있어요.",

    "무엇을 사야 할지 알려드릴순 없지만, 투자 아이디어를 전략으로 만들어 함께 백테스트해볼 수 있어요.\n\n"
    "예를 들어 이렇게 출발할 수 있어요:\n"
    "• 'RSI 30 이하 매수 / 70 이상 매도' 같은 지표 기반 전략\n"
    "• '단기 이동평균이 장기 이동평균을 상향 돌파하면 매수'하는 추세 전략\n"
    "• 'PER·PBR이 낮은 저평가 종목을 고르는' 스크리닝 전략\n\n"
    "어떤 시장이나 투자 스타일에 관심이 있으신가요? 아이디어를 들려주시면 전략으로 만들어 검증해 드릴게요.",
)

# [규제 안전] 특정 종목의 매수·매도·보유 판단 질문("삼성전자 사도 될까?")에는 판단·추천을
# 제공하지 않고, 그 종목에서 출발한 아이디어를 '조건 기반 전략' 설계로 전환해 안내한다.
# 예시는 엔진이 실제 실행할 수 있는 개념(대형주 유니버스·모멘텀 상위 K·가치 스크리닝·RSI)만
# 쓴다 — 섹터/업종 전략은 파서 미지원 개념이라 제안하지 않는다(막다른 길 방지).
_STOCK_REDIRECT_EXAMPLE_LARGE_CAP = (
    "• 시가총액 상위 대형주(코스피200) 중 최근 3개월 수익률 상위 5종목을 매수하는 모멘텀 전략"
)
_STOCK_REDIRECT_EXAMPLE_KOSDAQ = (
    "• 코스닥 종목 중 최근 3개월 수익률 상위 5종목을 매수하는 모멘텀 전략"
)
_STOCK_REDIRECT_EXAMPLES_COMMON = (
    "• PBR은 낮고 ROE는 높은 저평가 우량주를 고르는 가치 전략\n"
    "• RSI가 30 이하로 떨어지면 매수하고 70 이상에서 파는 과매도 반등 전략"
)


def _subject_particle(word: str) -> str:
    """주격 조사(이/가)를 마지막 글자의 받침 유무로 고른다. 한글이 아니면 '이(가)'."""
    last = (word or "")[-1:]
    if not last or not ("가" <= last <= "힣"):
        return "이(가)"
    return "이" if (ord(last) - ord("가")) % 28 else "가"


def stock_question_redirect(
    name: Optional[str] = None,
    market: Optional[str] = None,
    sector: Optional[str] = None,
) -> str:
    """특정 종목 매수·매도 질문에 대한 '추천 불가 안내 + 전략 전환' 문구를 만든다.

    name이 있으면 그 종목을 출발점으로 삼는 문장으로 만든다. sector가 있으면(엔진이
    섹터 유니버스를 지원하므로) '그 종목이 속한 업종 전략'을 첫 예시로, 없으면 market에
    맞춘 시장 예시(KOSDAQ→코스닥, 그 외→코스피200 대형주)를 첫 예시로 쓴다."""
    if name:
        lead = (
            f"{name}에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요.\n\n"
            f"대신 {name}에 관심이 있으시다면, 그 아이디어를 '어떤 조건에서 사고팔 것인가'라는 "
            "전략으로 만들어 백테스트해볼 수 있어요.\n\n"
            "예를 들어 이렇게 시작해볼 수 있어요:\n"
        )
    else:
        lead = (
            "특정 종목에 대한 매수·매도 판단이나 종목 추천은 제공하지 않아요.\n\n"
            "대신 관심 있는 종목에서 출발한 아이디어를 '어떤 조건에서 사고팔 것인가'라는 "
            "전략으로 만들어 백테스트해볼 수 있어요.\n\n"
            "예를 들어 이렇게 시작해볼 수 있어요:\n"
        )
    if sector and name:
        subject = f"{name}{_subject_particle(name)}"
        first_example = (
            f"• {subject} 속한 {sector} 업종 종목만 대상으로, "
            "최근 3개월 수익률 상위 5종목을 매수하는 전략"
        )
    elif (market or "").upper() == "KOSDAQ":
        first_example = _STOCK_REDIRECT_EXAMPLE_KOSDAQ
    else:
        first_example = _STOCK_REDIRECT_EXAMPLE_LARGE_CAP
    return (
        f"{lead}{first_example}\n{_STOCK_REDIRECT_EXAMPLES_COMMON}\n\n"
        "관심 가는 방식이 있으면 말씀해 주세요 — 바로 전략으로 만들어 백테스트해 드릴게요."
    )


# [온보딩] "어떻게 시작하지?"처럼 무엇을 해야 할지 모르는 막연한 도움 요청 신호.
# 이런 입력은 거절하거나 빈 전략 카드를 띄우지 말고 전략 빌더(단계별 가이드)로 이끈다.
# 특정 지표·종목·조건이 섞이면(=구체 질문) 여기서 잡지 않고 기존 흐름에 맡긴다(has_finance_cue 게이트).
_ONBOARDING_RE = re.compile(
    r"어떻게\s*(?:시작|해야|하는|하면|만들|진행|쓰|사용|이용)|"
    r"어디(?:서|부터|에서)\s*(?:부터\s*)?(?:시작|해야|하면)|"
    r"뭐(?:부터|를|가)?\s*(?:해야|하면|시작|할까)|뭘\s*(?:해야|하면|할까|할\s*수)|"
    r"무엇(?:을|부터)?\s*(?:해야|하면|할\s*수)|"
    r"처음(?:인데|이라|이에요|이야|입니다)|초보|입문|"
    r"잘\s*모르겠|어떻게\s*해야\s*할지|어디서부터|"
    r"사용법|이용\s*방법|어떻게\s*시작|도와줘|도와주세요|가이드|안내\s*해",
    re.IGNORECASE,
)
ONBOARDING_REPLY = (
    "처음이시거나 어디서부터 시작할지 막막하시면 제가 단계별로 함께 전략을 만들어 드릴게요. "
    "몇 가지만 골라 주시면 바로 백테스트까지 이어집니다."
)

# 투자 전략/백테스트 관련 신호. 하나라도 있으면 역할 밖(off-topic)으로 보지 않는다(오탐 방지).
_FINANCE_CUE = re.compile(
    r"전략|백테스트|backtest|매수|매도|손절|익절|보유\s*기간|종목\s*수|포트폴리오|"
    r"수익률?|손실|리스크|위험|변동성|낙폭|mdd|샤프|cagr|승률|손익비|과최적화|"
    r"rsi|macd|볼린저|이동\s*평균|이평|골든\s*크로스|데드\s*크로스|모멘텀|돌파|스토캐스틱|cci|adx|"
    r"per|pbr|roe|부채비율|시가총액|배당|재무|"
    r"가상\s*계좌|모의\s*투자|모의\s*계좌|"
    r"코스피|코스닥|kospi|kosdaq|유니버스|리밸런|트레일링|진입|청산|신호|지표|분산\s*투자|거래량|거래대금",
    re.IGNORECASE,
)
# 명백히 역할 밖인 주제 신호(날씨·프로그래밍·정치·건강·잡담 등).
_OFFTOPIC_CUE = re.compile(
    r"날씨|기온|미세먼지|"
    r"파이썬|python|자바스크립트|javascript|코드\s*(?:짜|작성|만들|좀)|프로그래밍|버그\s*고|함수\s*작성|"
    r"수학\s*문제|미적분|방정식|인수분해|"
    r"대통령|선거|정당|정치|"
    r"조선\s*시대|세계\s*대전|역사\s*(?:에\s*대해|를\s*알려|설명해)|"
    r"감기|두통|복통|병원|다이어트|건강\s*(?:상담|관리)|운동\s*추천|"
    r"사랑해|심심|농담|노래\s*불러|시\s*써\s*줘|"
    r"점심\s*뭐|저녁\s*뭐|영화\s*추천|게임\s*추천",
    re.IGNORECASE,
)


# 매수 대상을 직접 골라/추천해 달라는 '열린 추천' 신호.
_PICK_INTENT = re.compile(
    r"추천|사야|살까|살\s*만한|사면|뭐(?:를|가)?\s*사|뭘\s*사|골라\s*주|골라\s*줘",
    re.IGNORECASE,
)
# 특정 종목명 없이 '아무 종목'을 가리키는 일반 대상어(바스켓 명사·의문 대명사).
# 저평가·고배당·우량주 같은 '조건 카테고리'는 스크리닝 전략 설계이므로 여기 넣지 않는다(_PICK_EXCLUDE).
_PICK_TARGET = re.compile(r"종목|주식|관련주|테마주|대장주|뭐|뭘|무엇", re.IGNORECASE)
# "수익이 잘 날 종목" 처럼 매수 동사 없이 '돈 될 종목'을 골라 달라는 요청.
_PROFIT_PICK = re.compile(r"수익.{0,8}(?:나는|날|좋은|많은|잘\s*나).{0,4}(?:종목|주식)", re.IGNORECASE)
# 정량 스크리닝(PER/PBR 등 + 숫자), 밸류/배당/규모 카테고리 바스켓, 전략 설계 신호가 있으면
# '열린 추천'이 아니라 조건 기반 전략 설계다 — 가로채지 않고 일반 전략 흐름으로 넘긴다.
# 지표명과 숫자 사이에 조사('roe를 5')·연산자('roe >= 5')·'이상/이하'가 끼어도 스크리닝으로
# 인식하기 위한 공백·조사·연산자 갭. classifier._SCREENING_SIGNAL과 공유한다.
METRIC_NUM_GAP = r"\s*(?:은|는|이|가|을|를|도|만|의|값)?\s*(?:[:=<>]+|이상|이하|미만|초과|보다)?\s*"
_PICK_EXCLUDE = re.compile(
    r"전략|백테스트|backtest|유니버스|리밸런|포트폴리오|손절|익절|트레일링|스크리닝|"
    r"(?:per|pbr|psr|roe|roa|배당수익률|배당률|시가총액|시총|부채비율|거래량|거래대금)"
    + METRIC_NUM_GAP + r"\d"
    r"|(?:저평가|고평가|고배당|우량|가치|성장|배당|소형|대형|중소형)\s*(?:된|인)?\s*(?:종목|주식|주)",
    re.IGNORECASE,
)


# [규제 안전] "어떤 전략이 좋을까?"처럼 어떤 전략이 우수한지 골라/추천해 달라는 '열린 전략 추천'
# 요청. 전략 우열 판단·추천은 제공하지 않지만(CLAUDE.md 규제 안전), 거절만 하지 않고 함께 전략을
# 만들어 백테스트하는 전략 빌더로 자연스럽게 이끈다. 특정 지표·유형이 명시되면(모멘텀/RSI 등)
# 이미 구체적인 설계 요청이므로 여기서 잡지 않고 일반 전략 흐름(파서·빌더)에 맡긴다.
_STRATEGY_PICK_RE = re.compile(
    r"(?:어떤|무슨|뭔|어느|무엇)\s*전략(?:이|을|은|가|들)?\s*"
    r"(?:좋|나(?:은|을)|괜찮|적합|유리|낫|추천|해야|쓰면|써야|골라|선택)|"
    r"전략(?:을|를|좀)?\s*추천|추천(?:할\s*만한|해\s*줄|해\s*주|해\s*줘|해\s*주세요|하는|해)?\s*전략|"
    r"좋은\s*전략|최고의?\s*전략|best\s*strateg",
    re.IGNORECASE,
)
# 구체적인 전략 유형/지표가 있으면 '열린 추천'이 아니라 설계 요청이다. 기존 전략을 가리키는
# 지시어('이 전략')·수정 맥락도 제외해 다듬기 흐름을 가로채지 않는다([feedback_nl_parser_hybrid]).
_STRATEGY_PICK_EXCLUDE = re.compile(
    r"모멘텀|골든\s*크로스|데드\s*크로스|macd|볼린저|이동\s*평균|이평|돌파|거래량|거래대금|"
    r"스토캐스틱|cci|adx|rsi|과매도|과매수|저평가|고평가|가치|배당|우량|성장|"
    r"per|pbr|psr|roe|roa|시가총액|시총|부채비율|"
    r"백테스트|backtest|만들|짜\s*줘|구성|돌려|"
    r"이\s*전략|그\s*전략|내\s*전략|저\s*전략|현재\s*전략|위\s*전략",
    re.IGNORECASE,
)
STRATEGY_PICK_REPLY = (
    "어떤 전략이 더 좋은지 판단하거나 추천해 드리지는 않지만, 관심 있는 아이디어를 함께 "
    "전략으로 만들어 과거 데이터로 백테스트해 볼 수 있어요. 제가 단계별로 여쭤볼 테니 "
    "골라 주시면 바로 백테스트까지 이어집니다."
)


def is_strategy_pick_request(text: str) -> bool:
    """어떤 전략이 좋은지 골라/추천해 달라는 '열린 전략 추천' 요청인지 검사한다.
    구체적인 전략 유형·지표가 섞였거나 기존 전략 수정 맥락이면 설계 요청이므로 제외한다."""
    t = text or ""
    if _STRATEGY_PICK_EXCLUDE.search(t):
        return False
    return bool(_STRATEGY_PICK_RE.search(t))


def is_greeting_only(text: str) -> bool:
    """입력 전체가 인사로만 구성됐는지(전략 질문이 섞이지 않았는지) 검사한다."""
    if not _GREETING_RE.search(text):
        return False
    residual = _GREETING_RE.sub(" ", text)
    residual = re.sub(r"[^가-힣A-Za-z0-9]", "", residual)
    return residual == ""


def greeting_reply(text: str) -> str:
    """인사 응답을 입력 기반으로 결정적으로 하나 고른다(캐시 친화)."""
    idx = int(sha256(text.encode("utf-8")).hexdigest(), 16) % len(GREETING_REPLIES)
    return GREETING_REPLIES[idx]


def is_offtopic(text: str) -> bool:
    """역할 밖 주제 신호가 있고 금융 신호는 없을 때만 True(오탐 방지)."""
    return bool(_OFFTOPIC_CUE.search(text)) and not _FINANCE_CUE.search(text)


def is_stock_pick_request(text: str) -> bool:
    """특정 종목을 골라/추천해 달라는 '열린 추천' 요청인지 검사한다.
    명확한 핵심만 결정적으로 잡고(긴 꼬리는 LLM 분류에 위임), 정량 스크리닝·전략 설계
    신호가 섞였거나 특정 종목명이 있는 경우는 호출 측에서 제외한다([feedback_nl_parser_hybrid])."""
    t = text or ""
    if _PICK_EXCLUDE.search(t):
        return False
    if _PROFIT_PICK.search(t):
        return True
    return bool(_PICK_INTENT.search(t) and _PICK_TARGET.search(t))


def stock_pick_reply(text: str) -> str:
    """열린 추천 요청에 대한 전략 전환 안내를 입력 기반으로 결정적으로 하나 고른다."""
    idx = int(sha256(text.encode("utf-8")).hexdigest(), 16) % len(STOCK_PICK_REDIRECT)
    return STOCK_PICK_REDIRECT[idx]


def has_finance_cue(text: str) -> bool:
    """투자/전략 관련 신호가 하나라도 있는지(있으면 역할 안 주제)."""
    return bool(_FINANCE_CUE.search(text))


def is_onboarding_help_request(text: str) -> bool:
    """무엇을 해야 할지 모르는 막연한 도움 요청('어떻게 시작하지?')인지 검사한다.
    구체적인 지표·종목·전략 조건(금융 신호)이 섞이면 막연한 요청이 아니므로 잡지 않는다
    — 그런 입력은 기존 전략/분석 흐름이 더 잘 처리한다([feedback_nl_parser_hybrid])."""
    t = text or ""
    if has_finance_cue(t):
        return False
    return bool(_ONBOARDING_RE.search(t))
