"""조건 누락 대조 패스 — 1차 해석이 빠뜨린 조건을 **LLM에게 다시 묻는다**.

왜 필요한가(2026-08-18 실측): 9B는 조건이 여러 개 나열된 문장에서 **하나를 밀어낸다**.
temperature 0에서 재현되고, 무엇이 밀릴지는 위치·문장 길이가 정한다.
  - "…매출 성장률이 양호하고 PBR이 과도하게 높지 않은 기업만…" → PBR 소실
  - 순서를 바꾸면 둘 다 나오고, PBR만 남기면 이번엔 시가총액(숫자 조건)이 소실
프롬프트 규칙 보강은 효과가 없었고(규칙 4-1 확장 실측) 오히려 다른 예시의 조건을 밀어냈다.
num_ctx를 32768로 올려도 동일하다 — 컨텍스트 부족이 아니라 1차 생성의 회수(recall) 문제다.

계약상 위치: 이 패스는 **LLM 레인**이다(대원칙 1). 사용자 원문의 의미를 읽는 주체는 여기서도
LLM이고, 결정론 코드는 그 출력의 형식·정본 매핑·출처 대조만 한다:
  ① factor는 registry가 아는 것만(모르는 이름은 버린다)
  ② source_text는 입력에 실재해야 한다(_quote_has_echo — 환각 조건 가드와 같은 대조)
  ③ 이미 있는 factor는 다시 넣지 않는다
  ④ 값은 만들지 않는다 — 값이 없으면 MISSING으로 두고 되묻기 레인이 질문한다

2026-08-07에 폐지된 '전체 재생성'과 다른 점: 재생성은 1차와 **같은 정보**로 다시 만들게 해
47%가 바이트 동일이었다. 이 패스는 1차 출력을 근거로 주고 "빠진 것만" 뽑게 하므로 과제가
다르고, 1차 결과를 덮어쓰지 않는다(추가만 한다).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, List, Optional

from strategy_conversation.registry.indicator_registry import (
    REGISTRY,
    factor_ids_named_in,
    resolve,
)

logger = logging.getLogger(__name__)

# 랭킹 정본 → 같은 개념의 조건 지표(이름이 같은 쌍). 랭킹에 있으면 조건으로 되살리지 않는다.
_RANKING_CONDITION_TWINS = {
    "ranking.volatility": frozenset({"technical.volatility"}),
    "ranking.return": frozenset({"technical.roc"}),
    "ranking.relative_return": frozenset({"technical.relative_return"}),
}

# 한 턴에 되살리는 조건 수 상한 — 대조 패스가 폭주해 전략을 새로 쓰는 것을 막는다.
_MAX_RECOVERED = 3

_SYSTEM = """당신은 **추출기**입니다. 전략 문장에서 **조건을 말한 구절**을 빠짐없이 나열하세요.

규칙:
- 지표를 이름으로 부른 구절만 나열합니다(PBR·ROE·시가총액·거래대금·RSI·이동평균 등).
- 구절은 **입력 문장에 있는 그대로** 적습니다(요약·번역 금지).
- 값이 없어도 나열합니다("PBR이 과도하게 높지 않은"도 조건입니다).
- 유니버스(시장·업종)·종목 수·리밸런싱·손절·익절·기간·초기자금은 조건이 아닙니다 — 빼세요.
- 판단하지 말고 나열만 하세요. 순서는 문장에 나온 순서대로.

