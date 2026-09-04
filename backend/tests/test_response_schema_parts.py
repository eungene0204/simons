"""/backtest 응답 스키마가 구조화 사유·경고를 보존하는지 — 2026-09-04 사고 회귀.

엔진은 매매사유를 `condition`(한국어 정본)과 `conditionParts`(세그먼트)로, 경고를 `warnings`와
`warningParts`로 함께 싣는다(엔진 v16.4.2·v16.5.1). 그런데 `/backtest`는 `response_model=
BacktestResponse`라 스키마에 없는 필드는 조용히 사라진다 — 프론트가 한국어 문장으로 폴백해
/us 거래 내역과 CSV 내보내기에 "손절매 실행 … 247원" 같은 한글이 그대로 나갔다.
"""

from engine import trade_reason as tr
from schemas import BacktestResponse, SignalResult


def _minimal_result(**overrides):
    base = {
        "symbols": ["AAPL"],
        "totalReturn": 1.0, "cagr": 1.0, "buyAndHoldReturn": 0.5, "maxDrawdown": -2.0,
        "winRate": 50.0, "sharpe": 0.1, "sortino": 0.1, "volatility": 10.0, "trades": 1,
        "equity": [1.0, 1.01], "dates": ["2024-01-02", "2024-01-03"],
        "signals": [],
    }
    base.update(overrides)
    return base


def test_signal_result_keeps_condition_parts():
    parts = [tr.part(tr.STOP_LOSS_PCT, "10"), tr.part(tr.PNL_DETAIL_LOSS, "-8.45", 247.0, money=[1])]
    dumped = SignalResult(
        date="2024-03-12", symbol="AAPL", type="sell", price=168.42, quantity=3, amount=505.26,
        condition=tr.render_kr(parts), conditionParts=parts, pnl=-247.0,
    ).model_dump()
    assert dumped["conditionParts"] == parts


def test_backtest_response_keeps_condition_and_warning_parts():
    parts = [tr.part(tr.ENTRY_SIGNAL_FALLBACK)]
    warning_parts = [[tr.part(tr.NO_TRADES)]] if hasattr(tr, "NO_TRADES") else [[tr.literal("경고")]]
    result = _minimal_result(
        signals=[{
            "date": "2024-03-12", "symbol": "AAPL", "type": "buy", "price": 168.42,
            "quantity": 3, "amount": 505.26, "condition": tr.render_kr(parts), "conditionParts": parts,
        }],
        warnings=["경고"],
        warningParts=warning_parts,
    )
    dumped = BacktestResponse(**result).model_dump()
    assert dumped["signals"][0]["conditionParts"] == parts
    assert dumped["warningParts"] == warning_parts


def test_legacy_signal_without_parts_still_validates():
    # 구버전 캐시·과거 결과는 파츠가 없다 — 응답 모델이 거절하면 안 된다.
    dumped = SignalResult(
        date="2024-03-12", symbol="005930", type="buy", price=72100, quantity=10, amount=721000,
        condition="매수 조건 충족 (전략 시그널)",
    ).model_dump()
    assert dumped["conditionParts"] is None
