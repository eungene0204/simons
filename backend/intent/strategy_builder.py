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

import re
from typing import List, Optional

from pydantic import BaseModel, Field

Universe = str  # "KOSPI" | "KOSDAQ" | "KOSPI_KOSDAQ"
StrategyType = str  # "momentum" | "breakout" | "volume_spike" | "mean_reversion" | "custom"
RebalanceCycle = str  # "daily" | "weekly" | "monthly" | "quarterly" | "yearly"


class BuilderState(BaseModel):
    """전략 빌더 대화 상태. 프론트가 무상태 step 호출 사이에 보관·재전송한다."""

    universe: Optional[Universe] = None
    strategy_type: Optional[StrategyType] = None
    lookback_days: Optional[int] = None       # 모멘텀/돌파 기준 기간(거래일)
    lookback_label: Optional[str] = None       # 표시용 ("3개월", "60일")
    holding_count: Optional[int] = None
    rebalance_cycle: Optional[RebalanceCycle] = None
    entry_rule: Optional[str] = None           # custom 유형의 사용자 서술 진입 조건
    # 청산 조건(모두 선택) — 마지막 단계에서 한 번 묻고, 답하면 risk_done=True로 완료 처리.
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    hold_period_days: Optional[int] = None
    risk_done: bool = False


class StepResult(BaseModel):
    state: BuilderState
    reply: str = ""
    suggestions: List[str] = Field(default_factory=list)
    # collecting=필드 더 받음, confirmed=필수 필드 충족 → 합성 후 바로 백테스트 파싱(전략 요약 카드),
    # reset=상태 초기화 후 빌더 유지, exited=빌더 종료(일반 모드 복귀)
    status: str = "collecting"
    prompt: Optional[str] = None               # confirmed일 때 합성된 백테스트 프롬프트


# ─── 제어어(취소/처음부터/다른 질문) ─────────────────────────────────────────────

_RESTART_RE = re.compile(r"처음부터|새\s*전략|새로\s*(?:시작|만들)|다시\s*시작|리셋", re.IGNORECASE)
_EXIT_RE = re.compile(r"다른\s*질문|딴\s*거|다른\s*거\s*물어|그만\s*할게", re.IGNORECASE)
_CANCEL_RE = re.compile(r"취소|그만|관둘?|관둬|중단|됐어|그만할래", re.IGNORECASE)


def detect_control(text: str) -> Optional[str]:
    """제어어를 감지한다. 우선순위: restart → exit → cancel."""
    t = text or ""
    if _RESTART_RE.search(t):
        return "restart"
    if _EXIT_RE.search(t):
        return "exit"
    if _CANCEL_RE.search(t):
        return "cancel"
    return None


# ─── 필드 파서(짧은 답변 → patch) ────────────────────────────────────────────────

_UNIV_BOTH_RE = re.compile(r"둘\s*다|전체|모두|코스피.{0,4}코스닥|코스닥.{0,4}코스피", re.IGNORECASE)
_UNIV_KOSDAQ_RE = re.compile(r"코스닥|kosdaq", re.IGNORECASE)
_UNIV_KOSPI_RE = re.compile(r"코스피|kospi", re.IGNORECASE)

_TYPE_MOMENTUM_RE = re.compile(r"모멘텀|momentum|최근\s*(?:오른|강한|상승)|수익률\s*상위|상대\s*강도", re.IGNORECASE)
_TYPE_BREAKOUT_RE = re.compile(r"돌파|전고점|신고가|박스권|breakout", re.IGNORECASE)
_TYPE_VOLUME_RE = re.compile(r"거래량|거래\s*급증|volume", re.IGNORECASE)
_TYPE_MEANREV_RE = re.compile(r"과매도|반등|평균\s*회귀|역추세|rsi|mean\s*reversion", re.IGNORECASE)
_TYPE_CUSTOM_RE = re.compile(r"직접|아이디어|내가|제가\s*설명|설명할게|따로\s*있", re.IGNORECASE)

_MONTHS_RE = re.compile(r"(\d+)\s*개월", re.IGNORECASE)
_YEARS_RE = re.compile(r"(\d+)\s*년", re.IGNORECASE)
_DAYS_RE = re.compile(r"(\d+)\s*(?:거래일|일)", re.IGNORECASE)
# "3개월"의 "개"를 보유 수로 오인하지 않도록 "개월"은 제외한다.
_COUNT_RE = re.compile(r"(\d+)\s*(?:종목|개(?!월))", re.IGNORECASE)
_BARE_NUM_RE = re.compile(r"^\s*(\d+)\s*$")

