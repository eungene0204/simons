"""조건 인용 대조 — "이 인용 조각이 **이 조건**을 말하나"를 LLM에게 묻는다.

왜 필요한가: 인터프리터는 조건마다 근거 인용(source_text)을 남기는데, 인용이 입력에 실재한다는
것(출처 대조)만으로는 그 인용이 그 조건을 말하는지 알 수 없다.
  - "최대 보유 기간은 25거래일"을 인용으로 단 이동평균 청산 조건(2026-08-18 예시 73)
  - "-8% 손절 시 매도"를 인용으로 단 이동평균 청산 조건(2026-09-16, 3/3 재현)
  - "박스 상단 돌파"·"break above its 20-day high"를 인용으로 단 볼린저·이동평균 조건
    (2026-08-26 /us 게이트 27·69)
종전에는 한국어·영어 어휘 정규식이 인용의 의미를 판정했다(대원칙 1 위반, 2026-09-17 이관).

질문의 형태가 핵심이다(2026-09-17 9B 게이트 회귀로 교정). 처음 이관은 "인용이 어느 칸(손절·
종목 수·이동평균…)에 관한 말인가"를 물었는데, 9B는 "데드크로스가 나오면 매도"·"20일선 이탈 시
청산" 같은 **정당한 이동평균 청산**을 손절로 분류했다 — 청산 조건과 손절은 둘 다 '파는 말'이라
칸 분류로는 갈리지 않는다(예시 67 치명 4/4, 같은 39개 호출 재생에서 실제 조건 12개가 탈락 판정).
그래서 **조건 중심**으로 묻는다: 조건을 평이한 한국어로 적어 주고("매도 — 5일 이동평균선이 20일
이동평균선을 아래로 교차하면"), 인용이 그것을 말하는지 yes/no/unclear만 받는다. 신고가 오분류
교정을 위해 인용이 말하는 신호 종류(describes)를 같은 항목에 함께 받는다.
제거는 no 하나로 정하지 않는다(2026-09-19 120B 교정): 120B는 세부만 다른 이동평균 조건에도
no를 답했다. 인용이 이동평균도 볼린저도 신고가도 아닌 **다른 것(other)**을 말한다는 답이 함께
있을 때만 뺀다.

결정론 코드의 몫: ① 조건을 문장으로 옮겨 적기(LLM 출력 필드의 표기 변환) ② 응답이 정해진
enum인지 확인 ③ enum 값에 따른 분기. 인용 문자열은 읽지 않는다.

호출 범위: 결과를 바꿀 수 있는 조건(이동평균 계열·볼린저)만. 제거 판정은 별도 호출로 한 번
재확인하며 두 판정이 일치할 때만 제거한다. 그런 조건이 없으면 호출이 없다.

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치는 **판정 없음(None)** — 교정도 제거도 하지 않는다
(fail-open, 조건 회수 패스와 같은 원칙). 개별 항목이 enum 밖이거나 "unclear"여도 그 조건은 남긴다.
제거는 분명한 "no"이면서 describes가 "other"(또는 순위 선정 "ranking", 2026-10-07)일 때만이다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

MA_FACTORS = ("technical.ema", "technical.ma_crossover",
              "concept.golden_cross", "concept.dead_cross")
BOLLINGER_FACTOR = "technical.bollinger_bands"
# 밴드 지정 볼린저(엔진 v16.39) — 대조 문장에 밴드를 적어 인용이 그 밴드를 말하는지 묻는다.
BOLLINGER_BAND_NAMES = {
    "technical.bollinger_upper_breakout": "상단을 위로 돌파하면",
    "technical.bollinger_upper_fall": "상단 위에 있다가 상단 아래로 내려오면",
    "technical.bollinger_middle_up": "중심선을 위로 돌파하면",
    "technical.bollinger_middle_down": "중심선 아래로 이탈하면",
    "technical.bollinger_lower_touch": "하단에 닿거나 아래로 이탈하면",
    "technical.bollinger_lower_rebound": "하단 아래로 갔다가 다시 하단 위로 올라오면",
}
BOLLINGER_MIDDLE_RECOVERY = "technical.bollinger_middle_recovery"
BOLLINGER_FACTORS = (BOLLINGER_FACTOR, *BOLLINGER_BAND_NAMES, BOLLINGER_MIDDLE_RECOVERY)
CHECKED_FACTORS = MA_FACTORS + BOLLINGER_FACTORS

EXPRESSES = frozenset({"yes", "no", "unclear"})
DESCRIBES = frozenset({"moving_average", "bollinger", "new_high_breakout", "ranking", "other"})

_SYSTEM = """당신은 **대조기**입니다. 전략 문장에서 뽑은 조건마다, 함께 적힌 인용 조각이 그 조건을 말하는지 답하세요.