출력 형식(JSON만, 설명 금지):
{"phrases": ["<입력 조각>", "..."]}"""


def build_system_prompt() -> str:
    return _SYSTEM


def _draft_summary(conditions: List[Any]) -> str:
    rows = []
    for cond in conditions:
        quote = (getattr(cond, "source_text", None) or "").strip()
        rows.append(f'- {cond.factor} (근거: "{quote}")' if quote else f"- {cond.factor}")
    return "\n".join(rows) if rows else "- (없음)"


def extract_condition_phrases(
    user_input: str,
    chat: Callable[..., str],
) -> List[str]:
    """LLM에게 '조건을 말한 구절'만 나열시킨다 — 차집합 판단은 시키지 않는다.

    9B는 "무엇이 빠졌나"(집합 차) 과제를 신뢰할 수 없다(2026-08-18 실측: 1차가 PBR을
    빠뜨린 상태를 그대로 보여줘도 `{"missing": []}`). 나열은 훨씬 쉬운 과제이고, 대조는
    결정론이 정확하게 한다.

    실패(호출 오류·JSON 불성립)는 빈 목록이다 — 보조 그물이 턴을 깨지 않는다.
    """
    from strategy_conversation.interpreter.output_repair import extract_json_object

    try:
        raw = chat(build_system_prompt(), f"[전략 문장]\n{user_input}", max_tokens=512)
    except Exception:  # noqa: BLE001 — 보조 그물이 턴을 깨지 않는다
        logger.debug("condition recall pass failed", exc_info=True)
        return []
    try:
        payload = json.loads(extract_json_object(raw))
    except (ValueError, TypeError):
        return []
    phrases = payload.get("phrases") if isinstance(payload, dict) else None
    if not isinstance(phrases, list):
        return []
    return [p.strip() for p in phrases if isinstance(p, str) and p.strip()]


def recover_missing_conditions(
    intent: Any,
    user_input: str,
    chat: Callable[..., str],
    phrases: Optional[List[str]] = None,
) -> List[str]:
    """LLM이 나열한 구절 중 **1차 전략에 없는 지표**를 되살린다. 반환값은 factor id 목록.

    phrases: 1차 해석과 동시에 미리 뽑아 둔 구절(병렬 파스). 나열 호출은 원문만 입력으로
    받으므로 먼저 받아도 결과가 같다 — None이면 여기서 뽑는다.
    """
    from strategy_conversation.interpreter.models import StrategyCondition
    from strategy_conversation.primary import _quote_has_echo
    from engine.nl_parser import _compact

    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return []
    existing = list(strategy.entry_conditions) + list(strategy.exit_conditions)
    known = {cond.factor for cond in existing}
    # 랭킹으로 이미 표현된 지표도 빠진 것이 아니다(2026-09-19 실측 120B: '12개월 수익률에서
    # 1개월 제외한 모멘텀'·'60일 변동성이 낮은'이 랭킹에 있는데 ROC·변동성 **조건**으로 되살아나
    # 엉뚱한 기준값 질문이 먼저 나갔다). 랭킹 정본과 같은 개념의 조건 지표를 함께 안다고 본다.
    for rank in getattr(strategy, "ranking", None) or []:
        spec = resolve(rank.metric)
        if spec is None:
            continue
        known.add(spec.id)
        known |= _RANKING_CONDITION_TWINS.get(spec.id, frozenset())
    # 이미 어떤 조건의 **근거로 쓰인 구절**은 빠진 것이 아니다. factor만 대조하면,
    # 결정론 보정이 지표를 바꾼 조건('거래대금이 30일 평균보다 높은'→거래량 급증)을
    # 원래 지표로 되살려 같은 문구가 두 조건이 된다(2026-08-18 실측).
    # 랭킹·시장 국면 필터의 인용과 1차가 미지원으로 보고한 표현도 같은 뜻이다 — 셋 다
    # 1차가 이미 자리를 정한 구절이다(2026-09-19 실측: '코스피가 200일 이동평균선 아래에
    # 있으면'이 국면 필터로 반영됐는데 종목 이동평균 매수 조건으로 되살아났다 — 운영의
    # "이동평균 조건이 아니어서…" 안내와 로컬의 20/60 골든크로스 둔갑이 이 경로였다).
    quotes = [cond.source_text for cond in existing]
    quotes += [getattr(r, "source_text", None) for r in getattr(strategy, "ranking", None) or []]
    market_filter = getattr(strategy, "market_filter", None)
    if market_filter is not None:
        quotes.append(market_filter.source_text)
    quotes += list(getattr(intent, "unsupported_features", None) or [])
    used_quotes = {_compact(q) for q in quotes if q}

    if phrases is None:
        phrases = extract_condition_phrases(user_input, chat)
    compact_input = _compact(user_input)
    recovered: List[str] = []
    for phrase in phrases:
        if len(recovered) >= _MAX_RECOVERED:
            break
        compact_phrase = _compact(phrase)
        # ② 구절이 입력에 실재해야 한다(환각 조건 가드와 같은 출처 대조).
        if not _quote_has_echo(compact_phrase, compact_input):
            continue
        # ②-1 이미 쓰인 근거면 건너뛴다(양방향 포함 — 구절 경계가 조금씩 다르다).
        if any(
            compact_phrase in used or used in compact_phrase
            for used in used_quotes
            if used
        ):
            continue
        # ③ 구절이 지표를 **이름으로 불러야** 한다 — 정성 표현을 새 지표로 매핑하는 것은
        #    1차 해석의 몫이고, 이 패스는 되살리는 그물이지 해석하는 자리가 아니다
        #    (2026-08-18 실측: 대조를 LLM에 맡겼더니 '추세가 확실히 잡힌'→technical.roc,
        #    문장에 없는 AI 예측 조건까지 만들어 없던 되묻기가 생겼다).
        named = factor_ids_named_in(phrase)
        # 구절이 **미지원 개념만** 부르면 조건으로 되살릴 수는 없지만 조용히 사라지게 둘 수도
        # 없다 — 1차가 자리를 정하지 않은 구절이므로 미지원 보고로 올린다(2026-09-19 실측 120B
        # 2/3: '최근 3개월 실적 추정치 상향 여부'가 어디에도 없이 소실). 지식 조회는 LLM이
        # 뽑은 구절 → 레지스트리 별칭 대조(§ 3-2)다.
        if named and all(
            REGISTRY.get(n) is not None and REGISTRY[n].supported == "UNSUPPORTED" for n in named
        ):
            features = list(getattr(intent, "unsupported_features", None) or [])
            if phrase not in features:
                intent.unsupported_features = features + [phrase]
            continue
        for factor_id in sorted(named):
            if len(recovered) >= _MAX_RECOVERED:
                break
            if factor_id in known:
                continue
            spec = REGISTRY.get(factor_id)
            # ① registry가 모르거나 엔진에 붙지 않는 개념은 버린다.
            if spec is None or spec.engine_binding is None:
                continue
            strategy.entry_conditions.append(
                StrategyCondition(
                    factor=spec.id,
                    operator=None,
                    value=None,
                    # ④ 값은 만들지 않는다 — 되묻기 레인이 질문한다.
                    value_source="MISSING",
                    source_text=phrase,
                )
            )
            known.add(spec.id)
            recovered.append(spec.id)
    return recovered


# ── 백테스트 기간 회수 패스 ────────────────────────────────────────────────────
# 조건과 같은 결함이 설정 슬롯에서도 난다(2026-09-16 실측): "…손절은 -8%, 최대 5종목,
# 최근 1년, 초기 자본 1000만원으로 백테스트해 주세요"에서 1차 해석이 **기간만** 빠뜨렸고
# (같은 문장 API 6회 중 1회는 5y로 뒤바뀜), 사용자는 이미 말한 값을 다시 답해야 했다.
# 조건 회수와 같은 계약이다 — 판정은 LLM, 결정론은 ① 출처 대조 ② 정본 표기 정규화
# ③ 덮어쓰기 금지만 한다. 조건 회수 프롬프트에 얹지 않고 따로 두는 이유: 기간을 이미
# 해석한 턴(대부분)에서는 호출 자체가 없어야 하고, 조건 추출 프롬프트를 건드리면
# 조건 회수 쪽 품질이 함께 흔들린다(프롬프트 분량 회귀 계약).
_PERIOD_SYSTEM = """당신은 **추출기**입니다. 전략 문장에서 **백테스트 기간을 말한 구절**을 찾으세요.