_REBAL_RE: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("daily", re.compile(r"매일|데일리|하루\s*에\s*한", re.IGNORECASE)),
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

_STOP_LOSS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*(?:손절|스탑\s*로스|stop\s*loss)", re.IGNORECASE)
_TAKE_PROFIT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*(?:익절|목표\s*수익|take\s*profit)", re.IGNORECASE)
_TRAILING_RE = re.compile(
    r"(?:트레일링(?:\s*스탑)?|최고가\s*대비)\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE
)
# 보유기간 청산("20일 보유 후 청산", "3개월 보유"). 청산 단계에서만 해석한다.
_HOLD_RISK_RE = re.compile(
    r"(\d+)\s*(개월|달|주|일|거래일)\s*(?:동안\s*)?(?:보유|후\s*청산|뒤\s*청산|지나면|이상\s*보유)",
    re.IGNORECASE,
)


def _parse_universe(text: str) -> Optional[Universe]:
    if _UNIV_BOTH_RE.search(text):
        return "KOSPI_KOSDAQ"
    if _UNIV_KOSDAQ_RE.search(text):
        return "KOSDAQ"
    if _UNIV_KOSPI_RE.search(text):
        return "KOSPI"
    return None


def _parse_strategy_type(text: str) -> Optional[StrategyType]:
    if _TYPE_MOMENTUM_RE.search(text):
        return "momentum"
    if _TYPE_BREAKOUT_RE.search(text):
        return "breakout"
    if _TYPE_VOLUME_RE.search(text):
        return "volume_spike"
    if _TYPE_MEANREV_RE.search(text):
        return "mean_reversion"
    if _TYPE_CUSTOM_RE.search(text):
        return "custom"
    return None


def _parse_rebalance(text: str) -> Optional[RebalanceCycle]:
    for cycle, pat in _REBAL_RE:
        if pat.search(text):
            return cycle
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


def _parse_risk(text: str) -> dict:
    """청산 조건 단계의 답변을 파싱한다. 무엇을 답하든(없음 포함) risk_done=True — 한 번만 묻는다."""
    patch: dict = {"risk_done": True}
    sl = _STOP_LOSS_RE.search(text)
    if sl:
        patch["stop_loss_pct"] = float(sl.group(1))
    tp = _TAKE_PROFIT_RE.search(text)
    if tp:
        patch["take_profit_pct"] = float(tp.group(1))
    tr = _TRAILING_RE.search(text)
    if tr:
        patch["trailing_stop_pct"] = float(tr.group(1))
    hold = _parse_hold_days(text)
    if hold:
        patch["hold_period_days"] = hold
    return patch


def parse_input(text: str, state: BuilderState, expecting: Optional[str]) -> dict:
    """짧은 답변을 전략 필드 patch로 해석한다. 모호한 맨숫자는 현재 묻는 필드(expecting)로 해석."""
    t = text or ""
    patch: dict = {}

    # custom 유형에서 진입 조건을 서술로 받는 중이면, 입력 전체를 진입 규칙으로 저장한다
    # (자유 서술 안의 숫자를 기간/보유수로 오해하지 않도록 다른 파싱을 건너뛴다).
    if expecting == "entry_rule":
        stripped = t.strip()
        if stripped and detect_control(stripped) is None:
            return {"entry_rule": stripped}
        return {}

    # 청산 조건 단계 — 손절/익절/트레일링/보유기간만 해석하고(없음=값 없이) 완료 처리한다.
    if expecting == "risk":
        return _parse_risk(t)

    universe = _parse_universe(t)
    if universe and not state.universe:
        patch["universe"] = universe

    stype = _parse_strategy_type(t)
    if stype and not state.strategy_type:
        patch["strategy_type"] = stype

    rebal = _parse_rebalance(t)
    if rebal:
        patch["rebalance_cycle"] = rebal

    # 기준 기간(모멘텀=개월, 돌파=일). 접미사 우선, 없으면 expecting==lookback일 때 맨숫자.
    effective_type = patch.get("strategy_type") or state.strategy_type
    m_month = _MONTHS_RE.search(t)
    m_year = _YEARS_RE.search(t)
    m_day = _DAYS_RE.search(t)
    if m_year:
        patch["lookback_days"] = int(m_year.group(1)) * 252
        patch["lookback_label"] = f"{m_year.group(1)}년"
    elif m_month:
        patch["lookback_days"] = int(m_month.group(1)) * 21
        patch["lookback_label"] = f"{m_month.group(1)}개월"
    elif m_day:
        patch["lookback_days"] = int(m_day.group(1))
        patch["lookback_label"] = f"{m_day.group(1)}일"

    # 보유 종목 수. 접미사("N개/N종목") 우선.
    m_count = _COUNT_RE.search(t)
    if m_count:
        patch["holding_count"] = int(m_count.group(1))

    # 맨숫자는 현재 묻는 필드로 귀속(둘 다 채우지 않도록 분기).
    bare = _BARE_NUM_RE.match(t)
    if bare and "lookback_days" not in patch and "holding_count" not in patch:
        n = int(bare.group(1))
        if expecting == "lookback_days":
            if effective_type == "breakout":
                patch["lookback_days"] = n
                patch["lookback_label"] = f"{n}일"
            else:
                patch["lookback_days"] = n * 21
                patch["lookback_label"] = f"{n}개월"
        elif expecting == "holding_count":
            patch["holding_count"] = n

    return patch