항목마다 두 값을 채웁니다.
expresses — [전략 문장]이 실제로 그 조건을 요청하고 인용 조각도 같은 조건을 말하면 "yes".
인용이 다른 설정(종목 수·손절·기간 등)이거나 [전략 문장]에 없는 조건을 지어낸 것이면 "no",
판단이 어려우면 "unclear". 인용만 따로 읽어 원문에 없는 매도 규칙을 추론하지 마세요.
describes — 실제 요청과 인용이 함께 가리키는 신호: 이동평균선·골든크로스·데드크로스면 "moving_average", 볼린저 밴드면 "bollinger", 신고가·N일 고점 돌파·N일 저가 이탈·박스권 돌파면 "new_high_breakout", 수익률·상대강도 순위로 상위 종목을 고르는 말이면 "ranking", 그 밖이거나 원문에 없는 조작 인용이면 "other".
인용 자체가 '최근 60거래일 수익률 상위'처럼 수익률 순위로 종목을 고르는 말이면 조건과 맞지 않아도 describes는 "ranking"입니다(expresses는 "no").

N일선은 N일 이동평균선의 줄임말입니다. '20일선 이탈 시 청산'은 종가가 20일 이동평균선을
하향 교차할 때 매도하는 조건이므로 yes/moving_average입니다. '20일선 이탈 시 손절'도 같습니다.
'20일 이동평균선 근처에 있는' 매수는 종가가 20일 이동평균선 위에 있는 조건으로 반영하므로 yes/moving_average입니다.
'손절 -8%' 같은 고정 손실률이나 '최대 20일 보유' 같은 보유 기간만 인용한 이동평균 조건은
no/other입니다. 원문에 손절 설정이 함께 있어도 이동평균 청산 인용을 손절 설정으로 분류하지 마세요.
반대로 '20일 저가 아래로 내려오면 매도'는 이동평균선이 아니라 최근 20일 가격 저점 이탈이므로
no/new_high_breakout입니다. '20일선 이탈 시 청산'과 구별하세요.

[전략 문장]이 'MACD 골든크로스와 종가가 20일 이동평균선 위일 때 매수, MACD 데드크로스면
매도'라고만 했다면 이동평균 매수는 yes/moving_average입니다. 여기에 별도로 뽑힌
'20일 이동평균선 이탈 시 매도'는 원문에 **없는** 청산 규칙이므로 no/other입니다.
위에 있을 때만 매수한다는 말에서 이탈 시 매도를 만들어내지 마세요.

