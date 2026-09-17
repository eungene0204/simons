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

결정론 코드의 몫: ① 조건을 문장으로 옮겨 적기(LLM 출력 필드의 표기 변환) ② 응답이 정해진
enum인지 확인 ③ enum 값에 따른 분기. 인용 문자열은 읽지 않는다.

호출 범위: 결과를 바꿀 수 있는 조건(이동평균 계열·볼린저)만, 한 턴 한 번. 그런 조건이 없으면
호출이 없다.

실패 동작: 호출 오류·JSON 불성립·항목 수 불일치는 **판정 없음(None)** — 교정도 제거도 하지 않는다
(fail-open, 조건 회수 패스와 같은 원칙). 개별 항목이 enum 밖이거나 "unclear"여도 그 조건은 남긴다.
제거는 분명한 "no"일 때만이다.
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
CHECKED_FACTORS = MA_FACTORS + (BOLLINGER_FACTOR,)

EXPRESSES = frozenset({"yes", "no", "unclear"})
DESCRIBES = frozenset({"moving_average", "bollinger", "new_high_breakout", "other"})

_SYSTEM = """당신은 **대조기**입니다. 전략 문장에서 뽑은 조건마다, 함께 적힌 인용 조각이 그 조건을 말하는지 답하세요.

항목마다 두 값을 채웁니다.
expresses — 인용 조각이 그 조건을 말하면 "yes", 그 조건이 아닌 다른 설정(종목 수·손절·기간 등)을 말하면 "no", 판단이 어려우면 "unclear".
describes — 인용 조각이 말하는 신호: 이동평균선·골든크로스·데드크로스면 "moving_average", 볼린저 밴드면 "bollinger", 신고가·고점·박스권 돌파면 "new_high_breakout", 그 밖이면 "other".

출력 형식(JSON만, 항목 순서대로):
{"items": [{"expresses": "yes", "describes": "moving_average"}]}"""


def build_system_prompt() -> str:
    return _SYSTEM


@dataclass(frozen=True)
class Verdict:
    expresses: Optional[str]   # yes / no / unclear / None(enum 밖)
    describes: Optional[str]   # moving_average / bollinger / new_high_breakout / other / None


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
    if factor == BOLLINGER_FACTOR:
        period = _period(params.get("period"))
        band = f"{period}일 볼린저 밴드" if period else "볼린저 밴드"
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


def check_quotes(
    user_input: str, targets: List[Tuple[Any, str]], chat: Callable[..., str],
) -> Optional[QuoteVerdicts]:
    """조건마다 인용 대조 판정을 받는다. 실패는 None(fail-open)."""
    from observability import span
    from strategy_conversation.interpreter.output_repair import extract_json_object

    if not targets:
        return QuoteVerdicts([])
    rows = "\n".join(
        f'{i}. 조건: {render_condition(cond, role)}\n   인용: "{cond.source_text}"'
        for i, (cond, role) in enumerate(targets, 1)
    )
    with span("Quote Check · 조건 인용 대조", "chain",
              inputs={"conditions": [render_condition(c, r) for c, r in targets],
                      "quotes": [c.source_text for c, _ in targets]}) as trace:
        try:
            raw = chat(_SYSTEM, f"[전략 문장]\n{user_input}\n\n[조건]\n{rows}",
                       max_tokens=64 + 32 * len(targets))
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
    """이동평균 조건인데 LLM이 인용이 그 조건을 말하지 **않는다**고 분명히 답했는가.

    unclear·enum 밖·판정 없음은 False(남긴다). 인용이 신고가 돌파를 말한다고 답한 경우는
    제거가 아니라 교정 대상이라 False다.
    """
    verdict = _verdict(verdicts, cond)
    return (verdict is not None and verdict.expresses == "no"
            and verdict.describes != "new_high_breakout"
            and _canonical_factor(cond.factor) in MA_FACTORS)


def quote_describes_breakout(verdicts: Optional[QuoteVerdicts], cond: Any) -> bool:
    """볼린저·단순이동평균 조건인데 LLM이 인용을 신고가·고점·박스권 돌파로 답했는가."""
    verdict = _verdict(verdicts, cond)
    return (verdict is not None and verdict.describes == "new_high_breakout"
            and _canonical_factor(cond.factor) in (BOLLINGER_FACTOR, "technical.ma_crossover"))
