import copy
from datetime import date, datetime, timezone

import pytest

from public_simulation.summary import (
    SimulationResultError, build_public_result, check_executable, contributors, downsample, summarize,
)
from public_simulation.window import compute_window

NOW = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)
WINDOW = compute_window(NOW, date(2026, 10, 27))

SNAPSHOT = {
    "universe_id": "kospi200",
    "symbols": ["005930", "000660"],
    "entry": {"conditions": [{"type": "indicator", "id": "rsi", "params": {"period": 14}}]},
    "exit": {"conditions": []},
    "risk": {"position_size_pct": 10, "init_cash": 10_000_000, "execution_timing": "next_open"},
    "options": {"fee_rate": 0.00015, "slippage_rate": 0.0005},
    "period": "5y",
}


def engine_result(**over):
    equity = [10_000_000, 10_500_000, 9_900_000, 11_000_000]
    base = {
        "initialCapital": 10_000_000, "equity": equity,
        "dates": ["2023-10-30", "2024-10-30", "2025-10-30", "2026-10-27"],
        "totalReturn": 10.0, "maxDrawdown": -5.71, "cagr": 3.2, "sharpe": 0.8, "volatility": 12.0,
        "winRate": 60.0, "trades": 5,
        "perAssetStats": {
            "005930": {"profit": 1_500_000, "trades": 3},
            "000660": {"profit": -400_000, "trades": 2},
            "035420": {"profit": -100_000, "trades": 0},  # 거래 0·손익 ≠ 0 → 대상
            "051910": {"profit": 0, "trades": 0},          # 거래 없음 → 제외
        },
        "tradingCosts": {"buyFeeRate": 0.00015, "sellFeeRate": 0.00015, "slippageRate": 0.0005,
                         "sellTaxRate": None, "sellTaxRateRange": [0.0015, 0.0023]},
        "version": "16.43.0",
    }
    base.update(over)
    return base


# ── 실행 가능 판정 ──────────────────────────────────────────────────────────

def test_complete_snapshot_is_executable():
    assert check_executable(SNAPSHOT) is None


@pytest.mark.parametrize("bad", [None, {}, {"name": "x", "description": "y"}, "text"])
def test_metadata_only_snapshot_is_not_executable(bad):
    assert check_executable(bad)["reason"] == "NO_EXECUTABLE_SNAPSHOT"


def test_missing_run_conditions_are_listed_not_filled():
    snap = copy.deepcopy(SNAPSHOT)
    del snap["risk"]["init_cash"]
    snap["options"] = {"fee_rate": 0.00015}
    res = check_executable(snap)
    assert res["reason"] == "MISSING_RUN_CONDITION"
    assert res["detail"] == ["risk.init_cash", "options.slippage_rate"]
    assert "init_cash" not in snap["risk"]  # 입력을 고치지 않는다


def test_unsupported_variants():
    snap = copy.deepcopy(SNAPSHOT)
    snap["risk"].update(contribution_amount=100000, contribution_period="monthly")
    assert check_executable(snap)["reason"] == "UNSUPPORTED_CONTRIBUTIONS"
    snap = copy.deepcopy(SNAPSHOT)
    snap["risk"]["withdrawal_amount"] = 100000
    snap["risk"]["withdrawal_period"] = "monthly"
    assert check_executable(snap)["reason"] == "UNSUPPORTED_CONTRIBUTIONS"
    snap = copy.deepcopy(SNAPSHOT)
    snap["risk"]["contribution_amount"] = 100000  # 주기 없는 반쪽 요청
    assert check_executable(snap)["reason"] == "INVALID_SNAPSHOT"
    snap = copy.deepcopy(SNAPSHOT)
    snap["universe_id"], snap["symbols"] = "sp500", []
    assert check_executable(snap)["reason"] == "UNSUPPORTED_REGION"
    snap = copy.deepcopy(SNAPSHOT)
    snap["symbols"] = ["AAPL"]
    assert check_executable(snap)["reason"] == "UNSUPPORTED_REGION"
    snap = copy.deepcopy(SNAPSHOT)
    snap["entry"]["conditions"].append({"type": "group", "id": "g", "conditions": [{"id": "ai_model"}]})
    assert check_executable(snap)["reason"] == "UNSUPPORTED_AI_SIGNAL"


# ── 요약 지표 ───────────────────────────────────────────────────────────────

def test_summary_uses_engine_values():
    s = summarize(engine_result())
    assert s["initialCapital"] == 10_000_000 and s["finalEquity"] == 11_000_000
    assert s["totalProfit"] == 1_000_000 and s["totalReturnPct"] == 10.0
    assert s["maxDrawdownPct"] == -5.71 and s["cagrPct"] == 3.2 and s["trades"] == 5
    assert s["unavailableReasons"] == {}


