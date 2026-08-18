"""리밸런싱 기간별 결과 비교 분석(FR-BT-064) — 결정론 부분과 LLM 출력 형식 검증."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))

from ai.rebalance_comparison import (  # noqa: E402
    REBALANCE_PERIODS,
    analyze_rebalance_comparison,
    build_evidence,
    build_request_for_period,
    compute_turnover,
    extract_period_metrics,
    normalize_period,
    parse_rebalance_analysis,
    rebalance_applies,
    run_rebalance_backtests,
)


class _FakeEngine:
    """주기별로 다른 CAGR을 돌려주는 가짜 엔진 — 요청의 rebalancing_period를 기록한다."""

    CAGR = {"daily": 8.0, "weekly": 12.0, "monthly": 15.0, "quarterly": 14.0, "semiannual": 13.5, "yearly": 11.0}

    def __init__(self, fail_periods=()):
        self.seen = []
        self.fail_periods = set(fail_periods)

    def run_backtest(self, req):
        period = req["risk"]["rebalancing_period"]
        self.seen.append(period)
        if period in self.fail_periods:
            raise RuntimeError(f"boom-{period}")
        cagr = self.CAGR[period]
        return {
            "cagr": cagr,
            "maxDrawdown": -20.0 + REBALANCE_PERIODS.index(period),
            "sharpe": cagr / 10,
            "profitFactor": None if period == "yearly" else 1.5,
            "trades": 600 // (REBALANCE_PERIODS.index(period) + 1),
            "totalReturn": cagr * 3,
            "winRate": 50.0,
            "calmar": None,
            "equity": [100.0, 110.0, 120.0],
            "dates": ["2020-01-02", "2020-06-30", "2024-12-30"],
            "signals": [{"amount": 30.0}, {"amount": 30.0}],
        }


def _base_request(**risk_overrides):
    risk = {"position_size_pct": 10, "max_positions": 10, "rebalancing_period": "none"}
    risk.update(risk_overrides)
    return {"symbols": ["005930"], "entry": {"conditions": []}, "exit": {"conditions": []}, "risk": risk}


def _llm_json(recommended="monthly", **overrides):
    data = {
        "summary": {
            "recommended_rebalance_period": recommended,
            "confidence_score": 72,
            "strategy_character": "장기 팩터 성격",
            "stability_rating": "B",
        },
        "comparison_table": [{"period": p, "evaluation": f"{p} 평가"} for p in REBALANCE_PERIODS],
        "analysis": {
            "performance_analysis": "성과",
            "risk_analysis": "리스크",
            "transaction_cost_analysis": "비용",
            "overfitting_analysis": "과최적화",
        },
        "recommendation": {"recommended_period": recommended, "reason": "이유", "warning": "주의"},
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


# ── 결정론 ────────────────────────────────────────────────────────────────────

def test_normalize_period_accepts_aliases():
    assert normalize_period("semi-annual") == "semiannual"
    assert normalize_period("Annual") == "yearly"
    assert normalize_period("매월") == "monthly"
    assert normalize_period("fortnightly") is None


def test_build_request_overrides_only_rebalancing_period():
    base = _base_request(stop_loss_pct=5)
    req = build_request_for_period(base, "quarterly")
    assert req["risk"]["rebalancing_period"] == "quarterly"
    assert req["risk"]["stop_loss_pct"] == 5
    assert base["risk"]["rebalancing_period"] == "none"  # 원본 불변


def test_compute_turnover_matches_frontend_formula():
    # (총 체결금액 60 / 2) / 평균 자산 110 × 100
    assert compute_turnover([{"amount": 30}, {"price": 10, "quantity": 3}], [100, 110, 120]) == pytest.approx(60 / 2 / 110 * 100)
    assert compute_turnover([], []) == 0.0


def test_extract_period_metrics_keeps_none_profit_factor_and_fills_calmar():
    row = extract_period_metrics("yearly", _FakeEngine().run_backtest(build_request_for_period(_base_request(), "yearly")))
    assert row["profit_factor"] is None  # 손실 0건(∞)은 0이 아니라 None 그대로
    assert row["calmar"] == pytest.approx(11.0 / 15.0, abs=1e-4)  # cagr / |mdd| (mdd = -20+5), 소수 4자리 반올림
    assert row["turnover"] == pytest.approx(60 / 2 / 110 * 100, abs=1e-4)


def test_rebalance_applies_requires_position_cap():
    assert rebalance_applies(_base_request())
    assert rebalance_applies(_base_request(max_positions=None, max_positions_pct=20))
    assert not rebalance_applies(_base_request(max_positions=None))
    assert not rebalance_applies(_base_request(skip_position_setting=True))


def test_run_rebalance_backtests_runs_all_periods_and_isolates_failures():
    engine = _FakeEngine(fail_periods={"weekly"})
    seen_progress = []
    run = run_rebalance_backtests(engine, _base_request(), progress_callback=seen_progress.append)
    assert engine.seen == list(REBALANCE_PERIODS)
    rows = {r["period"]: r for r in run["rebalance_results"]}
    assert rows["weekly"]["error"] == "boom-weekly"
    assert rows["monthly"]["cagr"] == 15.0
    assert run["backtest_period"] == {"start": "2020-01-02", "end": "2024-12-30"}
    assert [p["index"] for p in seen_progress] == [1, 2, 3, 4, 5, 6]


def test_run_rebalance_backtests_cancels_between_periods():
    engine = _FakeEngine()
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 2  # 두 주기 실행 후 취소

    run = run_rebalance_backtests(engine, _base_request(), should_cancel=should_cancel)
    assert run["status"] == "cancelled"
    assert engine.seen == ["daily", "weekly"]


def test_build_evidence_ranks_and_adjacent_diffs():
    engine = _FakeEngine()
    run = run_rebalance_backtests(engine, _base_request())
    ev = build_evidence(run["rebalance_results"], run["backtest_period"])
    assert ev["best_by"]["cagr"] == "monthly"
    assert ev["best_by"]["sharpe_ratio"] == "monthly"
    assert ev["best_by"]["mdd"] == "yearly"  # 낙폭이 가장 작은 주기(-15)
    assert ev["cagr_spread"] == pytest.approx(7.0)
    assert ev["backtest_years"] == pytest.approx(4.99, abs=0.02)
    assert ev["short_backtest"] is False
    assert [a["from"] for a in ev["adjacent"]] == ["daily", "weekly", "monthly", "quarterly", "semiannual"]
    assert ev["adjacent"][1]["cagr_diff"] == pytest.approx(3.0)
    assert ev["trade_count_ratio_shortest_to_longest"] == pytest.approx(6.0)


# ── LLM 출력 형식 검증(정규화만) ───────────────────────────────────────────────

def test_parse_rebalance_analysis_normalizes_aliases_and_ratings():
    raw = "```json\n" + _llm_json(recommended="Semi-Annual", summary={
        "recommended_rebalance_period": "Semi-Annual", "confidence_score": 0.65,
        "strategy_character": " x ", "stability_rating": "b등급",
    }) + "\n```"
    parsed = parse_rebalance_analysis(raw, list(REBALANCE_PERIODS))
    assert parsed["summary"]["recommended_rebalance_period"] == "semiannual"
    assert parsed["summary"]["confidence_score"] == 65
    assert parsed["summary"]["stability_rating"] == "B"
    assert parsed["evaluations"]["monthly"] == "monthly 평가"
    assert parsed["recommendation"]["recommended_period"] == "semiannual"


def test_parse_rebalance_analysis_rejects_period_outside_executed_set():
    # 실행 안 된(실패한) 주기를 추천하면 형식 위반 — 임의 보정하지 않고 None.
    assert parse_rebalance_analysis(_llm_json(recommended="weekly"), ["daily", "monthly"]) is None
    assert parse_rebalance_analysis("<think>...</think> 그냥 텍스트", list(REBALANCE_PERIODS)) is None


# ── 진입점 ────────────────────────────────────────────────────────────────────

def test_analyze_runs_all_periods_even_without_position_cap_and_notices():
    # 2026-08-18 사용자 지시: 리밸런싱 설정·보유 상한이 없어도 막지 말고 6주기를 그대로 계산해 보여준다.
    engine = _FakeEngine()
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        return _llm_json()

    out = analyze_rebalance_comparison(engine, _base_request(max_positions=None), llm=llm)
    assert out["status"] == "ok"
    assert engine.seen == list(REBALANCE_PERIODS)
    assert out["notices"] and "보유 종목 수" in out["notices"][0]
    # LLM에도 사실을 전달해 동일 6행을 '안정'으로 오독하지 않게 한다.
    assert '"position_cap_absent": true' in prompts[0]


def test_analyze_has_no_notice_with_position_cap():
    out = analyze_rebalance_comparison(_FakeEngine(), _base_request(), llm=lambda p: _llm_json())
    assert out["notices"] == []


def test_analyze_happy_path_includes_rows_evidence_and_analysis():
    engine = _FakeEngine()
    prompts = []

    def llm(prompt):
        prompts.append(prompt)
        return _llm_json()

    out = analyze_rebalance_comparison(
        engine, _base_request(rebalancing_period="bimonthly"),
        strategy_name="테스트 전략", investment_universe="KOSPI200",
        current={"cagr": 9.0, "mdd": -18.0}, llm=llm,
    )
    assert out["status"] == "ok"
    assert out["current_period"] == "bimonthly"
    assert len(out["rebalance_results"]) == 6
    assert out["analysis"]["summary"]["recommended_rebalance_period"] == "monthly"
    assert out["analysis_degraded"] is False
    # 프롬프트에 입력 데이터·결정론 근거·현재 설정이 실린다.
    assert '"strategy_name": "테스트 전략"' in prompts[0]
    assert '"current_setting"' in prompts[0] and '"bimonthly"' in prompts[0]
    assert '"adjacent"' in prompts[0]


def test_analyze_degrades_when_llm_output_is_invalid_but_keeps_table():
    engine = _FakeEngine()
    attempts = {"n": 0}

    def llm(prompt):
        attempts["n"] += 1
        return "형식이 아닌 텍스트"

    out = analyze_rebalance_comparison(engine, _base_request(), llm=llm)
    assert out["status"] == "ok"
    assert out["analysis"] is None
    assert out["analysis_degraded"] is True
    assert attempts["n"] == 2  # 1회 재시도
    assert len([r for r in out["rebalance_results"] if not r.get("error")]) == 6


def test_analyze_reports_error_when_all_periods_fail():
    engine = _FakeEngine(fail_periods=set(REBALANCE_PERIODS))
    out = analyze_rebalance_comparison(engine, _base_request(), llm=lambda p: _llm_json())
    assert out["status"] == "error"
    assert "boom-daily" in out["message"]
