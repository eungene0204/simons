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
from typing import Callable, List, Optional

from pydantic import BaseModel, Field

Universe = str  # "KOSPI" | "KOSDAQ" | "KOSPI200" | "KOSPI_KOSDAQ"
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
    # 청산 조건(필수) — 마지막 단계에서 묻고, 하나 이상 인식되면 risk_done=True로 완료 처리.
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

# 코스피200은 '코스피'를 부분 문자열로 포함하므로 반드시 먼저 검사해야 KOSPI로 새지 않는다.
_UNIV_KOSPI200_RE = re.compile(r"코스피\s*200|kospi\s*200|k\s*200|대형주", re.IGNORECASE)
_UNIV_BOTH_RE = re.compile(r"둘\s*다|전체|모두|코스피.{0,4}코스닥|코스닥.{0,4}코스피", re.IGNORECASE)
_UNIV_KOSDAQ_RE = re.compile(r"코스닥|kosdaq", re.IGNORECASE)
_UNIV_KOSPI_RE = re.compile(r"코스피|kospi", re.IGNORECASE)

_TYPE_MOMENTUM_RE = re.compile(
    r"모멘텀|momentum|상대\s*강도|"
    r"최근\s*(?:오른|강한|상승)|많이\s*오른|가장\s*(?:많이\s*)?(?:오른|상승)|"
    r"수익률.{0,5}(?:상위|좋|높)|급등주",
    re.IGNORECASE,
)
_TYPE_GOLDEN_RE = re.compile(r"골든\s*크로스|golden\s*cross|이동\s*평균\s*교차|이평\s*교차|이동\s*평균선?\s*교차", re.IGNORECASE)
_TYPE_MACD_RE = re.compile(r"macd", re.IGNORECASE)
_TYPE_BREAKOUT_RE = re.compile(r"돌파|전고점|신고가|박스권|breakout", re.IGNORECASE)
_TYPE_VOLUME_RE = re.compile(r"거래량|거래\s*급증|volume", re.IGNORECASE)
_TYPE_MEANREV_RE = re.compile(r"과매도|반등|평균\s*회귀|역추세|rsi|mean\s*reversion", re.IGNORECASE)
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
_PCT_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
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
    if _UNIV_KOSPI200_RE.search(text):  # '코스피' 검사보다 먼저(부분 문자열 충돌 방지)
        return "KOSPI200"
    if _UNIV_KOSDAQ_RE.search(text):
        return "KOSDAQ"
    if _UNIV_KOSPI_RE.search(text):
        return "KOSPI"
    return None


