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


class ValueStatus(str, Enum):
    """사용자 값의 확정도 — **영속 상태**(설계 스펙 § 5, 2026-07-30 하이브리드 재정의).

    `filled`는 "더 물을 것이 없다"만 답한다. 그래서 **해당 없음과 완료가 같은 True**로
    보였고(단독 종목의 리밸런싱이 진행률에 체크로 표시), 기본값이 물질화된 값과 사용자가
    말한 값도 구분되지 않았다. 이 축은 그 셋을 나눈다.

    이 축의 정본 담지자는 값(`ParsedStrategy`)과 provenance 사이드카(`explicit_fields`)다
    — 값을 `{value, status, ...}`로 감싸지 않는다(컴파일러·디컴파일러·patch_applier·
    엔진 변환기·프론트를 전부 깨뜨린다).

    `filled`의 판정은 바뀌지 않는다 — 이 축은 옆에 붙는 정보이며, 기존 게이트·진행률의
    통과 여부를 바꾸지 않는다(되묻기 흐름 무영향).
    """

    # 값이 없고 아직 결정되지 않았다.
    UNKNOWN = "UNKNOWN"
    # 문맥에서 추론한 값. 확정값처럼 취급하지 않는다.
    # **현재 producer 없음** — 스키마로만 유지한다(2026-07-30 사용자 결정). 정성 표현
    # 매핑·암시적 유니버스 추론을 이 상태로 잇는 것은 별도 단계다. 외부에서 들어오면
    # 값 출처가 LLM_INFERENCE인지 검사하고 텔레메트리에 남긴다.
    INFERRED = "INFERRED"
    # 값은 있으나 사용자가 확인하지 않았다(기본값 물질화·추천값).
    PROVISIONAL = "PROVISIONAL"
    # 사용자가 직접 제공했거나 시스템이 확정해 협상 대상이 아니다.
    CONFIRMED = "CONFIRMED"


class DerivedStatus(str, Enum):
    """파생 런타임 상태 — **저장하지 않는다. 매 턴 전략 전체를 보고 계산한다.**

    ValueStatus와 축이 다르다: 저쪽은 "이 값이 어디서 왔나"(사용자 소유, 영속),
    이쪽은 "지금 이 전략에서 그 값이 성립하나"(시스템 판정, 계산).

    영속화하지 않는 이유가 이 타입의 존재 이유다. 유니버스를 ETF로 바꾸면 기존 PER
    조건은 NOT_APPLICABLE이 되지만, **원본 값은 지우지도 표시를 저장하지도 않는다** —
    다시 코스피로 되돌리면 역방향 패치 없이 APPLICABLE로 돌아와야 한다. 상태를 저장하면
    그 되돌림을 누군가(=LLM) 발행해야 하고, 빠뜨리면 멀쩡한 조건에 '적용 불가' 표시가
    영구히 남는다(2026-07-30 설계 결정).
    """

    # 현재 전략에서 그대로 성립한다(기본값).
    APPLICABLE = "APPLICABLE"
    # 현재 전략 유형·유니버스에서는 적용할 수 없어 물을 대상이 아니다.
    # 해결책은 유니버스를 바꾸는 것이다(값을 바꾸는 것이 아니다).
    NOT_APPLICABLE = "NOT_APPLICABLE"
    # 값이 있으나 엔진이 실행할 수 없다(미지원·미해석 지표). 해결책은 지표 교체다.
    INVALID = "INVALID"
    # 다른 값이나 조건과 모순된다.
    CONFLICTED = "CONFLICTED"


