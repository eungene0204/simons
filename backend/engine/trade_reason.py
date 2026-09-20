"""매매 사유의 한국어 정본 템플릿과 구조화 표현.

거래 내역의 '매매사유'는 엔진이 만드는 표시 문구다. 표시 번역은 프론트 t() 소관이라
(lib/i18n) 엔진은 **완성 문장 대신 한국어 정본 템플릿과 치환 인자**를 싣는다 — 값이 박힌
문장("252일 신고가 돌파")은 값마다 사전 키가 달라져 /us에서 번역할 수 없다.
(backend/stream_progress.py의 진행 문구와 같은 계약.)

사유 하나는 세그먼트 리스트로 표현한다.

    {"t": "<한국어 정본 템플릿>", "a": [인자...], "m": [금액 인자 index...]}  # 번역 대상
    {"s": "<리터럴>"}                                                       # 구분자·괄호

인자에는 세그먼트를 중첩할 수 있다(예: 지표 라벨·연산자 낱말). 금액 인자(m)는 통화가
지역마다 다르므로 값만 싣고 표기는 렌더러가 만든다 — 한국어는 "1,013원", /us는 "$1,013".

엔진 내부(신호 배열·오버라이드 맵)는 이 세그먼트 리스트를 JSON으로 인코딩한 문자열로
나른다(기존 문자열 슬롯을 그대로 쓴다). 밖으로 나갈 때 result_handler가 한국어 문장으로
렌더링해 `condition`에 싣고, 세그먼트는 `conditionParts`에 함께 싣는다.

새 템플릿을 추가하면 lib/i18n/en.ts에도 같은 원문을 키로 넣는다
(tests/trade-reason-i18n.test.ts가 이 파일을 스캔해 강제한다).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

Segment = Dict[str, Any]

# ── 조건 서술 (engine/signals.py) ────────────────────────────────────────────
MA_GOLDEN_CROSS = "{0}일선-{1}일선 골든크로스"
MA_DEAD_CROSS = "{0}일선-{1}일선 데드크로스"
MA_PRICE_CROSS_UP = "종가가 {0}일선 상향 돌파"
MA_PRICE_CROSS_DOWN = "종가가 {0}일선 하향 이탈"
MA_STAY_ABOVE = "{0}일선이 {1}일선 위 유지"
MA_STAY_BELOW = "{0}일선이 {1}일선 아래 유지"
MA_PRICE_STAY_ABOVE = "종가가 {0}일선 위 유지"
MA_PRICE_STAY_BELOW = "종가가 {0}일선 아래 유지"
RSI_REBOUND_UP = "RSI {0} 상향 돌파(과매도 반등)"
RSI_REBOUND_DOWN = "RSI {0} 하향 돌파"
RSI_LEVEL = "RSI {0} {1}"
EMA_STAY_ABOVE = "EMA{0}이 EMA{1} 위 유지"
EMA_STAY_BELOW = "EMA{0}이 EMA{1} 아래 유지"
EMA_GOLDEN_CROSS = "EMA{0}-EMA{1} 골든크로스"
EMA_DEAD_CROSS = "EMA{0}-EMA{1} 데드크로스"
EMA_PRICE_STAY_ABOVE = "종가가 EMA{0} 위 유지"
EMA_PRICE_STAY_BELOW = "종가가 EMA{0} 아래 유지"
EMA_PRICE_CROSS_UP = "가격 EMA{0} 상향 돌파"
EMA_PRICE_CROSS_DOWN = "가격 EMA{0} 하향 돌파"
MACD_ZERO_UP = "MACD 제로선 상향 돌파"
MACD_ZERO_DOWN = "MACD 제로선 하향 돌파"
MACD_GOLDEN_CROSS = "MACD 골든크로스"
MACD_DEAD_CROSS = "MACD 데드크로스"
STOCHASTIC_LEVEL = "Stochastic K {0} {1}"
STOCHASTIC_GOLDEN_CROSS = "Stochastic 골든크로스"
STOCHASTIC_DEAD_CROSS = "Stochastic 데드크로스"
CCI_LEVEL = "CCI({0}) {1} {2}"
ADX_LEVEL = "ADX {0} {1} (추세 강도)"
WILLIAMS_R_LEVEL = "Williams %R({0}) {1} {2}"
MFI_LEVEL = "MFI({0}) {1} {2}"
ROC_LEVEL = "ROC({0}) {1} {2} (모멘텀)"
RELATIVE_RETURN_LEVEL = "시장 대비 초과수익률({0}일) {1}%p {2}"
# 실측값 동봉 — "0%p 이상"만 보이면 얼마나 앞섰는지 읽을 수 없다(2026-09-13 사용자 지적).
# {1}=그 봉의 실측 초과수익률(부호 포함, 소수 1자리). 기준값은 싣지 않는다(사용자 지시).
RELATIVE_RETURN_MEASURED = "시장 대비 초과수익률({0}일) {1}%p"
VOLATILITY_LEVEL = "변동성({0}일, 연환산) {1}% {2}"
PRICE_LEVEL = "현재가 {0} {1}"
BOLLINGER_LOWER = "볼린저 밴드 하단 돌파(매수)"
BOLLINGER_UPPER = "볼린저 밴드 상단 돌파(매도)"
TRADING_VALUE = "거래대금 {0}억 이상"
VOLUME_OBV_GOLDEN_CROSS = "거래량 OBV 골든크로스"
VOLUME_OBV_DEAD_CROSS = "거래량 OBV 데드크로스"
VOLUME_RATIO = "거래량이 {0}일 평균의 {1}배 {2}"
TRADING_VALUE_RATIO = "거래대금이 {0}일 평균의 {1}배 {2}"
BREAKOUT_HIGH = "{0}일 신고가 돌파"
BREAKOUT_LOW = "{0}일 신저가 돌파"
BREAKOUT_HIGH_52W = "52주 신고가 돌파"
BREAKOUT_LOW_52W = "52주 신저가 돌파"
AI_UP_BUY = "AI {0}% 상승 확률 {1} 이상 (매수)"
AI_UP_SELL = "AI {0}% 상승 확률 {1} 이하 (매도)"
AI_DOWN_BUY = "AI {0}% 하락 확률 {1} 이하 (안전 진입)"
AI_DOWN_SELL = "AI {0}% 하락 확률 {1} 이상 (위험 청산)"
PRICE_LIMIT_BELOW = "현재가 {0} 이하"
PRICE_LIMIT_ABOVE = "현재가 {0} 이상"
PRICE_LIMIT_EXIT = "가격 제한 청산"
MAX_HOLDING_EXPIRY = "최대 {0}일 보유 만료"
TRAILING_STOP_COND = "트레일링 스탑 {0}%"
FUNDAMENTAL_LEVEL = "{0} {1} {2}"
FUNDAMENTAL_AMOUNT_LEVEL = "{0} {1}억 {2}"

# 연산자 낱말 — LLM 해석이 아니라 조건의 operator 표기에서 결정된다.
OP_GTE = "이상"
OP_LTE = "이하"
# 엄격 비교(>, <)는 경계값을 포함하지 않는다 — "이상/이하"로 적으면 PER > 0 전략의 사유가
# "PER 0 이상"으로 찍혀 조건과 어긋난다(2026-09-17 PER·PBR 워크스루 실측).
OP_GT = "초과"
OP_LT = "미만"
OP_EQ = "동일"

# ── 청산·리스크 사유 (engine/result_handler.py · engine/simulator.py) ────────
ENTRY_SIGNAL_FALLBACK = "매수 조건 충족 (전략 시그널)"
EXIT_STRATEGY_SIGNAL = "전략 매도 조건 충족"
STOP_LOSS_PCT = "손절매 실행 (-{0}%)"
STOP_LOSS = "손절매 실행"
TRAILING_STOP_PCT = "트레일링 스탑 (-{0}%)"
TRAILING_STOP_EXEC_PCT = "트레일링 스탑 실행 (-{0}%)"
TRAILING_STOP_EXEC = "트레일링 스탑 실행"
TAKE_PROFIT_PCT = "익절매 실행 (+{0}%)"
TAKE_PROFIT = "익절매 실행"
HOLDING_EXPIRED_DAYS = "보유 기간 만료 ({0}거래일 보유)"
HOLDING_EXPIRED = "보유 기간 만료"
BACKTEST_END = "백테스트 종료"
DATA_END = "데이터 종료"
DELISTED = "상장폐지"
REBALANCE_DROPOUT = "리밸런싱 제외 (목표 종목 이탈)"
# 손절로 목표에서 빠진 종목의 빈자리를 그 리밸런싱일 랭킹의 다음 순위로 채운 매수(v16.12).
# {0}=리밸런싱일 랭킹 순위(1부터) — '상위 N종목 편입 대상' 사유로 적으면 N+1위 종목이 상위 N에
# 든 것처럼 읽힌다.
STOP_LOSS_REFILL = "손절 종목 대체 편입 (리밸런싱일 순위 {0}위)"
# ── 가상계좌 자동매매(라이브 신호) 전용 ───────────────────────────────────────
# 백테스트 청산 사유보다 판정 근거(현재 수익률·임계값)를 함께 싣는다. 2026-09-13 이전에는
# virtual_trader가 f-string으로 완성 문장을 만들어 엔진의 인코딩된 조건 사유와 문자열로
# 이어 붙였고, 그 결과 매매 신호 카드에 인코딩 페이로드가 그대로 노출됐다.
LIVE_STOP_LOSS = "손절 ({0}% ≤ -{1}%)"
LIVE_TAKE_PROFIT = "익절 ({0}% ≥ +{1}%)"
LIVE_TRAILING_STOP = "트레일링스톱 (최고가 {0} 대비 {1}% 하락)"
LIVE_MAX_HOLDING = "최대보유일 초과 ({0}거래일 ≥ {1}거래일)"
LIVE_FORCED_LIQUIDATION = "강제청산 (상장 상태: {0})"
LIVE_RANK_POSITION = " ({0}/{1}위)"
# 예약 주문 집행(신호 후 N거래일 지연 체결) — 원 사유 뒤에 이어 붙는다.
LIVE_DELAYED_FILL = "신호 후 {0}거래일 지연 체결 (신호일 {1})"
REBALANCE_TRIM = "리밸런싱 비중 조정 (목표 비중 초과분 매도)"
# 시장 국면 필터(v16.14) — 지수가 N일 이동평균 아래로 내려가 보유 비중을 목표 노출까지 줄인
# 매도. {0}=지수 이름(KOSPI 등, 번역 대상 아님), {1}=이동평균 기간, {2}=목표 노출 비율(%).
MARKET_REGIME_REDUCE = "시장 국면 비중 축소 ({0} {1}일 이동평균 아래, 목표 노출 {2}%)"
PNL_DETAIL_PROFIT = " [수익률: {0}%, 수익: {1}]"
PNL_DETAIL_LOSS = " [수익률: {0}%, 손실: {1}]"

# ── 랭킹 매수 사유 (backend/backtest_engine.py) ──────────────────────────────
RANKING_RETURN = "최근 {0}거래일 수익률 {1} {2}%{3}"
RANKING_VOLATILITY = "최근 {0}거래일 변동성 {1} {2}%{3}"
RANKING_RELATIVE_RETURN = "최근 {0}거래일 시장 대비 초과수익률 {1} {2}%{3}"
RANKING_COMPOSITE = "{0} 상위 {1}%{2}"
RANKING_FUNDAMENTAL = "{0} {1}상위 {2}%{3}"
RANK_TOP = "상위"
RANK_BOTTOM = "하위"
RANK_LOWEST_FIRST = "낮은 순 "
REBAL_NOTE_QUANTILE = ", {0} 리밸런싱 {1}분위 그룹{2} 편입 대상"
REBAL_NOTE_GROUP_CAP = "(그룹당 {0}종목)"
REBAL_NOTE_PCT = ", {0} 리밸런싱 상위 {1}% 편입 대상"
REBAL_NOTE_TOP_N = ", {0} 리밸런싱 상위 {1}종목 편입 대상"
REBAL_PERIOD_DAILY = "일간"
REBAL_PERIOD_WEEKLY = "주간"
REBAL_PERIOD_MONTHLY = "월간"
REBAL_PERIOD_BIMONTHLY = "격월"
REBAL_PERIOD_QUARTERLY = "분기"
REBAL_PERIOD_YEARLY = "연간"
COMPOSITE_RANK = "복합 순위({0})"
COMPOSITE_RETURN_METRIC = "최근 {0}거래일 수익률"
# 최근 N거래일을 뺀 수익률(v16.14, 12-1 모멘텀). {0}=산정 기간, {1}=최근 제외 기간.
COMPOSITE_RETURN_SKIP_METRIC = "최근 {0}거래일 수익률(최근 {1}거래일 제외)"
RANKING_RETURN_SKIP = "최근 {0}거래일 수익률(최근 {1}거래일 제외) {2} {3}%{4}"
COMPOSITE_RELATIVE_RETURN_METRIC = "최근 {0}거래일 시장 대비 초과수익률"
COMPOSITE_VOLATILITY_METRIC = "최근 {0}거래일 변동성"
COMPOSITE_COMPONENT_HIGH = "{0} 높은"
COMPOSITE_COMPONENT_LOW = "{0} 낮은"

# ── 리터럴 구분자 (번역 대상 아님) ───────────────────────────────────────────
SEP_AND = {"s": " + "}
SEP_MID_DOT = {"s": "·"}
PAREN_OPEN = {"s": "("}
PAREN_CLOSE = {"s": ")"}
# '또는'만은 낱말이라 번역 대상이다.
OR_WORD = "또는"

_PAYLOAD_PREFIX = "\x1eRJ"


def part(template: str, *args: Any, money: Sequence[int] = ()) -> Segment:
    """번역 대상 세그먼트. `money`는 통화 표기를 렌더러에 맡길 인자 index."""
    seg: Segment = {"t": template}
    if args:
        seg["a"] = list(args)
    if money:
        seg["m"] = list(money)
    return seg


def literal(text: str) -> Segment:
    """번역하지 않는 리터럴 세그먼트(구분자·괄호·미매핑 연산자 기호)."""
    return {"s": text}


def join(segment_lists: Sequence[List[Segment]], separator: List[Segment]) -> List[Segment]:
    """세그먼트 묶음들을 구분자로 잇는다."""
    joined: List[Segment] = []
    for i, seg_list in enumerate(segment_lists):
        if i:
            joined.extend(separator)
        joined.extend(seg_list)
    return joined


def or_separator() -> List[Segment]:
    return [literal(" "), part(OR_WORD), literal(" ")]


def format_money_kr(value: Any) -> str:
    try:
        return f"{float(value):,.0f}원"
    except (TypeError, ValueError):
        return f"{value}원"


def _render_arg(arg: Any, is_money: bool) -> str:
    if isinstance(arg, dict):
        return render_kr([arg])
    if isinstance(arg, list):
        return render_kr(arg)
    if is_money:
        return format_money_kr(arg)
    return str(arg)


def render_kr(segments: Sequence[Segment]) -> str:
    """세그먼트를 한국어 정본 문장으로 렌더링한다."""
    out: List[str] = []
    for seg in segments:
        if "s" in seg:
            out.append(str(seg["s"]))
            continue
        template = str(seg.get("t", ""))
        args = seg.get("a") or []
        money = set(seg.get("m") or [])
        text = template
        for i, arg in enumerate(args):
            text = text.replace("{" + str(i) + "}", _render_arg(arg, i in money))
        out.append(text)
    return "".join(out)


def encode(segments: Sequence[Segment]) -> str:
    """엔진 내부 문자열 슬롯에 실을 인코딩. 빈 사유는 빈 문자열."""
    if not segments:
        return ""
    return _PAYLOAD_PREFIX + json.dumps(list(segments), ensure_ascii=False, separators=(",", ":"))


def decode(value: Any) -> Optional[List[Segment]]:
    """인코딩된 사유면 세그먼트 리스트, 아니면 None(과거 결과의 평문 문자열)."""
    if not isinstance(value, str) or not value.startswith(_PAYLOAD_PREFIX):
        return None
    try:
        parsed = json.loads(value[len(_PAYLOAD_PREFIX):])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) else None


def segments_of(value: Any) -> List[Segment]:
    """어떤 사유 값이든 세그먼트로 만든다 — 평문은 리터럴 한 조각."""
    decoded = decode(value)
    if decoded is not None:
        return decoded
    if not value:
        return []
    return [literal(str(value))]


def text(value: Any) -> str:
    """어떤 사유 값이든 한국어 문장으로 만든다(평문은 그대로)."""
    decoded = decode(value)
    if decoded is None:
        return "" if value is None else str(value)
    return render_kr(decoded)


def first_template(value: Any) -> Optional[str]:
    """첫 번역 세그먼트의 템플릿 — 엔진 내부에서 사유 종류를 판별할 때 쓴다.

    구조화 이전에 저장된 평문 사유는 문자열 자체가 판별 키다(캐시·과거 결과 호환).
    """
    decoded = decode(value)
    if decoded is None:
        return str(value) if value else None
    for seg in decoded:
        if "t" in seg:
            return str(seg["t"])
    return None
