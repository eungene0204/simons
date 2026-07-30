"""변경 이력 — 되돌리기(설계 스펙 § 19)의 근거.

되돌리려면 "무엇이 언제 바뀌었나"를 알아야 한다. 대화는 무상태이므로 이력의 보관은
프론트가 하고(pending_ask·explicit_fields와 같은 에코 계약), 백엔드는 **턴마다 무엇이
바뀌었는지 산출**하고 **어디로 되돌릴지 판정**한다.

여기서 산출하는 것은 사람이 읽는 문장이 아니라 **구조화된 필드 이름**이다 —
`_diff_fields`의 "max_positions: 10 → 5"는 로그용이라 되돌리기 대상으로 쓸 수 없다.
필드 이름이 있어야 "그 필드만 이전 값으로" 복원할 수 있다.

이 모듈은 이벤트 소싱의 전체 구현이 아니다. 상태 재구성(replay)이 아니라 **스냅샷
되감기**이며, 그것이 이 대화 모델에 필요한 전부다 — 각 턴의 ParsedStrategy 전체가
이미 스냅샷이라 이벤트를 되감아 상태를 만들 필요가 없다.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# 되돌리기 대상이 아닌 필드 — 값이 아니라 발화 기록·시스템 표기라 되돌릴 의미가 없다.
_NON_RESTORABLE = frozenset({"description", "theme_universe"})


def changed_field_names(
    before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]]
) -> List[str]:
    """두 ParsedStrategy dump 사이에 값이 달라진 최상위 필드 이름(정렬).

    before가 None이면 최초 턴이라 되돌릴 이전 상태가 없다 — 빈 목록이다(전략 전체가
    처음 생긴 것을 '변경'으로 보면 첫 턴으로 되돌리기가 빈 전략을 만든다).
    """
    if before is None or after is None:
        return []
    return sorted(
        key
        for key in set(before) | set(after)
        if key not in _NON_RESTORABLE and before.get(key) != after.get(key)
    )


# 필드 이름 → 사용자가 쓰는 말. 이력에 영문 필드명만 보여주면 "손절 바꾼 거 되돌려"가
# stop_loss_pct와 연결되지 않아 모델이 엉뚱한 턴을 고른다(2026-07-30 실측: 9B가 손절
# 요청에 fundamental_filters 턴을 선택). 라벨을 키로 정해진 문구를 고르는 결정론 매핑이며
# 원문 해석이 아니다.
_FIELD_LABELS: Dict[str, str] = {
    "universe": "유니버스(시장)",
    "sector": "업종",
    "etf_theme": "ETF 테마",
    "target_symbols": "지정 종목",
    "new_listing_only": "신규 상장 제한",
    "listing_from": "상장 시기 하한",
    "listing_to": "상장 시기 상한",
    "fundamental_filters": "재무 조건(PER·PBR·ROE 등)",
    "entry_signals": "매수 신호",
    "exit_signals": "매도 신호",
    "entry_filters": "매수 필터",
    "ranking_metric": "랭킹 기준",
    "ranking_lookback_days": "랭킹 산정 기간",
    "max_positions": "최대 보유 종목 수",
    "hold_period_days": "보유 기간",
    "rebalancing_period": "리밸런싱 주기",
    "stop_loss_pct": "손절",
    "take_profit_pct": "익절",
    "trailing_stop_pct": "트레일링 스탑",
    "max_mdd_limit_pct": "최대 낙폭(MDD) 한도",
    "backtest_period": "백테스트 기간",
    "backtest_start_date": "백테스트 시작일",
    "backtest_end_date": "백테스트 종료일",
    "initial_capital": "초기 자본",
    "execution_timing": "체결 시점",
    "fee_rate": "수수료율",
    "slippage_rate": "슬리피지율",
}


def label_for(field: str) -> str:
    """필드 이름을 사용자 어휘로. 목록에 없으면 이름 그대로(지어내지 않는다)."""
    return _FIELD_LABELS.get(field, field)


def summarize_for_prompt(events: List[Dict[str, Any]]) -> str:
    """변경 이력을 되돌리기 판정 LLM에 보여줄 텍스트로 만든다.

    값이 아니라 **무엇이 바뀌었는지**만 싣는다 — 판정에 필요한 것은 어느 턴을 가리키는지
    뿐이고, 전략 전체를 실으면 작은 모델이 되돌리기가 아니라 전략 해석을 시작한다.

    필드는 `이름(사용자 어휘)` 형태로 싣는다. 모델이 답에 쓸 이름은 영문 필드명이지만,
    사용자 발화("손절 바꾼 거")와 잇는 다리가 없으면 턴 선택이 어긋난다.
    """
    lines: List[str] = []
    for event in events:
        index = event.get("index")
        text = (event.get("user_text") or "").strip()
        if len(text) > 80:
            text = text[:80] + "…"
        fields = event.get("changed_fields") or []
        changed = (
            ", ".join(f"{f}({label_for(f)})" for f in fields)
            if fields else "(전략 최초 작성)"
        )
        lines.append(f"{index}. \"{text}\" → 바뀐 항목: {changed}")
    return "\n".join(lines)


def restorable_fields(events: List[Dict[str, Any]]) -> List[str]:
    """이력에 등장한 되돌릴 수 있는 필드 전체(정렬, 중복 제거).

    LLM이 고를 수 있는 닫힌 목록이다 — 지어낸 필드 이름을 되돌리기 대상으로 받지 않는다.
    """
    seen: set[str] = set()
    for event in events:
        for field in event.get("changed_fields") or []:
            if isinstance(field, str) and field not in _NON_RESTORABLE:
                seen.add(field)
    return sorted(seen)
