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

    def test_grid_method_fails_fast_when_combinations_exceed_cap(self):
        """모든 윈도우가 같은 이유(조합 상한 초과)로 실패하면 부분 결과 대신 에러를 반환한다."""
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

        assert result["status"] == "error"
        assert "상한" in result["message"]

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


class SequentialDatesEngine(DummyEngine):
    """실제 달력처럼 단조 증가하는 날짜를 반환하는 더미 엔진."""

    def __init__(self, total_days=240):
        super().__init__(total_days)
        self.total_dates = [
            f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(total_days)
        ]


class TestExplicitBarsSplit:
    def test_rolling_windows_use_exact_bar_counts(self):
        """is_bars/oos_bars 지정 시 UI에 표시된 거래일 수 그대로 창을 만든다."""
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        dates = engine.total_dates

        windows = analyzer._split_windows(
            dates, n_splits=5, train_pct=0.7, anchor=False, is_bars=84, oos_bars=28
        )

        # (240 - 84) / 28 = 5.57 → 완전한 OOS 창 5개
        assert len(windows) == 5
        for k, (is_s, is_e, oos_s, oos_e) in enumerate(windows):
            assert is_s == dates[k * 28]
            assert is_e == dates[k * 28 + 83]
            assert oos_s == dates[k * 28 + 84]
            assert oos_e == dates[k * 28 + 111]

    def test_no_lookahead_oos_always_after_is(self):
        """모든 창에서 OOS 시작이 IS 종료보다 뒤여야 한다 (look-ahead 방지)."""
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        dates = engine.total_dates
        index = {d: i for i, d in enumerate(dates)}

        for anchor in (False, True):
            windows = analyzer._split_windows(
                dates, n_splits=4, train_pct=0.7, anchor=anchor, is_bars=100, oos_bars=30
            )
            assert windows
            for is_s, is_e, oos_s, oos_e in windows:
                assert index[is_s] <= index[is_e] < index[oos_s] <= index[oos_e]

    def test_anchored_windows_expand_from_start(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        dates = engine.total_dates

        windows = analyzer._split_windows(
            dates, n_splits=3, train_pct=0.5, anchor=True, is_bars=120, oos_bars=40
        )

        assert len(windows) == 3
        for is_s, _, _, _ in windows:
            assert is_s == dates[0]
        # IS 종료가 매 창마다 oos_bars만큼 확장
        assert [w[1] for w in windows] == [dates[119], dates[159], dates[199]]

    def test_bars_too_large_returns_no_windows(self):
        engine = SequentialDatesEngine(100)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=90,
            oos_bars=20,
        )

        assert result["status"] == "error"
        assert "윈도우 분할" in result["message"]

    def test_too_many_windows_rejected(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=10,
            oos_bars=5,
        )

        assert result["status"] == "error"
        assert "상한" in result["message"]


class NaNMetricsEngine(SequentialDatesEngine):
    """sharpe가 NaN인 결과를 돌려주는 엔진 — 집계 오염 방지 검증용."""

    def run_backtest(self, req):
        result = super().run_backtest(req)
        result["sharpe"] = float("nan")
        result["profitFactor"] = float("inf")
        return result


class TestAggregateGuards:
    def test_aggregate_skips_non_finite_metrics(self):
        engine = NaNMetricsEngine(240)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=2,
            method="grid",
        )

        assert result["status"] == "ok"
        # NaN sharpe / inf profitFactor는 표본에서 제외되어 0.0으로 집계
        assert result["aggregate"]["avg_oos_sharpe"] == 0.0
        assert result["aggregate"]["avg_oos_profitFactor"] == 0.0
        # 정상 지표는 그대로 집계된다
        assert result["aggregate"]["avg_oos_cagr"] == 30.0

    def test_aggregate_includes_calmar_and_expectancy_keys(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=2,
            method="grid",
        )

        assert result["status"] == "ok"
        assert "avg_oos_calmar" in result["aggregate"]
        assert "avg_oos_expectancy" in result["aggregate"]


class NegativeReturnEngine(SequentialDatesEngine):
    def run_backtest(self, req):
        result = super().run_backtest(req)
        result["totalReturn"] = -5.0
        return result


class TestWfeValidity:
    def test_wfe_invalid_when_is_returns_non_positive(self):
        engine = NegativeReturnEngine(240)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=2,
            method="grid",
        )

        assert result["status"] == "ok"
        assert result["wfe_valid"] is False
        assert result["walk_forward_efficiency"] == 0.0