# ─── 필수 필드 우선순위 ──────────────────────────────────────────────────────────

def required_missing(state: BuilderState) -> Optional[str]:
    """필수 필드 우선순위 중 첫 빈 필드를 반환한다(없으면 None=완성)."""
    if not state.universe:
        return "universe"
    if not state.strategy_type:
        return "strategy_type"
    if state.strategy_type == "custom":
        if not state.entry_rule:
            return "entry_rule"
    elif state.strategy_type in ("momentum", "breakout"):
        if not state.lookback_days:
            return "lookback_days"
    if not state.holding_count:
        return "holding_count"
    if not state.rebalance_cycle:
        return "rebalance_cycle"
    if not state.risk_done:
        return "risk"
    return None


# ─── 응답 생성(다음 질문 / 요약) ─────────────────────────────────────────────────

_UNIVERSE_LABEL = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KOSPI_KOSDAQ": "코스피·코스닥 전체"}
_TYPE_LABEL = {
    "momentum": "모멘텀",
    "breakout": "돌파",
    "volume_spike": "거래량 급증",
    "mean_reversion": "과매도 반등",
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


def next_question(state: BuilderState) -> tuple[str, list[str]]:
    """가장 먼저 비어 있는 필수 필드 하나만 자연스럽게 질문한다(+옵션 칩)."""
    field = required_missing(state)
    prefix = _ack_prefix(state)

    if field == "universe":
        return (
            prefix + "어떤 시장을 대상으로 할까요?",
            ["코스피", "코스닥", "코스피·코스닥 전체"],
        )
    if field == "strategy_type":
        msg = (
            prefix + "어떤 방식으로 종목을 고를까요?\n\n"
            "• 최근 강한 종목을 추종하는 모멘텀 전략\n"
            "• 전고점(신고가)을 돌파할 때 잡는 돌파 전략\n"
            "• 거래량이 급증한 종목을 찾는 전략\n"
            "• RSI 과매도에서 반등을 노리는 전략\n"
            "• 직접 아이디어를 설명하기"
        )
        return (msg, ["모멘텀", "돌파", "거래량 급증", "과매도 반등"])
    if field == "lookback_days":
        if state.strategy_type == "breakout":
            return (prefix + "며칠 신고가(박스권 상단) 돌파를 기준으로 볼까요?", ["20일", "60일", "120일"])
        return (prefix + "최근 몇 개월 수익률을 기준으로 볼까요?", ["1개월", "3개월", "6개월"])
    if field == "entry_rule":
        return (
            prefix + "어떤 조건에서 매수할지 말씀해 주세요. "
            "(예: 'RSI가 30 이하로 떨어지면', '20일선이 60일선을 상향 돌파하면')",
            [],
        )
    if field == "holding_count":
        if state.strategy_type == "momentum":
            return (prefix + "상위 몇 개 종목을 보유할까요?", ["5개", "10개", "20개"])
        return (prefix + "최대 몇 종목까지 보유할까요?", ["5개", "10개", "20개"])
    if field == "rebalance_cycle":
        return (prefix + "얼마나 자주 종목을 교체(리밸런싱)할까요?", ["매주", "매월", "분기마다", "안 함"])
    if field == "risk":
        msg = (
            prefix + "마지막으로 청산 조건을 더할까요? 손절·익절·트레일링 스탑·보유기간을 "
            "자유롭게 말씀해 주세요.\n"
            "(예: '10% 손절', '20% 익절', '최고가 대비 10% 하락 시 청산', '20일 보유 후 청산')\n"
            "필요 없으면 '청산 조건 없음'을 선택하세요."
        )
        return (msg, ["10% 손절", "10% 손절·20% 익절", "최고가 대비 10% 하락 시 청산", "청산 조건 없음"])
    # 필드가 다 찼으면 step()이 confirmed로 보내므로 여기 도달하지 않는다.
    return ("", [])


def _ack_prefix(state: BuilderState) -> str:
    """직전에 채운 필드를 가볍게 확인하는 도입부(자연스러운 흐름)."""
    if state.rebalance_cycle:
        if state.rebalance_cycle == "none":
            return "좋아요. 정기 리밸런싱은 하지 않겠습니다.\n\n"
        return f"좋아요. {_REBAL_LABEL.get(state.rebalance_cycle, '')} 리밸런싱하겠습니다.\n\n"
    if state.holding_count:
        return f"좋아요. 최대 {state.holding_count}종목으로 하겠습니다.\n\n"
    if state.lookback_days and state.strategy_type in ("momentum", "breakout"):
        return f"좋아요. 최근 {state.lookback_label} 기준으로 보겠습니다.\n\n"
    if state.entry_rule:
        return "좋아요. 말씀하신 조건으로 진입하겠습니다.\n\n"
    if state.strategy_type:
        return f"좋아요. {_TYPE_LABEL.get(state.strategy_type, '')} 전략으로 구성해 볼게요.\n\n"
    if state.universe:
        return f"좋아요. {_UNIVERSE_LABEL.get(state.universe, '')} 시장을 대상으로 하겠습니다.\n\n"
    return ""


def _fmt_pct(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


# ─── 백테스트 프롬프트 합성(검증된 한국어 표현) ─────────────────────────────────────

def synthesize_prompt(state: BuilderState) -> str:
    """수집한 필드를 기존 NL 파서가 안정적으로 해석하는 한국어 프롬프트로 합성한다."""
    universe = _UNIVERSE_LABEL.get(state.universe or "KOSPI", "코스피")
    rebal = _REBAL_PHRASE.get(state.rebalance_cycle or "", "")
    n = state.holding_count or 10
    days = state.lookback_days or 63

    if state.strategy_type == "momentum":
        core = f"{universe} 종목 중 최근 {days}일 수익률 상위 {n}개 종목을 매수"
    elif state.strategy_type == "breakout":
        core = f"{universe} 종목 중 최근 {days}일 신고가를 돌파하면 매수, 최대 {n}종목 보유"
    elif state.strategy_type == "volume_spike":
        core = f"{universe} 종목 중 거래량이 평소보다 급증하면 매수, 최대 {n}종목 보유"
    elif state.strategy_type == "mean_reversion":
        core = (
            f"{universe} 종목 중 RSI가 30 이하로 과매도되면 매수하고 70 이상이면 매도, "
            f"최대 {n}종목 보유"
        )
    else:  # custom
        entry = (state.entry_rule or "").strip().rstrip(".")
        core = f"{universe} 종목 중 {entry}, 최대 {n}종목 보유"

    parts = [core]
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


# ─── 종료/리셋 안내 문구 ─────────────────────────────────────────────────────────

CANCEL_REPLY = "알겠습니다. 전략 구성을 취소했어요. 다른 투자 아이디어가 있으면 언제든 말씀해 주세요."
EXIT_REPLY = "네, 다른 질문도 도와드릴게요. 무엇이 궁금하신가요?"
RESTART_PREFIX = "처음부터 새로 구성해볼게요.\n\n"


# ─── 오케스트레이션 ──────────────────────────────────────────────────────────────

def step(state: BuilderState, text: str) -> StepResult:
    """빌더 모드의 한 턴을 처리한다."""
    ctrl = detect_control(text)
    if ctrl == "cancel":
        return StepResult(state=BuilderState(), reply=CANCEL_REPLY, status="exited")
    if ctrl == "exit":
        return StepResult(state=BuilderState(), reply=EXIT_REPLY, status="exited")
    if ctrl == "restart":
        fresh = BuilderState()
        msg, sug = next_question(fresh)
        return StepResult(state=fresh, reply=RESTART_PREFIX + msg, suggestions=sug, status="reset")

    expecting = required_missing(state)
    patch = parse_input(text, state, expecting)
    new_state = state.model_copy(update=patch)

    # 필수 필드가 모두 채워지면 중간 요약 없이 곧바로 합성→백테스트 파싱으로 넘긴다.
    # (전략 요약 카드 + 검증이 곧 확인 단계이므로 별도 텍스트 요약은 중복이다.)
    if required_missing(new_state) is None:
        return StepResult(state=new_state, status="confirmed", prompt=synthesize_prompt(new_state))

    msg, sug = next_question(new_state)
    return StepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")
