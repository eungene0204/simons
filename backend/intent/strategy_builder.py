"""Strategy Builder Mode — 열린 종목 추천을 전략 설계 대화로 잇는 결정적 상태 머신.

[규제 안전] "어떤 종목을 사야 하나" 같은 열린 추천(STOCK_PICK)으로 전환 안내를 보낸 뒤,
이 모듈이 사용자의 짧은 답변을 전략 필드(유니버스 → 전략유형 → 기준기간 → 보유수 →
리밸런싱)로 누적한다. 필수 필드가 채워지면 요약을 보여주고, 사용자가 확정하면 검증된
자연어 프롬프트로 합성해 기존 백테스트 파서로 넘긴다.

[feedback_nl_parser_hybrid] 핵심만 결정적 regex로 처리하고 phrasing마다 규칙을 늘리지
않는다. LLM 없이 동작한다. parser/state-transition/response-generation을 분리한다.
짧은 답·비질문 입력을 거절하지 않는다(파싱 실패 시 같은 질문을 자연스럽게 다시 한다).
"""

from __future__ import annotations

import json
import re
from typing import Callable, List, Optional, Union

from pydantic import BaseModel, Field

Universe = str  # "KOSPI" | "KOSDAQ" | "KOSPI200" | "KOSPI_KOSDAQ"
StrategyType = str  # "momentum" | "breakout" | "volume_spike" | "mean_reversion" | "custom"
RebalanceCycle = str  # "daily" | "weekly" | "monthly" | "quarterly" | "yearly"


class BuilderState(BaseModel):
    """전략 빌더 대화 상태. 프론트가 무상태 step 호출 사이에 보관·재전송한다."""

    # 단일 종목 모드(FR-STR-068b): 지정 종목 코드·표시 라벨. 설정되면 종목 선별용 질문
    # (유니버스·보유 종목 수·리밸런싱 주기)을 건너뛰고, 횡단면 전략 유형(모멘텀 랭킹·
    # 재무 스크리닝 가치주)을 기본 선택지에서 제외한다 — 질문의 중심은 "어떤 종목을
    # 살까"가 아니라 "이 종목을 언제 사고 언제 팔까"다.
    single_symbol: Optional[str] = None
    single_label: Optional[str] = None

    universe: Optional[Universe] = None
    # 업종/섹터 제한(정본 섹터명, FR-STR-066). 질문으로 묻지 않고 진입 시드에서만 채운다 —
    # 종목 질문 리다이렉트 뒤 "반도체 주도주로 전략 만들어줘"처럼 사용자가 이미 말한 업종을
    # 기억해 최종 전략의 유니버스에 반영한다. 복수 언급("반도체와 로봇")은 list 정규형
    # (FR-STR-066 ⑦)을 그대로 담는다.
    sector: Optional[Union[str, List[str]]] = None
    # 업종/테마 언급('로봇주 관련')을 봤지만 지원 목록(정본 38개)으로 매핑하지 못한 상태.
    # step이 LLM 해석을 한 번 시도하고, 그래도 안 되면 안내를 보여준 뒤 끄는 일회성 플래그
    # — 조용히 전체 시장으로 진행되는 유실 방지.
    sector_unresolved: bool = False
    # 미해결 업종 언급이 담긴 원문(LLM 해석 재료). sector_unresolved와 함께 설정·소비된다.
    sector_hint: Optional[str] = None
    # 미해결 업종을 사용자에게 한 번 되물었는지. 조용히 전체 시장으로 강등하지 않고 오타·
    # 목록 밖 표현을 정정할 기회를 준다(1회 한정 — 답에도 실패하면 안내 후 제한 없이 진행).
    sector_reask_done: bool = False
    # 미해결 힌트가 '약한 신호'(큐 없는 미지 테마어 추정 — "소부장 전략")인지. 약한 힌트는
    # 해석 실패 시 되묻기·안내 없이 조용히 해제한다 — 오탐('역발상 전략' 같은 수식어)이
    # 사용자에게 "업종을 인식하지 못했다"는 엉뚱한 되묻기로 새지 않게 하는 계약.
    sector_hint_weak: bool = False
    # ── 테마 유니버스(FR-STR-071) — 테마와 함께 언급된 것으로 학습·검증된 상장사 제한 ────
    # 그라운딩/지식그래프가 테마의 관련 상장사(related_company verified 엣지)를 알면 업종
    # 근사 대신 '이 종목들로만 vs 업종 전체'를 한 번 되묻는다. 자동 적용하지 않는다 —
    # 오늘 기준 정보라 시점 편향 고지와 함께 사용자가 고른다(객관적 관계 표시, 추천 아님).
    theme_term: Optional[str] = None
    theme_candidates: Optional[List[dict]] = None   # [{symbol, name}] 되묻기 후보
    theme_first_date: Optional[str] = None          # 뉴스 최초 보도일(시점 편향 가드)
    theme_reask_done: bool = False                  # 되묻기를 보여줬는지(답 분기 게이트)
    theme_symbols: Optional[List[str]] = None       # '이 종목들로만' 선택 시 확정 심볼
    theme_label: Optional[str] = None               # 확정 종목명 나열(요약·합성용)
    strategy_type: Optional[StrategyType] = None
    lookback_days: Optional[int] = None       # 모멘텀/돌파 기준 기간(거래일)
    lookback_label: Optional[str] = None       # 표시용 ("3개월", "60일")
    holding_count: Optional[int] = None
    rebalance_cycle: Optional[RebalanceCycle] = None
    entry_rule: Optional[str] = None           # custom 유형의 사용자 서술 진입 조건

    # ── 전략별 특화 파라미터(엔진이 실제 반영하는 값만 수집) ──────────────────────────
    # RSI: 기간·과매도·과매수. 이동평균: SMA/EMA·단기·장기. MACD/스토캐스틱: 신호 모드.
    # CCI: 기간·기준값. 거래량: 평균 기간. 가치: PBR/ROE 기준. (돌파/모멘텀은 lookback_days 재사용.)
    rsi_period: Optional[int] = None
    rsi_oversold: Optional[float] = None
    rsi_overbought: Optional[float] = None
    ma_kind: Optional[str] = None              # "sma" | "ema"
    ma_short: Optional[int] = None
    ma_long: Optional[int] = None
    macd_mode: Optional[str] = None            # "crossover" | "zero"
    cci_period: Optional[int] = None
    cci_threshold: Optional[float] = None
    volume_period: Optional[int] = None
    value_pbr: Optional[float] = None
    value_roe: Optional[float] = None

    # ── 옵션 진입 필터(추세·거래대금·RSI 결합) — 진입 신호와 AND 결합되는 게이트 ──────────
    # filters_asked=한 번 물었으면 True(옵션이라 값이 없어도 완료). 나머지는 선택된 필터값.
    filters_asked: bool = False
    trend_filter_ma: Optional[int] = None       # 이 EMA 기간 위에서만 매수(예: 200)
    liquidity_min: Optional[float] = None        # 거래대금 하한(억)
    rsi_filter: Optional[float] = None           # RSI가 이 값 이하일 때만 매수(결합)

    # 청산 조건(필수) — 마지막 단계에서 묻고, 하나 이상 인식되면 risk_done=True로 완료 처리.
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    hold_period_days: Optional[int] = None
    risk_done: bool = False

    # 연속 미인식 카운터 — 같은 질문만 말없이 반복하는 대신, 2회부터는 이해하지 못했다고
    # 알려주고 선택지를 안내한다(영어/자유 표현 무한 루프 방지, 퍼징 QA BF-15).
    miss_streak: int = 0


class StepResult(BaseModel):
    state: BuilderState
    reply: str = ""
    suggestions: List[str] = Field(default_factory=list)
    # collecting=필드 더 받음, confirmed=필수 필드 충족 → 합성 후 바로 백테스트 파싱(전략 요약 카드),
    # reset=상태 초기화 후 빌더 유지, exited=빌더 종료(일반 모드 복귀)
    status: str = "collecting"
    prompt: Optional[str] = None               # confirmed일 때 사람이 읽는 전략 설명(코치 입력·표시용)
    # confirmed일 때 직접 구성한 DSL. parsed=ParsedStrategy dump, backtest_request=엔진 요청,
    # notices=하한선 보정 안내. 프론트는 한국어 재파싱 왕복 없이 이 구조를 그대로 소비한다
    # (custom 유형만 이 필드가 없어 기존 prompt 재파싱 경로를 탄다).
    parsed: Optional[dict] = None
    backtest_request: Optional[dict] = None
    notices: List[str] = Field(default_factory=list)


# ─── 제어어(취소/처음부터/다른 질문) ─────────────────────────────────────────────

_RESTART_RE = re.compile(r"처음부터|새\s*전략|새로\s*(?:시작|만들)|다시\s*시작|리셋", re.IGNORECASE)
_EXIT_RE = re.compile(r"다른\s*질문|딴\s*거|다른\s*거\s*물어|그만\s*할게", re.IGNORECASE)
# '관둘?'은 ?가 '둘'에만 붙어 맨 '관' 한 글자에도 매칭됐다 — '관련주로 해줘'가 취소로
# 오인돼 빌더가 종료되던 버그. '관두/관둬/관둘'만 취소로 본다.
_CANCEL_RE = re.compile(r"취소|그만|관[두둬둘]|중단|됐어|그만할래", re.IGNORECASE)
# 취소어가 있어도 취소가 아닌 경우(퍼징 QA BF-01/02):
#  · 부정/전환: "취소하지 말고", "그만 물어보고 …" — 취소어 자체가 부정됨
#  · 진행 의사: "됐어, 손절 10%로 해줘"·"이제 됐어 백테스트 돌려줘" — 전략 값/진행 동사 동반
_CANCEL_NEG_RE = re.compile(r"취소하지\s*마|취소하지\s*말|취소\s*말고|그만\s*(?:물어|묻)", re.IGNORECASE)
_PROCEED_CUE_RE = re.compile(
    r"진행|계속|백테스트|돌려|손절|익절|트레일링|보유|매수|매도|%|퍼센트|프로", re.IGNORECASE
)


def detect_control(text: str) -> Optional[str]:
    """제어어를 감지한다. 우선순위: restart → exit → cancel."""
    t = text or ""
    if _RESTART_RE.search(t):
        return "restart"
    if _EXIT_RE.search(t):
        return "exit"
    if _CANCEL_RE.search(t) and not _CANCEL_NEG_RE.search(t) and not _PROCEED_CUE_RE.search(t):
        return "cancel"
    return None


# ─── 빌더 용어 질문(정의형) 처리 ─────────────────────────────────────────────────
# 빌더 모드는 분류기를 거치지 않아 "손절이 뭐야?" 같은 용어 질문이 필드 답변으로 오인돼
# 같은 질문만 반복되는 막다른 길이 됐다. 빌더가 스스로 제시하는 어휘에 한해 짧은 '객관적
# 정의'만 답하고(추천·권유 없음 — 규제 안전) 현재 질문을 이어간다. LLM 불필요.

_DEFINITION_MARKER_RE = re.compile(
    r"뭐야|뭐예요|뭔가요|뭐죠|뭐지|무엇|무슨\s*뜻|뜻이|뜻은|의미가|의미는|설명해", re.IGNORECASE
)

# (감지 패턴, 정의문). 위에서부터 첫 매치 하나만 답한다 — 구체적 용어를 앞에 둔다.
_BUILDER_GLOSSARY: tuple[tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"트레일링|최고가\s*대비", re.IGNORECASE),
     "트레일링 스탑은 보유 중 도달한 최고가 대비 정해진 비율만큼 하락하면 청산하는 방식이에요."),
    (re.compile(r"손절", re.IGNORECASE),
     "손절은 매수가 대비 정해진 비율 이상 하락하면 손실을 제한하기 위해 파는 규칙이에요."),
    (re.compile(r"익절", re.IGNORECASE),
     "익절은 매수가 대비 목표한 수익률에 도달하면 수익을 확정하며 파는 규칙이에요."),
    (re.compile(r"리밸런싱|리밸런스", re.IGNORECASE),
     "리밸런싱은 정해진 주기마다 조건에 맞춰 보유 종목을 다시 골라 교체하는 것을 말해요."),
    (re.compile(r"모멘텀", re.IGNORECASE),
     "모멘텀 전략은 최근 일정 기간 수익률이 높았던 종목을 골라 추세를 따라가는 방식이에요."),
    (re.compile(r"골든\s*크로스", re.IGNORECASE),
     "골든크로스는 단기 이동평균선이 장기 이동평균선을 아래에서 위로 뚫고 올라가는 것을 말해요."),
    (re.compile(r"macd", re.IGNORECASE),
     "MACD는 단기·장기 지수이동평균의 차이로 추세의 방향과 전환을 보는 지표예요."),
    # 빌더가 선택지로 제시하는 어휘는 전부 커버한다 — 미커버 용어의 정의 질문이 필드
    # 답변으로 오인돼 전략 유형이 조용히 확정되던 사고(퍼징 QA BF-03) 방지.
    (re.compile(r"볼린저|볼린져|bollinger", re.IGNORECASE),
     "볼린저 밴드는 이동평균 주위에 표준편차 범위의 밴드를 그려, 주가가 밴드 하단·상단에 닿는지를 보는 지표예요."),
    (re.compile(r"스토캐스틱|스토케스틱|stochastic", re.IGNORECASE),
     "스토캐스틱은 일정 기간의 고가·저가 범위에서 현재 주가의 상대적 위치(%K·%D)로 과매수·과매도를 가늠하는 지표예요."),
    (re.compile(r"cci(?![a-z])|씨씨아이", re.IGNORECASE),
     "CCI는 주가가 일정 기간 평균에서 얼마나 벗어났는지를 지수화해 과매수(+기준값)·과매도(-기준값)를 보는 지표예요."),
    (re.compile(r"rsi|과매도", re.IGNORECASE),
     "RSI는 일정 기간의 상승·하락 폭으로 과매수(70 이상)·과매도(30 이하) 상태를 가늠하는 지표예요."),
    (re.compile(r"pbr", re.IGNORECASE),
     "PBR은 주가를 주당 순자산으로 나눈 값으로, 낮을수록 자산 대비 주가가 낮게 거래된다는 뜻이에요."),
    (re.compile(r"per(?![a-z])", re.IGNORECASE),
     "PER은 주가를 주당 순이익으로 나눈 값으로, 이익 대비 주가 수준을 보는 지표예요."),
    (re.compile(r"거래량|obv", re.IGNORECASE),
     "거래량 급증 전략은 거래량 흐름(OBV)이 상승 전환한 종목을 찾는 방식이에요."),
    (re.compile(r"이동\s*평균|이평|ema|sma", re.IGNORECASE),
     "이동평균은 최근 N일 주가의 평균을 이어 그린 선으로, 추세의 방향을 보는 기본 지표예요. "
     "단순(SMA)은 균등 평균, 지수(EMA)는 최근 값에 가중치를 둔 평균이에요."),
    (re.compile(r"roe", re.IGNORECASE),
     "ROE는 자기자본 대비 순이익의 비율로, 자본을 얼마나 효율적으로 활용했는지 보는 지표예요."),
    (re.compile(r"코스피\s*200|kospi\s*200", re.IGNORECASE),
     "코스피200은 코스피 시장을 대표하는 대형 200개 종목으로 구성된 지수예요."),
    (re.compile(r"돌파|신고가", re.IGNORECASE),
     "돌파 전략은 주가가 일정 기간의 최고가(신고가)를 넘어설 때 매수하는 방식이에요."),
    (re.compile(r"보유\s*기간", re.IGNORECASE),
     "보유기간 청산은 매수 후 정해진 거래일이 지나면 파는 규칙이에요."),
)


