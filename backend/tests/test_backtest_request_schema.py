"""BacktestRequest 스키마가 모멘텀 랭킹 필드를 보존하는지 검증.

회귀 배경: RiskManagement 스키마에 ranking_metric/ranking_lookback_days가 없어서
Pydantic이 조용히 버렸고(extra=ignore), 프론트가 risk.ranking_metric='return'을 보내도
엔진은 None을 받아 진입 후보가 0이 되어 0거래로 끝났다(표시 배지엔 '21일 수익률 상위'가
보이는데 실행은 안 됨). 엔진을 직접 호출하면(스키마 우회) 정상 동작해 진단이 어려웠다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from schemas import BacktestRequest, RiskManagement


def test_risk_management_preserves_ranking_fields():
    risk = RiskManagement(
        position_size_pct=20.0,
        max_positions=5,
        rebalancing_period="monthly",
        ranking_metric="return",
        ranking_lookback_days=21,
    )
    dumped = risk.model_dump()
    assert dumped["ranking_metric"] == "return"
    assert dumped["ranking_lookback_days"] == 21


def test_backtest_request_model_dump_keeps_ranking():
    # 엔드포인트는 engine.run_backtest(request.model_dump())로 실행하므로,
    # model_dump 단계에서 랭킹이 살아남아야 엔진이 '선정=진입'을 적용한다.
    req = BacktestRequest(
        symbols=["005930", "000660"],
        universe_id="kospi",
        entry={"conditions": []},
        exit={"conditions": []},
        risk={
            "position_size_pct": 20.0,
            "max_positions": 5,
            "ranking_metric": "return",
            "ranking_lookback_days": 21,
            "init_cash": 10000000,
        },
        period="5Y",
    )
    dumped = req.model_dump()
    assert dumped["risk"]["ranking_metric"] == "return"
    assert dumped["risk"]["ranking_lookback_days"] == 21


def test_ranking_fields_default_to_none():
    # 랭킹을 안 쓰는 전략은 명시적으로 None이어야 한다(엔진이 펀더멘털 랭킹 분기로 감).
    risk = RiskManagement(position_size_pct=10.0)
    dumped = risk.model_dump()
    assert dumped["ranking_metric"] is None
    assert dumped["ranking_lookback_days"] is None


if __name__ == "__main__":
    test_risk_management_preserves_ranking_fields()
    test_backtest_request_model_dump_keeps_ranking()
    test_ranking_fields_default_to_none()
    print("[SUCCESS] BacktestRequest ranking schema regression passed.")