규칙:
- 과거 데이터를 얼마나 쓸지 말한 구절만 찾습니다("최근 1년", "3년치 데이터", "전체 기간").
- 다음은 백테스트 기간이 **아닙니다** — 빼세요: 지표 기간(20일 이동평균), 보유 기간,
  리밸런싱 주기, 수익률 산정 기간.
- quote는 **입력 문장에 있는 그대로** 적습니다(요약·번역 금지).
- period는 말한 그대로 옮겨 적습니다: <N>y(년) / <N>m(개월) / full(전체 기간).
- 해당 구절이 없으면 {"quote": null, "period": null}.
- 판단하지 말고 옮겨 적기만 하세요.

출력 형식(JSON만, 설명 금지):
{"quote": "<입력 조각>", "period": "<N>y"}"""


def build_period_system_prompt() -> str:
    return _PERIOD_SYSTEM


def recover_backtest_period(
    intent: Any,
    user_input: str,
    chat: Callable[..., str],
) -> Optional[str]:
    """1차 해석이 빠뜨린 백테스트 기간을 되살린다. 반환값은 채워진 표기(없으면 None).

    호출 전제: `strategy.backtest.period`도 명시 날짜도 비어 있는 턴에서만 부른다.
    이미 값이 있으면 **절대 덮어쓰지 않는다** — 회수는 빈 칸을 채우는 그물이지
    1차 해석을 교정하는 자리가 아니다(조건 회수의 '추가만 한다'와 같은 계약).
    """
    from strategy_conversation.interpreter.models import BacktestSpec
    from strategy_conversation.interpreter.output_repair import extract_json_object
    from strategy_conversation.primary import _quote_has_echo
    from engine.nl_parser import _compact

    strategy = getattr(intent, "strategy", None)
    if strategy is None:
        return None
    spec = strategy.backtest
    if spec.period is not None or spec.start_date or spec.end_date:
        return None
    try:
        raw = chat(_PERIOD_SYSTEM, f"[전략 문장]\n{user_input}", max_tokens=128)
    except Exception:  # noqa: BLE001 — 보조 그물이 턴을 깨지 않는다
        logger.debug("backtest period recall pass failed", exc_info=True)
        return None
    try:
        payload = json.loads(extract_json_object(raw))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    transcribed = payload.get("period")
    quote = payload.get("quote")
    if not isinstance(transcribed, str) or not transcribed.strip():
        return None
    # ① 출처 대조 — LLM이 인용한 조각이 입력에 실재해야 한다(환각 조건 가드와 같은 판정).
    #    인용을 내지 않았으면 대조할 수 없으므로 채우지 않는다(되묻기가 정상 동작).
    if not isinstance(quote, str) or not quote.strip():
        return None
    if not _quote_has_echo(_compact(quote), _compact(user_input)):
        return None
    # ② 정본 표기 정규화 — 버킷·날짜 창 변환은 BacktestSpec이 이미 가진 결정론 규칙이다
    #    (<N>y 옮겨 적기 계약, 2026-09-07). 표현 불가(1년 미만)면 비운 채 되묻기로 보낸다.
    #    1년 미만이 버려지는 덕에 지표 기간·랭킹 산정 기간·짧은 보유 기간은 애초에 새지 않는다.
    try:
        filled = BacktestSpec.model_validate(
            {**spec.model_dump(), "period": transcribed.strip()}
        )
    except Exception:  # noqa: BLE001 — Literal 검증 실패는 '못 읽은 것'과 같다
        return None
    if filled.period is None and not filled.start_date:
        return None
    # ③ 보유 기간과 같은 길이면 채우지 않는다 — 1년 이상인 보유 기간("최대 보유 2년")은
    #    위 하한을 통과하므로, 프롬프트의 제외 규칙을 모델이 어기면 그대로 백테스트 창이
    #    된다. 판정은 두 숫자 대조뿐이다(원문도 어휘도 보지 않는다). 겹치면 되묻기에 맡긴다.
    if _matches_hold_period(strategy, transcribed.strip()):
        logger.debug("backtest period recall skipped — matches hold period")
        return None
    strategy.backtest = filled
    return filled.period or f"{filled.start_date}~{filled.end_date}"


# 거래일/월 환산 — 되묻기 칩·엔진이 쓰는 근사(1개월 ≈ 21거래일, 1년 ≈ 252거래일)와 같다.
_TRADING_DAYS_PER_MONTH = 21
_HOLD_PERIOD_TOLERANCE_DAYS = 21


def _matches_hold_period(strategy: Any, transcribed: str) -> bool:
    """회수한 기간이 이미 잡힌 **보유 기간**과 같은 길이인가(숫자 대조뿐)."""
    from strategy_conversation.interpreter.models import _normalize_period

    hold_days = getattr(getattr(strategy, "portfolio", None), "hold_period_days", None)
    if not hold_days:
        return False
    normalized = _normalize_period(transcribed)
    if isinstance(normalized, tuple):                     # ("window", 개월수)
        months = normalized[1]
    elif normalized == "1y":
        months = 12
    elif normalized == "3y":
        months = 36
    elif normalized == "5y":
        months = 60
    else:                                                 # "full" 등 — 길이 비교 불가
        return False
    return abs(months * _TRADING_DAYS_PER_MONTH - hold_days) <= _HOLD_PERIOD_TOLERANCE_DAYS