출력 형식(JSON만, 항목 순서대로):
{"items": [{"expresses": "yes", "describes": "moving_average"}]}"""

_CONFIRM_SYSTEM = _SYSTEM + """
이 검사는 조건을 제거하기 전의 독립 재확인입니다. 각 인용이 가리키는 지표와 조건을 다시 대조하세요.
매도·청산·손절이라는 동사 자체는 신호 종류가 아닙니다. 청산을 유발하는 기준으로 판단하세요.
이동평균 신호의 기간이나 연산자만 다르면 describes는 moving_average이며 other가 아닙니다.
인용이 이동평균과 무관한 다른 설정이거나 원문에 없는 조작 인용임이 명확할 때만
no/other로 답하세요. 매수 조건의 역방향 청산을 원문에 없는데 만들어낸 것은 조작 인용입니다."""

_ROLE_SYSTEM = """당신은 전략 원문에 없는 청산 규칙을 찾는 대조기입니다.
[전략 문장]만 보고 [후보 청산]을 사용자가 실제로 요청했는지 답하세요.
매수 조건이 이동평균선 위라는 사실로 그 선 아래에서 자동 청산한다고 추론하지 마세요.
매도 문장에 MACD만 있으면 이동평균 매도 조건은 요청되지 않았습니다.
후보가 원문에 없으면 {"items":[{"expresses":"no","describes":"other"}]},
있으면 {"items":[{"expresses":"yes","describes":"moving_average"}]}처럼 JSON만 출력하세요."""

_ROLE_CONFIRM_SYSTEM = _ROLE_SYSTEM + """
조건을 제거하기 전의 독립 재확인입니다. 후보 청산을 매수 조건에서 역으로 추론하지 말고,
원문이 명시적으로 그 청산을 요청했는지만 다시 판정하세요."""


def build_system_prompt() -> str:
    return _SYSTEM


@dataclass(frozen=True)
class Verdict:
    expresses: Optional[str]   # yes / no / unclear / None(enum 밖)
    describes: Optional[str]   # moving_average / bollinger / new_high_breakout / ranking / other / None


class QuoteVerdicts:
    """조건 객체 → 판정. 조회는 객체 동일성(is)뿐이다 — 인용이 같은 두 조건(진입·청산 미러)도
    조건마다 따로 판정하기 때문이고, 강한 참조로 들고 있어 id 재사용 충돌이 없다."""

    def __init__(self, pairs: List[Tuple[Any, Verdict]]):
        self._pairs = pairs

    def get(self, cond: Any) -> Optional[Verdict]:
        for held, verdict in self._pairs:
            if held is cond:
                return verdict
        return None

    def __len__(self) -> int:
        return len(self._pairs)


def _canonical_factor(factor: Optional[str]) -> Optional[str]:
    from strategy_conversation.registry.indicator_registry import REGISTRY

    spec = REGISTRY.get(factor) if factor else None
    return spec.id if spec is not None else factor


def _period(value: Any) -> Optional[int]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number > 0 else None


def render_condition(cond: Any, role: str) -> str:
    """조건(LLM 출력 필드)을 평이한 한국어로 옮겨 적는다 — 표기 변환뿐, 인용은 읽지 않는다."""
    factor = _canonical_factor(cond.factor)
    params = cond.parameters or {}
    side = "매수" if role == "entry_conditions" else "매도"
    op = cond.operator or ""
    if op == "crosses_above":
        motion = "위로 교차하면"
    elif op == "crosses_below":
        motion = "아래로 교차하면"
    elif op in (">", ">="):
        motion = "위에 있으면"
    elif op in ("<", "<="):
        motion = "아래에 있으면"
    else:
        motion = "관계가 성립하면"
    if factor in BOLLINGER_FACTORS:
        period = _period(params.get("period"))
        band = f"{period}일 볼린저 밴드" if period else "볼린저 밴드"
        if factor == BOLLINGER_MIDDLE_RECOVERY:
            return f"{side} — 종가가 {band} 하단을 터치한 뒤 중심선을 위로 교차하면"
        if factor in BOLLINGER_BAND_NAMES:
            return f"{side} — 종가가 {band} {BOLLINGER_BAND_NAMES[factor]}"
        return f"{side} — 종가가 {band}를 {motion}"
    if factor in ("concept.golden_cross", "concept.dead_cross"):
        name = "골든크로스" if factor == "concept.golden_cross" else "데드크로스"
        return f"{side} — {name}(단기 이동평균선이 장기 이동평균선을 교차)가 나오면"
    line = "지수이동평균선(EMA)" if factor == "technical.ema" else "이동평균선"
    short, long_ = _period(params.get("short_period")), _period(params.get("long_period"))
    subject = "종가가" if short in (None, 1) else f"{short}일 {line}이"
    target = f"{long_}일 {line}" if long_ else line
    return f"{side} — {subject} {target}을 {motion}"


def conditions_to_check(
    strategy: Any, only: Optional[List[Any]] = None,
    skip: Callable[[Any], bool] = lambda _c: False,
) -> List[Tuple[Any, str]]:
    """물어볼 (조건, 역할) 목록 — 이동평균 계열·볼린저이고 인용이 있는 조건만."""
    targets: List[Tuple[Any, str]] = []
    for role in ("entry_conditions", "exit_conditions"):
        for cond in getattr(strategy, role):
            if only is not None and not any(cond is c for c in only):
                continue
            if (_canonical_factor(cond.factor) in CHECKED_FACTORS and cond.source_text
                    and not skip(cond)):
                targets.append((cond, role))
    return targets


def targets_for_intent(intent, user_input, only=None):
    from .output_repair import whole_input_quote_fields

    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return []
    violating = set(whole_input_quote_fields(intent, user_input)) if only is None else set()
    excluded = [c for role in ("entry_conditions", "exit_conditions")
                for index, c in enumerate(getattr(strategy, role))
                if f"strategy.{role}[{index}].source_text" in violating]
    return conditions_to_check(strategy, only=only, skip=lambda c: any(c is x for x in excluded))


def build_request(user_input, targets):
    rows = "\n".join(
        f'{i}. 조건: {render_condition(cond, role)}\n   인용: "{cond.source_text}"'
        for i, (cond, role) in enumerate(targets, 1)
    )
    return _SYSTEM, f"[전략 문장]\n{user_input}\n\n[조건]\n{rows}", 64 + 32 * len(targets)


def check_quotes(
    user_input: str, targets: List[Tuple[Any, str]], chat: Callable[..., str],
) -> Optional[QuoteVerdicts]:
    """Confirm destructive verdicts once; disagreement or failure preserves the condition."""
    from engine.nl_parser import _compact

    verdicts = _request_verdicts(user_input, targets, chat)
    rejected = [(c, role) for c, role in targets if quote_does_not_express(verdicts, c)]
    confirmed = (_request_verdicts(user_input, rejected, chat, system=_CONFIRM_SYSTEM)
                 if rejected else None)
    resolved = [
        (cond, Verdict(None, None) if quote_does_not_express(verdicts, cond)
         and not quote_does_not_express(confirmed, cond)
         else verdicts.get(cond) if verdicts is not None else Verdict(None, None))
        for cond, _ in targets
    ]

    compact_input = _compact(user_input)
    entries = [c for c, role in targets if role == "entry_conditions"]
    suspect_exits = [
        (c, role) for c, role in targets
        if role == "exit_conditions" and _compact(c.source_text or "") not in compact_input
        and any(_canonical_factor(c.factor) == _canonical_factor(entry.factor)
                for entry in entries)
    ]
    if verdicts is None and not suspect_exits:
        return None
    # The quote can itself invent a plausible exit. Ask about the original
    # sentence without that quote; two independent no verdicts are required.
    if suspect_exits:
        first = _request_verdicts(user_input, suspect_exits, chat, system=_ROLE_SYSTEM)
        second = _request_verdicts(user_input, suspect_exits, chat, system=_ROLE_CONFIRM_SYSTEM)
        for index, (cond, _role) in enumerate(targets):
            if any(cond is candidate for candidate, _ in suspect_exits):
                a = first.get(cond) if first else None
                b = second.get(cond) if second else None
                if a and b and a.expresses == b.expresses == "no":
                    resolved[index] = (cond, Verdict("no", "other"))
    return QuoteVerdicts(resolved) if targets else verdicts


def _request_verdicts(
    user_input: str, targets: List[Tuple[Any, str]], chat: Callable[..., str],
    system: Optional[str] = None,
) -> Optional[QuoteVerdicts]:
    """조건마다 인용 대조 판정을 받는다. 실패는 None(fail-open)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not targets:
        return QuoteVerdicts([])
    default_system, user, max_tokens = build_request(user_input, targets)
    system = system or default_system
    if system in (_ROLE_SYSTEM, _ROLE_CONFIRM_SYSTEM):
        rows = "\n".join(f"{i}. {render_condition(cond, role)}"
                         for i, (cond, role) in enumerate(targets, 1))
        user = f"[전략 문장]\n{user_input}\n\n[후보 청산]\n{rows}"
    trace_name = ("Quote Check · 원문 청산 재확인" if system == _ROLE_CONFIRM_SYSTEM
                  else "Quote Check · 원문 청산 대조" if system == _ROLE_SYSTEM
                  else "Quote Check · 제거 재확인" if system == _CONFIRM_SYSTEM
                  else "Quote Check · 조건 인용 대조")
    with span(trace_name, "chain",
              inputs={"conditions": [render_condition(c, r) for c, r in targets],
                      "quotes": [c.source_text for c, _ in targets]}) as trace:
        try:
            raw = chat(system, user, max_tokens=max_tokens)
            payload = json.loads(extract_json_object(raw))
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list) or len(items) != len(targets):
                raise ValueError(f"항목 수 불일치: {len(targets)}개 요청")
        except Exception as exc:  # noqa: BLE001 — 보조 판정이 턴을 깨지 않는다(fail-open)
            logger.warning("quote check pass failed — no verdicts | err=%s", str(exc)[:200])
            trace.output(failed=True, error=str(exc)[:300])
            return None
        pairs: List[Tuple[Any, Verdict]] = []
        for (cond, _role), item in zip(targets, items):
            item = item if isinstance(item, dict) else {}
            expresses = item.get("expresses")
            describes = item.get("describes")
            pairs.append((cond, Verdict(
                expresses=expresses if expresses in EXPRESSES else None,
                describes=describes if describes in DESCRIBES else None,
            )))
        trace.output(verdicts=[
            {"quote": c.source_text, "expresses": v.expresses, "describes": v.describes}
            for c, v in pairs
        ])
        return QuoteVerdicts(pairs)


