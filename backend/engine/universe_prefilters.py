"""유니버스 사전 필터(엔진 v16.32)의 판정 — 조건·랭킹 이전에 대상 자체를 좁힌다.

엔진은 이 마스크를 진입 신호(`ents_df`)와 랭킹 후보 풀에 그대로 곱한다. 판정은 그날
횡단면(시가총액 분위)이거나 그 시점에 알려진 최신 재무(적자 여부)이며, 신호와 같은
지연(next_open이면 1일)을 거쳐 창에 정렬된다 — 지연은 엔진이 건다.

두 필터의 **모르는 칸 처리가 다르다**(2026-09-23 실측으로 갈랐다):

* 시가총액은 실측·근사 두 경로가 있어 사실상 모든 상장 종목에 값이 있다 → 모르면 제외.
* 재무는 상장폐지 종목에 거의 없다(2026 시점 1%, 2010 시점 0%) → 모르면 **남긴다**.
  모르면 제외로 다루면 상폐 종목이 통째로 사라져 생존 편향이 들어온다. 대신 판정하지
  못한 종목 수를 결과 경고로 알린다(조용한 드롭 금지).
"""

from __future__ import annotations

from typing import Sequence, Tuple

import pandas as pd


def bottom_percentile_mask(panel: pd.DataFrame, cut_pct: float) -> pd.DataFrame:
    """그날 횡단면 백분위 하위 `cut_pct`%를 제외하는 통과 마스크. 값이 없는 칸은 False."""
    return (panel.rank(axis=1, pct=True) > float(cut_pct) / 100.0).fillna(False)


def profitability_mask(panels: Sequence[pd.DataFrame]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """이익 패널들로 만든 (통과 마스크, 판정 가능 마스크).

    통과 마스크는 **적자(<=0)로 확인된 칸만** False다 — 값이 없는 칸은 True(남긴다).
    패널이 여럿이면(both) 모두 통과해야 통과이고, 판정 가능은 하나라도 값이 있으면 참이다.
    """
    if not panels:
        raise ValueError("이익 패널이 비어 있습니다")
    ok = known = None
    for panel in panels:
        has_value = panel.notna()
        passes = ~(has_value & panel.le(0.0))
        ok = passes if ok is None else (ok & passes)
        known = has_value if known is None else (known | has_value)
    return ok, known
