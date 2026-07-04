from engine.walk_forward import WalkForwardAnalyzer


class DummyEngine:
    """
    period 값에 비례하는 더미 백테스트 결과를 반환.
    dates가 없는(period="full", startDate/endDate 없음) 최초 호출은
    전체 기간 조회(_get_full_dates)로 취급해 고정된 날짜 리스트를 반환한다.
    """

    def __init__(self, total_days=240):
        self.total_dates = [f"2024-01-{(i % 28) + 1:02d}" for i in range(total_days)]

    def run_backtest(self, req):
        period = 14
        try:
            period = req["entry"]["conditions"][0]["params"]["period"]
        except (KeyError, IndexError, TypeError):
            pass

        return {
            "cagr": float(period) * 1.5,
            "totalReturn": float(period),
            "maxDrawdown": 100.0 - float(period),
            "sharpe": 1.0,
            "winRate": 0.5,
            "profitFactor": 1.2,
            "trades": 10,
            "dates": self.total_dates,
            "equity": [1_000_000 * (1 + 0.001 * i) for i in range(len(self.total_dates))],
        }


def _base_request():
    return {
        "symbols": ["005930"],
        "entry": {
            "conditions": [
                {"id": "rsi_cross", "params": {"period": 14, "threshold": 30}}
            ]
        },
    }


def _ranges():
    return {"entry.conditions.0.params.period": [10, 14, 20]}


class TestWalkForwardGridMethod:
    def test_grid_method_runs_and_picks_best_params_per_window(self):
        engine = DummyEngine()
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=2,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            method="grid",
        )

        assert result["status"] == "ok"
        assert len(result["windows"]) == 2
        for window in result["windows"]:
            assert window.get("error") is None
            # DummyEngine: cagr = period * 1.5 → period=20이 항상 최적
            assert window["best_params"]["entry.conditions.0.params.period"] == 20
            assert window["is_metrics"]["cagr"] == 30.0

    def test_grid_method_window_error_when_combinations_exceed_cap(self):
        engine = DummyEngine()
        analyzer = WalkForwardAnalyzer(engine)

        huge_ranges = {
            "a": {"type": "number", "min": 0, "max": 29, "step": 1},
            "b": {"type": "number", "min": 0, "max": 29, "step": 1},
        }

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=huge_ranges,
            n_splits=1,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            method="grid",
        )

        assert result["status"] == "ok"
        assert len(result["windows"]) == 1
        assert "상한" in result["windows"][0]["error"]

    def test_default_method_is_bayesian(self):
        """method 인자를 생략하면 기존 베이지안 경로가 그대로 동작한다."""
        engine = DummyEngine()
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=1,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            n_trials=6,
        )

        assert result["status"] == "ok"
        assert len(result["windows"]) == 1
        assert result["windows"][0].get("error") is None
