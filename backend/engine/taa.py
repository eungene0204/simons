"""전술 자산배분 템플릿(엔진 v16.29) — VAA·DAA·PAA(Keller) 비중 스케줄.

사용자가 말한 공격·방어(·카나리아) 자산 목록과 모델 이름으로, 거래일마다 그 시점까지의 가격으로
정한 목표 비중 패널을 만든다. 엔진은 이 패널을 랭킹 점수(rank_df)·후보(비중>0)·비중 방식
('schedule' — 기준값에 비례)으로 순수 리밸런싱 경로에 태운다. 월간 리밸런싱이 전제다.

모멘텀 점수(13612W, Keller): 12·r1 + 4·r3 + 2·r6 + r12 (r_k = 최근 k개월 수익률, 1개월=21거래일).

  VAA: 공격 자산 중 점수가 음수인 개수 ≥ breadth(기본 1)면 방어 자산 중 점수 최고 하나에 100%,
       아니면 점수 상위 top_n 공격 자산에 균등.
  DAA: 카나리아 자산 중 점수가 음수인 비율(b/len)만큼을 방어 자산 최고 하나에, 나머지를 점수
       상위 top_n 공격 자산에 균등.
  PAA: 공격 자산 중 가격 > 12개월 SMA(252거래일 평균)인 개수 n. 채권 비중 = (N−n)/(N−a)
       (a=protection, 기본 1, 0~1로 자름)을 방어 자산 최고 하나에, 나머지를 (가격/SMA−1) 상위
       top_n(양수인 것만) 공격 자산에 균등. 양수 자산이 없으면 전부 방어.

자료가 모자란 초기 구간(12개월 수익률·SMA가 NaN)은 비중 NaN(후보 없음 → 현금).
"""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

MODELS = ("vaa", "daa", "paa")
MONTH_DAYS = 21
DEFAULT_TOP_N = {"vaa": 1, "daa": 3, "paa": 3}
SMA_DAYS = 252
LOOKBACK_DAYS = SMA_DAYS + MONTH_DAYS


def momentum_13612w(price: pd.DataFrame) -> pd.DataFrame:
    """13612W 모멘텀 점수 패널(종목별). 입력은 ffill한 종가 패널(bfill 금지)."""
    px = price.ffill()
    r1 = px / px.shift(MONTH_DAYS) - 1.0
    r3 = px / px.shift(3 * MONTH_DAYS) - 1.0
    r6 = px / px.shift(6 * MONTH_DAYS) - 1.0
    r12 = px / px.shift(12 * MONTH_DAYS) - 1.0
    return 12.0 * r1 + 4.0 * r3 + 2.0 * r6 + r12


def _best(scores: pd.Series) -> Optional[str]:
    s = scores.dropna()
    return None if s.empty else str(s.idxmax())


def taa_weight_panel(price: pd.DataFrame, model: str, offensive: List[str], defensive: List[str],
                     canary: Optional[List[str]] = None, top_n: Optional[int] = None,
                     breadth: Optional[int] = None, protection: int = 1) -> pd.DataFrame:
    """거래일 × 종목 목표 비중(합 ≤ 1, 자료 부족 행은 NaN). 열은 price의 열 순서를 따른다."""
    model = str(model).lower()
    if model not in MODELS:
        raise ValueError(f"알 수 없는 전술 자산배분 모델: {model}")
    offensive = [s for s in offensive if s in price.columns]
    defensive = [s for s in defensive if s in price.columns]
    canary = [s for s in (canary or []) if s in price.columns]
    if not offensive or not defensive:
        raise ValueError("전술 자산배분에는 공격 자산과 방어 자산이 각각 하나 이상 필요합니다")
    k = int(top_n or DEFAULT_TOP_N[model])
    k = max(1, min(k, len(offensive)))
    px = price.ffill()
    score = momentum_13612w(price)
    out = pd.DataFrame(np.nan, index=price.index, columns=price.columns, dtype=float)
    if model == "paa":
        sma = px.rolling(SMA_DAYS).mean()
        mom = px / sma - 1.0
    for i, day in enumerate(price.index):
        row = np.zeros(len(price.columns))
        col_pos = {c: j for j, c in enumerate(price.columns)}
        off_scores = score.loc[day, offensive] if model != "paa" else mom.loc[day, offensive]
        def_scores = score.loc[day, defensive]
        if off_scores.isna().all() or def_scores.isna().all():
            continue
        best_def = _best(def_scores)
        if model == "vaa":
            neg = int((off_scores < 0).sum())
            b = int(breadth or 1)
            if neg >= b:
                if best_def is None:
                    continue
                row[col_pos[best_def]] = 1.0
            else:
                top = off_scores.dropna().sort_values(ascending=False).index[:k]
                for s in top:
                    row[col_pos[s]] = 1.0 / len(top)
        elif model == "daa":
            if canary:
                can = score.loc[day, canary]
                if can.isna().all():
                    continue
                cash_frac = float((can < 0).sum()) / float(len(canary))
            else:
                cash_frac = 1.0 if int((off_scores < 0).sum()) >= 1 else 0.0
            cash_frac = min(1.0, max(0.0, cash_frac))
            if cash_frac > 0 and best_def is not None:
                row[col_pos[best_def]] += cash_frac
            if cash_frac < 1.0:
                top = off_scores.dropna().sort_values(ascending=False).index[:k]
                for s in top:
                    row[col_pos[s]] += (1.0 - cash_frac) / len(top)
        else:  # paa
            n_good = int((off_scores > 0).sum())
            n_all = len(offensive)
            a = min(int(protection), n_all - 1) if n_all > 1 else 0
            bond_frac = (n_all - n_good) / float(max(n_all - a, 1))
            bond_frac = min(1.0, max(0.0, bond_frac))
            if bond_frac > 0 and best_def is not None:
                row[col_pos[best_def]] += bond_frac
            if bond_frac < 1.0 and n_good > 0:
                good = off_scores[off_scores > 0].sort_values(ascending=False).index[:k]
                for s in good:
                    row[col_pos[s]] += (1.0 - bond_frac) / len(good)
        out.iloc[i] = row
    return out


def taa_symbols(spec: Dict) -> List[str]:
    """설정에 등장하는 종목 전체(중복 제거, 순서 유지)."""
    seen: List[str] = []
    for key in ("offensive", "defensive", "canary"):
        for s in spec.get(key) or []:
            if s and s not in seen:
                seen.append(s)
    return seen