def _glossary_answer(text: str) -> Optional[str]:
    """용어 정의 질문이면 해당 정의문을, 아니면 None을 반환한다(빌더 어휘 한정)."""
    t = text or ""
    if not _DEFINITION_MARKER_RE.search(t):
        return None
    for pattern, answer in _BUILDER_GLOSSARY:
        if pattern.search(t):
            return answer
    return None


# ─── 필드 파서(짧은 답변 → patch) ────────────────────────────────────────────────

# ETF는 시장명보다 먼저 검사한다 — "코스피 ETF"도 ETF 유니버스다(상품 유형이 우선).
_UNIV_ETF_RE = re.compile(r"etf|etn|이티에프|상장지수펀드", re.IGNORECASE)
# 코스피200은 '코스피'를 부분 문자열로 포함하므로 반드시 먼저 검사해야 KOSPI로 새지 않는다.
_UNIV_KOSPI200_RE = re.compile(r"코스피\s*200|kospi\s*200|k\s*200|대형주", re.IGNORECASE)
# 두 시장을 함께 지목하는 표현. '전체/모두'는 단일 시장 수식("코스피 전체"=코스피 전 종목)일 수
# 있으므로 여기 넣지 않고, 시장명이 하나도 없을 때만 양시장으로 해석한다(_UNIV_ALL_RE).
_UNIV_BOTH_RE = re.compile(r"둘\s*다|코스피.{0,4}코스닥|코스닥.{0,4}코스피", re.IGNORECASE)
_UNIV_ALL_RE = re.compile(r"전체|모두|모든\s*(?:시장|종목)", re.IGNORECASE)
_UNIV_KOSDAQ_RE = re.compile(r"코스닥|kosdaq", re.IGNORECASE)
_UNIV_KOSPI_RE = re.compile(r"코스피|kospi", re.IGNORECASE)

_TYPE_MOMENTUM_RE = re.compile(
    r"모멘텀|momentum|상대\s*강도|"
    r"최근\s*(?:오른|강한|상승)|많이\s*오른|가장\s*(?:많이\s*)?(?:오른|상승)|"
    r"수익률.{0,5}(?:상위|좋|높)|급등주|주도주",
    re.IGNORECASE,
)
_TYPE_GOLDEN_RE = re.compile(r"골든\s*크로스|golden\s*cross|이동\s*평균\s*교차|이평\s*교차|이동\s*평균선?\s*교차", re.IGNORECASE)
_TYPE_MACD_RE = re.compile(r"macd", re.IGNORECASE)
# 볼린저는 breakout보다 먼저 검사한다 — "볼린저 밴드 하단 돌파"의 '돌파'가 breakout으로 새지 않게.
_TYPE_BOLLINGER_RE = re.compile(r"볼린저|볼린져|볼리저|bollinger", re.IGNORECASE)
_TYPE_BREAKOUT_RE = re.compile(r"돌파|전고점|신고가|박스권|breakout", re.IGNORECASE)
_TYPE_VOLUME_RE = re.compile(r"거래량|거래\s*급증|volume", re.IGNORECASE)
_TYPE_STOCH_RE = re.compile(r"스토캐스틱|스토케스틱|stochastic|스토ca스틱", re.IGNORECASE)
_TYPE_CCI_RE = re.compile(r"\bcci\b|씨씨아이", re.IGNORECASE)
# RSI를 이름으로 지목하면 기간·과매도/과매수를 묻는 전용 rsi 흐름으로. '과매도 반등'만 mean_reversion(프리셋).
_TYPE_RSI_RE = re.compile(r"\brsi\b|알에스아이|아르에스아이", re.IGNORECASE)
_TYPE_MEANREV_RE = re.compile(r"과매도|반등|평균\s*회귀|역추세|mean\s*reversion", re.IGNORECASE)
_TYPE_VALUE_RE = re.compile(r"저평가|가치주?|우량주?|저\s*pbr|밸류|value", re.IGNORECASE)
_TYPE_CUSTOM_RE = re.compile(r"직접|아이디어|내가|제가\s*설명|설명할게|따로\s*있", re.IGNORECASE)

_MONTHS_RE = re.compile(r"(\d+)\s*개월", re.IGNORECASE)
_YEARS_RE = re.compile(r"(\d+)\s*년", re.IGNORECASE)
_WEEKS_RE = re.compile(r"(\d+)\s*주(?:일)?", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d+)\s*(?:거래일|일)", re.IGNORECASE)
# "3개월"의 "개"를 보유 수로 오인하지 않도록 "개월"은 제외한다.
_COUNT_RE = re.compile(r"(\d+)\s*(?:종목|개(?!월))", re.IGNORECASE)
_BARE_NUM_RE = re.compile(r"^\s*(\d+)\s*$")

_REBAL_RE: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("daily", re.compile(r"매일|일간|데일리|하루\s*에\s*한|하루\s*마다", re.IGNORECASE)),
    ("weekly", re.compile(r"매주|주간|주\s*1|일주일|위클리", re.IGNORECASE)),
    ("monthly", re.compile(r"매월|월간|월\s*1|한\s*달|먼슬리", re.IGNORECASE)),
    ("quarterly", re.compile(r"분기", re.IGNORECASE)),
    ("yearly", re.compile(r"매년|연간|1년\s*마다|일년\s*마다", re.IGNORECASE)),
    ("none", re.compile(
        r"안\s*함|안\s*해|안\s*바꾸|리밸런[싱]?\s*(?:안|없|불필요)|교체\s*(?:안|없)|"
        r"정기\s*(?:교체|리밸런)[^.?!]{0,4}(?:안|없)|그대로\s*(?:보유|들고)|하지\s*않",
        re.IGNORECASE,
    )),
)

# 손절/익절 키워드. 값(%)은 키워드의 앞·뒤 어느 쪽에 와도(예: "10% 손절", "손절 10%")
# 인식해야 하므로, 아래 _nearest_pct_to_keyword가 키워드에 '가장 가까운 %값'을 고른다.
# (예전엔 '숫자→키워드' 순서만 잡아 "손절 10% 익절 20%"에서 익절이 앞의 10%를 훔쳐가는
#  치명적 오귀속 버그가 있었다. 메인 NL 파서 수정(commit 2811cdd8)과 동일한 접근.)
_STOP_LOSS_KW = re.compile(r"손절|스탑\s*로스|stop\s*loss", re.IGNORECASE)
_TAKE_PROFIT_KW = re.compile(r"익절|목표\s*수익|take\s*profit", re.IGNORECASE)
# '10프로'·'10퍼센트'·'10퍼'는 %의 흔한 한국어 표기다 — 결정적으로 인식한다(퍼징 QA BF-13).
_PCT_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로|퍼)")
# 키워드 바로 뒤에 부정어가 오면('손절 없이/안 함') 그 조건은 '없음'으로 보고 값을 뽑지 않는다.
_NEG_AFTER_KW = re.compile(r"\s*(?:없|안\s|안$|말고|제외|불필요|필요\s*없|하지\s*않|빼)", re.IGNORECASE)
_SL_TP_MAX_GAP = 4  # 값-키워드 사이 허용 최대 글자 간격(연결어 제외)
# 값과 키워드 사이가 공백/조사(에·에서·로·으로)/구분자(,·)뿐이면 '바로 붙었다'(gap 0)고 본다.
# "15%에 손절"·"30%로 익절"처럼 조사가 껴도 그 값이 그 키워드의 값이 되도록.
_SL_TP_CONNECTOR = re.compile(r"^\s*(?:에서?|으?로)?\s*[,·]?\s*$")


def _sl_tp_gap(seg: str) -> int:
    """값과 키워드 사이 텍스트의 '거리'. 연결어(공백/조사/구분자)뿐이면 0, 아니면 글자 수."""
    return 0 if _SL_TP_CONNECTOR.match(seg) else len(seg)


def _parse_sl_tp(text: str) -> dict:
    """손절/익절 %값을 함께 추출한다. 값은 키워드 앞·뒤 어디에 와도 되며(순서 무관), 각 키워드는
    '자신에게 가장 가까운(간격 동률이면 앞쪽) 아직 안 쓰인 %값'을 하나씩 가져간다.
    → "손절 10% 익절 20%"에서 익절이 손절의 10%를 훔쳐가는 오귀속을 막는다.
    키워드 뒤 부정어('손절 없이')는 건너뛴다."""
    nums = [(m.start(), m.end(), float(m.group(1))) for m in _PCT_NUM_RE.finditer(text)]
    kws = []  # (pos, field)
    for m in _STOP_LOSS_KW.finditer(text):
        if not _NEG_AFTER_KW.match(text[m.end():]):
            kws.append((m.start(), m.end(), "stop_loss_pct"))
    for m in _TAKE_PROFIT_KW.finditer(text):
        if not _NEG_AFTER_KW.match(text[m.end():]):
            kws.append((m.start(), m.end(), "take_profit_pct"))
    kws.sort()  # 왼쪽 키워드부터 값을 선점(같은 값을 두 키워드가 다투지 않도록)

    patch: dict = {}
    used: set[int] = set()
    for kstart, kend, field in kws:
        if field in patch:
            continue
        best_i, best_gap = None, None
        for i, (nstart, nend, _val) in enumerate(nums):
            if i in used:
                continue
            if nend <= kstart:          # 값이 키워드 앞
                gap = _sl_tp_gap(text[nend:kstart])
            elif nstart >= kend:        # 값이 키워드 뒤
                gap = _sl_tp_gap(text[kend:nstart])
            else:
                gap = 0
            if gap > _SL_TP_MAX_GAP:
                continue
            # 간격이 더 작으면 채택. 동률이면 앞쪽 값(먼저 나온 값)을 유지("10% 손절 20%"→손절=10).
            if best_gap is None or gap < best_gap:
                best_gap, best_i = gap, i
        if best_i is not None:
            patch[field] = nums[best_i][2]
            used.add(best_i)
    return patch
_TRAILING_RE = re.compile(
    r"(?:트레일링(?:\s*스탑)?|최고가\s*대비)\s*(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로|퍼)", re.IGNORECASE
)
# 보유기간 청산("20일 보유 후 청산", "3개월 보유"). 청산 단계에서만 해석한다.
_HOLD_RISK_RE = re.compile(
    r"(\d+)\s*(개월|달|주|일|거래일)\s*(?:동안\s*)?(?:보유|후\s*청산|뒤\s*청산|지나면|이상\s*보유)",
    re.IGNORECASE,
)


def _parse_universe(text: str) -> Optional[Universe]:
    if _UNIV_ETF_RE.search(text):
        return "ETF"
    if _UNIV_BOTH_RE.search(text):
        return "KOSPI_KOSDAQ"
    if _UNIV_KOSPI200_RE.search(text):  # '코스피' 검사보다 먼저(부분 문자열 충돌 방지)
        return "KOSPI200"
    # 단일 시장 언급이 '전체/모두'보다 먼저다 — "코스피 전체"는 코스피 전 종목이지 양시장이 아니다
    # (메인 NL 파서 _extract_explicit_universe와 동일한 의미론).
    if _UNIV_KOSDAQ_RE.search(text):
        return "KOSDAQ"
    if _UNIV_KOSPI_RE.search(text):
        return "KOSPI"
    if _UNIV_ALL_RE.search(text):  # 시장명 없는 "전체"/"모두"만 양시장
        return "KOSPI_KOSDAQ"
    return None


def _parse_strategy_type(text: str) -> Optional[StrategyType]:
    if _TYPE_MOMENTUM_RE.search(text):
        return "momentum"
    if _TYPE_GOLDEN_RE.search(text):
        return "golden_cross"
    if _TYPE_MACD_RE.search(text):
        return "macd"
    if _TYPE_BOLLINGER_RE.search(text):  # breakout('돌파')보다 먼저 — '볼린저 하단 돌파' 오분류 방지
        return "bollinger"
    if _TYPE_BREAKOUT_RE.search(text):
        return "breakout"
    if _TYPE_STOCH_RE.search(text):
        return "stochastic"
    if _TYPE_CCI_RE.search(text):
        return "cci"
    if _TYPE_VOLUME_RE.search(text):
        return "volume_spike"
    if _TYPE_RSI_RE.search(text):  # 'RSI' 지목 → 전용 흐름. '과매도 반등'은 아래 mean_reversion.
        return "rsi"
    if _TYPE_MEANREV_RE.search(text):
        return "mean_reversion"
    if _TYPE_VALUE_RE.search(text):
        return "value"
    if _TYPE_CUSTOM_RE.search(text):
        return "custom"
    return None


def _parse_rebalance(text: str) -> Optional[RebalanceCycle]:
    for cycle, pat in _REBAL_RE:
        if pat.search(text):
            return cycle
    return None


def _parse_lookback(text: str) -> Optional[dict]:
    """기준 기간 접미사(년/개월/주/일)를 거래일 수와 표시 라벨로 환산한다. 없으면 None.
    우선순위: 년 > 개월 > 주 > 일 (긴 단위가 짧은 단위 패턴에 먹히지 않게).
    0 기간('0개월')은 성립하지 않으므로 채우지 않는다(BF-17)."""
    for pattern, mult, unit in ((_YEARS_RE, 252, "년"), (_MONTHS_RE, 21, "개월"),
                                (_WEEKS_RE, 5, "주일"), (_DAYS_RE, 1, "일")):
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if n <= 0:
                return None
            return {"lookback_days": n * mult, "lookback_label": f"{n}{unit}"}
    return None


