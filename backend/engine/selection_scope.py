"""종목 선정 범위(설계 스펙 § 6 `universe.selection_scope`) — 지정인가 후보군인가.

`target_symbols`에는 성격이 다른 두 가지가 같은 모양으로 들어간다:

  ① **지정**   — 사용자가 직접 지목한 종목("삼성전자랑 SK하이닉스로").
                 전부 매수한다. 고를 것이 없으므로 랭킹도 보유 수 상한도 무의미하다.
  ② **후보군** — 테마 조회가 채운 관련 상장사("이차전지 관련주" → 36곳).
                 사용자가 그중에서 고르라고 했다면 고를 대상이다.

둘을 구분하지 않고 "target_symbols가 있으면 지정"으로 보면, 후보군을 지정으로 오인해
**사용자가 말한 선정 기준이 조용히 사라진다** — 실측: "이차전지 관련주 중 최근 60일
수익률 상위 10종목"이 랭킹 없이 36종목 전부 매수로 나갔다(ranking_enabled=False,
max_positions=36). 사용자가 말한 두 가지(랭킹·10종목)가 동시에 증발한다.

구분의 근거는 이미 State에 있다 — `theme_universe`(종목이 어느 테마 조회에서 왔는지)가
있으면 그 종목들은 조회 결과이지 사용자의 지목이 아니다.

**저장하지 않고 계산한다**(하이브리드 상태 모델 § FR-SA-011 ②) — 값에서 온전히 유도되고,
저장하면 테마를 바꿀 때 함께 갱신해야 하는 두 번째 진실이 생긴다.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class SelectionScope(str, Enum):
    """`target_symbols`를 어떻게 다룰 것인가."""

    # 사용자가 지목한 종목 — 전부 매수한다(선정 없음).
    EXPLICIT = "EXPLICIT"
    # 지식 조회가 채운 후보군 — 사용자가 말한 기준으로 그중에서 고른다.
    CANDIDATE_POOL = "CANDIDATE_POOL"
    # 지정 종목이 없다 — 유니버스(시장·업종) 전체가 선정 대상이다.
    UNIVERSE = "UNIVERSE"


def selection_scope(parsed: Any) -> SelectionScope:
    """전략의 종목 선정 범위를 판정한다.

    테마 유래 종목이라도 **사용자가 선정 기준을 말했을 때만** 후보군으로 본다.
    기준이 없으면 기존 동작(전부 매수)을 유지한다 — 테마 유니버스를 임의로 잘라
    상위 N곳만 남기지 않기로 한 결정(2026-07-28 '비만치료 관련주' 사고)을 지킨다.
    선정 기준의 유일한 신호는 랭킹이다: 랭킹이 없으면 "36곳 중 10곳"을 고를 근거가
    없고(무엇을 기준으로 자를지 아무도 말하지 않았다), 있으면 그것이 곧 기준이다.
    """
    if not (getattr(parsed, "target_symbols", None) or []):
        return SelectionScope.UNIVERSE
    if getattr(parsed, "theme_universe", None) and getattr(parsed, "ranking_metric", None):
        return SelectionScope.CANDIDATE_POOL
    return SelectionScope.EXPLICIT
