"""전략 골격 슬롯 충족 판정 — 단일 정본(SOT).

"이 전략에서 무엇이 아직 비었나"를 판정하는 곳은 여기 하나다. 이전에는 같은 판정이
네 곳에 각자 구현돼 있었고(planner State의 filled_slots, 백엔드 되묻기 게이트,
프론트 게이트, 빌더), 어휘·기본값 취급·세부 규칙이 서로 달라 이음매마다 사고가 났다:

- 2026-07-28 리밸런싱: '지정 종목 존재=단독'으로 봐 질문 없이 '설정 안 함' 확정
- 2026-07-29 매수 조건 ①: planner가 채워진 슬롯을 재질문(프롬프트 지시로만 금지돼 있었음)
- 2026-07-29 매수 조건 ②: 채택 관문이 "어딘가 비었나"만 물어(다른 슬롯의 공백을 근거로)
  이미 채워진 매수 조건 ask를 통과시킴 — topic은 8슬롯 어휘, 판정은 6조건 게이트
- 2026-07-29 백테스트 기간: 판정을 이 모듈로 모은 **뒤에도** 재질문이 났다. 원인은
  축의 부재 — 신규 상장 코호트는 백테스트 창을 **시스템이 확정**하는데, 판정 축이
  "값이 있나"와 "사용자가 말했나" 둘뿐이라 그 값은 영원히 '미언급'으로 남았다.
  아래 _decided(③)가 그 자리다. **판정을 한 곳에 모으는 것만으로는 부족하고, 그 곳이
  표현할 수 있는 축이 실제 사례를 모두 덮어야 한다.**

특히 기본값 취급이 갈렸다. ParsedStrategy는 유니버스·최대 보유·기간·초기 자본에
기본값을 물질화하므로 **값의 존재는 사용자가 말했다는 증거가 아니다** — 빈 전략조차
'4/8 완료'로 보였다. 그래서 이 모듈은 값 판정과 provenance 판정을 분리하고,
되묻기 목적의 호출자는 require_explicit=True로 provenance를 함께 본다(FR-STR-019k).

세분(field) 9개가 판정 단위이고, 진행 골격(slot) 8개는 그 그룹이다 —
리스크 관리 슬롯만 손절·익절 두 필드를 묶는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence


class FieldStatus(str, Enum):
    """필드의 상태 — `filled` 불리언이 뭉개던 정보를 되살린 축(설계 스펙 § 5).

    `filled`는 "더 물을 것이 없다"만 답한다. 그래서 **해당 없음과 완료가 같은 True**로
    보였고(단독 종목의 리밸런싱이 진행률에 체크로 표시), 기본값이 물질화된 값과 사용자가
    말한 값도 구분되지 않았다. 이 축은 그 셋을 나눈다.

    `filled`의 판정은 바뀌지 않는다 — 이 축은 옆에 붙는 정보이며, 기존 게이트·진행률의
    통과 여부를 바꾸지 않는다(되묻기 흐름 무영향).
    """

    # 값이 없고 아직 결정되지 않았다.
    UNKNOWN = "UNKNOWN"
    # 사용자가 직접 제공했거나 시스템이 확정해 협상 대상이 아니다.
    CONFIRMED = "CONFIRMED"
    # 문맥에서 추론한 값. 확정값처럼 취급하지 않는다.
    INFERRED = "INFERRED"
    # 값은 있으나 사용자가 확인하지 않았다(기본값 물질화·추천값).
    PROVISIONAL = "PROVISIONAL"
    # 값이 있으나 현재 실행할 수 없다(미지원·미해석 지표).
    INVALID = "INVALID"
    # 다른 값이나 조건과 모순된다.
    CONFLICTED = "CONFLICTED"
    # 현재 전략 유형·유니버스에서는 적용할 수 없어 물을 대상이 아니다.
    NOT_APPLICABLE = "NOT_APPLICABLE"


# 값이 있으나 사용자·시스템의 개입이 필요한 상태 — 진행률에서 '확인 필요'로 묶인다.
NEEDS_ATTENTION: frozenset[FieldStatus] = frozenset(
    {FieldStatus.INVALID, FieldStatus.CONFLICTED}
)

# ── 필드(판정 단위) ─────────────────────────────────────────────────────────────
UNIVERSE = "universe"
ENTRY = "entry"
EXIT = "exit"
MAX_POSITIONS = "max_positions"
REBALANCING = "rebalancing"
STOP_LOSS = "stop_loss"
TAKE_PROFIT = "take_profit"
BACKTEST_PERIOD = "backtest_period"
INITIAL_CAPITAL = "initial_capital"

# 진행 순서 = 사용자에게 보이는 골격 순서(유니버스 → 매수 → 매도 → 최대 보유 →
# 리밸런싱 → 리스크 → 기간 → 자본). 되묻기는 이 순서의 첫 공백 하나만 낸다.
FIELD_ORDER: tuple[str, ...] = (
    UNIVERSE, ENTRY, EXIT, MAX_POSITIONS, REBALANCING,
    STOP_LOSS, TAKE_PROFIT, BACKTEST_PERIOD, INITIAL_CAPITAL,
)

# ── 슬롯(진행 골격 8칸) — planner State·진행률 표시가 쓰는 라벨 ──────────────────
SLOT_LABELS: dict[str, str] = {
    UNIVERSE: "유니버스",
    ENTRY: "매수 조건",
    EXIT: "매도 조건",
    MAX_POSITIONS: "최대 보유",
    REBALANCING: "리밸런싱",
    STOP_LOSS: "리스크 관리",
    TAKE_PROFIT: "리스크 관리",
    BACKTEST_PERIOD: "백테스트 기간",
    INITIAL_CAPITAL: "초기 자본",
}
SLOT_ORDER: tuple[str, ...] = (
    "유니버스", "매수 조건", "매도 조건", "최대 보유",
    "리밸런싱", "리스크 관리", "백테스트 기간", "초기 자본",
)

# provenance(사용자가 실제로 말했는지)를 함께 봐야 하는 필드 — ParsedStrategy가
# 기본값을 물질화하는 필드들이다. 나머지(진입·청산·손절·익절)는 기본값이 없어
# 값의 존재가 곧 사용자 입력이다.
PROVENANCE_FIELDS: frozenset[str] = frozenset(
    {UNIVERSE, MAX_POSITIONS, REBALANCING, BACKTEST_PERIOD, INITIAL_CAPITAL}
)


@dataclass(frozen=True)
class SlotStatus:
    field: str
    slot: str
    filled: bool
    question: str
    suggestions: tuple[str, ...]
    # 상태 축(§ 5). filled와 독립이다 — require_explicit=False 레인에서 기본값이
    # 물질화된 필드는 filled=True이면서 status=PROVISIONAL이다(둘 다 사실이다).
    status: FieldStatus = FieldStatus.UNKNOWN


# 되묻기 문구는 판정과 함께 둔다 — 판정과 질문이 떨어져 있으면 슬롯이 늘 때
# 한쪽만 갱신되어 어긋난다(이번 사고의 구조적 원인).
_QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    UNIVERSE: (
        "어떤 시장·종목을 대상으로 할까요?\n\n예: 코스피200, 코스닥 전체",
        ("코스피200 대상으로", "코스닥 전체 대상으로"),
    ),
    ENTRY: (
        "어떤 조건에서 매수할까요?\n\n예: 골든크로스(5일/20일) 발생 시 매수, PER 10 이하",
        ("골든크로스(5일/20일) 발생 시 매수", "RSI 30 이하에서 매수",
         "MACD 골든크로스 매수", "볼린저밴드 하단 터치 시 매수",
         "20일 고점 돌파 시 매수", "거래량 급증 시 매수",
         "PER 10 이하", "ROE 15% 이상"),
    ),
    EXIT: (
        "청산 조건 — 언제 팔까요?\n\n예: 데드크로스(5일/20일) 발생 시 매도, 20일 보유 후 청산",
        ("20일 보유 후 청산", "데드크로스(5일/20일) 발생 시 매도"),
    ),
    MAX_POSITIONS: (
        "포트폴리오에 최대 몇 종목을 담을까요?",
        ("최대 5종목", "최대 10종목", "최대 20종목"),
    ),
    REBALANCING: (
        "포트폴리오 교체 주기(리밸런싱)는 얼마로 할까요?\n\n예: 매월, 분기마다",
        ("매월 리밸런싱", "분기마다 리밸런싱", "리밸런싱 안 함"),
    ),
    STOP_LOSS: (
        "손절 — 손실을 제한할 비율을 정해주세요 (예: 손절 -10%, 손절 -5%)",
        ("손절 -10%", "손절 -5%"),
    ),
    TAKE_PROFIT: (
        "익절 — 목표 수익 비율을 정해주세요 (예: 익절 20%, 익절 10%)",
        ("익절 20%", "익절 10%"),
    ),
    BACKTEST_PERIOD: (
        "어느 기간의 과거 데이터로 백테스트할까요?",
        ("최근 1년 데이터", "최근 3년 데이터", "최근 5년 데이터", "사용 가능한 전체 데이터"),
    ),
    INITIAL_CAPITAL: (
        "초기 투자 자금을 얼마로 설정할까요?",
        ("500만원", "1,000만원", "3,000만원", "5,000만원"),
    ),
}


def _nonempty(value: Any) -> bool:
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return bool(value)


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _has_value(parsed: Any, field: str) -> bool:
    """필드에 값이 있는가(기본값 물질화 포함 — provenance는 별개로 본다)."""
    g = lambda name: getattr(parsed, name, None)  # noqa: E731
    rebal = g("rebalancing_period")
    has_rebalancing = bool(rebal and rebal != "none")
    if field == UNIVERSE:
        # 신규 상장 제한(FR-STR-073)도 유니버스 지정이다 — 기준 일수를 되묻는 중이라
        # 값이 아직 없어도 사용자가 대상을 말한 것이므로 시장을 다시 묻지 않는다.
        return (_nonempty(g("universe")) or _nonempty(g("target_symbols"))
                or _nonempty(g("sector")) or bool(g("new_listing_only")))
    if field == ENTRY:
        # 지정 종목은 진입 조건이 아니다 — 종목이 정해져도 매수 시점 규칙이 없으면
        # 엔진은 매수를 만들지 않는다(빈 조건 그룹=all-False, 0거래).
        return (_nonempty(g("entry_signals")) or _nonempty(g("fundamental_filters"))
                or _nonempty(g("ranking_metric")))
    if field == EXIT:
        return _nonempty(g("exit_signals")) or _positive(g("hold_period_days")) or has_rebalancing
    if field == MAX_POSITIONS:
        return _positive(g("max_positions"))
    if field == REBALANCING:
        return has_rebalancing
    if field == STOP_LOSS:
        return _positive(g("stop_loss_pct"))
    if field == TAKE_PROFIT:
        return _positive(g("take_profit_pct"))
    if field == BACKTEST_PERIOD:
        # provenance 판정(explicit_fields_from_spec)과 같은 필드 집합을 본다. ParsedStrategy의
        # backtest_period는 기본값 "5y"가 물질화돼 실제로 비는 일이 없으므로 이 항들은 방어적
        # 일관성이다 — 두 축이 서로 다른 필드를 보는 상태를 남겨두지 않는다.
        return (_nonempty(g("backtest_period")) or _nonempty(g("backtest_start_date"))
                or _nonempty(g("backtest_end_date")))
    if field == INITIAL_CAPITAL:
        return _positive(g("initial_capital"))
    raise ValueError(f"알 수 없는 슬롯 필드: {field}")


def _decided(parsed: Any, field: str, rebalancing_declined: bool) -> Optional[FieldStatus]:
    """질문이 이미 끝난 필드 — 값 유무·provenance와 무관하게 더 묻지 않는다.

    None이면 '아직 결정되지 않음'이고, FieldStatus면 결정된 이유다. 세 경우가 있고
    **서로 다른 상태**다 — 이전에는 셋 다 filled=True 하나로 뭉개져 있었다:

    ① 구성상 무의미한 질문(단독 종목의 리밸런싱) → NOT_APPLICABLE.
       값이 없는 것이 정상이며, 진행률의 분모에서도 빠져야 한다.
    ② 사용자가 명시적으로 거부한 설정(리밸런싱 안 함) → CONFIRMED.
       사용자가 '안 함'을 결정한 것이므로 확정값이다. 스펙에서 null이라 미언급과
       구분되지 않으므로 호출자가 플래그로 전달한다 — 이 판정을 provenance 쪽에 두면
       require_explicit=False인 레인에서 무시돼 같은 질문이 무한 반복된다.
    ③ 다른 조건이 시스템 차원에서 확정한 값(신규 상장 코호트의 백테스트 창) →
       CONFIRMED. 사용자가 말하지는 않았지만 다른 답이 성립하지 않아 협상 대상이
       아니다(스펙 § 5의 7종에는 '시스템 확정'이 없어 CONFIRMED로 둔다 — 추천값처럼
       확인을 기다리는 PROVISIONAL과 달리, 이 값은 바꿀 수 없다).

    ③이 provenance가 아니라 여기인 이유: provenance는 "사용자가 말했나"만 답한다.
    시스템이 결정했고 협상 대상도 아닌 값은 그 축으로 표현할 수 없어, 영원히
    '미언급'으로 남아 매번 다시 묻힌다(2026-07-29 사고).
    """
    symbols = getattr(parsed, "target_symbols", None) or []
    if field == REBALANCING:
        # 단독 종목(지정 1개)은 교체가 없다. 지정 종목이라도 여럿이면 포트폴리오이므로
        # 묻는다 — '지정 종목 존재=단독'으로 본 2026-07-28 사고.
        if len(symbols) == 1:
            return FieldStatus.NOT_APPLICABLE
        if rebalancing_declined:
            return FieldStatus.CONFIRMED
        return None
    if field == BACKTEST_PERIOD:
        # 신규 상장 코호트(FR-STR-073)는 창 시작이 상장일 하한으로 확정된다 — 그 이전엔
        # 종목이 존재하지 않아 다른 답이 성립하지 않는다. "최근 5년 데이터"를 고를 수
        # 있는 것처럼 물으면 사용자가 고른 답을 클램프가 도로 덮어쓴다.
        if getattr(parsed, "listing_from", None):
            return FieldStatus.CONFIRMED
    return None


def _status_only_not_applicable(parsed: Any, field: str) -> bool:
    """구성상 물을 대상이 아니지만 `filled` 판정은 건드리지 않는 경우.

    _decided에 넣으면 값이 없을 때 filled가 False→True로 뒤집혀 되묻기 흐름이 바뀐다.
    이 축은 표시 전용이므로 filled와 분리한다(기존 게이트 동작 보존).
    """
    symbols = getattr(parsed, "target_symbols", None) or []
    # 지정 종목 모드는 보유 수가 종목 수로 확정된다(_explicit_ok의 같은 판정) —
    # '최대 보유'를 물을 것이 없다는 사실이 이전에는 상태로 드러나지 않았다.
    return field == MAX_POSITIONS and bool(symbols)


def _explicit_ok(parsed: Any, field: str, explicit_fields: Sequence[str]) -> bool:
    """사용자가 그 필드를 실제로 말했는가(provenance). 값 존재와 별개다."""
    if field not in PROVENANCE_FIELDS:
        return True
    symbols = getattr(parsed, "target_symbols", None) or []
    if field == UNIVERSE and symbols:
        return True  # 지정 종목은 그 자체가 유니버스 명시
    if field == MAX_POSITIONS and symbols:
        return True  # 지정 종목 모드는 보유 수가 종목 수로 확정된다
    return field in explicit_fields


def evaluate(
    parsed: Any,
    *,
    explicit_fields: Optional[Iterable[str]] = None,
    require_explicit: bool = False,
    rebalancing_declined: bool = False,
    fields: Optional[Iterable[str]] = None,
    status_overrides: Optional[Dict[str, FieldStatus]] = None,
) -> List[SlotStatus]:
    """골격 필드별 충족 상태를 진행 순서대로 반환한다.

    require_explicit=True면 값이 있어도 사용자가 말하지 않은 필드(provenance 부재)는
    미충족으로 본다 — 기본값을 질문 없이 확정하지 않기 위함(FR-STR-019k).
    fields로 판정 범위를 좁힐 수 있다(레거시 게이트의 6조건 등).

    status_overrides는 이 모듈이 볼 수 없는 상위 판정(검증 리포트의 INVALID·CONFLICTED)을
    상태 축에만 덮어쓴다 — `filled`는 바꾸지 않는다. 지표 미지원·조건 모순은
    ParsedStrategy가 아니라 StrategySpec 검증 단계에서만 알 수 있기 때문이다.
    """
    explicit = list(explicit_fields or [])
    scope = tuple(fields) if fields is not None else FIELD_ORDER
    overrides = status_overrides or {}
    statuses: List[SlotStatus] = []
    for field in FIELD_ORDER:
        if field not in scope:
            continue
        # ── filled 판정: 기존 3축 그대로(동작 불변) ─────────────────────────────
        decided = _decided(parsed, field, rebalancing_declined)
        has_value = _has_value(parsed, field)
        explicit_ok = _explicit_ok(parsed, field, explicit)
        if decided is not None:
            filled = True
        else:
            filled = has_value
            if filled and require_explicit:
                filled = explicit_ok
        # ── 상태 축: filled와 독립으로 산출한다 ────────────────────────────────
        if decided is not None:
            status = decided
        elif _status_only_not_applicable(parsed, field):
            status = FieldStatus.NOT_APPLICABLE
        elif not has_value:
            status = FieldStatus.UNKNOWN
        elif explicit_ok:
            status = FieldStatus.CONFIRMED
        else:
            # 값은 있으나 사용자가 말한 적 없다 — ParsedStrategy가 물질화한 기본값이다.
            # require_explicit 레인에서 되묻는 대상이 바로 이것이다.
            status = FieldStatus.PROVISIONAL
        # 상위 검증 판정은 값의 존재를 전제하므로 UNKNOWN·NOT_APPLICABLE은 덮지 않는다.
        override = overrides.get(field)
        if override is not None and status not in (
            FieldStatus.UNKNOWN, FieldStatus.NOT_APPLICABLE
        ):
            status = override
        question, suggestions = _QUESTIONS[field]
        statuses.append(SlotStatus(
            field=field, slot=SLOT_LABELS[field], filled=filled,
            question=question, suggestions=suggestions, status=status,
        ))
    return statuses


def missing(parsed: Any, **kwargs: Any) -> List[SlotStatus]:
    """아직 비어 있는 필드만 진행 순서대로."""
    return [s for s in evaluate(parsed, **kwargs) if not s.filled]


def next_missing(parsed: Any, **kwargs: Any) -> Optional[SlotStatus]:
    """가장 먼저 비어 있는 필드 하나(없으면 None = 완성)."""
    remaining = missing(parsed, **kwargs)
    return remaining[0] if remaining else None


# 슬롯 묶음(리스크 관리)의 대표 상태를 고르는 우선순위 — 가장 손이 필요한 것이 이긴다.
# NOT_APPLICABLE은 여기 없다: 구성원 전부가 해당 없음일 때만 슬롯이 해당 없음이므로
# 별도로 처리한다(하나만 해당 없음인 것은 나머지 구성원의 상태로 대표된다).
_STATUS_PRECEDENCE: tuple[FieldStatus, ...] = (
    FieldStatus.INVALID,
    FieldStatus.CONFLICTED,
    FieldStatus.UNKNOWN,
    FieldStatus.PROVISIONAL,
    FieldStatus.INFERRED,
    FieldStatus.CONFIRMED,
)


def slot_statuses(parsed: Any, **kwargs: Any) -> Dict[str, FieldStatus]:
    """진행 골격 8칸의 대표 상태(진행 순서). 진행률 표시의 입력이다.

    `filled_slots`가 답하지 못하던 것을 답한다 — 어떤 칸이 '해당 없음'이라 분모에서
    빠져야 하고, 어떤 칸이 '값은 있으나 미확인'인지. 리스크 관리 슬롯만 손절·익절 두
    필드를 묶으므로 대표 상태를 고른다.
    """
    per_field = {s.field: s.status for s in evaluate(parsed, **kwargs)}
    result: Dict[str, FieldStatus] = {}
    for slot in SLOT_ORDER:
        members = [per_field[f] for f in FIELD_ORDER
                   if SLOT_LABELS[f] == slot and f in per_field]
        if not members:
            continue
        if all(m is FieldStatus.NOT_APPLICABLE for m in members):
            result[slot] = FieldStatus.NOT_APPLICABLE
            continue
        applicable = [m for m in members if m is not FieldStatus.NOT_APPLICABLE]
        result[slot] = next(
            (s for s in _STATUS_PRECEDENCE if s in applicable), FieldStatus.CONFIRMED
        )
    return result


def filled_slots(parsed: Any, **kwargs: Any) -> List[str]:
    """채워진 골격 슬롯 라벨(8칸 기준, 진행 순서). 리스크 관리는 손절·익절이 모두
    채워져야 충족 — 한쪽만 있으면 아직 물을 것이 남았다."""
    statuses = {s.field: s.filled for s in evaluate(parsed, **kwargs)}
    done: List[str] = []
    for slot in SLOT_ORDER:
        members = [f for f in FIELD_ORDER if SLOT_LABELS[f] == slot and f in statuses]
        if members and all(statuses[f] for f in members):
            done.append(slot)
    return done