# 값이 있으나 사용자·시스템의 개입이 필요한 상태 — 진행률에서 '확인 필요'로 묶인다.
NEEDS_ATTENTION: frozenset[DerivedStatus] = frozenset(
    {DerivedStatus.INVALID, DerivedStatus.CONFLICTED}
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
# [2026-08-18] 리밸런싱 뒤에 '종목 선정 기준' 슬롯을 넣었다가 같은 날 폐기했다 — 리밸런싱
# 후보는 이미 매수 조건이 정하므로 별도 선정 기준을 필수로 묻는 것은 전략의 그림과 어긋난다
# (사용자 결정). 후보가 빈 자리를 넘는 날의 우선순위는 엔진이 최근 수익률 순으로 정하고
# 결과에 고지한다(엔진 v16.3). 랭킹은 사용자가 말했을 때만(모멘텀·재무 순위) 전략의 일부다.
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

# 확정(CONFIRM, 설계 스펙 § 7)이 성립하는 필드 — 값이 이미 물질화돼 PROVISIONAL로 남는
# 단일 스칼라 설정이다. "값은 그대로 두고 상태만 CONFIRMED로 올린다"가 확정의 정의이므로,
# 물질화 기본값이 없는 필드(진입·청산·손절·익절)에는 확정할 대상이 없다.
# universe는 시장·업종·종목 여러 속성의 합이라 '그 값 그대로'가 하나로 정해지지 않아
# 제외한다(유니버스 범위 칩은 _apply_universe_chip이 값 적용으로 처리하는 별도 레인).
CONFIRMABLE_FIELDS: tuple[str, ...] = (
    MAX_POSITIONS, REBALANCING, BACKTEST_PERIOD, INITIAL_CAPITAL,
)

# 사용자가 '안 함'으로 **거부**할 수 있는 필드(_decided ②). 손절·익절은 스키마에서
# null이라 "아직 안 물었다"와 "안 하기로 했다"가 구분되지 않는다 — 그 구분을 값이 아니라
# 거부 목록(declined_fields)이 나른다(리밸런싱의 rebalancing_declined와 같은 축).
# 값으로 표현하지 않는 이유: 0은 enforce_strategy_minimums가 "0%보다 커야 한다"로 이미
# 거부하는 값이라, 센티널로 쓰면 그 가드를 무력화해야 한다(2026-08-10).
DECLINABLE_FIELDS: frozenset[str] = frozenset({REBALANCING, STOP_LOSS, TAKE_PROFIT})

# 거부 칩(정본 표기) → 필드. 칩=값 결속 계약에서 이 칩들은 **값을 바꾸지 않으므로**
# _apply_prompt_overrides로는 결속되지 않는다(무변경 = 노출 제외). 확정 칩(chip_confirms)과
# 같은 이유로 별도 채널을 둔다 — 클릭은 값이 아니라 거부 상태를 남긴다.
DECLINE_CHIP_FIELDS: dict[str, str] = {
    "손절 안 함": STOP_LOSS,
    "익절 안 함": TAKE_PROFIT,
}


def _field_for_topic(topic: Optional[str], candidates: Sequence[str]) -> Optional[str]:
    """topic 표기를 정본 슬롯 라벨에 맞춘다(후보 중 첫 일치).

    topic은 planner LLM이 낸 슬롯 라벨이므로 표기 정규화(공백 무시·부분 일치)로 정본
    라벨에 맞춘다 — 원문 해석이 아니라 LLM 출력 정규화다(계약 § 판정 기준).
    9B가 'ㅤ최대 보유 종목 수'처럼 라벨을 늘려 쓰는 실측 드리프트 때문에 정확 일치가
    아니라 포함으로 본다(_is_universe_topic과 같은 계약).
    """
    normalized = (topic or "").replace(" ", "")
    if not normalized:
        return None
    for field in candidates:
        label = SLOT_LABELS[field].replace(" ", "")
        if label in normalized or normalized in label:
            return field
    return None


def confirmable_field_for_topic(topic: Optional[str]) -> Optional[str]:
    """ask의 topic이 가리키는 확정 가능 필드(없으면 None)."""
    return _field_for_topic(topic, CONFIRMABLE_FIELDS)


def slot_for_topic(topic: Optional[str]) -> Optional[str]:
    """ask의 topic이 가리키는 진행 골격 슬롯(없으면 None).

    `confirmable_field_for_topic`이 확정 가능한 4개만 보는 것과 달리 8칸 전체를 본다 —
    planner가 칩 없는 ask를 냈을 때 그 슬롯의 정본 칩으로 보완하기 위한 것이다.
    `stop_loss`·`take_profit`은 라벨('리스크 관리')을 공유하므로 FIELD_ORDER상 앞선
    `stop_loss`가 잡힌다 — 두 슬롯을 구분해야 하면 topic이 아니라 필드로 받아야 한다.
    """
    return _field_for_topic(topic, FIELD_ORDER)


def suggestions_for_topic(
    topic: Optional[str], universe: Optional[Sequence[str]] = None,
    parsed: Any = None,
) -> List[str]:
    """topic이 가리키는 슬롯의 정본 예시 칩(없으면 빈 목록).

    사용자에게 노출되는 슬롯 ask 칩의 유일한 출처다(2026-08-02 사용자 결정) — planner
    LLM이 지어낸 칩은 발행 전에 폐기되고 항상 이 정본으로 대체된다. 칩이 지원 조건임을
    보증하는 방법은 사람이 정한 목록뿐이기 때문이다(부분 결속 칩 '거래량 급증(전일 대비
    3배) 시 매수' 노출 사고). 칩 어휘를 다른 곳에 복제하지 않는다(복제하면 반드시
    어긋난다, 이 모듈 도입 배경).

    universe가 ETF면 개별 기업 재무 칩(PER·ROE)은 제외한다 — ETF는 기업 재무제표
    지표를 조건으로 쓸 수 없다(engine.universe_capabilities).
    """
    field = slot_for_topic(topic)
    if not field:
        return []
    chips = list(_question_for(parsed, field)[1])
    from engine.universe_capabilities import is_etf_strategy

    if is_etf_strategy(universe):
        chips = [c for c in chips if c not in _FUNDAMENTAL_CHIPS]
    return chips


@dataclass(frozen=True)
class SlotState:
    """한 슬롯의 두 상태 축. 영속(value)과 계산(derived)을 같은 이름으로 섞지 않는다."""

    value_status: ValueStatus = ValueStatus.UNKNOWN
    derived_status: DerivedStatus = DerivedStatus.APPLICABLE

    def as_payload(self) -> Dict[str, str]:
        """프론트로 나가는 표현(진행률 카드 전용)."""
        return {"value": self.value_status.value, "derived": self.derived_status.value}


@dataclass(frozen=True)
class SlotStatus:
    field: str
    slot: str
    filled: bool
    question: str
    suggestions: tuple[str, ...]
    # 상태 두 축(§ 5). filled와 독립이다 — require_explicit=False 레인에서 기본값이
    # 물질화된 필드는 filled=True이면서 value_status=PROVISIONAL이다(둘 다 사실이다).
    value_status: ValueStatus = ValueStatus.UNKNOWN
    derived_status: DerivedStatus = DerivedStatus.APPLICABLE


# 되묻기 문구는 판정과 함께 둔다 — 판정과 질문이 떨어져 있으면 슬롯이 늘 때
# 한쪽만 갱신되어 어긋난다(이번 사고의 구조적 원인).
#
# [2026-08-16 단일 정본 통합] 여기 적힌 문구·칩이 **사용자에게 보이는 최종 표기**다.
# 이전에는 같은 질문의 사본이 네 벌이었고 서로 어긋나 있었다:
#   ① 이 표  ② 프론트 backtestReadiness.SLOT_PROMPTS  ③ 빌더 next_question
#   ④ 프론트 makeBuilderQuestionFriendly(①②를 렌더 직전에 다시 쓰는 치환표)
# 같은 유니버스 질문이 레인마다 다른 문구·다른 칩으로 나갔고(빌더 5개·게이트 4개·
# 정본 2개), ④ 때문에 표에 적힌 문구가 화면 문구도 아니었다. 그래서 ②③④를 없애고
# 이 표만 남긴다 — 문구를 고칠 곳은 여기 하나다.
#
# 칩 어휘 제약: 두 레인의 답 해석기가 **모두** 읽을 수 있어야 한다.
#   · 빌더 레인: intent.strategy_builder._parse_*(칩 텍스트를 발화처럼 해석)
#   · 게이트 레인: 프론트 deterministicConditionFlow(칩 → 값 결정론 적용)
# 한쪽만 읽을 수 있는 표기를 넣으면 그 레인에서 클릭이 조용히 LLM 왕복으로 떨어진다.
_QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    UNIVERSE: (
        "먼저 어떤 시장·종목을 대상으로 할지 정해볼까요?",
        ("코스피", "코스닥", "코스피200", "코스피·코스닥 전체", "ETF"),
    ),
    # 칩에 기간을 명시한다 — 기간 없는 신호는 엔진 기본값으로 조용히 돌면서 요약 카드에
    # 드러나지 않는다(2026-07-26 사고). 모멘텀(랭킹)은 전략 빌더에만 있던 선택지였는데,
    # 두 레인이 같은 질문을 쓰게 되면서 정본 목록에 합류했다(2026-08-16).
    ENTRY: (
        "다음으로 어떤 조건에서 매수할지 정해볼까요?",
        ("골든크로스(5일/20일) 발생 시 매수", "RSI 30 이하에서 매수",
         "MACD 골든크로스 매수", "볼린저밴드 하단 터치 시 매수",
         "20일 고점 돌파 시 매수", "거래량 급증 시 매수",
         "최근 3개월 수익률 상위 매수",
         "PER 10 이하", "ROE 15% 이상"),
    ),
    # 매도 칩은 **매수 칩의 반대**를 같은 순서로 세운다(2026-08-16 사용자 지시) — 위 ENTRY
    # 목록과 나란히 읽히면 "무엇을 뒤집은 것인지"가 설명 없이 보인다. 마지막 '보유 후 청산'만
    # 대응하는 매수 조건이 없는 기간 기반 청산이라 끝에 둔다.
    #   골든크로스→데드크로스 · RSI 과매도→과매수 · MACD 골든→데드 ·
    #   볼린저 하단→상단 · 고점 돌파→저점 이탈
    # 대응을 넣지 못한 매수 칩 3종:
    #   · 거래량 급증 — 엔진은 OBV 하락 전환(매도)을 지원하지만 파서에 그 매도 표현이 없어
    #     칩이 값에 결속되지 않는다. 결속 안 되는 칩은 노출하지 않는다(칩=값 결속 계약).
    #     어휘를 덧붙여 결속시키는 것은 대원칙 1이 금지하는 방향이라 하지 않는다.
    #   · 모멘텀 상위 — 랭킹 전략의 청산은 매도 신호가 아니라 리밸런싱 편출이다(FR-BT-015b).
    #   · PER·ROE — 재무 지표는 청산 조건이 될 수 없다(역할 검증, FR-STR-019t ②).
    EXIT: (
        "이제 언제 매도할지 정해볼까요?",
        ("데드크로스(5일/20일) 발생 시 매도", "RSI 70 이상에서 매도",
         "MACD 데드크로스 매도", "볼린저밴드 상단 터치 시 매도",
         "20일 저점 이탈 시 매도", "20일 보유 후 청산"),
    ),
    MAX_POSITIONS: (
        "포트폴리오에 최대 몇 종목을 담을까요?",
        ("최대 5종목", "최대 10종목", "최대 20종목"),
    ),
    REBALANCING: (
        "다음으로 포트폴리오를 얼마나 자주 다시 구성할지 정해볼까요?",
        ("매주 리밸런싱", "매월 리밸런싱", "분기마다 리밸런싱", "리밸런싱 안 함"),
    ),
    # 손절·익절은 쓰지 않는 것도 정상적인 전략 설계다 — '안 함'을 고를 수 없으면
    # 값을 넣어야만 실행 게이트를 통과할 수 있다(2026-08-10 사용자 지시).
    STOP_LOSS: (
        "이제 손절 기준을 몇 %로 정할까요?",
        ("손절 -5%", "손절 -10%", "손절 -15%", "손절 안 함"),
    ),
    TAKE_PROFIT: (
        "이제 익절 기준을 몇 %로 정할까요?",
        ("익절 10%", "익절 20%", "익절 30%", "익절 안 함"),
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

# 개별 기업 재무제표에서 계산되는 칩 — ETF 유니버스에는 노출하지 않는다
# (suggestions_for_topic, engine.universe_capabilities의 fundamental 미지원 계약).
_FUNDAMENTAL_CHIPS: frozenset = frozenset({"PER 10 이하", "ROE 15% 이상"})

# 분위 그룹 전략(FR-BT-060b) 전용 '최대 보유' 질문 — 그룹이 편입 구간을 정의하므로
# 일반 질문("포트폴리오에 최대 몇 종목")은 상황에 맞지 않는다. 답은 그룹당 보유 상한이며
# 모든 그룹에 동일 적용된다. 칩은 그룹 수(최대 10) 이상에서 시작한다(2026-08-06 지시).
_QUANTILE_MAX_POSITIONS_QUESTION: tuple[str, tuple[str, ...]] = (
    "각 분위 그룹에 최대 몇 종목을 담을까요?\n\n"
    "그룹 내 랭킹 상위순으로 담고, 모든 그룹에 동일하게 적용해 그룹 간 비교 규칙을 맞춥니다.",
    ("그룹당 10종목", "그룹당 20종목", "그룹당 30종목"),
)

# 랭킹 전략(모멘텀 상위 K 등)의 '최대 보유' 변형 — 상한이 아니라 상위 몇 개를 담을지가
# 실제 의미다. 분위 그룹 변형(위)과 같은 자리·같은 축이며, 변형도 정본 표에 둔다
# (레인마다 자기 변형을 들고 있으면 그 자체가 사본이다).
_RANKING_MAX_POSITIONS_QUESTION: tuple[str, tuple[str, ...]] = (
    "상위 몇 종목을 보유할까요?",
    ("상위 5종목", "상위 10종목", "상위 20종목"),
)

# 변형 키 — 호출자가 자기 상태(parsed / BuilderState)를 보고 고른다. 판정은 레인마다
# 다르지만(랭킹 여부를 보는 필드가 다르다) 문구는 여기 하나다.
VARIANT_QUANTILE = "quantile"
VARIANT_RANKING = "ranking"

_SLOT_VARIANTS: dict[tuple[str, str], tuple[str, tuple[str, ...]]] = {
    (MAX_POSITIONS, VARIANT_QUANTILE): _QUANTILE_MAX_POSITIONS_QUESTION,
    (MAX_POSITIONS, VARIANT_RANKING): _RANKING_MAX_POSITIONS_QUESTION,
}


def slot_question(field: str, variant: Optional[str] = None) -> tuple[str, List[str]]:
    """슬롯 필드의 정본 질문·칩. 변형이 없으면 기본 문구.

    되묻기 게이트(evaluate)와 전략 빌더(intent.strategy_builder)가 **둘 다** 이 함수로
    문구를 가져온다 — 두 레인이 같은 질문을 다른 문구로 묻지 않게 하는 유일한 장치다.
    """
    entry = _SLOT_VARIANTS.get((field, variant)) if variant else None
    if entry is None:
        entry = _QUESTIONS[field]
    return entry[0], list(entry[1])


def _quantile_groups(parsed: Any) -> Optional[int]:
    """분위 그룹 전략이면 그룹 수(FR-BT-060), 아니면 None."""
    value = getattr(parsed, "ranking_quantile_groups", None)
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _question_for(parsed: Any, field: str) -> tuple[str, tuple[str, ...]]:
    """필드의 되묻기 문구·칩 — 분위 그룹 전략의 '최대 보유'만 전용 변형을 쓴다."""
    if field == MAX_POSITIONS and _quantile_groups(parsed):
        return _QUANTILE_MAX_POSITIONS_QUESTION
    return _QUESTIONS[field]


# ── 전략 빌더 세부 질문 ────────────────────────────────────────────────────────
# 빌더(intent.strategy_builder)는 슬롯 9칸보다 잘게 묻는다 — 진입 조건 하나를 전략 유형·
# 지표 파라미터·추가 필터로 나눠 단계별로 받는다. 슬롯 표에 대응 필드가 없는 그 질문들의
# 문구·칩도 여기 둔다. **질문 문구를 authoring하는 곳은 이 모듈 하나**라는 것이 요점이며,
# 슬롯 판정과 무관한 항목이라는 이유로 다시 빌더 파일로 흩어놓지 않는다.
#
# 값이 상태에 따라 달라지는 부분(상장 연도 칩, 종목 프로파일 근거 문장, 유형별 추가 필터
# 칩)은 호출자가 조립한다 — 조립 규칙은 빌더의 것이고, 조립에 쓰이는 **문구**는 여기 것이다.
BUILDER_QUESTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    # 신규 상장 유니버스(FR-STR-073) — 칩(연도)은 호출 시점에 만들어 붙인다.
    "listing_period": ("어느 시기에 상장한 종목을 대상으로 할까요?", ()),
    # [2026-08-16] 빌더의 '어떤 방식으로 종목을 고를까요?'(전략 유형 + 불릿 8줄 + 유형
    # 이름 칩)는 폐지됐다 — 되묻기 게이트가 묻는 매수 조건과 같은 슬롯을 다른 질문·다른
    # 선택지로 물어, 어느 경로로 들어왔느냐에 따라 사용자가 다른 화면을 받았다. 지금은
    # 두 레인 모두 위 ENTRY 질문을 쓴다. 단일 종목 모드만 질문이 실제로 다르다(아래).
    #
    # 단일 종목 모드(FR-STR-068b) — 근거 문장(신호 발생 횟수)은 호출자가 덧붙이고,
    # 선택지는 ENTRY 정본에서 횡단면 항목(랭킹·재무 스크리닝)을 뺀 것을 쓴다.
    "strategy_type.single_asset": (
        "{label} 단일 종목 전략이니 어떤 조건에서 사고팔지를 정하면 돼요. "
        "어떤 진입 방식을 사용할까요?",
        (),
    ),
    "lookback_days": ("최근 몇 개월 수익률을 기준으로 볼까요?", ("1개월", "3개월", "6개월")),
    "lookback_days.breakout": (
        "며칠 신고가(박스권 상단) 돌파를 기준으로 볼까요?", ("20일", "60일", "120일"),
    ),
    "rsi_period": ("RSI를 며칠 기준으로 계산할까요?", ("14일 (기본)", "9일", "21일")),
    "rsi_bounds": (
        "과매도·과매수 기준을 정해볼까요? (매수=과매도 아래, 매도=과매수 위)",
        ("30 / 70 (기본)", "25 / 75", "35 / 65"),
    ),
    "ma_kind": ("어떤 이동평균을 쓸까요?", ("단순(SMA)", "지수(EMA)")),
    "ma_periods": (
        "단기·장기 이동평균 기간을 정해볼까요? (단기가 장기를 상향 돌파=매수)",
        ("5일 / 20일 (기본)", "10일 / 60일", "20일 / 120일"),
    ),
    "macd_mode": ("MACD 신호를 어떻게 잡을까요?", ("시그널선 교차 (기본)", "제로선 돌파")),
    "cci_params": (
        "CCI 기준값을 정해볼까요? (매수=-기준값 아래, 매도=+기준값 위, 기간 기본 14)",
        ("±100 (기본)", "±150"),
    ),
    "volume_period": ("거래량 흐름(OBV) 평균을 며칠 기준으로 볼까요?", ("20일 (기본)", "60일")),
    "value_params": (
        "저평가 기준을 정해볼까요?",
        ("PBR 1 이하 · ROE 10 이상 (기본)", "PBR 0.8 · ROE 15"),
    ),
    "filters": (
        "지금 조건만 쓰면 횡보장에서도 매수 신호가 너무 자주 발생할 수 있어요. "
        "매수에 추가 필터를 넣을까요? 추세·거래대금 조건을 더하면 이런 신호가 걸러져요. "
        "(여러 개를 함께 말해도 돼요, 예: 'EMA200 위 + 거래대금 100억')",
        ("EMA200 위에서만", "거래대금 100억 이상", "없음"),
    ),
    # 평균회귀·볼린저 매수에는 과매도 확인 필터를 함께 제시한다(문구는 같다).
    "filters.mean_reversion": (
        "지금 조건만 쓰면 횡보장에서도 매수 신호가 너무 자주 발생할 수 있어요. "
        "매수에 추가 필터를 넣을까요? 추세·거래대금 조건을 더하면 이런 신호가 걸러져요. "
        "(여러 개를 함께 말해도 돼요, 예: 'EMA200 위 + 거래대금 100억')",
        ("EMA200 위에서만", "거래대금 100억 이상", "RSI 30 이하일 때만", "없음"),
    ),
    "entry_rule": (
        "어떤 조건에서 매수할지 함께 정해볼까요? "
        "(예: 'RSI가 30 이하로 떨어지면', '20일선이 60일선을 상향 돌파하면')",
        (),
    ),
    # 빌더는 청산을 한 번에 묻는다(슬롯 표는 매도·손절·익절 세 칸으로 나눠 묻는다) —
    # 같은 자리를 가리키지만 질문의 단위가 달라 슬롯 문구를 그대로 쓸 수 없다.
    "risk": (
        "이제 언제 매도할지 정하면 전략이 완성됩니다. "
        "손절·익절·트레일링 스탑·보유기간 중 하나를 정해볼까요?\n"
        "(예: '-10% 손절', '20% 익절', '최고가 대비 10% 하락 시 청산', '20일 보유 후 청산')",
        ("-10% 손절", "-10% 손절·20% 익절", "최고가 대비 10% 하락 시 청산"),
    ),
}


def builder_question(key: str) -> tuple[str, List[str]]:
    """빌더 세부 질문의 정본 문구·칩(`BUILDER_QUESTIONS` 키)."""
    question, chips = BUILDER_QUESTIONS[key]
    return question, list(chips)


# 여러 종목을 비교해 고르는 선택지 — 대상이 한 종목으로 확정된 전략에는 성립하지 않는다.
_CROSS_SECTIONAL_CHIPS: frozenset = frozenset({"최근 3개월 수익률 상위 매수"})


def entry_chips(
    universe: Optional[Sequence[str]] = None, *, cross_sectional: bool = True,
) -> List[str]:
    """매수 조건 정본 칩에서 **그 전략에 성립하지 않는 항목만** 뺀 목록.

    두 레인(되묻기 게이트·전략 빌더)이 같은 목록을 쓰되, 유니버스·전략 형태가 표현할 수
    없는 선택지는 내놓지 않는다. 목록을 따로 만들지 않고 정본에서 빼기만 하는 것이 요점이다
    — 레인마다 자기 목록을 만들면 그 순간 다시 사본이 된다.
    """
    from engine.universe_capabilities import is_etf_strategy

    chips = _QUESTIONS[ENTRY][1]
    excluded: set[str] = set()
    if is_etf_strategy(universe):
        excluded |= _FUNDAMENTAL_CHIPS   # ETF는 기업 재무제표 지표를 조건으로 쓸 수 없다
    if not cross_sectional:
        excluded |= _CROSS_SECTIONAL_CHIPS
    return [chip for chip in chips if chip not in excluded]


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
        # 분위 그룹 전략(FR-BT-060b)의 이 자리는 '그룹당 보유 상한'이다 — cap은 물질화
        # 기본값이 없어 값의 존재가 곧 사용자 답변이다(max_positions=10 물질화와 무관).
        if _quantile_groups(parsed):
            return g("ranking_group_cap") is not None
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


@dataclass(frozen=True)
class _Decided:
    """질문이 끝난 이유. `filled`(=이 값의 존재 자체)와 두 상태 축을 함께 나른다."""

    value: Optional[ValueStatus] = None
    not_applicable: bool = False


def _decided(parsed: Any, field: str, declined: frozenset[str]) -> Optional[_Decided]:
    """질문이 이미 끝난 필드 — 값 유무·provenance와 무관하게 더 묻지 않는다.

    None이면 '아직 결정되지 않음'이고, _Decided면 결정된 이유다. 세 경우가 있고
    **서로 다른 상태**다 — 이전에는 셋 다 filled=True 하나로 뭉개져 있었다:

    ① 구성상 무의미한 질문(단독 종목의 리밸런싱) → NOT_APPLICABLE(파생 축).
       값이 없는 것이 정상이며, 진행률의 분모에서도 빠져야 한다. **값 축에는 아무
       주장도 하지 않는다** — 물을 대상이 아닌 것과 값이 확정된 것은 다르다.
    ② 사용자가 명시적으로 거부한 설정(리밸런싱 안 함·손절 안 함·익절 안 함) → CONFIRMED.
       사용자가 '안 함'을 결정한 것이므로 확정값이다. 스펙에서 null이라 미언급과
       구분되지 않으므로 호출자가 `declined_fields`로 전달한다 — 이 판정을 provenance 쪽에
       두면 require_explicit=False인 레인에서 무시돼 같은 질문이 무한 반복된다.
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
            return _Decided(not_applicable=True)
        if REBALANCING in declined:
            return _Decided(value=ValueStatus.CONFIRMED)
        return None
    if field in (STOP_LOSS, TAKE_PROFIT) and field in declined:
        # 값이 있는데 거부가 함께 오면 값이 이긴다 — 사용자가 값을 준 뒤 마음을 바꾼
        # 경우는 거부가 먼저 지워져야 한다(호출자가 목록에서 뺀다). 여기서 값을
        # 무시하면 화면에 보이는 값과 판정이 어긋난다.
        if not _has_value(parsed, field):
            return _Decided(value=ValueStatus.CONFIRMED)
    if field == BACKTEST_PERIOD:
        # 신규 상장 코호트(FR-STR-073)는 창 시작이 상장일 하한으로 확정된다 — 그 이전엔
        # 종목이 존재하지 않아 다른 답이 성립하지 않는다. "최근 5년 데이터"를 고를 수
        # 있는 것처럼 물으면 사용자가 고른 답을 클램프가 도로 덮어쓴다.
        if getattr(parsed, "listing_from", None):
            return _Decided(value=ValueStatus.CONFIRMED)
    return None


def _status_only_not_applicable(parsed: Any, field: str) -> bool:
    """구성상 물을 대상이 아니지만 `filled` 판정은 건드리지 않는 경우.

    _decided에 넣으면 값이 없을 때 filled가 False→True로 뒤집혀 되묻기 흐름이 바뀐다.
    이 축은 표시 전용이므로 filled와 분리한다(기존 게이트 동작 보존).
    """
    symbols = getattr(parsed, "target_symbols", None) or []
    # 단독 종목(지정 1개)만 '최대 보유'가 해당 없음이다 — 포트폴리오 자체가 없다
    # (리밸런싱의 단독/다종목 경계와 동일 축). 다종목 지정(테마 유니버스 등)은 보유
    # 수가 종목 수로 확정된 **완료**이지 해당 없음이 아니다 — 요약 카드는 '지정 종목
    # N개 균등 투자'를 보여주는데 진행률만 '해당 없음'이던 모순(2026-08-02 HBM 33곳).
    return field == MAX_POSITIONS and len(symbols) == 1


def _explicit_ok(parsed: Any, field: str, explicit_fields: Sequence[str]) -> bool:
    """사용자가 그 필드를 실제로 말했는가(provenance). 값 존재와 별개다."""
    if field not in PROVENANCE_FIELDS:
        return True
    symbols = getattr(parsed, "target_symbols", None) or []
    if field == UNIVERSE and symbols:
        return True  # 지정 종목은 그 자체가 유니버스 명시
    if field == MAX_POSITIONS and symbols:
        return True  # 지정 종목 모드는 보유 수가 종목 수로 확정된다
    if field == MAX_POSITIONS and _quantile_groups(parsed):
        # 그룹당 상한(cap)은 물질화 기본값이 없다 — 값의 존재가 곧 사용자 답변이라
        # provenance를 따로 볼 필요가 없다(_has_value가 cap 유무로 판정).
        return True
    return field in explicit_fields


def evaluate(
    parsed: Any,
    *,
    explicit_fields: Optional[Iterable[str]] = None,
    require_explicit: bool = False,
    rebalancing_declined: bool = False,
    declined_fields: Optional[Iterable[str]] = None,
    fields: Optional[Iterable[str]] = None,
    status_overrides: Optional[Dict[str, DerivedStatus]] = None,
) -> List[SlotStatus]:
    """골격 필드별 충족 상태를 진행 순서대로 반환한다.

    require_explicit=True면 값이 있어도 사용자가 말하지 않은 필드(provenance 부재)는
    미충족으로 본다 — 기본값을 질문 없이 확정하지 않기 위함(FR-STR-019k).
    fields로 판정 범위를 좁힐 수 있다(레거시 게이트의 6조건 등).

    declined_fields는 사용자가 '안 함'으로 거부한 필드(DECLINABLE_FIELDS) — _decided ②.
    `rebalancing_declined`는 그 목록의 리밸런싱 전용 별칭이다(기존 호출자 호환).

    status_overrides는 이 모듈이 볼 수 없는 상위 판정(검증 리포트의 INVALID·CONFLICTED)을
    **파생 축에만** 덮어쓴다 — `filled`도 값 축도 바꾸지 않는다. 지표 미지원·조건 모순은
    ParsedStrategy가 아니라 StrategySpec 검증 단계에서만 알 수 있기 때문이다.
    """
    declined = {f for f in (declined_fields or ()) if f in DECLINABLE_FIELDS}
    if rebalancing_declined:
        declined.add(REBALANCING)
    declined_frozen = frozenset(declined)
    explicit = list(explicit_fields or [])
    scope = tuple(fields) if fields is not None else FIELD_ORDER
    overrides = status_overrides or {}
    statuses: List[SlotStatus] = []
    for field in FIELD_ORDER:
        if field not in scope:
            continue
        # ── filled 판정: 기존 3축 그대로(동작 불변) ─────────────────────────────
        decided = _decided(parsed, field, declined_frozen)
        has_value = _has_value(parsed, field)
        explicit_ok = _explicit_ok(parsed, field, explicit)
        if decided is not None:
            filled = True
        else:
            filled = has_value
            if filled and require_explicit:
                filled = explicit_ok
        # ── 값 축(영속): filled와 독립으로 산출한다 ─────────────────────────────
        if decided is not None and decided.value is not None:
            value_status = decided.value
        elif not has_value:
            value_status = ValueStatus.UNKNOWN
        elif explicit_ok:
            value_status = ValueStatus.CONFIRMED
        else:
            # 값은 있으나 사용자가 말한 적 없다 — ParsedStrategy가 물질화한 기본값이다.
            # require_explicit 레인에서 되묻는 대상이 바로 이것이다.
            value_status = ValueStatus.PROVISIONAL
        # ── 파생 축(계산): 저장하지 않는다. 매 턴 여기서 다시 정해진다 ──────────
        if (decided is not None and decided.not_applicable) or _status_only_not_applicable(
            parsed, field
        ):
            derived_status = DerivedStatus.NOT_APPLICABLE
        else:
            # 상위 검증 판정은 값의 존재를 전제한다 — 값이 없으면 모순일 수도
            # 미지원일 수도 없다(판정 대상 자체가 없다).
            override = overrides.get(field)
            derived_status = (
                override if override is not None and value_status is not ValueStatus.UNKNOWN
                else DerivedStatus.APPLICABLE
            )
        question, suggestions = _question_for(parsed, field)
        statuses.append(SlotStatus(
            field=field, slot=SLOT_LABELS[field], filled=filled,
            question=question, suggestions=suggestions,
            value_status=value_status, derived_status=derived_status,
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
# NOT_APPLICABLE은 파생 축 목록에 없다: 구성원 전부가 해당 없음일 때만 슬롯이 해당
# 없음이므로 별도로 처리한다(하나만 해당 없음인 것은 나머지 구성원의 상태로 대표된다).
_DERIVED_PRECEDENCE: tuple[DerivedStatus, ...] = (
    DerivedStatus.INVALID,
    DerivedStatus.CONFLICTED,
    DerivedStatus.APPLICABLE,
)
_VALUE_PRECEDENCE: tuple[ValueStatus, ...] = (
    ValueStatus.UNKNOWN,
    ValueStatus.PROVISIONAL,
    ValueStatus.INFERRED,
    ValueStatus.CONFIRMED,
)


def slot_statuses(parsed: Any, **kwargs: Any) -> Dict[str, SlotState]:
    """진행 골격 8칸의 대표 상태(진행 순서). 진행률 표시의 입력이다.

    `filled_slots`가 답하지 못하던 것을 답한다 — 어떤 칸이 '해당 없음'이라 분모에서
    빠져야 하고, 어떤 칸이 '값은 있으나 미확인'인지. 리스크 관리 슬롯만 손절·익절 두
    필드를 묶으므로 대표 상태를 고른다. 두 축은 **각자** 대표를 고른다 — 섞어서 하나로
    줄이면 "값은 확정인데 지금 유니버스에서 못 쓴다" 같은 조합이 표현되지 않는다.
    """
    per_field = {s.field: s for s in evaluate(parsed, **kwargs)}
    result: Dict[str, SlotState] = {}
    for slot in SLOT_ORDER:
        members = [per_field[f] for f in FIELD_ORDER
                   if SLOT_LABELS[f] == slot and f in per_field]
        if not members:
            continue
        na = DerivedStatus.NOT_APPLICABLE
        applicable = [m for m in members if m.derived_status is not na]
        if not applicable:
            result[slot] = SlotState(
                value_status=_pick(_VALUE_PRECEDENCE,
                                   [m.value_status for m in members], ValueStatus.CONFIRMED),
                derived_status=na,
            )
            continue
        result[slot] = SlotState(
            value_status=_pick(_VALUE_PRECEDENCE,
                               [m.value_status for m in applicable], ValueStatus.CONFIRMED),
            derived_status=_pick(_DERIVED_PRECEDENCE,
                                 [m.derived_status for m in applicable],
                                 DerivedStatus.APPLICABLE),
        )
    return result


def _pick(precedence: tuple, members: list, fallback):
    """우선순위 목록에서 구성원에 실제로 있는 첫 값을 고른다."""
    return next((s for s in precedence if s in members), fallback)


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
