"""횡단면(cross-sectional) AI 하락 랭킹 청산 — vectorbt 비의존, 단위 테스트 가능.

AI 하락 헤드(ai_drop_score)는 점수가 좁은 밴드(~0.35~0.38)로 압축돼 절대 임계값이
불안정하다(약한 분리). 대신 횡단면 *순위*는 의미가 있으므로(AUC≈0.60), 매일 유니버스
전 종목의 하락점수를 비교해 상위 X%(가장 위험)를 청산 대상으로 삼는다. 이 방식은
유니버스 크기와 무관하게 일관되고, 절대 보정에 의존하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_topk_drop_exits(
    drop_df: pd.DataFrame,
    percentile: float,
    available_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """매일 유니버스 횡단면에서 하락점수 상위 ``percentile``(0~1) 종목을 True로 표시.

    Args:
        drop_df: date×symbol 의 ai_drop_score (높을수록 하락 위험 큼).
        percentile: 청산할 상위 비율(0~1]. 예: 0.1 = 상위 10%.
        available_df: date×symbol 거래가능 마스크. 주어지면 미거래 종목은 랭킹에서 제외.

    Returns:
        drop_df 와 동일 shape 의 boolean DataFrame(청산 대상 True). drop_df 가 None 이면 None.

    선정 개수는 그날 랭킹 가능 종목 수 n 에 대해 ``max(1, floor(n*percentile))`` 로 두어
    유니버스가 작아도 최소 1종목은 청산되게 하고, 점수 동률(압축으로 흔함)은 컬럼 순서
    기준 결정적 타이브레이크('first')로 정확히 k개만 고른다.
    """
    if drop_df is None:
        return None
    empty = pd.DataFrame(False, index=drop_df.index, columns=drop_df.columns)
    if drop_df.empty:
        return empty
    pct = float(percentile)
    if not (0.0 < pct <= 1.0):
        return empty

    scores = drop_df.where(available_df) if available_df is not None else drop_df
    n_valid = scores.notna().sum(axis=1).to_numpy()
    k = np.floor(n_valid * pct).astype(int)
    k = np.where(n_valid > 0, np.maximum(1, k), 0)  # 랭킹 가능 종목이 있으면 최소 1개

    # 하락점수 내림차순 순위(1 = 가장 위험). NaN(미거래)은 순위 없음 → 선정 제외.
    desc_rank = scores.rank(axis=1, ascending=False, method="first")
    mask = desc_rank.le(pd.Series(k, index=scores.index), axis=0)
    return mask.fillna(False)
