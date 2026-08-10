"""모멘텀(수익률) 랭킹의 상장 전 backfill 오염 가드(엔진 v13.3).

변동성 랭킹 v13.2와 같은 계약 — 랭킹 패널은 bfill 전 원시 종가로 계산해, 상장 후
관측이 lookback개 미만인 신규 상장 종목은 NaN(후보 자연 배제)이어야 한다.
2023-12-01 백테스트 실측(사용자 검증 요청): 상장 10거래일째 에코프로머티가
'최근 60거래일 수익률 상위 1%'로 매수됐다 — bfill 패널의 pct_change가 상장 이후
수익률을 60일 수익률로 위장한 것.
"""
import numpy as np
import pandas as pd

from engine.indicators import lookback_return_panel


def test_momentum_panel_excludes_prelisting_backfill():
    lookback = 60
    n = 103
    idx = pd.bdate_range("2023-07-03", periods=n)
    rng = np.random.default_rng(7)
    old = pd.Series(10000 * np.cumprod(1 + rng.normal(0, 0.01, n)), index=idx)
    # 신규 상장: 마지막 10거래일만 데이터 존재(그 전은 NaN — 엔진 raw_price_df 형태), 급등
    newly = pd.Series(np.nan, index=idx)
    newly.iloc[-10:] = 5000 * np.cumprod(1 + rng.normal(0.05, 0.01, 10))
    raw = pd.DataFrame({"OLD": old, "NEW": newly})

    ret = lookback_return_panel(raw, lookback)
    assert np.isfinite(ret["OLD"].iloc[-1])
    # 상장 10거래일째 — 60일 수익률은 정의되지 않는다(후보 배제)
    assert np.isnan(ret["NEW"].iloc[-1])

    # 오염 경로 재현: bfill된 패널을 넘기면 상장 이후 수익률이 60일 수익률로 위장된다
    # (이 단언이 깨지면 bfill 위장 자체가 사라진 것).
    contaminated = raw.ffill().bfill().pct_change(lookback)
    assert np.isfinite(contaminated["NEW"].iloc[-1])
    assert contaminated["NEW"].iloc[-1] > 0


def test_momentum_panel_defined_once_lookback_observed():
    """상장 후 lookback 봉이 쌓인 시점부터 값이 정의된다 — 기존 종목 동작 불변."""
    lookback = 5
    idx = pd.bdate_range("2024-01-01", periods=12)
    px = pd.Series(np.nan, index=idx)
    px.iloc[2:] = 100.0 + np.arange(10)  # 상장 3번째 봉부터 데이터 존재
    raw = pd.DataFrame({"A": px})

    ret = lookback_return_panel(raw, lookback)
    assert np.isnan(ret["A"].iloc[6])      # 기준 봉(i-5)이 상장 전 — 미정의
    assert np.isfinite(ret["A"].iloc[7])   # 첫 정의 시점(기준 봉 = 첫 실봉)