def _parse_hold_days(text: str) -> Optional[int]:
    m = _HOLD_RISK_RE.search(text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit in ("개월", "달"):
        return n * 21
    if unit == "주":
        return n * 5
    return n  # 일/거래일


# 청산 조건 자체를 거부하는 표현("없음", "필요 없어", "안 할래"). 청산 조건은 필수라
# 거부를 수락하진 않지만, 같은 질문을 그대로 반복하는 대신 이유를 설명하며 되묻는다.
# ("손절 없이 익절 20%"처럼 값이 함께 있으면 _parse_risk가 값을 잡으므로 여기 오지 않는다.)
_RISK_REFUSAL_RE = re.compile(
    r"없음|없이|없어|안\s*(?:할|해|함|만들|정)|필요\s*없|생략|스킵|패스", re.IGNORECASE
)
RISK_REQUIRED_REPLY = (
    "청산 조건은 하나 이상 꼭 필요해요. 청산 기준이 없으면 백테스트에서 언제 팔지 정할 수 없거든요.\n"
    "손절·익절·트레일링 스탑·보유기간 중 하나만 골라 주세요. "
    "(예: '10% 손절', '20일 보유 후 청산')"
)

# 종목 수 지원 범위(엔진 스키마 max_positions le=100과 동일) — 밖이면 조용히 클램프하지
# 않고 채우지 않는다(step이 안내하며 되묻는다, BF-17).
_MAX_HOLDING_COUNT = 100


def _valid_count(n: int) -> bool:
    return 1 <= n <= _MAX_HOLDING_COUNT


# 파라미터 스텝별 유효 범위 안내 — 범위 밖/모순 값 입력 시 같은 질문을 말없이 반복하지
# 않고 이유를 알려준다(퍼징 QA BF-09).
_PARAM_HINTS: dict = {
    "rsi_period": "RSI 기간은 2~250 사이 정수로 말씀해 주세요.",
    "rsi_bounds": "과매도·과매수 기준은 0~100 사이이고 과매도가 과매수보다 작아야 해요. (예: 30 70)",
    "ma_periods": "단기·장기 기간은 1 이상이고 서로 달라야 해요. (예: 5 20)",
    "cci_params": "CCI 기간은 2~250, 기준값은 0보다 커야 해요. (예: 14 100)",
    "volume_period": "거래량 평균 기간은 2~250 사이로 말씀해 주세요.",
    "value_params": "저평가 기준은 'PBR 1 이하 · ROE 10 이상'처럼 0보다 큰 값으로 말씀해 주세요.",
    "lookback_days": "기간은 0보다 커야 해요. (예: 3개월, 60일)",
    "holding_count": f"보유 종목 수는 1~{_MAX_HOLDING_COUNT}개 사이로 말씀해 주세요.",
    "filters": "필터를 인식하지 못했어요. 'EMA200 위', '거래대금 100억', 'RSI 30 이하'처럼 "
               "말씀하시거나, 필터 없이 진행하려면 '없음'이라고 답해 주세요.",
}

# 저평가 기준의 방향이 빌더 고정(PBR≤·ROE≥)과 반대인 요청 안내(BF-07).
VALUE_DIRECTION_REPLY = (
    "이 빌더의 가치 전략은 'PBR ○ 이하 · ROE ○ 이상'(저평가) 기준만 지원해요. "
    "반대 방향 조건(PBR 이상·ROE 이하)이 필요하시면 전략 문장 전체를 채팅에 직접 입력해 주세요."
)

# 연속 미인식 시(2회부터) 같은 질문만 반복하지 않고 이해하지 못했음을 알린다(BF-15).
UNRECOGNIZED_HINT = (
    "죄송해요, 답변을 이해하지 못했어요. 아래 선택지에서 고르거나 예시 형식으로 입력해 주세요."
)

# 용어 정의 질문인데 빌더 글로서리에 없는 용어 — 필드 답변으로 오해석하지 않고 안내한다(BF-03/04).
GLOSSARY_FALLBACK_REPLY = (
    "그 용어 설명은 빌더에 준비돼 있지 않아요. 전략을 완성한 뒤 채팅에서 물어봐 주시면 "
    "자세히 답해 드릴게요."
)

# ETF 유니버스에서 가치 전략을 고른 경우 — 조용히 되묻지 않고 이유를 설명한다(BF-12).
ETF_VALUE_BLOCKED_REPLY = (
    "ETF 유니버스에는 개별 기업 재무지표(PBR·ROE)가 없어 저평가 가치주 전략을 적용할 수 "
    "없어요. 다른 진입 방식을 골라 주세요."
)

# 빌더 진행 중 특정 종목 지정 요청(BF-11) — 빌더는 종목 선별 전략을 만드는 흐름이라
# 조용히 무시하지 않고 단일 종목 흐름으로 가는 길을 안내한다.
_SINGLE_SWITCH_CUE_RE = re.compile(r"단일|하나만|종목만|테스트|만\s*(?:하고|할래|해|사)", re.IGNORECASE)
SINGLE_SWITCH_REPLY = (
    "지금은 조건에 맞는 종목을 고르는 전략을 만들고 있어서 특정 종목({name})을 지정할 수 "
    "없어요. {name} 한 종목만 백테스트하려면 '취소'라고 입력해 빌더를 마친 뒤 "
    "\"{name} 단일 종목 테스트해줘\"라고 말씀해 주세요. 계속 만들려면 아래 질문에 답해 주세요."
)


def _is_risk_refusal(text: str) -> bool:
    return bool(_RISK_REFUSAL_RE.search(text or ""))


# ─── 정정 표현("A 말고 B") 처리 ───────────────────────────────────────────────────
# "3개월 말고 6개월"에서 첫 매치(버려진 값 3개월)를 채택하던 오파싱(퍼징 QA BF-06) 방지.
# 정정 큐가 있으면 마지막 조각(사용자가 원하는 쪽)만 값 해석에 쓴다.

_CORRECTION_SPLIT_RE = re.compile(r"말고|말구|아니라|대신", re.IGNORECASE)
# 이미 채워진 필드를 바꾸려는 의도(정정/변경) 큐 — 유니버스·전략유형 덮어쓰기를 허용한다(BF-05).
_CHANGE_CUE_RE = re.compile(r"바꾸|바꿔|변경|교체|수정|말고|말구|아니라|대신", re.IGNORECASE)


def _correction_focus(text: str) -> str:
    """'A 말고 B'류 정정 표현에서 사용자가 원하는 쪽(마지막 조각)만 남긴다. 정정 큐가
    없거나 마지막 조각이 비어 있으면 원문 그대로."""
    parts = _CORRECTION_SPLIT_RE.split(text or "")
    if len(parts) < 2:
        return text
    tail = parts[-1].strip()
    return tail if tail else text


def _apply_risk_correction(text: str) -> str:
    """청산 단계의 정정 표현을 해석 가능한 문장으로 재구성한다.

    "손절 10% 말고 15%"처럼 키워드가 앞 조각에만 있으면, 앞 조각의 유일한 청산 키워드를
    뒤 조각에 붙여("손절 15%") 값이 올바른 필드로 귀속되게 한다. 키워드가 여럿이거나
    뒤 조각에 이미 키워드가 있으면 뒤 조각(또는 원문)을 그대로 쓴다."""
    parts = _CORRECTION_SPLIT_RE.split(text or "")
    if len(parts) < 2:
        return text
    tail = parts[-1].strip()
    if not tail:
        return text
    kw_res = (("손절", _STOP_LOSS_KW), ("익절", _TAKE_PROFIT_KW),
              ("트레일링", re.compile(r"트레일링|최고가\s*대비", re.IGNORECASE)))
    if any(pat.search(tail) for _, pat in kw_res) or _HOLD_RISK_RE.search(tail):
        return tail
    head = " ".join(parts[:-1])
    found = [label for label, pat in kw_res if pat.search(head)]
    if len(found) == 1 and _PCT_NUM_RE.search(tail):
        return f"{found[0]} {tail}"
    return tail


# 청산 비율 유효 범위 — 엔진 하한 보정(enforce_strategy_minimums)과 동일 기준을 입력
# 시점에 적용한다. 범위 밖 값이 '필수 청산' 게이트를 통과한 뒤 조용히 제거되던 사고
# (퍼징 QA BF-08) 방지: 손절·트레일링은 매수 포지션 손실 한계(0~100%), 익절은 0 초과.
_RISK_RANGE_NOTICES = {
    "stop_loss_pct": "손절 비율은 0%보다 크고 100% 이하여야 해요.",
    "trailing_stop_pct": "트레일링 스탑 비율은 0%보다 크고 100% 이하여야 해요.",
    "take_profit_pct": "익절 비율은 0%보다 커야 해요.",
}


def _risk_value_valid(field: str, value) -> bool:
    if field == "hold_period_days":
        return value > 0
    if field == "take_profit_pct":
        return value > 0
    return 0 < value <= 100  # stop_loss / trailing


def _validate_risk_patch(patch: dict) -> tuple[dict, list[str]]:
    """범위 밖 청산 값을 제거하고 안내 문구를 모은다. 유효 값이 남을 때만 risk_done."""
    valid: dict = {}
    notes: list[str] = []
    for field in RISK_FIELDS:
        value = patch.get(field)
        if value is None:
            continue
        if _risk_value_valid(field, value):
            valid[field] = value
        else:
            notes.append(_RISK_RANGE_NOTICES.get(field, "청산 값이 유효 범위를 벗어났어요."))
    if valid:
        valid["risk_done"] = True
    return valid, notes


def _parse_risk_ex(text: str) -> tuple[dict, list[str]]:
    """청산 조건 답변 파싱 + 범위 검증 → (patch, 범위 안내 문구)."""
    text = _apply_risk_correction(text)
    raw: dict = {}
    raw.update(_parse_sl_tp(text))
    tr = _TRAILING_RE.search(text)
    if tr:
        raw["trailing_stop_pct"] = float(tr.group(1))
    hold = _parse_hold_days(text)
    if hold:
        raw["hold_period_days"] = hold
    return _validate_risk_patch(raw)


def _parse_risk(text: str) -> dict:
    """청산 조건 단계의 답변을 파싱한다. 청산 조건은 필수이므로, 유효한 손절·익절·트레일링·
    보유기간을 하나 이상 인식했을 때만 risk_done=True로 완료 처리한다."""
    return _parse_risk_ex(text)[0]


# ─── 청산 조건 LLM 검증/보강(정규식 우선, 누락만 LLM으로 채움) ──────────────────────
# [feedback_nl_parser_hybrid] 자유 입력 단계는 결정론 regex로 핵심을 잡되, regex가 키워드는
# 봤지만 값을 못 뽑은 경우에만 LLM 파서로 보강한다. regex가 깨끗이 잡으면 LLM을 호출하지
# 않아(비용/지연 절감) 결정론을 유지한다.

RISK_FIELDS: tuple[str, ...] = (
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "hold_period_days",
)

# 청산 키워드별 대상 필드 — 키워드가 있는데 해당 값이 비어 있으면 LLM 검증을 트리거한다.
_RISK_KEYWORD_FIELDS: tuple[tuple["re.Pattern[str]", str], ...] = (
    (re.compile(r"손절|스탑\s*로스|stop\s*loss", re.IGNORECASE), "stop_loss_pct"),
    (re.compile(r"익절|목표\s*수익|take\s*profit", re.IGNORECASE), "take_profit_pct"),
    (re.compile(r"트레일링|최고가\s*대비", re.IGNORECASE), "trailing_stop_pct"),
    (re.compile(r"보유|후\s*청산|지나면", re.IGNORECASE), "hold_period_days"),
)

RISK_LLM_SYSTEM_PROMPT = (
    "너는 한국어 투자 전략의 '청산 조건' 문장에서 수치만 뽑아내는 파서다.\n"
    "다음 네 필드를 JSON으로만 출력한다(언급 없으면 null):\n"
    "- stop_loss_pct: 손절(손실 제한) 비율 %. 예 '15%에 손절'→15, '이십프로 손절'→20\n"
    "- take_profit_pct: 익절(목표 수익) 비율 %. 예 '30% 익절'→30\n"
    "- trailing_stop_pct: 트레일링 스탑/최고가 대비 하락 비율 %. 예 '최고가 대비 10% 하락'→10\n"
    "- hold_period_days: 보유 후 청산까지 거래일 수. '3개월'→63, '20일'→20\n"
    "설명·코드블록 없이 JSON 객체만 출력한다. "
    '예: {"stop_loss_pct": 15, "take_profit_pct": 30, "trailing_stop_pct": null, "hold_period_days": null}'
)


def _risk_needs_llm(text: str, regex_patch: dict) -> bool:
    """정규식이 청산 키워드는 봤으나 그 값을 못 뽑은 경우 True(=LLM 보강 필요)."""
    for pat, field in _RISK_KEYWORD_FIELDS:
        if pat.search(text) and regex_patch.get(field) is None:
            return True
    return False


def _parse_llm_risk(raw: str) -> dict:
    """LLM이 반환한 JSON에서 청산 필드를 안전하게 추출한다(잘못된 출력은 무시)."""
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    for field in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
        v = data.get(field)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
            out[field] = float(v)
    h = data.get("hold_period_days")
    if isinstance(h, (int, float)) and not isinstance(h, bool) and h > 0:
        out["hold_period_days"] = int(h)
    return out


def llm_extract_risk(text: str, chat: Callable[..., str]) -> dict:
    """LLM 파서로 청산 조건을 추출한다. chat은 (system, user, *, max_tokens)->str."""
    raw = chat(RISK_LLM_SYSTEM_PROMPT, text, max_tokens=120)
    return _parse_llm_risk(raw)


def _sector_llm_prompt() -> str:
    """지원 업종 전체 목록을 담은 섹터 매핑 프롬프트(지연 구성 — 무거운 엔진 모듈).

    목록은 sectors_for_llm_prompt()를 쓴다 — 이름만으로 관례를 오해하기 쉬운 업종
    (통신/유틸리티=사업자, 에너지/원자력=전력설비 제조 포함)에 짧은 주석이 붙어 있다."""
    from engine.universe_pit import sectors_for_llm_prompt

    return (
        "너는 한국어 주식 전략 문장에서 사용자가 종목 범위를 제한하려는 업종/테마 언급을 찾아 "
        "지원 업종 목록 중 하나로 매핑하는 분류기다.\n"
        "지원 업종(괄호는 분류 관례 설명 — 업종명만 그대로 출력): "
        + sectors_for_llm_prompt() + "\n"
        "언급된 테마가 어느 업종에 속하거나 그 하위 테마면 그 업종명을 쓴다"
        "(예: '원자로'→'에너지/원자력', '전력설비'→'에너지/원자력', '은행주'→'은행/금융지주'). "
        "명백한 오타/오기는 교정해서 매핑한다"
        "(예: '재약주'→'제약주'→'바이오/제약', '반도채'→'반도체'). "
        "회사명의 일부(예: 'LG화학'의 '화학')는 업종 언급이 아니다. "
        "어떤 업종과도 연결하기 어려우면 null.\n"
        '설명 없이 JSON 객체만 출력한다. 예: {"sector": "에너지/원자력"} 또는 {"sector": null}'
    )


def llm_extract_sector(text: str, chat: Callable[..., str]) -> Optional[str]:
    """LLM으로 업종/테마 언급을 정본 섹터명으로 매핑한다. chat은 (system, user, *, max_tokens)->str.

    출력은 반드시 normalize_sector로 재검증한다 — LLM이 목록 밖 이름을 지어내도 None."""
    from engine.universe_pit import normalize_sector

    raw = chat(_sector_llm_prompt(), text, max_tokens=60)
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("sector")
    return normalize_sector(value) if isinstance(value, str) else None


def _merge_risk(regex_patch: dict, llm_patch: dict) -> dict:
    """정규식 결과를 우선하고, 정규식이 놓친 청산 필드만 LLM 결과로 채운다.
    LLM 값도 범위 검증을 통과해야 한다(정규식 경로와 동일 기준)."""
    merged = dict(regex_patch)
    for field in RISK_FIELDS:
        value = llm_patch.get(field)
        if merged.get(field) is None and value is not None and _risk_value_valid(field, value):
            merged[field] = value
    if any(merged.get(field) is not None for field in RISK_FIELDS):
        merged["risk_done"] = True
    return merged


# ─── 전략별 특화 파라미터 스텝(엔진이 실제 반영하는 값만) ──────────────────────────────
# 유형 확정 후 ~ 보유수 이전에 그 전략의 핵심 파라미터를 묻는다. 각 파서는 patch를 반환하고,
# 인식 실패 시 {}를 반환해 같은 질문을 다시 하게 한다(초보자는 '기본값'으로 넘어갈 수 있다).

_DEFAULT_RE = re.compile(r"기본|디폴트|default|아무거나|알아서|추천|그냥|상관\s*없|몰라", re.IGNORECASE)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _wants_default(text: str) -> bool:
    return bool(_DEFAULT_RE.search(text or ""))


def _nums(text: str) -> list[float]:
    return [float(x) for x in _NUM_RE.findall(text or "")]


# 지표 파라미터의 상식적 기간 상한(그 이상은 오타/오해로 보고 되묻는다).
_MAX_INDICATOR_PERIOD = 250


def _parse_rsi_period(text: str) -> dict:
    if _wants_default(text):
        return {"rsi_period": 14}
    ns = _nums(text)
    if not ns:
        return {}
    n = int(ns[0])
    # 0·음수·비상식적 기간은 채우지 않는다(합성 시 기본값으로 조용히 치환되던 BF-09 방지).
    return {"rsi_period": n} if 2 <= n <= _MAX_INDICATOR_PERIOD else {}


def _labeled_rsi_bounds(text: str) -> dict:
    """'과매도 25 과매수 80'처럼 라벨이 명시된 경우만 값을 뽑는다(순서 무관).
    라벨이 서로 뒤바뀐 모순 입력(과매도>과매수)은 조용히 재정렬하지 않고 {}로 되묻는다."""
    m_lo = re.search(r"과매도[^0-9]{0,8}(\d+(?:\.\d+)?)", text)
    m_hi = re.search(r"과매수[^0-9]{0,8}(\d+(?:\.\d+)?)", text)
    if not (m_lo and m_hi):
        return {}
    lo, hi = float(m_lo.group(1)), float(m_hi.group(1))
    if 0 <= lo < hi <= 100:
        return {"rsi_oversold": lo, "rsi_overbought": hi}
    return {}


def _parse_rsi_bounds(text: str) -> dict:
    if _wants_default(text):
        return {"rsi_oversold": 30.0, "rsi_overbought": 70.0}
    if re.search(r"과매도", text) and re.search(r"과매수", text):
        # 라벨이 명시됐으면 라벨 해석만 쓴다 — 라벨 모순('과매도 80 과매수 20')이
        # 무라벨 정렬 폴백으로 흘러 조용히 재정렬되지 않게 한다(BF-09).
        return _labeled_rsi_bounds(text)
    ns = _nums(text)
    if len(ns) >= 2:
        lo, hi = sorted(ns[:2])
        # RSI는 0~100 범위, 과매도<과매수여야 신호가 성립한다(BF-09: 150·동일값 수락 방지).
        if 0 <= lo < hi <= 100:
            return {"rsi_oversold": lo, "rsi_overbought": hi}
    return {}  # 값 부족/범위 밖 → 다시 묻는다


def _parse_ma_kind(text: str) -> dict:
    t = (text or "").lower()
    if re.search(r"지수|ema", t):
        return {"ma_kind": "ema"}
    if re.search(r"단순|sma|단리|이동\s*평균", t) or _wants_default(text):
        return {"ma_kind": "sma"}
    return {}


def _parse_ma_periods(text: str) -> dict:
    if _wants_default(text):
        return {"ma_short": 5, "ma_long": 20}
    ns = [int(x) for x in _nums(text)]
    if len(ns) >= 2:
        lo, hi = sorted(ns[:2])
        # 동일 기간은 교차가 발생할 수 없다(BF-09) — 되묻는다.
        if 1 <= lo < hi:
            return {"ma_short": lo, "ma_long": hi}
    return {}


def _parse_macd_mode(text: str) -> dict:
    if re.search(r"제로|0\s*선|zero", text or ""):
        return {"macd_mode": "zero"}
    if re.search(r"교차|크로스|시그널|골든|cross", text or "") or _wants_default(text):
        return {"macd_mode": "crossover"}
    return {}


def _parse_cci_params(text: str) -> dict:
    if _wants_default(text):
        return {"cci_period": 14, "cci_threshold": 100.0}
    ns = _nums(text)
    if len(ns) >= 2:
        period, thr = int(ns[0]), ns[1]
        if 2 <= period <= _MAX_INDICATOR_PERIOD and thr > 0:
            return {"cci_period": period, "cci_threshold": thr}
        return {}
    if len(ns) == 1 and ns[0] > 0:
        return {"cci_period": 14, "cci_threshold": ns[0]}  # 기준값만 주면 기간은 기본 14
    return {}


def _parse_volume_period(text: str) -> dict:
    if _wants_default(text):
        return {"volume_period": 20}
    ns = _nums(text)
    if not ns:
        return {}
    n = int(ns[0])
    return {"volume_period": n} if 2 <= n <= _MAX_INDICATOR_PERIOD else {}


# 저평가 기준의 방향이 빌더 고정(PBR≤·ROE≥)과 반대인 요청("PBR 5 이상"·"ROE 3 이하") —
# 숫자만 뽑아 정반대 스크리닝을 조용히 만들지 않도록(BF-07) 감지해서 채우지 않고 안내한다.
_PBR_WRONG_DIR_RE = re.compile(r"pbr[^0-9]{0,6}\d+(?:\.\d+)?\s*(?:이상|초과|넘|보다\s*[크높])", re.IGNORECASE)
_ROE_WRONG_DIR_RE = re.compile(r"roe[^0-9]{0,6}\d+(?:\.\d+)?\s*(?:이하|미만|밑|아래|보다\s*[작낮])", re.IGNORECASE)


def _value_direction_conflict(text: str) -> bool:
    t = text or ""
    return bool(_PBR_WRONG_DIR_RE.search(t) or _ROE_WRONG_DIR_RE.search(t))


def _parse_value_params(text: str) -> dict:
    if _wants_default(text):
        return {"value_pbr": 1.0, "value_roe": 10.0}
    t = text or ""
    pbr_conflict = bool(_PBR_WRONG_DIR_RE.search(t))
    roe_conflict = bool(_ROE_WRONG_DIR_RE.search(t))
    m_pbr = None if pbr_conflict else re.search(r"pbr[^0-9]{0,6}(\d+(?:\.\d+)?)", t, re.IGNORECASE)
    m_roe = None if roe_conflict else re.search(r"roe[^0-9]{0,6}(\d+(?:\.\d+)?)", t, re.IGNORECASE)
    if m_pbr or m_roe:
        patch: dict = {}
        if m_pbr and float(m_pbr.group(1)) > 0:
            patch["value_pbr"] = float(m_pbr.group(1))
        if m_roe and float(m_roe.group(1)) > 0:
            patch["value_roe"] = float(m_roe.group(1))
        return patch  # 하나만 라벨돼도 채운다(나머지는 다시 묻음)
    if pbr_conflict or roe_conflict:
        return {}  # 방향 충돌만 있으면 채우지 않는다 — step이 사유를 설명하며 되묻는다
    ns = _nums(t)
    if len(ns) >= 2 and ns[0] > 0 and ns[1] > 0:
        return {"value_pbr": ns[0], "value_roe": ns[1]}  # 라벨 없으면 'PBR 먼저, ROE 다음' 순서
    return {}


_FILTER_NONE_RE = re.compile(r"없음|없이|안\s*(?:넣|쓰|해|할)|그냥|필요\s*없|스킵|패스|괜찮", re.IGNORECASE)
_FILTER_TREND_RE = re.compile(r"ema\s*(\d+)|(\d+)\s*일?\s*(?:지수\s*)?이동\s*평균", re.IGNORECASE)
_FILTER_LIQ_RE = re.compile(r"(\d+)\s*억")
_FILTER_RSI_RE = re.compile(r"rsi\s*(\d+)", re.IGNORECASE)


def _parse_filters(text: str) -> dict:
    """옵션 필터 답변을 해석한다. '없음'/기본값 계열 또는 필터 어휘를 인식했을 때만
    filters_asked=True로 완료한다 — 무관한 입력("근데 삼성전자만 하면 안돼?")까지
    '필터 없음'으로 조용히 소비하던 사고(퍼징 QA BF-10) 방지. 무매치면 {}로 되묻는다.
    추세(EMA 기간)·거래대금(억)·RSI 결합을 자유 입력에서 함께 인식한다."""
    patch: dict = {"filters_asked": True}
    t = text or ""
    if _FILTER_NONE_RE.search(t) or _wants_default(t):
        return patch  # 필터 없이 완료
    m = _FILTER_TREND_RE.search(t)
    if m:
        patch["trend_filter_ma"] = int(m.group(1) or m.group(2))
    elif re.search(r"추세", t):
        patch["trend_filter_ma"] = 200  # '추세 필터'만 언급하면 기본 EMA200
    ml = _FILTER_LIQ_RE.search(t)
    if ml:
        patch["liquidity_min"] = float(ml.group(1))
    mr = _FILTER_RSI_RE.search(t)
    if mr:
        patch["rsi_filter"] = float(mr.group(1))
    if len(patch) == 1:  # 아무 필터도 인식 못 함 → 완료 처리하지 않고 다시 묻는다
        return {}
    return patch


# 스텝 키 → 파서. (lookback_days·entry_rule·filters는 아래 전용 분기가 처리하므로 제외.)
_PARAM_STEP_PARSERS: dict[str, Callable[[str], dict]] = {
    "rsi_period": _parse_rsi_period,
    "rsi_bounds": _parse_rsi_bounds,
    "ma_kind": _parse_ma_kind,
    "ma_periods": _parse_ma_periods,
    "macd_mode": _parse_macd_mode,
    "cci_params": _parse_cci_params,
    "volume_period": _parse_volume_period,
    "value_params": _parse_value_params,
}

# 전략별 특화 파라미터 스텝(유형 확정 후 순서대로 첫 미충족 스텝을 질문). 없는 유형은 프리셋.
# 기술적 진입 전략은 마지막에 옵션 "filters" 스텝(추세·거래대금·RSI 결합)을 둔다.
# momentum(랭킹 선정)·value(재무 스크리닝)·custom(자유 서술)은 진입 게이트 필터 대상이 아니라 제외.
STRATEGY_PARAM_STEPS: dict[str, tuple[str, ...]] = {
    "momentum": ("lookback_days",),
    "breakout": ("lookback_days", "filters"),
    "rsi": ("rsi_period", "rsi_bounds", "filters"),
    "golden_cross": ("ma_kind", "ma_periods", "filters"),
    "macd": ("macd_mode", "filters"),
    "cci": ("cci_params", "filters"),
    "stochastic": ("filters",),  # 신호는 크로스오버 프리셋, 옵션 필터만 물음
    "bollinger": ("filters",),
    "mean_reversion": ("filters",),
    "volume_spike": ("volume_period", "filters"),
    "value": ("value_params",),
    "custom": ("entry_rule",),
}


def _step_filled(state: BuilderState, step: str) -> bool:
    """전략별 스텝이 완료됐는지(필요한 상태 필드가 모두 채워졌는지)."""
    checks: dict[str, Callable[[BuilderState], bool]] = {
        "lookback_days": lambda s: s.lookback_days is not None,
        "rsi_period": lambda s: s.rsi_period is not None,
        "rsi_bounds": lambda s: s.rsi_oversold is not None and s.rsi_overbought is not None,
        "ma_kind": lambda s: s.ma_kind is not None,
        "ma_periods": lambda s: s.ma_short is not None and s.ma_long is not None,
        "macd_mode": lambda s: s.macd_mode is not None,
        "cci_params": lambda s: s.cci_period is not None and s.cci_threshold is not None,
        "volume_period": lambda s: s.volume_period is not None,
        "value_params": lambda s: s.value_pbr is not None and s.value_roe is not None,
        "entry_rule": lambda s: bool(s.entry_rule),
        "filters": lambda s: s.filters_asked,  # 옵션 — 한 번 물으면 완료(값 없어도)
    }
    return checks.get(step, lambda s: True)(state)


# 전략 유형 변경 시 함께 초기화할 유형 특화 파라미터(이전 유형의 값이 새 유형에
# 그대로 남지 않게). 변경 cue가 있는 명시적 정정에서만 쓴다.
_TYPE_PARAM_RESET: dict = {
    "lookback_days": None, "lookback_label": None,
    "rsi_period": None, "rsi_oversold": None, "rsi_overbought": None,
    "ma_kind": None, "ma_short": None, "ma_long": None,
    "macd_mode": None, "cci_period": None, "cci_threshold": None,
    "volume_period": None, "value_pbr": None, "value_roe": None,
    "entry_rule": None, "filters_asked": False,
    "trend_filter_ma": None, "liquidity_min": None, "rsi_filter": None,
}

def parse_input(text: str, state: BuilderState, expecting: Optional[str]) -> dict:
    """짧은 답변을 전략 필드 patch로 해석한다. 모호한 맨숫자는 현재 묻는 필드(expecting)로 해석.

    '말고/아니라' 정정 표현은 마지막 조각만 값 해석에 쓴다(BF-06). 전용 스텝(필터·특화
    파라미터)에서 인식 실패 + 변경 cue가 있으면 공통 필드 정정(유니버스·유형 변경)으로
    떨어져 처리한다 — 파라미터 질문 중의 "코스닥으로 바꿔줘"가 조용히 무시되지 않게."""
    t = text or ""
    patch: dict = {}

    # custom 유형에서 진입 조건을 서술로 받는 중이면, 입력 전체를 진입 규칙으로 저장한다
    # (자유 서술 안의 숫자를 기간/보유수로 오해하지 않도록 다른 파싱을 건너뛴다).
    # 단, 명시적 "N개/N종목" 접미사는 보유 수로만 해석되므로(RSI 30 같은 맨숫자와 달리 모호하지
    # 않다) 진입 서술에 종목 수가 섞여 있으면 함께 잡아 보유 수를 다시 묻지 않는다.
    if expecting == "entry_rule":
        stripped = t.strip()
        if stripped and detect_control(stripped) is None:
            patch = {"entry_rule": stripped}
            m_count = _COUNT_RE.search(t)
            if m_count and not state.holding_count and _valid_count(int(m_count.group(1))):
                patch["holding_count"] = int(m_count.group(1))
            return patch
        return {}

    # 청산 조건 단계 — 손절/익절/트레일링/보유기간만 해석하고(없음=값 없이) 완료 처리한다.
    if expecting == "risk":
        return _parse_risk(t)

    focused = _correction_focus(t)
    change_cue = bool(_CHANGE_CUE_RE.search(t))

    # 옵션 필터 스텝 — 필터 어휘를 인식했을 때만 완료. 추세·거래대금·RSI 결합을 함께 인식.
    if expecting == "filters":
        patch = _parse_filters(focused)
        if patch or not change_cue:
            return patch
        # 인식 실패 + 변경 cue → 아래 공통 필드 정정으로 폴백

    # 전략별 특화 파라미터 스텝은 전용 파서로 처리한다(그 값만 해석, 다른 필드 오염 방지).
    elif expecting in _PARAM_STEP_PARSERS:
        patch = _PARAM_STEP_PARSERS[expecting](focused)
        if patch:
            # 복합 답변("14일로 하고 과매도 25 과매수 80")의 후속 슬롯을 함께 흡수한다(BF-14).
            # 오귀속 위험이 없는 조합만: 라벨 명시 RSI 경계, 이동평균 종류+두 기간.
            if expecting == "rsi_period":
                patch.update(_labeled_rsi_bounds(focused))
            elif expecting == "ma_kind":
                patch.update(_parse_ma_periods(focused))
            return patch
        if not change_cue:
            return patch
        # 인식 실패 + 변경 cue → 아래 공통 필드 정정으로 폴백

    t = focused

    universe = _parse_universe(t)
    if universe and (not state.universe or (change_cue and universe != state.universe)):
        patch["universe"] = universe

    # 대화 중 업종/테마 언급 — 지원 업종이면 유니버스 제한으로 반영하고, 목록 밖이면
    # 조용히 무시하는 대신 안내 플래그를 켠다(시드와 동일 규칙, 정본=universe_pit).
    from engine.nl_parser import _extract_sector, _mentioned_unsupported_concepts

    sector = _extract_sector(t)
    if sector and not state.sector:
        patch["sector"] = sector
    elif sector is None and "sector" in _mentioned_unsupported_concepts(t):
        patch["sector_unresolved"] = True
        patch["sector_hint"] = t

    stype = _parse_strategy_type(t)
    if stype and (not state.strategy_type or (change_cue and stype != state.strategy_type)):
        # ETF 유니버스에는 가치 전략(PBR/ROE 재무 필터)을 만들 수 없다 — 채우지 않고
        # step()이 이유를 설명하며 되묻는다(BF-12).
        # 단일 종목 모드에는 종목 선별형 유형(모멘텀 랭킹·가치 스크리닝)을 채우지 않는다
        # (step()이 이유를 설명하며 되묻는다 — 조용한 무시 방지).
        if not (stype == "value" and (patch.get("universe") or state.universe) == "ETF") \
                and not (state.single_symbol is not None and stype in _SINGLE_ASSET_BLOCKED_TYPES):
            patch["strategy_type"] = stype
            if state.strategy_type and stype != state.strategy_type:
                # 명시적 유형 변경(BF-05) — 이전 유형의 특화 파라미터를 초기화한다.
                patch.update(_TYPE_PARAM_RESET)

    rebal = _parse_rebalance(t)
    if rebal:
        patch["rebalance_cycle"] = rebal

    # 기준 기간(모멘텀=개월, 돌파=일). 접미사 우선, 없으면 expecting==lookback일 때 맨숫자.
    effective_type = patch.get("strategy_type") or state.strategy_type
    lookback = _parse_lookback(t)
    if lookback:
        patch.update(lookback)

    # 보유 종목 수. 접미사("N개/N종목") 우선. 범위 밖(0·100 초과)은 채우지 않는다(BF-17).
    m_count = _COUNT_RE.search(t)
    if m_count and _valid_count(int(m_count.group(1))):
        patch["holding_count"] = int(m_count.group(1))

    # 맨숫자는 현재 묻는 필드로 귀속(둘 다 채우지 않도록 분기).
    bare = _BARE_NUM_RE.match(t)
    if bare and "lookback_days" not in patch and "holding_count" not in patch:
        n = int(bare.group(1))
        if expecting == "lookback_days" and n > 0:
            if effective_type == "breakout":
                patch["lookback_days"] = n
                patch["lookback_label"] = f"{n}일"
            else:
                patch["lookback_days"] = n * 21
                patch["lookback_label"] = f"{n}개월"
        elif expecting == "holding_count" and _valid_count(n):
            patch["holding_count"] = n

    return patch


def is_empty(state: BuilderState) -> bool:
    """아직 아무 필드도 채워지지 않은 초기 상태인지 판단한다(시드 적용 여부 게이트)."""
    return state == BuilderState()


def seed_state(text: str) -> BuilderState:
    """빌더 진입 시 사용자의 원본 메시지에서 인식 가능한 모든 전략 필드를 미리 채운다.

    [규제 안전/UX] 열린 추천(STOCK_PICK)으로 빌더에 진입하더라도 사용자가 이미 말한
    조건(유니버스·전략유형·기준기간·보유수·리밸런싱·청산)은 다시 묻지 않고, 빠진 필드만
    질문하기 위함이다. 단계별 parse_input과 달리 청산 조건도 단계 무관하게 추출한다.

    업종/섹터("반도체 주도주"·"2차전지 관련주")도 여기서 기억한다 — 종목 질문 리다이렉트
    뒤 업종 전략으로 넘어온 사용자에게 종목 범위를 다시 묻지 않는다(NL 파서의 결정적
    섹터 추출을 재사용, 정본=universe_pit)."""
    patch: dict = {}
    # 지연 import(무거운 엔진 모듈)
    from engine.nl_parser import _extract_sector, _mentioned_unsupported_concepts

    sector = _extract_sector(text)
    if sector:
        patch["sector"] = sector
    elif "sector" in _mentioned_unsupported_concepts(text):
        # 업종/테마를 말했지만 결정적 매핑 실패('원자로 관련주') — 조용히 버리지 않고
        # LLM 해석(step의 sector_resolver)에 원문을 넘기고, 그래도 안 되면 안내한다.
        patch["sector_unresolved"] = True
        patch["sector_hint"] = text
    else:
        from engine.nl_parser import _weak_theme_candidate

        if _weak_theme_candidate(text):
            # 큐 없는 미지 테마어 추정("소부장 전략") — 약한 힌트로 그라운딩 체인에 넘긴다.
            # 오탐 여지가 있어 해석 실패 시 되묻기 없이 조용히 해제된다(sector_hint_weak).
            patch["sector_unresolved"] = True
            patch["sector_hint"] = text
            patch["sector_hint_weak"] = True
    # 테마 관련 상장사가 이미 학습·검증돼 있으면(재사용 발화) 되묻기 후보를 즉시 챙긴다 —
    # 미해결 힌트 경로는 해석 후 _consume_sector_notice가 같은 조회를 한다(FR-STR-071).
    if not patch.get("sector_unresolved"):
        theme = _theme_companies(text)
        if theme:
            patch.update(_theme_patch(theme))
    universe = _parse_universe(text)
    if universe:
        patch["universe"] = universe
    stype = _parse_strategy_type(text)
    if stype:
        patch["strategy_type"] = stype
    rebal = _parse_rebalance(text)
    if rebal:
        patch["rebalance_cycle"] = rebal
    lookback = _parse_lookback(text)
    if lookback:
        patch.update(lookback)
    count = _COUNT_RE.search(text)
    if count and _valid_count(int(count.group(1))):
        patch["holding_count"] = int(count.group(1))
    patch.update(_parse_risk(text))  # 손절/익절/트레일링/보유기간(+risk_done, 범위 검증 포함)
    return BuilderState().model_copy(update=patch)


def apply_parsed_seed(state: BuilderState, parsed: Optional[dict]) -> BuilderState:
    """파싱 파이프라인(룰 파스 → LLM 검증 교정 → LLM 폴백)이 이미 해석한 ParsedStrategy
    dump에서, 결정적 시드 regex가 놓친 필드를 이어받는다.

    [하이브리드] 긴 꼬리 표현("반도체 중심으로")은 phrasing마다 regex를 늘리는 대신
    LLM 레이어가 해석한다 — 빈 전략으로 빌더에 전환될 때 그 결과를 버리지 않는 채널.
    ParsedStrategy 기본값과 사용자 언급을 구분할 수 없는 필드(universe·max_positions·
    rebalancing_period)는 받지 않고, None-기본 필드(sector·청산)만 받는다. 결정적 시드가
    이미 채운 값이 우선한다."""
    if not isinstance(parsed, dict) or not parsed:
        return state
    patch: dict = {}
    sector = parsed.get("sector")
    if isinstance(sector, (str, list)) and sector and state.sector is None:
        from engine.universe_pit import normalize_sector_value  # 지연 import(무거운 엔진 모듈)

        canonical = normalize_sector_value(sector)
        if canonical:
            patch["sector"] = canonical
    for field in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
        v = parsed.get(field)
        if (isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0
                and getattr(state, field) is None):
            patch[field] = float(v)
    hold = parsed.get("hold_period_days")
    if isinstance(hold, int) and not isinstance(hold, bool) and hold > 0 and state.hold_period_days is None:
        patch["hold_period_days"] = hold
    if any(f in patch for f in RISK_FIELDS):
        patch["risk_done"] = True
    return state.model_copy(update=patch) if patch else state


# ─── 필수 필드 우선순위 ──────────────────────────────────────────────────────────

def required_missing(state: BuilderState) -> Optional[str]:
    """필수 필드 우선순위 중 첫 빈 필드를 반환한다(없으면 None=완성).

    단일 종목 모드에서는 종목 선별용 필드(유니버스·보유 종목 수·리밸런싱 주기)를 묻지
    않는다 — 대상이 한 종목으로 확정돼 있어 횡단면 질문이 무의미하다(FR-STR-068b)."""
    single = state.single_symbol is not None
    # 테마 종목 목록이 확정되면 대상이 목록으로 정해져 시장(유니버스) 질문이 무의미하다.
    if not single and not state.theme_symbols and not state.universe:
        return "universe"
    if not state.strategy_type:
        return "strategy_type"
    # 전략별 특화 파라미터(순서대로 첫 미충족 스텝). 없는 유형은 프리셋이라 건너뛴다.
    for step in STRATEGY_PARAM_STEPS.get(state.strategy_type, ()):
        if not _step_filled(state, step):
            return step
    if not single and not state.holding_count:
        return "holding_count"
    if not single and not state.rebalance_cycle:
        return "rebalance_cycle"
    if not state.risk_done:
        return "risk"
    return None


# ─── 응답 생성(다음 질문 / 요약) ─────────────────────────────────────────────────

_UNIVERSE_LABEL = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KOSPI200": "코스피200", "KOSPI_KOSDAQ": "코스피·코스닥 전체", "ETF": "ETF"}
_TYPE_LABEL = {
    "momentum": "모멘텀",
    "golden_cross": "골든크로스",
    "macd": "MACD",
    "bollinger": "볼린저 밴드",
    "breakout": "돌파",
    "volume_spike": "거래량 급증",
    "stochastic": "스토캐스틱",
    "cci": "CCI",
    "rsi": "RSI",
    "mean_reversion": "과매도 반등",
    "value": "저평가 가치주",
    "custom": "직접 설계",
}
_REBAL_LABEL = {
    "daily": "매일",
    "weekly": "매주",
    "monthly": "매월",
    "quarterly": "분기마다",
    "yearly": "매년",
    "none": "안 함",
}
_REBAL_PHRASE = {
    "daily": "매일 리밸런싱",
    "weekly": "매주 리밸런싱",
    "monthly": "매월 리밸런싱",
    "quarterly": "분기마다 리밸런싱",
    "yearly": "매년 리밸런싱",
}


# 단일 종목 모드의 전략 유형 선택지(횡단면 제외 — 시계열 진입 방식만). 칩 텍스트는
# _parse_strategy_type이 그대로 해석할 수 있는 어휘여야 한다.
_SINGLE_ASSET_TYPE_CHIPS = ["골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등"]

# 프로파일 카테고리 → (선택지 라벨, 대응 신호 통계 키). reason은 발생 횟수 사실만 담는다.
_SINGLE_ASSET_CATEGORY_BULLETS: tuple[tuple[str, str, str], ...] = (
    ("trend_following", "골든크로스·MACD 같은 추세 추종", "golden_cross_5_20"),
    ("mean_reversion", "RSI 과매도·볼린저 하단에서 반등을 노리는 평균회귀", "rsi_below_30"),
    ("breakout", "신고가 돌파", "breakout_60d"),
    ("volume", "거래량 급증", "volume_spike_3x"),
)


def _single_asset_strategy_question(
    state: BuilderState, prefix: str,
) -> tuple[str, list[str]]:
    """단일 종목의 진입 방식 질문. 가능하면 종목 프로파일의 신호 발생 횟수를 근거로
    선택지를 설명한다(수익 보장·우열 표현 없음). 프로파일 조회 실패 시 정적 문구."""
    label = state.single_label or state.single_symbol or "선택한 종목"
    bullets: list[str] = []
    try:  # 지연 import + 방어 — 프로파일이 없어도 질문은 항상 가능해야 한다
        from engine.stock_profile import get_stock_profile

        profile = get_stock_profile(state.single_symbol) if state.single_symbol else None
        if profile is not None:
            for category, text, stat_key in _SINGLE_ASSET_CATEGORY_BULLETS:
                if category not in profile.supported_strategy_categories:
                    continue
                count = profile.signal_statistics.get(f"{stat_key}_count")
                if isinstance(count, (int, float)):
                    bullets.append(f"• {text} — 과거 데이터에서 관련 신호 {int(count)}회 발생")
                else:
                    bullets.append(f"• {text}")
    except Exception:
        bullets = []
    if not bullets:
        bullets = [f"• {text}" for _, text, _ in _SINGLE_ASSET_CATEGORY_BULLETS]
    # '직접 입력' 칩은 프론트가 공통으로 붙이므로 여기서 자유 서술 항목을 중복 노출하지
    # 않는다('직접 설명하기'+'직접 입력' 이중 버튼 문제).
    msg = (
        prefix + f"{label} 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. "
        "어떤 진입 방식을 사용할까요?\n\n"
        + "\n".join(bullets)
    )
    return (msg, list(_SINGLE_ASSET_TYPE_CHIPS))


# 자유 서술 진입 조건으로 인정할 최소 큐(지표·비교·매매 어휘 또는 숫자). 인사말·잡담이
# custom 진입 규칙으로 저장되는 것을 막는다.
_ENTRY_DESCRIPTION_CUE_RE = re.compile(
    r"매수|매도|사고|팔|진입|이상|이하|이내|돌파|하락|상승|반등|연속|평균|지표|밴드|%|\d",
    re.IGNORECASE,
)

# 단일 종목 모드에서 쓸 수 없는 종목 선별형 전략 유형 → 안내 문구.
_SINGLE_ASSET_BLOCKED_TYPES: dict[str, str] = {
    "momentum": (
        "모멘텀 전략은 여러 종목의 수익률을 비교해 상위 종목을 고르는 방식이라 "
        "단일 종목에는 적용할 수 없어요. 비슷한 아이디어로는 신고가 '돌파' 진입이 있어요."
    ),
    "value": (
        "저평가 가치주 전략은 여러 종목을 재무지표로 비교·선별하는 방식이라 "
        "단일 종목에는 적용할 수 없어요. 이 종목의 당시 PBR·PER 수준을 진입 조건으로 "
        "쓰고 싶으시면 '직접 입력'으로 조건을 말씀해 주세요(예: 'PBR 1 이하일 때 매수')."
    ),
}


def next_question(
    state: BuilderState, just_filled: Optional[set[str]] = None,
) -> tuple[str, list[str]]:
    """가장 먼저 비어 있는 필수 필드 하나만 자연스럽게 질문한다(+옵션 칩).

    just_filled: 직전 턴에 채워진 필드명 집합. 그 필드를 확인하는 도입부를 만든다.
    None이면 초기(시드) 호출로 보고, 미리 채워진 필드들을 한 줄로 요약해 보여준다."""
    field = required_missing(state)
    prefix = _ack_prefix(state, just_filled)

    if field == "universe":
        return (
            prefix + "어떤 시장을 대상으로 할까요?",
            ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체", "ETF"],
        )
    if field == "strategy_type":
        # 단일 종목 모드: 종목 선별형 유형(모멘텀 랭킹·재무 스크리닝 가치주)을 빼고,
        # 가능하면 종목 프로파일의 신호 발생 통계를 근거로 선택지를 설명한다.
        if state.single_symbol is not None:
            return _single_asset_strategy_question(state, prefix)
        # ETF 유니버스: 기업 재무지표가 없어 가치 전략(PBR/ROE)은 제시하지 않는다.
        value_bullet = (
            "" if state.universe == "ETF"
            else "• PBR 낮고 ROE 높은 저평가 우량주를 고르는 가치 전략\n"
        )
        msg = (
            prefix + ("어떤 방식으로 매매할까요?\n\n" if state.universe == "ETF"
                      else "어떤 방식으로 종목을 고를까요?\n\n")
            + "• 최근 강한 종목을 추종하는 모멘텀 전략\n"
            "• 단기 이동평균이 장기 이동평균을 뚫는 골든크로스 전략\n"
            "• MACD가 시그널선을 돌파할 때 잡는 전략\n"
            "• 전고점(신고가)을 돌파할 때 잡는 돌파 전략\n"
            "• 거래량 흐름(OBV)이 상승 전환한 종목을 찾는 전략\n"
            "• RSI 과매도에서 반등을 노리는 전략\n"
            + value_bullet +
            "• 직접 아이디어를 설명하기"
        )
        chips = ["모멘텀", "골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등"]
        if state.universe != "ETF":
            chips.append("저평가 가치주")
        # "직접 설명하기"는 자유 서술(custom) 진입로 — 선택 시 entry_rule 질문(칩 없음)으로
        # 넘어가 프론트가 채팅창을 다시 보여준다. 가장 오른쪽 칩으로 노출한다.
        return (msg, chips + ["직접 설명하기"])
    if field == "lookback_days":
        if state.strategy_type == "breakout":
            return (prefix + "며칠 신고가(박스권 상단) 돌파를 기준으로 볼까요?", ["20일", "60일", "120일"])
        return (prefix + "최근 몇 개월 수익률을 기준으로 볼까요?", ["1개월", "3개월", "6개월"])
    # ── 전략별 특화 파라미터 질문(초보자용 기본값 제안) ──────────────────────────────
    if field == "rsi_period":
        return (prefix + "RSI를 며칠 기준으로 계산할까요?", ["14일 (기본)", "9일", "21일", "직접 입력"])
    if field == "rsi_bounds":
        return (
            prefix + "과매도·과매수 기준을 정해 주세요. (매수=과매도 아래, 매도=과매수 위)",
            ["30 / 70 (기본)", "25 / 75", "35 / 65", "직접 입력"],
        )
    if field == "ma_kind":
        return (prefix + "어떤 이동평균을 쓸까요?", ["단순(SMA)", "지수(EMA)"])
    if field == "ma_periods":
        return (
            prefix + "단기·장기 이동평균 기간을 정해 주세요. (단기가 장기를 상향 돌파=매수)",
            ["5일 / 20일 (기본)", "10일 / 60일", "20일 / 120일", "직접 입력"],
        )
    if field == "macd_mode":
        return (
            prefix + "MACD 신호를 어떻게 잡을까요?",
            ["시그널선 교차 (기본)", "제로선 돌파"],
        )
    if field == "cci_params":
        return (
            prefix + "CCI 기준값을 정해 주세요. (매수=-기준값 아래, 매도=+기준값 위, 기간 기본 14)",
            ["±100 (기본)", "±150", "직접 입력"],
        )
    if field == "volume_period":
        return (prefix + "거래량 흐름(OBV) 평균을 며칠 기준으로 볼까요?", ["20일 (기본)", "60일", "직접 입력"])
    if field == "value_params":
        return (
            prefix + "저평가 기준을 정해 주세요.",
            ["PBR 1 이하 · ROE 10 이상 (기본)", "PBR 0.8 · ROE 15", "직접 입력"],
        )
    if field == "filters":
        chips = ["EMA200 위에서만", "거래대금 100억 이상"]
        if state.strategy_type in ("bollinger", "mean_reversion"):
            chips.append("RSI 30 이하일 때만")  # 평균회귀 매수에 과매도 확인을 더한다
        chips += ["없음", "직접 입력"]
        return (
            prefix + "지금 조건만 쓰면 횡보장에서도 매수 신호가 너무 자주 발생할 수 있어요. "
            "매수에 추가 필터를 넣을까요? 추세·거래대금 조건을 더하면 이런 신호가 걸러져요. "
            "(여러 개를 함께 말해도 돼요, 예: 'EMA200 위 + 거래대금 100억')",
            chips,
        )
    if field == "entry_rule":
        return (
            prefix + "어떤 조건에서 매수할지 말씀해 주세요. "
            "(예: 'RSI가 30 이하로 떨어지면', '20일선이 60일선을 상향 돌파하면')",
            [],
        )
    if field == "holding_count":
        # "직접 입력"은 빌더 답변이 아니라 프론트에서 채팅창을 다시 띄우는 토글 칩이다
        # (제시한 5/10/20개 외의 종목 수를 사용자가 직접 타이핑할 수 있게 한다).
        if state.strategy_type == "momentum":
            return (prefix + "상위 몇 개 종목을 보유할까요?", ["5개", "10개", "20개", "직접 입력"])
        return (prefix + "최대 몇 종목까지 보유할까요?", ["5개", "10개", "20개", "직접 입력"])
    if field == "rebalance_cycle":
        return (prefix + "얼마나 자주 종목을 교체(리밸런싱)할까요?", ["매주", "매월", "분기마다", "안 함"])
    if field == "risk":
        msg = (
            prefix + "마지막으로 청산 조건을 정해 주세요. 손절·익절·트레일링 스탑·보유기간 중 "
            "하나 이상을 자유롭게 말씀해 주세요.\n"
            "(예: '10% 손절', '20% 익절', '최고가 대비 10% 하락 시 청산', '20일 보유 후 청산')"
        )
        # "직접 입력"은 빌더 답변이 아니라 프론트에서 채팅창을 다시 띄우는 토글 칩이다
        # (청산 조건은 자유 서술을 인라인으로 받으므로 별도 질문 없이 사용자가 직접 타이핑).
        return (
            msg,
            ["10% 손절", "10% 손절·20% 익절", "최고가 대비 10% 하락 시 청산", "직접 입력"],
        )
    # 필드가 다 찼으면 step()이 confirmed로 보내므로 여기 도달하지 않는다.
    return ("", [])


# 확인 도입부에서 필드를 다룰 우선순위(높을수록 먼저). 직전 답변이 여럿이면 이 순서로 하나만.
# 전략별 특화 파라미터를 공통 필드보다 앞에 둬(그 값을 방금 답한 경우가 대부분) 자연스럽게 확인한다.
_ACK_PRIORITY = (
    "filters_asked", "rsi_overbought", "rsi_period", "ma_long", "ma_kind", "macd_mode",
    "cci_threshold", "volume_period", "value_roe",
    "rebalance_cycle", "holding_count", "lookback_days", "entry_rule", "strategy_type",
    "theme_symbols", "sector", "universe",
)


def _filter_phrases(state: BuilderState) -> list[str]:
    """선택된 옵션 필터를 짧은 한국어 구로. 없으면 빈 리스트."""
    parts: list[str] = []
    if state.trend_filter_ma:
        parts.append(f"{state.trend_filter_ma}일선 위")
    if state.liquidity_min:
        parts.append(f"거래대금 {_fmt_pct(state.liquidity_min)}억 이상")
    if state.rsi_filter:
        parts.append(f"RSI {_fmt_pct(state.rsi_filter)} 이하")
    return parts


def _sector_label(state: BuilderState) -> str:
    """sector 정규형(str/list)을 표시용 라벨로 — 복수는 '·'로 잇는다("반도체·로봇")."""
    from engine.universe_pit import sector_value_as_list  # 지연 import(무거운 엔진 모듈)
    return "·".join(sector_value_as_list(state.sector))


def _ack_sentence(state: BuilderState, field: str) -> str:
    """단일 필드를 확인하는 완결 문장(마침표 없이)."""
    if field == "filters_asked":
        phrases = _filter_phrases(state)
        return f"{'·'.join(phrases)} 필터를 더하겠습니다" if phrases else "추가 필터 없이 진행하겠습니다"
    if field == "rsi_period":
        return f"RSI {state.rsi_period}일 기준으로 보겠습니다"
    if field == "rsi_overbought":
        return f"과매도 {_fmt_pct(state.rsi_oversold)}·과매수 {_fmt_pct(state.rsi_overbought)} 기준으로 하겠습니다"
    if field == "ma_kind":
        return f"{'지수' if state.ma_kind == 'ema' else '단순'} 이동평균을 쓰겠습니다"
    if field == "ma_long":
        return f"{state.ma_short}일·{state.ma_long}일 이동평균 교차로 하겠습니다"
    if field == "macd_mode":
        return f"MACD {'제로선 돌파' if state.macd_mode == 'zero' else '시그널선 교차'}로 하겠습니다"
    if field == "cci_threshold":
        return f"CCI ±{_fmt_pct(state.cci_threshold)} 기준으로 하겠습니다"
    if field == "volume_period":
        return f"거래량 흐름(OBV) {state.volume_period}일 평균 기준으로 보겠습니다"
    if field == "value_roe":
        if state.value_pbr is None:  # 한쪽만 채워진 부분 답변 — 채워진 값만 확인한다
            return f"ROE {_fmt_pct(state.value_roe)} 이상으로 하겠습니다"
        return f"PBR {_fmt_pct(state.value_pbr)} 이하·ROE {_fmt_pct(state.value_roe)} 이상으로 하겠습니다"
    if field == "rebalance_cycle":
        if state.rebalance_cycle == "none":
            return "정기 리밸런싱은 하지 않겠습니다"
        return f"{_REBAL_LABEL.get(state.rebalance_cycle, '')} 리밸런싱하겠습니다"
    if field == "holding_count":
        return f"최대 {state.holding_count}종목으로 하겠습니다"
    if field == "lookback_days":
        return f"최근 {state.lookback_label} 기준으로 보겠습니다"
    if field == "entry_rule":
        return "말씀하신 조건으로 진입하겠습니다"
    if field == "strategy_type":
        return f"{_TYPE_LABEL.get(state.strategy_type, '')} 전략으로 구성해 볼게요"
    if field == "sector":
        return f"{_sector_label(state)} 업종 종목만 대상으로 하겠습니다"
    if field == "theme_symbols":
        return f"{state.theme_label} 종목만 대상으로 하겠습니다"
    if field == "universe":
        return f"{_UNIVERSE_LABEL.get(state.universe, '')} 시장을 대상으로 하겠습니다"
    return ""


def _seed_summary(state: BuilderState) -> list[str]:
    """시드로 미리 채워진 조건을 짧은 명사구로 요약한다(초기 질문에서 '이해한 내용' 표시).

    단일 종목 모드에서는 시스템이 자동 고정하는 값(보유 1종목·리밸런싱 없음)을 사용자가
    말한 조건처럼 복창하지 않는다 — "1종목, 안 함 리밸런싱(으)로 이해했어요" 같은 어색한
    문장이 나오던 버그."""
    single = state.single_symbol is not None
    parts: list[str] = []
    if state.sector and not single:
        parts.append(f"{_sector_label(state)} 업종 대상")
    if state.strategy_type:
        parts.append(f"{_TYPE_LABEL.get(state.strategy_type, '')} 전략")
    if state.lookback_days and state.strategy_type in ("momentum", "breakout"):
        parts.append(f"최근 {state.lookback_label} 기준")
    if state.holding_count and not single:
        parts.append(f"{state.holding_count}종목")
    if state.rebalance_cycle and not single:
        parts.append(_REBAL_LABEL.get(state.rebalance_cycle, "") + " 리밸런싱")
    risk: list[str] = []
    if state.stop_loss_pct is not None:
        risk.append(f"{_fmt_pct(state.stop_loss_pct)}% 손절")
    if state.take_profit_pct is not None:
        risk.append(f"{_fmt_pct(state.take_profit_pct)}% 익절")
    if state.trailing_stop_pct is not None:
        risk.append(f"최고가 대비 {_fmt_pct(state.trailing_stop_pct)}% 청산")
    if state.hold_period_days:
        risk.append(f"{state.hold_period_days}거래일 보유")
    if risk:
        parts.append("·".join(risk))
    return parts


def _ack_prefix(state: BuilderState, just_filled: Optional[set[str]] = None) -> str:
    """확인 도입부를 만든다.

    just_filled가 주어지면(후속 질문) 그 안에서 우선순위가 가장 높은 필드 하나만 확인한다 —
    시드로 미리 채워진 필드를 직전 답변으로 오인해 엉뚱하게 확인하는 일을 막는다.
    None이면(초기/시드 호출) 미리 채워진 조건들을 한 줄로 요약한다."""
    if just_filled is None:
        summary = _seed_summary(state)
        if summary:
            return "좋아요. " + ", ".join(summary) + "(으)로 이해했어요.\n\n"
        return ""
    for field in _ACK_PRIORITY:
        if field in just_filled:
            sentence = _ack_sentence(state, field)
            if sentence:
                return f"좋아요. {sentence}.\n\n"
    return ""


def _fmt_pct(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


# ─── 백테스트 프롬프트 합성(검증된 한국어 표현) ─────────────────────────────────────

def synthesize_prompt(state: BuilderState) -> str:
    """수집한 필드를 기존 NL 파서가 안정적으로 해석하는 한국어 프롬프트로 합성한다."""
    single = state.single_symbol is not None
    universe = _UNIVERSE_LABEL.get(state.universe or "KOSPI", "코스피")
    if state.theme_symbols and state.theme_label and not single:
        # 테마 종목 목록 확정(FR-STR-071): 종목명 나열로 합성 — custom 유형의 prompt
        # 재파싱 경로에서 _extract_target_symbols가 결정적으로 잡는다('업종/테마' 단어를
        # 넣지 않는다 — 문맥 가드가 종목 추출을 차단해 목록이 무효화되는 함정).
        universe = state.theme_label
    elif state.sector and not single:
        # "업종" 큐를 붙여 custom 유형의 prompt 재파싱 경로에서도 섹터가 다시 인식되게 한다.
        # 복수 섹터는 '·'로 잇는다 — 재파싱의 _extract_sector가 각 항목을 다시 잡는다.
        universe = f"{universe} {_sector_label(state)} 업종"
    rebal = _REBAL_PHRASE.get(state.rebalance_cycle or "", "")
    n = 1 if single else (state.holding_count or 10)
    days = state.lookback_days or 63

    if state.strategy_type == "momentum":
        core = f"{universe} 종목 중 최근 {days}일 수익률 상위 {n}개 종목을 매수"
    elif state.strategy_type == "golden_cross":
        short, long_ = state.ma_short or 5, state.ma_long or 20
        kind = "지수" if state.ma_kind == "ema" else ""
        core = (
            f"{universe} 종목 중 {short}일 {kind}이동평균이 {long_}일 {kind}이동평균을 상향 돌파하는 "
            f"골든크로스에서 매수하고 데드크로스에서 매도, 최대 {n}종목 보유"
        )
    elif state.strategy_type == "macd":
        signal = "제로선을 상향 돌파하면 매수, 하향 돌파하면 매도" if state.macd_mode == "zero" \
            else "골든크로스에서 매수, 데드크로스에서 매도"
        core = f"{universe} 종목 중 MACD가 {signal}, 최대 {n}종목 보유"
    elif state.strategy_type == "rsi":
        period, lo, hi = state.rsi_period or 14, state.rsi_oversold or 30, state.rsi_overbought or 70
        core = (
            f"{universe} 종목 중 RSI({period}일)가 {_fmt_pct(lo)} 이하로 과매도되면 매수하고 "
            f"{_fmt_pct(hi)} 이상이면 매도, 최대 {n}종목 보유"
        )
    elif state.strategy_type == "stochastic":
        core = f"{universe} 종목 중 스토캐스틱 %K가 %D를 상향 교차하면 매수, 하향 교차하면 매도, 최대 {n}종목 보유"
    elif state.strategy_type == "cci":
        thr = _fmt_pct(state.cci_threshold or 100)
        core = f"{universe} 종목 중 CCI가 -{thr} 이하면 매수하고 +{thr} 이상이면 매도, 최대 {n}종목 보유"
    elif state.strategy_type == "bollinger":
        # 엔진이 지원하는 볼린저 신호는 하단 밴드 터치 매수·상단 밴드 터치 매도(평균회귀)뿐이다
        # (기간/표준편차·중심선 변형은 엔진이 반영하지 않아 묻지 않는다).
        core = f"{universe} 종목 중 볼린저밴드 하단에 닿으면 매수하고 상단 밴드에 닿으면 매도, 최대 {n}종목 보유"
    elif state.strategy_type == "value":
        pbr, roe = _fmt_pct(state.value_pbr or 1), _fmt_pct(state.value_roe or 10)
        core = f"{universe} 종목 중 PBR {pbr} 이하, ROE {roe}% 이상인 저평가 우량주를 최대 {n}종목 매수"
    elif state.strategy_type == "breakout":
        core = f"{universe} 종목 중 최근 {days}일 신고가를 돌파하면 매수, 최대 {n}종목 보유"
    elif state.strategy_type == "volume_spike":
        # '거래량 급증'을 붙여 쓰면 재파싱(volume_rising 규칙)이 volume_spike로 다시 인식한다.
        core = f"{universe} 종목 중 거래량 급증(OBV 상승 전환) 신호가 나오면 매수, 최대 {n}종목 보유"
    elif state.strategy_type == "mean_reversion":
        core = (
            f"{universe} 종목 중 RSI가 30 이하로 과매도되면 매수하고 70 이상이면 매도, "
            f"최대 {n}종목 보유"
        )
    else:  # custom
        entry = (state.entry_rule or "").strip().rstrip(".")
        core = f"{universe} 종목 중 {entry}, 최대 {n}종목 보유"

    if single:
        # 단일 종목: "{시장} 종목 중" 선별 서술을 지정 종목 서술로 바꾼다. custom 유형의
        # prompt 재파싱 경로에서도 종목명이 결정적 추출(_extract_target_symbols)에 잡힌다.
        label = state.single_label or state.single_symbol
        core = re.sub(r"^.*?종목 중\s*", "", core)
        core = f"{label} 단일 종목에 적용하는 전략: {core}"

    parts = [core]
    # 옵션 진입 필터를 매수 조건 뒤에 덧붙인다(설명과 DSL 일치).
    if state.trend_filter_ma:
        parts.append(f"주가가 {state.trend_filter_ma}일 지수이동평균 위에 있을 때만 매수")
    if state.liquidity_min:
        parts.append(f"거래대금 {_fmt_pct(state.liquidity_min)}억 이상")
    if state.rsi_filter:
        parts.append(f"RSI가 {_fmt_pct(state.rsi_filter)} 이하일 때만 매수")
    if rebal:
        parts.append(rebal)
    if state.stop_loss_pct is not None:
        parts.append(f"-{_fmt_pct(state.stop_loss_pct)}% 손절")
    if state.take_profit_pct is not None:
        parts.append(f"{_fmt_pct(state.take_profit_pct)}% 익절")
    if state.trailing_stop_pct is not None:
        parts.append(f"최고가 대비 {_fmt_pct(state.trailing_stop_pct)}% 하락 시 청산")
    if state.hold_period_days:
        parts.append(f"최대 {state.hold_period_days}거래일 보유 후 청산")
    return ", ".join(parts)


# ─── DSL 직접 구성(한국어 재파싱 왕복 없이 파라미터 정확 반영) ──────────────────────
# 수집한 전략별 파라미터를 ParsedStrategy로 직접 조립한다. 엔진까지 흐르는 파라미터 매핑은
# strategy_converter._tech_signal_to_condition(SSOT)이 담당하므로 여기선 그 필드만 채운다.
# custom 유형은 자유 서술이라 DSL을 만들 수 없어 None을 반환(호출 측이 prompt 재파싱 폴백).

_UNIVERSE_DSL = {
    "KOSPI": ["KOSPI"], "KOSDAQ": ["KOSDAQ"], "KOSPI200": ["KOSPI200"],
    "KOSPI_KOSDAQ": ["KOSPI", "KOSDAQ"], "ETF": ["ETF"],
}


def build_parsed_strategy(state: BuilderState):
    """수집한 상태를 ParsedStrategy로 직접 조립한다(custom이면 None)."""
    if state.strategy_type == "custom" or state.strategy_type is None:
        return None
    from engine.nl_parser import ParsedStrategy, TechnicalSignal, FundamentalFilter

    st = state.strategy_type
    entry: list = []
    exit_: list = []
    filters: list = []
    ranking_metric = None
    ranking_lookback_days = None

    if st == "momentum":
        ranking_metric = "return"
        ranking_lookback_days = state.lookback_days or 63
    elif st == "golden_cross":
        ind = "ema" if state.ma_kind == "ema" else "ma_crossover"
        short, long_ = state.ma_short or 5, state.ma_long or 20
        entry = [TechnicalSignal(indicator=ind, signal_type="buy", short_period=short, long_period=long_)]
        exit_ = [TechnicalSignal(indicator=ind, signal_type="sell", short_period=short, long_period=long_)]
    elif st == "macd":
        mode = state.macd_mode or "crossover"
        entry = [TechnicalSignal(indicator="macd", signal_type="buy", mode=mode)]
        exit_ = [TechnicalSignal(indicator="macd", signal_type="sell", mode=mode)]
    elif st == "rsi":
        period = state.rsi_period or 14
        lo, hi = state.rsi_oversold or 30, state.rsi_overbought or 70
        entry = [TechnicalSignal(indicator="rsi", signal_type="buy", period=period, operator="<=", value=lo)]
        exit_ = [TechnicalSignal(indicator="rsi", signal_type="sell", period=period, operator=">=", value=hi)]
    elif st == "mean_reversion":
        entry = [TechnicalSignal(indicator="rsi", signal_type="buy", period=14, operator="<=", value=30)]
        exit_ = [TechnicalSignal(indicator="rsi", signal_type="sell", period=14, operator=">=", value=70)]
    elif st == "stochastic":
        # 엔진 level 모드는 스키마로 표현 불가 → 크로스오버만(엔진 지원 신호).
        entry = [TechnicalSignal(indicator="stochastic", signal_type="buy", mode="crossover")]
        exit_ = [TechnicalSignal(indicator="stochastic", signal_type="sell", mode="crossover")]
    elif st == "cci":
        period, thr = state.cci_period or 14, state.cci_threshold or 100
        entry = [TechnicalSignal(indicator="cci", signal_type="buy", period=period, operator="<", value=-thr)]
        exit_ = [TechnicalSignal(indicator="cci", signal_type="sell", period=period, operator=">", value=thr)]
    elif st == "bollinger":
        entry = [TechnicalSignal(indicator="bollinger_bands", signal_type="buy")]
        exit_ = [TechnicalSignal(indicator="bollinger_bands", signal_type="sell")]
    elif st == "breakout":
        entry = [TechnicalSignal(indicator="breakout", signal_type="buy", lookback_period=state.lookback_days or 20)]
    elif st == "volume_spike":
        entry = [TechnicalSignal(indicator="volume_spike", signal_type="buy", period=state.volume_period or 20)]
    elif st == "value":
        filters = [
            FundamentalFilter(metric="pbr", operator="<=", value=state.value_pbr or 1),
            FundamentalFilter(metric="roe_or_gpa", operator=">=", value=state.value_roe or 10),
        ]
    else:
        return None

    # 옵션 진입 게이트 필터(추세·거래대금·RSI 결합) — 진입 신호와 AND 결합된다.
    entry_filters: list = []
    if state.trend_filter_ma:
        entry_filters.append(TechnicalSignal(indicator="ema", signal_type="buy",
                                             period=state.trend_filter_ma, mode="above"))
    if state.liquidity_min:
        entry_filters.append(TechnicalSignal(indicator="trading_value", signal_type="buy",
                                             value=state.liquidity_min))
    if state.rsi_filter:
        entry_filters.append(TechnicalSignal(indicator="rsi", signal_type="buy",
                                             period=14, operator="<", value=state.rsi_filter))

    single = state.single_symbol is not None
    theme = bool(state.theme_symbols)
    return ParsedStrategy(
        description=synthesize_prompt(state),
        universe=_UNIVERSE_DSL.get(state.universe or "KOSPI", ["KOSPI"]),
        sector=None if (single or theme) else state.sector,
        # 단일 종목 모드: 지정 종목·집중 보유·리밸런싱 없음(엔진 계약 FR-STR-068).
        # 테마 종목 목록(FR-STR-071)도 같은 지정 종목 계약을 재사용한다(universe 무시).
        target_symbols=(state.theme_symbols if theme
                        else [state.single_symbol] if single else []),
        # 시작일 클램프 없음 — 자동 적용 전환(2026-07-25) 후 목록 확인 시점(theme_first_date)
        # 으로 백테스트를 조용히 자르지 않는다(1개월짜리 침묵 축소 방지). 시점 편향은
        # 파싱 경로의 notices가 고지한다.
        backtest_start_date=None,
        fundamental_filters=filters,
        entry_signals=entry,
        exit_signals=exit_,
        entry_filters=entry_filters,
        ranking_metric=ranking_metric,
        ranking_lookback_days=ranking_lookback_days,
        max_positions=1 if single else (state.holding_count or 10),
        hold_period_days=state.hold_period_days,
        rebalancing_period="none" if single else (state.rebalance_cycle or "none"),
        stop_loss_pct=state.stop_loss_pct,
        take_profit_pct=state.take_profit_pct,
        trailing_stop_pct=state.trailing_stop_pct,
    )


# ─── 종료/리셋 안내 문구 ─────────────────────────────────────────────────────────

# [규제 안전] 능력 고지일 뿐 특정 업종을 권하지 않는다 — 예시는 종목 수 상위의 중립 나열.
SECTOR_UNSUPPORTED_NOTICE = (
    "말씀하신 업종/테마는 아직 지원 목록에 없어 업종 제한 없이 진행돼요. "
    "반도체·이차전지·바이오/제약·자동차·기계/장비·소프트웨어/플랫폼 같은 지원 업종을 "
    "말씀해 주시면 그 업종 종목만 대상으로 할 수 있어요."
)

# 미해결 업종을 조용히 강등하기 전에 한 번 되묻는다 — 오타('재약주'→'제약주')·목록 밖 표현을
# 사용자가 정정할 기회를 준다(예시는 종목 수 상위의 중립 나열 — 규제상 특정 업종을 권하지 않음).
SECTOR_REASK_PROMPT = (
    "말씀하신 업종/테마를 지원 목록에서 인식하지 못했어요(오타일 수도 있어요). "
    "어떤 업종을 말씀하신 건지 다시 알려주시겠어요? 아래에서 고르거나 직접 입력해 주세요. "
    "업종 제한 없이 진행하려면 '업종 상관없음'이라고 답해 주세요."
)
SECTOR_REASK_SUGGESTIONS = ("반도체", "이차전지", "바이오/제약", "자동차", "업종 상관없음")


def _resolve_sector_answer(text: str) -> Optional[Union[str, List[str]]]:
    """되묻기 답으로 받은 업종 표현을 정본 섹터명으로 결정적 해석한다.

    맨 용어('제약'·'반도체')는 normalize_sector가, 큐 동반('제약주'·'제약 관련주')은
    _extract_sector가 잡는다 — 둘 다 시도해 되묻기 답의 여러 형태를 모두 커버한다."""
    from engine.nl_parser import _extract_sector
    from engine.universe_pit import normalize_sector
    return _extract_sector(text) or normalize_sector((text or "").strip())

CANCEL_REPLY = "알겠습니다. 전략 구성을 취소했어요. 다른 투자 아이디어가 있으면 언제든 말씀해 주세요."
EXIT_REPLY = "네, 다른 질문도 도와드릴게요. 무엇이 궁금하신가요?"
RESTART_PREFIX = "처음부터 새로 구성해볼게요.\n\n"


# ─── 오케스트레이션 ──────────────────────────────────────────────────────────────

# 테마 유니버스 되묻기(FR-STR-071) — 후보 종목 수 상한(파싱 경로 _THEME_COMPANY_CHIP_MAX와 동률).
_THEME_CHIP_MAX = 10


def _theme_companies(text: Optional[str]) -> Optional[dict]:
    """문장 속 테마의 학습·검증된 관련 상장사 조회(없음·실패=None). knowledge_graph 위임.

    학습 앵커는 Concept Universe(FR-STR-072) 확장 뷰(theme_backtest_companies)로 조회한다 —
    직접 학습 엣지 몇 건이 컨셉을 대표하지 못하던 'bts 관련 종목' 사고 2차(2026-07-25)."""
    if not text:
        return None
    try:
        from engine.knowledge_graph import theme_backtest_companies
        theme = theme_backtest_companies(text)
    except Exception:  # noqa: BLE001 — 테마 조회 실패가 빌더를 막으면 안 된다
        return None
    return theme if theme and theme.get("companies") else None


def _theme_patch(theme: dict) -> dict:
    """테마 관련 검증 상장사를 되묻기 없이 지정 종목으로 즉시 확정한다(FR-STR-071b ④ 개정,
    사용자 결정 2026-07-25 — 종전 '이 종목들로만 vs 업종 전체' 되묻기 폐지). 업종 근사는
    해제한다 — 관련 종목엔 타업종(넷마블=플랫폼·신세계=유통)이 섞여 있어 sector 필터가
    남으면 방금 확정한 종목을 도로 걸러낸다(칩 답 핸들러와 동일 계약)."""
    companies = theme["companies"][:_THEME_CHIP_MAX]
    return {
        "theme_term": theme.get("term"),
        "theme_candidates": [{"symbol": c["symbol"], "name": c["name"]} for c in companies],
        "theme_first_date": theme.get("first_known_date"),
        "theme_symbols": [c["symbol"] for c in companies],
        "theme_label": ", ".join(c["name"] for c in companies),
        "theme_reask_done": True,
        "sector": None,
    }


def _consume_sector_notice(
    state: BuilderState,
    sector_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> tuple[Optional[str], Optional[tuple[str, list[str]]], BuilderState]:
    """미해결 업종 언급을 처리한다 → (notice, reask, state).

    결정적 정규화가 실패한 언급('원자로 관련주')도 지원 업종의 하위 테마면 LLM이 정본
    업종으로 매핑할 수 있다(성공 시 sector 반영 → 요약 배지까지 관통). resolver 출력은
    normalize_sector로 재검증한다. LLM이 매핑하지 못하면 조용히 전체 시장으로 강등하지
    않고 사용자에게 한 번 되묻는다(reask=(질문, 칩)). 되묻기 답은 step의 전용 분기
    (_answer_sector_reask)에서 종결하므로 reask_done 상태로 여기 다시 오지 않는다.
    LLM 시드나 후속 입력이 이미 정본 업종을 채웠으면 조용히 플래그만 정리한다.

    해석(그라운딩 검색 포함) 후 테마의 관련 상장사가 학습·검증돼 있으면 되묻기 없이
    지정 종목으로 즉시 확정한다(_theme_patch — FR-STR-071b ④ 개정, 사용자 결정
    2026-07-25). 약한 힌트(sector_hint_weak)는 해석 실패 시 안내 없이 조용히 해제한다."""
    if not state.sector_unresolved:
        return None, None, state
    cleared = {
        "sector_unresolved": False, "sector_hint": None,
        "sector_reask_done": False, "sector_hint_weak": False,
    }
    if state.sector is not None:
        return None, None, state.model_copy(update=cleared)
    if not state.sector_reask_done:
        hint = state.sector_hint
        canonical = None
        if sector_resolver is not None and hint:
            from engine.universe_pit import normalize_sector  # 지연 import(무거운 엔진 모듈)

            try:
                canonical = normalize_sector(sector_resolver(hint))
            except Exception:  # noqa: BLE001 — LLM 실패 시 되묻기로 안전 폴백
                canonical = None
        # 해석 결과와 무관하게, 그라운딩이 관련 상장사를 알면 지정 종목으로 즉시 확정한다
        # (업종 매핑 실패여도 종목 목록이 문자 그대로의 해석 — '소부장'. 되묻기 폐지,
        # 사용자 결정 2026-07-25. _theme_patch가 sector 근사도 해제한다).
        theme = _theme_companies(hint)
        if theme:
            new_state = state.model_copy(update={**cleared, **_theme_patch(theme)})
            return None, None, new_state
        if canonical:
            return None, None, state.model_copy(update={**cleared, "sector": canonical})
        if state.sector_hint_weak:
            # 약한 힌트(미지 테마어 추정)는 오탐일 수 있다 — 엉뚱한 업종 되묻기로 새지
            # 않고 조용히 해제한다(업종 제한 없음 = 기존 기본 동작).
            return None, None, state.model_copy(update=cleared)
        return None, (SECTOR_REASK_PROMPT, list(SECTOR_REASK_SUGGESTIONS)), \
            state.model_copy(update={"sector_reask_done": True})
    # 방어적 폴백: 되묻기 답은 전용 분기가 처리하므로 정상적으로 여기 도달하지 않는다.
    return SECTOR_UNSUPPORTED_NOTICE, None, state.model_copy(update=cleared)


def _answer_sector_reask(
    state: BuilderState,
    text: str,
    sector_resolver: Optional[Callable[[str], Optional[str]]],
) -> StepResult:
    """업종 되묻기(reask)에 대한 답을 종결적으로 처리한다(무한 되묻기 방지 — 여기서 항상 종결).

    지원 업종이면 반영, '업종 상관없음'이면 안내 없이 제한 없이 진행, 그 외엔 LLM 1회 해석 후
    실패 시 미지원 안내와 함께 전체 시장으로 진행한다."""
    from engine.nl_parser import _SECTOR_AGNOSTIC_RE, _compact
    from engine.universe_pit import normalize_sector

    agnostic = bool(_SECTOR_AGNOSTIC_RE.search(_compact(text)))
    resolved = None if agnostic else _resolve_sector_answer(text)
    if resolved is None and not agnostic and sector_resolver is not None:
        try:
            resolved = normalize_sector(sector_resolver(text))
        except Exception:  # noqa: BLE001 — LLM 실패 시 안내로 안전 폴백
            resolved = None

    cleared = {"sector_unresolved": False, "sector_hint": None, "sector_reask_done": False}
    if resolved:
        new_state = state.model_copy(update={**cleared, "sector": resolved})
        notice = None
    else:
        new_state = state.model_copy(update=cleared)
        notice = None if agnostic else SECTOR_UNSUPPORTED_NOTICE

    if required_missing(new_state) is None:
        return StepResult(state=new_state, status="confirmed",
                          prompt=synthesize_prompt(new_state),
                          notices=[notice] if notice else [])
    msg, sug = next_question(new_state, just_filled={"sector"} if resolved else None)
    if notice:
        msg = notice + "\n\n" + msg
    return StepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")


# 테마 되묻기 답 판정 — 칩 문구('이 종목들로만 백테스트' / '~업종 전체로 백테스트')와
# 자유 표현을 모두 커버한다. 종목 선택은 '종목' 어휘가 있고 업종/전체 어휘가 없을 때만.
def step(
    state: BuilderState,
    text: str,
    risk_extractor: Optional[Callable[[str], dict]] = None,
    sector_resolver: Optional[Callable[[str], Optional[str]]] = None,
) -> StepResult:
    """빌더 모드의 한 턴을 처리한다.

    빈 입력은 상태를 바꾸지 않고 현재(첫) 질문을 그대로 보여준다 — 빌더 진입 직후
    사용자의 후속 입력을 기다리지 않고 첫 질문을 능동적으로 띄우는 데 쓴다.

    risk_extractor: 청산 조건 자유 입력 단계에서 정규식이 키워드는 봤지만 값을 못 뽑았을
    때 호출하는 LLM 보강 파서(text -> 청산 필드 dict). None이면 정규식만으로 동작한다.
    sector_resolver: 결정적 정규화가 실패한 업종/테마 언급을 정본 업종으로 매핑하는 LLM
    해석기(text -> 정본 섹터명|None). None이거나 실패하면 미지원 안내로 폴백한다.
    """
    if not (text or "").strip():
        notice, reask, state = _consume_sector_notice(state, sector_resolver)
        if reask:
            prompt, sug = reask
            return StepResult(state=state, reply=prompt, suggestions=sug, status="collecting")
        if required_missing(state) is None:
            return StepResult(state=state, status="confirmed", prompt=synthesize_prompt(state),
                              notices=[notice] if notice else [])
        msg, sug = next_question(state)
        if notice:
            msg = notice + "\n\n" + msg
        return StepResult(state=state, reply=msg, suggestions=sug, status="collecting")

    ctrl = detect_control(text)
    if ctrl == "cancel":
        return StepResult(state=BuilderState(), reply=CANCEL_REPLY, status="exited")
    if ctrl == "exit":
        return StepResult(state=BuilderState(), reply=EXIT_REPLY, status="exited")
    if ctrl == "restart":
        # "처음부터 다시. 이번엔 코스닥으로"처럼 리셋과 함께 말한 조건은 버리지 않고
        # 새 상태의 시드로 쓴다(BF-18). 단일 종목 모드는 대상 종목을 유지한 채 재시작한다.
        fresh = seed_state(text)
        if state.single_symbol is not None:
            fresh = fresh.model_copy(update={
                "single_symbol": state.single_symbol, "single_label": state.single_label,
            })
        if required_missing(fresh) is None:
            return StepResult(state=fresh, status="confirmed", prompt=synthesize_prompt(fresh))
        msg, sug = next_question(fresh)
        return StepResult(state=fresh, reply=RESTART_PREFIX + msg, suggestions=sug, status="reset")

    # 업종 되묻기(reask)를 이미 한 상태면, 이번 입력은 그 업종 답으로 종결 처리한다
    # (지원 업종 반영 / '업종 상관없음' 진행 / 실패 시 안내 — 무한 되묻기 없음).
    if state.sector_unresolved and state.sector_reask_done and state.sector is None:
        return _answer_sector_reask(state, text, sector_resolver)

    expecting = required_missing(state)

    # 용어 질문("손절이 뭐야?")은 필드 답변이 아니다 — 같은 질문을 말없이 반복하는 대신
    # 짧은 객관적 정의를 알려주고 현재 질문을 이어간다(상태 불변). 글로서리에 없는 용어도
    # 정의 질문이면 필드 파싱으로 넘기지 않는다 — "볼린저가 뭐야?"가 전략 유형을 조용히
    # 확정하던 사고(BF-03) 방지. (자유 서술 단계는 제외 — 서술 안의 '뜻' 어휘 오탐 방지.)
    definition = _glossary_answer(text)
    if (definition is None and expecting != "entry_rule"
            and _DEFINITION_MARKER_RE.search(text)
            and not _NUM_RE.search(text) and len(text.strip()) <= 30):
        definition = GLOSSARY_FALLBACK_REPLY
    if definition is not None:
        msg, sug = next_question(state)
        return StepResult(
            state=state, reply=definition + "\n\n" + msg, suggestions=sug, status="collecting"
        )

    # 빌더 중 특정 종목 지정 요청("그냥 삼성전자만 테스트할래") — 빌더는 분류기를 거치지
    # 않아 조용히 무시되던 요청(BF-11). 종목명이 실제로 인식될 때만 안내한다(상태 불변).
    if (state.single_symbol is None and expecting != "entry_rule"
            and _SINGLE_SWITCH_CUE_RE.search(text)):
        try:  # 지연 import — 종목 마스터 로딩은 cue가 있을 때만
            from stock_analysis.symbol_resolver import find_in_text
            refs = find_in_text(text)
        except Exception:  # noqa: BLE001 — 종목 인식 실패 시 일반 흐름 유지
            refs = []
        if refs:
            msg, sug = next_question(state)
            return StepResult(
                state=state, reply=SINGLE_SWITCH_REPLY.format(name=refs[0].name) + "\n\n" + msg,
                suggestions=sug, status="collecting",
            )

    # 단일 종목 모드: 종목 선별형 유형(모멘텀 랭킹·가치 스크리닝)을 고르면 조용히 무시하지
    # 않고 이유를 설명하며 시계열 진입 방식으로 되묻는다(FR-STR-068b).
    if expecting == "strategy_type" and state.single_symbol is not None:
        blocked = _SINGLE_ASSET_BLOCKED_TYPES.get(_parse_strategy_type(text) or "")
        if blocked:
            msg, sug = next_question(state)
            return StepResult(
                state=state, reply=blocked + "\n\n" + msg, suggestions=sug, status="collecting"
            )

    # ETF 유니버스에서 가치 전략 선택 — 조용히 되묻지 않고 이유를 설명한다(BF-12).
    if (expecting == "strategy_type" and state.universe == "ETF"
            and _parse_strategy_type(_correction_focus(text)) == "value"):
        msg, sug = next_question(state)
        return StepResult(
            state=state, reply=ETF_VALUE_BLOCKED_REPLY + "\n\n" + msg,
            suggestions=sug, status="collecting",
        )

    # 청산 단계는 범위 검증 안내까지 함께 받는다(BF-08) — 그 외 단계는 공용 파서.
    risk_range_notes: List[str] = []
    if expecting == "risk":
        patch, risk_range_notes = _parse_risk_ex(text)
    else:
        patch = parse_input(text, state, expecting)

    # 단일 종목 모드에서 '직접 입력'으로 받은 자유 서술 진입 조건: 알려진 유형에 매칭되지
    # 않아도 조건 서술 큐가 있으면 custom 진입 규칙으로 바로 저장한다 — '직접 설명하기' 칩
    # 제거 후에도 같은 질문만 반복되는 막다른 길을 막는다.
    if (expecting == "strategy_type" and state.single_symbol is not None
            and "strategy_type" not in patch
            and len(text.strip()) >= 5  # 맨숫자·한두 글자 답은 서술로 보지 않는다
            and _ENTRY_DESCRIPTION_CUE_RE.search(text)):
        patch = {"strategy_type": "custom", "entry_rule": text.strip()}

    # 청산 조건 자유 입력: 정규식이 키워드를 봤는데 값을 못 뽑았으면 LLM으로 보강·검증한다.
    if expecting == "risk" and risk_extractor is not None and _risk_needs_llm(text, patch):
        try:
            llm_patch = risk_extractor(text) or {}
        except Exception:  # noqa: BLE001 — LLM 실패 시 정규식 결과로 안전 폴백
            llm_patch = {}
        patch = _merge_risk(patch, llm_patch)

    # 청산 조건 거부("없음"·"필요 없어")는 같은 질문을 그대로 반복하지 않고,
    # 청산 조건이 왜 필요한지 설명하며 되묻는다(필수 설계 유지, 침묵 루프 방지).
    if expecting == "risk" and not patch and _is_risk_refusal(text):
        _, sug = next_question(state)
        return StepResult(state=state, reply=RISK_REQUIRED_REPLY, suggestions=sug, status="collecting")

    new_state = state.model_copy(update=patch)
    notice, reask, new_state = _consume_sector_notice(new_state, sector_resolver)
    if reask:
        prompt, sug = reask
        return StepResult(state=new_state, reply=prompt, suggestions=sug, status="collecting")
    # 확인 도입부는 실제로 채워진 값만 다룬다 — 유형 변경 리셋(None/False)이 직전 답변으로
    # 오인돼 엉뚱한 확인 문장("추가 필터 없이…")이 나가지 않게 한다.
    just_filled = {k for k, v in patch.items() if v not in (None, False, 0)}
    if new_state.sector and "sector" not in patch and state.sector is None:
        just_filled.add("sector")  # LLM 해석으로 채워진 업종도 확인 문장으로 알린다

    # 필수 필드가 모두 채워지면 중간 요약 없이 곧바로 합성→백테스트 파싱으로 넘긴다.
    # (전략 요약 카드 + 검증이 곧 확인 단계이므로 별도 텍스트 요약은 중복이다.)
    if required_missing(new_state) is None:
        return StepResult(state=new_state, status="confirmed", prompt=synthesize_prompt(new_state),
                          notices=[n for n in [notice, *risk_range_notes] if n])

    # 미인식/범위 밖 입력 안내 — 같은 질문을 말없이 반복하지 않는다(BF-09/15).
    hint: Optional[str] = None
    if not patch:
        new_state = new_state.model_copy(update={"miss_streak": state.miss_streak + 1})
        if risk_range_notes:
            hint = " ".join(risk_range_notes)
        elif expecting == "value_params" and _value_direction_conflict(text):
            hint = VALUE_DIRECTION_REPLY
        elif expecting in _PARAM_HINTS and (_NUM_RE.search(text) or expecting == "filters"):
            hint = _PARAM_HINTS[expecting]
        elif new_state.miss_streak >= 2:
            hint = UNRECOGNIZED_HINT
    elif state.miss_streak:
        new_state = new_state.model_copy(update={"miss_streak": 0})

    msg, sug = next_question(new_state, just_filled=just_filled)
    prefix_parts = [notice] if notice else []
    if patch and risk_range_notes:  # 일부 값만 유효했던 경우 제외된 값의 사유를 알린다
        prefix_parts.extend(risk_range_notes)
    if hint:
        prefix_parts.append(hint)
    if prefix_parts:
        msg = "\n\n".join(prefix_parts + [msg])
    return StepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")