def _parse_strategy_type(text: str) -> Optional[StrategyType]:
    if _TYPE_MOMENTUM_RE.search(text):
        return "momentum"
    if _TYPE_GOLDEN_RE.search(text):
        return "golden_cross"
    if _TYPE_MACD_RE.search(text):
        return "macd"
    if _TYPE_BREAKOUT_RE.search(text):
        return "breakout"
    if _TYPE_VOLUME_RE.search(text):
        return "volume_spike"
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
    우선순위: 년 > 개월 > 주 > 일 (긴 단위가 짧은 단위 패턴에 먹히지 않게)."""
    m_year = _YEARS_RE.search(text)
    if m_year:
        return {"lookback_days": int(m_year.group(1)) * 252, "lookback_label": f"{m_year.group(1)}년"}
    m_month = _MONTHS_RE.search(text)
    if m_month:
        return {"lookback_days": int(m_month.group(1)) * 21, "lookback_label": f"{m_month.group(1)}개월"}
    m_week = _WEEKS_RE.search(text)
    if m_week:
        return {"lookback_days": int(m_week.group(1)) * 5, "lookback_label": f"{m_week.group(1)}주일"}
    m_day = _DAYS_RE.search(text)
    if m_day:
        return {"lookback_days": int(m_day.group(1)), "lookback_label": f"{m_day.group(1)}일"}
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
    """청산 조건 단계의 답변을 파싱한다. 청산 조건은 필수이므로, 손절·익절·트레일링·보유기간을
    하나 이상 인식했을 때만 risk_done=True로 완료 처리한다(없으면 같은 질문을 다시 한다)."""
    patch: dict = {}
    patch.update(_parse_sl_tp(text))
    tr = _TRAILING_RE.search(text)
    if tr:
        patch["trailing_stop_pct"] = float(tr.group(1))
    hold = _parse_hold_days(text)
    if hold:
        patch["hold_period_days"] = hold
    if patch:
        patch["risk_done"] = True
    return patch


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


def _merge_risk(regex_patch: dict, llm_patch: dict) -> dict:
    """정규식 결과를 우선하고, 정규식이 놓친 청산 필드만 LLM 결과로 채운다."""
    merged = dict(regex_patch)
    for field in RISK_FIELDS:
        if merged.get(field) is None and llm_patch.get(field) is not None:
            merged[field] = llm_patch[field]
    if any(merged.get(field) is not None for field in RISK_FIELDS):
        merged["risk_done"] = True
    return merged


def parse_input(text: str, state: BuilderState, expecting: Optional[str]) -> dict:
    """짧은 답변을 전략 필드 patch로 해석한다. 모호한 맨숫자는 현재 묻는 필드(expecting)로 해석."""
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
            if m_count and not state.holding_count:
                patch["holding_count"] = int(m_count.group(1))
            return patch
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
    lookback = _parse_lookback(t)
    if lookback:
        patch.update(lookback)

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


def is_empty(state: BuilderState) -> bool:
    """아직 아무 필드도 채워지지 않은 초기 상태인지 판단한다(시드 적용 여부 게이트)."""
    return state == BuilderState()


def seed_state(text: str) -> BuilderState:
    """빌더 진입 시 사용자의 원본 메시지에서 인식 가능한 모든 전략 필드를 미리 채운다.

    [규제 안전/UX] 열린 추천(STOCK_PICK)으로 빌더에 진입하더라도 사용자가 이미 말한
    조건(유니버스·전략유형·기준기간·보유수·리밸런싱·청산)은 다시 묻지 않고, 빠진 필드만
    질문하기 위함이다. 단계별 parse_input과 달리 청산 조건도 단계 무관하게 추출한다."""
    patch: dict = {}
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
    if count:
        patch["holding_count"] = int(count.group(1))
    patch.update(_parse_risk(text))  # 손절/익절/트레일링/보유기간(+risk_done)
    return BuilderState().model_copy(update=patch)


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

_UNIVERSE_LABEL = {"KOSPI": "코스피", "KOSDAQ": "코스닥", "KOSPI200": "코스피200", "KOSPI_KOSDAQ": "코스피·코스닥 전체"}
_TYPE_LABEL = {
    "momentum": "모멘텀",
    "golden_cross": "골든크로스",
    "macd": "MACD",
    "breakout": "돌파",
    "volume_spike": "거래량 급증",
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
            ["코스피", "코스닥", "코스피200", "코스피·코스닥 전체"],
        )
    if field == "strategy_type":
        msg = (
            prefix + "어떤 방식으로 종목을 고를까요?\n\n"
            "• 최근 강한 종목을 추종하는 모멘텀 전략\n"
            "• 단기 이동평균이 장기 이동평균을 뚫는 골든크로스 전략\n"
            "• MACD가 시그널선을 돌파할 때 잡는 전략\n"
            "• 전고점(신고가)을 돌파할 때 잡는 돌파 전략\n"
            "• 거래량이 급증한 종목을 찾는 전략\n"
            "• RSI 과매도에서 반등을 노리는 전략\n"
            "• PBR 낮고 ROE 높은 저평가 우량주를 고르는 가치 전략\n"
            "• 직접 아이디어를 설명하기"
        )
        # "직접 설명하기"는 자유 서술(custom) 진입로 — 선택 시 entry_rule 질문(칩 없음)으로
        # 넘어가 프론트가 채팅창을 다시 보여준다. 가장 오른쪽 칩으로 노출한다.
        return (
            msg,
            ["모멘텀", "골든크로스", "MACD", "돌파", "거래량 급증", "과매도 반등", "저평가 가치주", "직접 설명하기"],
        )
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
_ACK_PRIORITY = (
    "rebalance_cycle", "holding_count", "lookback_days", "entry_rule", "strategy_type", "universe",
)


def _ack_sentence(state: BuilderState, field: str) -> str:
    """단일 필드를 확인하는 완결 문장(마침표 없이)."""
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
    if field == "universe":
        return f"{_UNIVERSE_LABEL.get(state.universe, '')} 시장을 대상으로 하겠습니다"
    return ""


def _seed_summary(state: BuilderState) -> list[str]:
    """시드로 미리 채워진 조건을 짧은 명사구로 요약한다(초기 질문에서 '이해한 내용' 표시)."""
    parts: list[str] = []
    if state.strategy_type:
        parts.append(f"{_TYPE_LABEL.get(state.strategy_type, '')} 전략")
    if state.lookback_days and state.strategy_type in ("momentum", "breakout"):
        parts.append(f"최근 {state.lookback_label} 기준")
    if state.holding_count:
        parts.append(f"{state.holding_count}종목")
    if state.rebalance_cycle:
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
    universe = _UNIVERSE_LABEL.get(state.universe or "KOSPI", "코스피")
    rebal = _REBAL_PHRASE.get(state.rebalance_cycle or "", "")
    n = state.holding_count or 10
    days = state.lookback_days or 63

    if state.strategy_type == "momentum":
        core = f"{universe} 종목 중 최근 {days}일 수익률 상위 {n}개 종목을 매수"
    elif state.strategy_type == "golden_cross":
        core = (
            f"{universe} 종목 중 20일 이동평균이 60일 이동평균을 상향 돌파하는 골든크로스에서 "
            f"매수하고 데드크로스에서 매도, 최대 {n}종목 보유"
        )
    elif state.strategy_type == "macd":
        core = f"{universe} 종목 중 MACD 골든크로스에서 매수, MACD 데드크로스에서 매도, 최대 {n}종목 보유"
    elif state.strategy_type == "value":
        core = f"{universe} 종목 중 PBR 1 이하, ROE 10% 이상인 저평가 우량주를 최대 {n}종목 매수"
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

def step(
    state: BuilderState,
    text: str,
    risk_extractor: Optional[Callable[[str], dict]] = None,
) -> StepResult:
    """빌더 모드의 한 턴을 처리한다.

    빈 입력은 상태를 바꾸지 않고 현재(첫) 질문을 그대로 보여준다 — 빌더 진입 직후
    사용자의 후속 입력을 기다리지 않고 첫 질문을 능동적으로 띄우는 데 쓴다.

    risk_extractor: 청산 조건 자유 입력 단계에서 정규식이 키워드는 봤지만 값을 못 뽑았을
    때 호출하는 LLM 보강 파서(text -> 청산 필드 dict). None이면 정규식만으로 동작한다.
    """
    if not (text or "").strip():
        if required_missing(state) is None:
            return StepResult(state=state, status="confirmed", prompt=synthesize_prompt(state))
        msg, sug = next_question(state)
        return StepResult(state=state, reply=msg, suggestions=sug, status="collecting")

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

    # 청산 조건 자유 입력: 정규식이 키워드를 봤는데 값을 못 뽑았으면 LLM으로 보강·검증한다.
    if expecting == "risk" and risk_extractor is not None and _risk_needs_llm(text, patch):
        try:
            llm_patch = risk_extractor(text) or {}
        except Exception:  # noqa: BLE001 — LLM 실패 시 정규식 결과로 안전 폴백
            llm_patch = {}
        patch = _merge_risk(patch, llm_patch)

    new_state = state.model_copy(update=patch)

    # 필수 필드가 모두 채워지면 중간 요약 없이 곧바로 합성→백테스트 파싱으로 넘긴다.
    # (전략 요약 카드 + 검증이 곧 확인 단계이므로 별도 텍스트 요약은 중복이다.)
    if required_missing(new_state) is None:
        return StepResult(state=new_state, status="confirmed", prompt=synthesize_prompt(new_state))

    msg, sug = next_question(new_state, just_filled=set(patch.keys()))
    return StepResult(state=new_state, reply=msg, suggestions=sug, status="collecting")