def _verdict(verdicts: Optional[QuoteVerdicts], cond: Any) -> Optional[Verdict]:
    return verdicts.get(cond) if verdicts is not None else None


def quote_does_not_express(verdicts: Optional[QuoteVerdicts], cond: Any) -> bool:
    """이동평균 조건인데 LLM이 인용이 그 조건을 말하지 **않고**, 인용이 말하는 것이 이동평균·
    볼린저·신고가가 아닌 다른 것(other — 종목 수·손절·보유 기간 같은 설정 문구)이라고 답했는가.

    no만으로는 빼지 않는다(2026-09-19 120B 게이트): 120B는 세부만 다른 이동평균 조건(20일선
    '근처' vs '위', 기간을 잘못 옮긴 EMA)에 no/moving_average를 답했고, 예시 53의 청산 규칙이
    "이동평균 조건이 아니어서"라는 거짓 안내와 함께 지워졌다(4회 중 2회). 트레이스 재생 비교
    (같은 입력·프롬프트 불변): 120B 거짓 제거 17/104 → 1/104, 설정 문구 조작 제거 12/12 유지 /
    9B 거짓 제거 2/106 → 0/106, 조작 제거 12/12 → 8/12(9B가 '5종목'·'-15% 손절' 인용에
    moving_average를 답한다). 낱말 옮겨 적기 형태(signal_words)는 9B가 설정 문구를 통째로
    옮겨 적어 조작 제거 0/12라 기각했다. unclear·enum 밖·판정 없음은 False(남긴다). 신고가
    돌파는 제거가 아니라 교정 대상이다(quote_describes_breakout).
    """
    verdict = _verdict(verdicts, cond)
    return (verdict is not None and verdict.expresses == "no"
            and verdict.describes in ("other", "ranking")
            and _canonical_factor(cond.factor) in MA_FACTORS)


def quote_describes_ranking(verdicts: Optional[QuoteVerdicts], cond: Any) -> bool:
    """LLM이 인용을 수익률·상대강도 **순위 선정**을 말한다고 답했는가(2026-10-07 예시 57·70:
    형태 견본의 이동평균 조건을 베끼며 랭킹 구절을 인용으로 붙였다). 그 구절이 랭킹으로
    반영됐는지는 호출부가 전략의 랭킹 칸으로 확인한다."""
    verdict = _verdict(verdicts, cond)
    return verdict is not None and verdict.describes == "ranking"


def quote_describes_breakout(verdicts: Optional[QuoteVerdicts], cond: Any) -> bool:
    """볼린저·단순이동평균 조건인데 LLM이 인용을 신고가·고점·박스권 돌파로 답했는가."""
    verdict = _verdict(verdicts, cond)
    return (verdict is not None and verdict.describes == "new_high_breakout"
            and _canonical_factor(cond.factor) in (*BOLLINGER_FACTORS, "technical.ma_crossover"))
