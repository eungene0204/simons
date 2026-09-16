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
있으면 그 종목들은 조회 결과이지 사용자의 지목이 아니다. 그 위에 "사용자가 고르라고
했는가"를 얹는다: 랭킹·보유 수·비율 선정 중 하나라도 사용자가 말했으면 고를 대상이다.

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

    **무엇이 '선정 기준을 말했다'인가**(2026-09-16 개정): 종전에는 랭킹 하나뿐이었는데,
    그 규칙은 "아무도 자를 기준을 말하지 않았다"를 전제한다. 사용자가 **보유 종목 수를
    직접 말했다면** 그 전제가 성립하지 않는다 — 실측 사고: "전쟁 관련주 중 … 골든크로스
    매수 … **최대 5종목**"이 66종목 전부 균등 매수로 나갔다(컴파일된 전략에는 5가 남아
    있는데 변환기가 `max_positions=len(target_symbols)`로 덮었다). 사용자가 말한 값이
    질문도 안내도 없이 사라지는 것은 이 모듈이 막으려던 바로 그 결함이다.

    그래서 기준은 셋 중 하나다 — 랭킹(무엇을 기준으로 고르나), 보유 수(몇 개를 고르나),
    비율 선정(몇 %를 고르나). 셋 다 **사용자가 말했을 때만** 값이 선다: 랭킹·비율은
    미언급이면 null이고, 보유 수는 기본값 10이 물질화되므로 컴파일러가 남긴 출처 표식
    (`max_positions_explicit`)을 본다.

    **동점 처리는 이미 있다**: 신호 충족 종목이 빈 자리보다 많은 날은 유니버스 전략에서도
    생기고, 엔진이 기본 순서로 담으며 결과 로그에 경고를 남긴다. 후보군 경로는 유니버스
    경로와 같은 그 처리를 그대로 탄다(랭킹이 있으면 랭킹이, 없으면 그 기본 순서가 고른다).
    """
    if not (getattr(parsed, "target_symbols", None) or []):
        return SelectionScope.UNIVERSE
    if getattr(parsed, "theme_universe", None) and (
        getattr(parsed, "ranking_metric", None)
        or getattr(parsed, "max_positions_explicit", False)
        or getattr(parsed, "max_positions_pct", None)
    ):
        return SelectionScope.CANDIDATE_POOL
    return SelectionScope.EXPLICIT
