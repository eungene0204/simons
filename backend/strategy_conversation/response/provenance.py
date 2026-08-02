"""필드 provenance — "이 설정값을 사용자가 실제로 말했나"의 정본 판정.

되묻기 게이트와 진행률 표시는 "값이 있나"가 아니라 "사용자가 말했나"를 물어야 한다.
설정 필드는 시스템 기본값이 물질화되므로(max_positions=10, initial_capital=10M) 값의
존재만으로는 둘을 구분할 수 없기 때문이다.

그 판정의 유일한 입력은 **인터프리터 LLM의 구조화 출력(StrategySpec)**이다 — 미언급
필드는 None/빈 배열로 오고, 그것이 곧 "사용자가 말하지 않았다"는 LLM의 해석 결과다.
사용자 원문을 정규식으로 재분석해 같은 질문에 답하는 것은 계약 위반이며(§ 판정 기준:
"입력이 사용자 원문이면 그것은 해석이다 → LLM"), 실제로 양방향 사고를 냈다:
  · 오탐 2026-07-29 '원자력 관련주' — '거래대금 20억 원'을 초기 자본 명시로 오인
  · 미탐 2026-07-29 '부채비율·ROE 보유 조건' — '보유 종목은 10개'를 못 잡음

대화 상태 계약: ParsedStrategy 왕복은 기본값을 물질화해 provenance를 지운다
(decompiler `selection_count=parsed.max_positions`). 그래서 이 목록은 pending_ask와
같은 무상태 에코로 프론트가 다음 턴에 되돌려주고, 여기서 합집합으로 누적한다 —
한 번 명시한 값은 이후 턴에서도 명시로 남는다(누적 원문을 보던 기존 의미와 동일).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# 프론트 되묻기 게이트·진행률 슬롯과 1:1로 맞춘 필드 이름(정본).
UNIVERSE = "universe"
MAX_POSITIONS = "max_positions"
REBALANCING = "rebalancing"
BACKTEST_PERIOD = "backtest_period"
INITIAL_CAPITAL = "initial_capital"

KNOWN_FIELDS = (UNIVERSE, MAX_POSITIONS, REBALANCING, BACKTEST_PERIOD, INITIAL_CAPITAL)


def explicit_fields_from_spec(strategy: Any) -> List[str]:
    """LLM 구조화 출력에서 사용자가 명시한 설정 필드를 뽑는다(정규식 무관여).

    strategy: StrategySpec. None이면 빈 목록(판단 근거 없음 = 명시 없음).
    """
    if strategy is None:
        return []
    universe = getattr(strategy, "universe", None)
    portfolio = getattr(strategy, "portfolio", None)
    backtest = getattr(strategy, "backtest", None)

    fields: List[str] = []
    if universe is not None and any((
        getattr(universe, "markets", None),
        getattr(universe, "sectors", None),
        getattr(universe, "symbols", None),
        getattr(universe, "etf_theme", None),
        getattr(universe, "new_listing_only", None),
    )):
        fields.append(UNIVERSE)
    if portfolio is not None and getattr(portfolio, "selection_count", None) is not None:
        fields.append(MAX_POSITIONS)
    if portfolio is not None and getattr(portfolio, "rebalance_frequency", None) is not None:
        fields.append(REBALANCING)
    if backtest is not None and any((
        getattr(backtest, "period", None),
        getattr(backtest, "start_date", None),
        getattr(backtest, "end_date", None),
    )):
        fields.append(BACKTEST_PERIOD)
    if backtest is not None and getattr(backtest, "initial_capital", None) is not None:
        fields.append(INITIAL_CAPITAL)
    return fields


# 패치 경로 → provenance 필드. 인덱스(`/0`)는 정규화 단계에서 떨어진다.
_PATCH_PATH_FIELDS: tuple[tuple[str, str], ...] = (
    ("universe", UNIVERSE),
    ("portfolio.selection_count", MAX_POSITIONS),
    ("portfolio.rebalance_frequency", REBALANCING),
    ("backtest.period", BACKTEST_PERIOD),
    ("backtest.start_date", BACKTEST_PERIOD),
    ("backtest.end_date", BACKTEST_PERIOD),
    ("backtest.initial_capital", INITIAL_CAPITAL),
)


def explicit_fields_from_patches(patches: Optional[Iterable[Any]]) -> List[str]:
    """수정 턴에서 **이번 발화가 실제로 바꾼** 설정 필드(정규식 무관여, 경로 표기만 본다).

    수정 레인은 spec에서 판정하면 안 된다 — 그 spec은 "LLM이 사용자 발화에서 뽑은 것"이
    아니라 **이전 전략을 디컴파일한 초안 + 패치**다. 디컴파일러가 물질화 기본값
    (`initial_capital=10,000,000`)을 채워 넣으므로, 값의 존재로 판정하면 사용자가 말한 적
    없는 기본값이 '명시'로 둔갑한다(2026-08-02 실측 2/2: 백테스트 기간만 답했는데
    initial_capital이 explicit로 올라가 초기 자금을 **묻지 않게 됐다** → 1천만원 조용히 확정).
    이번 턴의 근거는 환각 게이트를 통과한 패치뿐이고, 이전 턴 값은 에코 합집합이 지킨다.
    """
    fields: List[str] = []
    for patch in patches or ():
        raw = getattr(patch, "path", None) or (
            patch.get("path") if isinstance(patch, dict) else None
        )
        parts = [p for p in str(raw or "").strip("/").split("/") if p and not p.isdigit()]
        normalized = ".".join(parts)
        if not normalized:
            continue
        for prefix, field in _PATCH_PATH_FIELDS:
            if normalized == prefix or normalized.startswith(prefix + "."):
                if field not in fields:
                    fields.append(field)
    return fields


def merge_explicit_fields(
    previous: Optional[Iterable[Any]], current: Optional[Iterable[Any]]
) -> List[str]:
    """이전 턴 에코와 이번 턴 판정을 합집합으로 누적한다(정본 순서 유지).

    비정상 입력(문자열 아닌 항목·알 수 없는 이름)은 조용히 버린다 — 프론트 에코는
    신뢰 경계 밖이고, 알 수 없는 이름을 통과시키면 게이트가 오작동한다.
    """
    seen = set()
    for source in (previous or (), current or ()):
        for item in source:
            if isinstance(item, str) and item in KNOWN_FIELDS:
                seen.add(item)
    return [field for field in KNOWN_FIELDS if field in seen]


# ── 비권위 메타데이터 (2026-07-30 사용자 결정) ─────────────────────────────────
# `source`·`updated_at`·`confidence`는 **판정에 쓰지 않는다.** 되묻기 게이트·진행률·
# 실행 가능 여부·사용자 노출·분기 조건은 전부 값과 explicit_fields만 본다.
# 여기 있는 것은 "이 값이 언제, 어느 해석으로 바뀌었나"를 나중에 되짚기 위한 기록이다.
#
# 이 채널을 explicit_fields와 **섞지 않은** 이유: explicit_fields는 게이트가 읽는
# 권위 있는 축이고, 비권위 메타를 같은 자리에 넣으면 언젠가 판정에 새어 든다.
# 소비자가 생기면 그때 권위를 부여할지 따로 판단한다(지금은 부여하지 않는다).
#
# confidence는 **필드별 producer가 없다** — 인터프리터는 턴 하나에 confidence 하나를
# 낸다. 그래서 여기 실리는 값은 '이 필드를 마지막으로 바꾼 해석의 확신도'이며,
# 필드 자체의 확신도가 아니다(4B가 자주 0.0을 내는 신뢰 불가 신호라는 판단도 그대로다 —
# pipeline.py 머리주석). 이름이 사실을 넘어서지 않게 이 주석을 붙여 둔다.
_METADATA_KEYS = ("source", "updated_at", "confidence")


def merge_field_metadata(
    previous: Any,
    changed_fields: Optional[Iterable[Any]],
    *,
    source: str,
    updated_at: str,
    confidence: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """이번 턴에 바뀐 필드의 기록을 이전 턴 에코 위에 덮는다(무상태 누적).

    changed_fields는 change_log와 같은 어휘(ParsedStrategy 최상위 필드 이름)다 —
    explicit_fields의 5개 설정 필드보다 넓다. 바뀌지 않은 필드의 기록은 건드리지 않는다.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    if isinstance(previous, dict):
        for field, meta in previous.items():
            if isinstance(field, str) and isinstance(meta, dict):
                merged[field] = {k: meta[k] for k in _METADATA_KEYS if k in meta}
    entry = {"source": source, "updated_at": updated_at}
    if confidence is not None:
        entry["confidence"] = confidence
    for field in changed_fields or ():
        if isinstance(field, str) and field:
            merged[field] = dict(entry)
    return merged