def test_summary_marks_undefined_values_with_reasons():
    short = engine_result(dates=["2026-01-02", "2026-03-02", "2026-06-01", "2026-10-27"])
    s = summarize(short)
    assert s["cagrPct"] is None and "cagrPct" in s["unavailableReasons"]
    flat = summarize(engine_result(volatility=0.0))
    assert flat["sharpe"] is None and "sharpe" in flat["unavailableReasons"]


def test_no_trades_is_distinct_from_failure():
    res = engine_result(equity=[10_000_000] * 4, totalReturn=0.0, maxDrawdown=0.0, trades=0, winRate=0.0,
                        perAssetStats={})
    pub = build_public_result(res, SNAPSHOT, WINDOW)
    assert pub["status"] == "no_trades"
    assert pub["summary"]["winRatePct"] is None and "winRatePct" in pub["summary"]["unavailableReasons"]
    assert pub["summary"]["totalReturnPct"] == 0.0
    assert pub["contributors"] == {"top": [], "bottom": []}


@pytest.mark.parametrize("over", [
    {"equity": []}, {"dates": ["2026-01-01"]}, {"initialCapital": 0}, {"initialCapital": None},
    {"totalReturn": 12.0},               # 평가자산과 어긋남
    {"maxDrawdown": float("nan")},
])
def test_inconsistent_or_empty_result_fails_instead_of_zero(over):
    with pytest.raises(SimulationResultError):
        summarize(engine_result(**over))


# ── 종목 기여 ───────────────────────────────────────────────────────────────

def test_contributors_top_bottom_without_duplicates():
    res = engine_result()
    out = contributors(res, 1_000_000, lambda s: {"005930": "삼성전자"}.get(s))
    assert out["top"] == [{"symbol": "005930", "name": "삼성전자", "profit": 1_500_000}]
    assert [r["symbol"] for r in out["bottom"]] == ["000660", "035420"]
    assert out["bottom"][0]["name"] == "000660"  # 이름 조회 실패 시 코드
    shown = [r["symbol"] for r in out["top"] + out["bottom"]]
    assert len(shown) == len(set(shown))


def test_contributors_limited_to_three_each_with_stable_ties():
    stats = {f"{i:06d}": {"profit": 100_000 * (1 if i < 5 else -1), "trades": 1} for i in range(10)}
    out = contributors({"perAssetStats": stats}, 0.0)
    assert len(out["top"]) == 3 and len(out["bottom"]) == 3
    assert [r["symbol"] for r in out["top"]] == ["000000", "000001", "000002"]
    assert not {r["symbol"] for r in out["top"]} & {r["symbol"] for r in out["bottom"]}


def test_contributors_hidden_when_sum_disagrees_with_total():
    out = contributors(engine_result(), 5_000_000)
    assert out == {"top": [], "bottom": [], "hidden": "INCONSISTENT"}
    bad = engine_result(perAssetStats={"005930": {"profit": float("nan"), "trades": 1}})
    assert contributors(bad, 0.0)["hidden"] == "INCONSISTENT"


# ── 곡선·공개 DTO ───────────────────────────────────────────────────────────

def test_downsample_keeps_first_and_last_points():
    curve = {"dates": [f"d{i}" for i in range(1000)], "returnPct": [float(i) for i in range(1000)]}
    small = downsample(curve, 120)
    assert len(small["dates"]) == 120 and len(small["returnPct"]) == 120
    assert small["dates"][0] == "d0" and small["dates"][-1] == "d999"
    assert downsample(curve, 5000) is curve


def test_public_result_shape_and_conditions_come_from_engine():
    pub = build_public_result(engine_result(), SNAPSHOT, WINDOW, computed_at=NOW)
    assert pub["status"] == "ready" and pub["computedAt"].startswith("2026-10-28T03:00")
    assert pub["curve"]["returnPct"] == [0.0, 5.0, -1.0, 10.0]
    assert pub["curve"]["dates"][-1] == "2026-10-27"
    assert pub["conditions"]["buyFeeRate"] == 0.00015 and pub["conditions"]["sellTaxRateRange"] == [0.0015, 0.0023]
    assert pub["conditions"]["savedPeriod"] == "5y" and pub["conditions"]["executionTiming"] == "next_open"
    assert pub["window"]["limited"] is False and pub["window"]["dataAsOf"] == "2026-10-27"
    # 소유자·원본 결과 필드가 새지 않는다.
    assert not {"signals", "perAssetStats", "symbols", "strategy_id", "userId"} & set(pub)


def test_public_result_limited_data_reports_actual_period():
    res = engine_result(dates=["2025-03-03", "2025-10-30", "2026-03-02", "2026-10-27"])
    pub = build_public_result(res, SNAPSHOT, WINDOW)
    assert pub["window"]["limited"] is True and pub["window"]["actualStart"] == "2025-03-03"


def test_missing_trading_costs_fails():
    with pytest.raises(SimulationResultError) as exc:
        build_public_result(engine_result(tradingCosts=None), SNAPSHOT, WINDOW)
    assert exc.value.code == "MISSING_TRADING_COSTS"
