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
    "대신 투자 전략, 백테스트, 종목 분석과 관련된 질문은 도와드릴 수 있습니다."
)

# 투자 전략/백테스트 관련 신호. 하나라도 있으면 역할 밖(off-topic)으로 보지 않는다(오탐 방지).
_FINANCE_CUE = re.compile(
    r"전략|백테스트|backtest|매수|매도|손절|익절|보유\s*기간|종목\s*수|포트폴리오|"
    r"수익률?|손실|리스크|위험|변동성|낙폭|mdd|샤프|cagr|승률|손익비|과최적화|"
    r"rsi|macd|볼린저|이동\s*평균|이평|골든\s*크로스|데드\s*크로스|모멘텀|돌파|스토캐스틱|cci|adx|"
    r"per|pbr|roe|부채비율|시가총액|배당|재무|"
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


def has_finance_cue(text: str) -> bool:
    """투자/전략 관련 신호가 하나라도 있는지(있으면 역할 안 주제)."""
    return bool(_FINANCE_CUE.search(text))
