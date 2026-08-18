"""값 없이 지목된 수정 대상(clarify_target)의 닫힌 목록 — 되묻기 레인 이관용.

이관 전에는 프론트 정규식이 원문을 읽어 "무엇을 바꾸려는데 값이 없다"를 판정했다
(`getModificationClarification`·`buildTakeProfitPercentagePrompt`·
`buildFundamentalFactorPrompt`). 그 판정은 의미 해석이므로 LLM 소관이다(대원칙 1).

여기서는 **LLM이 고를 수 있는 값의 목록**과, LLM이 뽑은 (대상·값 표기·삭제 여부)에서
되묻기 대상을 정하는 결정론 판정(`resolve_clarify_target`)만 정의한다. 무엇을 물을지
(문구·선택지)는 프론트의 기존 표가 라벨을 키로 고른다 — "라벨을 키로 정해진 안내 문구를
고른다"는 허용 패턴이며, 문구를 새로 짓지 않으므로 이관으로 표현이 바뀌지 않는다.

LLM에게 `clarify_target`을 직접 내게 하지 않는 이유(2026-08-17): "값이 함께 있으면
null"이라는 조건부 규칙을 9B가 지키지 않아('손절을 -15%로 해줘' → stop_loss, 실측 9/9)
값이 있는데도 되물었다. 대상과 값 표기를 **각각 뽑게** 하면 지킨다(9/9) — 출력 형태가
산문 규칙보다 강하다.

재무 지표 키의 정본은 `data/fundamental-factors.json` 하나다(프론트와 공유).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data" / "fundamental-factors.json"

# 값이 빠진 채 지목된 **설정 필드**. 값 칩으로 되묻는다.
SETTING_TARGETS: tuple[str, ...] = (
    "stop_loss",
    "take_profit",
    "trailing_stop",
    "mdd",
    "max_positions",
    "hold_period",
    "rebalancing",
    "initial_capital",
    "backtest_period",
)

# 값도 필드도 없이 **영역만** 지목한 경우. 영역 선택지로 되묻는다.
AREA_TARGETS: tuple[str, ...] = (
    "entry_signal",
    "exit_signal",
    "universe",
    "target_symbols",
    "portfolio",
    "risk",
    "condition",
)


@lru_cache(maxsize=1)
def factor_targets() -> tuple[str, ...]:
    """재무 지표 키 목록(정본 JSON 순서 그대로)."""
    try:
        entries = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(
        str(e["key"]) for e in entries if isinstance(e, dict) and e.get("key")
    )


@lru_cache(maxsize=1)
def allowed_targets() -> frozenset[str]:
    return frozenset(SETTING_TARGETS + AREA_TARGETS + factor_targets())


def normalize_clarify_target(value: object) -> Optional[str]:
    """LLM이 낸 표기를 목록의 값으로 정규화한다. 목록 밖이면 None.

    입력이 LLM 출력이므로 표기 정규화는 결정론 코드 소관이다(계약 § 3-2).
    모르는 값을 되묻기 대상으로 승격하지 않는다 — 없는 문구를 물을 수는 없다.
    """
    if not isinstance(value, str):
        return None
    label = value.strip().strip("\"'").lower().replace("-", "_").replace(" ", "_")
    if not label or label in ("null", "none", "n/a", "없음"):
        return None
    return label if label in allowed_targets() else None


def _has_value(value: object) -> bool:
    """LLM이 modify_value에 값의 원문 표기를 실었는가. null 표기·빈 문자열은 '값 없음'.

    '없음'은 null 표기로 보지 않는다 — '리밸런싱 없음으로'처럼 값 자체일 수 있다."""
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        text = value.strip().strip("\"'")
        return bool(text) and text.lower() not in ("null", "none", "n/a")
    return False


def resolve_clarify_target(
    modify_target: object, modify_value: object, modify_removes: object,
) -> Optional[str]:
    """LLM이 뽑은 (대상, 값 표기, 삭제 여부)에서 되묻기 대상을 결정한다.

    되묻기는 **값이 없어 무엇으로 바꿀지 알 수 없을 때**만 성립한다. 값 표기가 실려
    있으면(값의 해석은 파스 레인 LLM 몫) 되묻지 않고, 지워 달라는 요청도 값이 필요
    없으므로 되묻지 않는다. 판정 입력은 전부 LLM 출력이고 표기 유무만 보므로 결정론
    소관이다(계약 § 3-2). 값 표기의 **내용**은 여기서 읽지 않는다.
    """
    target = normalize_clarify_target(modify_target)
    if target is None:
        return None
    if _has_value(modify_value):
        return None
    if modify_removes is True or (
        isinstance(modify_removes, str) and modify_removes.strip().lower() == "true"
    ):
        return None
    return target


def prompt_target_lines() -> str:
    """분류 프롬프트에 넣을 목록 텍스트(정본에서 생성 — 목록이 갈라지지 않게)."""
    return (
        "  설정 값: " + " / ".join(SETTING_TARGETS) + "\n"
        "  영역: " + " / ".join(AREA_TARGETS) + "\n"
        "  재무 지표: " + " / ".join(factor_targets())
    )
