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
            "timing": {
                "phase1": 11.95,
                "simulator": 0.26,
                "format": 0.39,
                "total": 12.6,
                "symbols": 976,
            },
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

    def test_grid_method_surfaces_backtest_error_when_all_combinations_fail(self):
        """전 조합의 백테스트가 실패하면 NoneType 크래시 대신 원인 메시지를 담은 에러를 반환한다."""

        class FailingEngine(DummyEngine):
            def run_backtest(self, req):
                # _get_backtest_dates(파라미터 오버라이드 없음)는 성공시켜 창 분할까지 진행시킨다
                if "startDate" not in req:
                    return super().run_backtest(req)
                raise TypeError("float() argument must be a string or a real number, not 'dict'")

        analyzer = WalkForwardAnalyzer(FailingEngine())

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=1,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            method="grid",
        )

        assert result["status"] == "error"
        assert "NoneType" not in result["message"]
        assert "float() argument" in result["message"]

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


class CountingEngine(DummyEngine):
    """run_backtest 호출 횟수를 세는 더미 엔진 (취소 반응성 검증용)."""

    def __init__(self, total_days=240):
        super().__init__(total_days)
        self.backtest_calls = 0

    def run_backtest(self, req):
        if "startDate" in req:  # 최초 전체 기간 조회는 제외하고 최적화 백테스트만 센다
            self.backtest_calls += 1
        return super().run_backtest(req)


class TestCooperativeCancel:
    """취소는 창 경계뿐 아니라 창 내부(시도/조합=백테스트 1회) 단위로도 반응해야 한다.

    회귀 배경(2026-07-07): should_cancel이 창 경계에서만 확인되어, 취소 후에도
    진행 중인 창의 IS 최적화(그리드 최대 500조합)가 통째로 계속 실행되던 버그.
    """

    def _run_cancelled_analysis(self, method: str, cancel_after: int, **kwargs):
        engine = CountingEngine()
        analyzer = WalkForwardAnalyzer(engine)

        # cancel_after회의 최적화 백테스트가 실행된 뒤 취소된 상황을 흉내낸다.
        result = analyzer.analyze(
            base_request=_base_request(),
            ranges={"entry.conditions.0.params.period": [10, 12, 14, 16, 18, 20]},
            n_splits=2,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            method=method,
            should_cancel=lambda: engine.backtest_calls >= cancel_after,
            **kwargs,
        )
        return result, engine

    def test_grid_cancel_stops_inside_window(self):
        result, engine = self._run_cancelled_analysis("grid", cancel_after=2)

        assert result["status"] == "cancelled"
        assert "취소" in result["message"]
        # 취소 시점(2회) 직후 조합 경계에서 멈춰야 한다 — 창 하나(6조합+OOS)를 다 돌면 회귀
        assert engine.backtest_calls == 2

    def test_bayesian_cancel_stops_inside_window(self):
        result, engine = self._run_cancelled_analysis("bayesian", cancel_after=2, n_trials=6)

        assert result["status"] == "cancelled"
        assert "취소" in result["message"]
        # optuna study.stop()은 진행 중 시도까지 마치고 멈춘다 — 창 전체(6시도+OOS)보다는 작아야 한다
        assert engine.backtest_calls <= 3

    def test_cancel_before_oos_skips_oos_backtest(self):
        # IS 최적화(6조합)가 끝난 직후 취소 → OOS 백테스트는 실행되지 않아야 한다
        result, engine = self._run_cancelled_analysis("grid", cancel_after=6)

        assert result["status"] == "cancelled"
        assert engine.backtest_calls == 6

    def test_no_cancel_runs_all_windows(self):
        engine = CountingEngine()
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            n_splits=2,
            train_pct=0.7,
            anchor=False,
            target_metric="cagr",
            method="grid",
            should_cancel=lambda: False,
        )

        assert result["status"] == "ok"
        assert len(result["windows"]) == 2


class SequentialDatesEngine(DummyEngine):
    """실제 달력처럼 단조 증가하는 날짜를 반환하는 더미 엔진."""

    def __init__(self, total_days=240):
        super().__init__(total_days)
        self.total_dates = [
            f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(total_days)
        ]


class PeriodAwareEngine(DummyEngine):
    """period='full'이면 긴 히스토리를, 그 외에는 짧은 백테스트 범위를 반환.

    프론트가 보여주는 result.dates(짧은 범위)와 워크포워드가 실제로 나누는
    날짜 범위가 어긋나던 버그(표시=실행 위반)를 재현하기 위한 엔진.
    """

    def __init__(self, backtest_days=240, full_days=3360):
        super().__init__(backtest_days)
        self.backtest_dates = [
            f"20{20 + (i // 336):02d}-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}"
            for i in range(backtest_days)
        ]
        self.full_dates = [
            f"20{10 + (i // 336):02d}-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}"
            for i in range(full_days)
        ]
        self.requested_periods = []

    def run_backtest(self, req):
        result = super().run_backtest(req)
        period = str(req.get("period", "")).lower()
        self.requested_periods.append(period)
        result["dates"] = self.full_dates if period == "full" else self.backtest_dates
        result["equity"] = [1_000_000 * (1 + 0.001 * i) for i in range(len(result["dates"]))]
        return result


class TestBacktestRangeMatchesDisplay:
    """워크포워드는 백테스트가 표시한 기간에서 구간을 나눠야 한다 (표시=실행)."""

    def test_uses_backtest_range_not_forced_full_history(self):
        # 백테스트는 240일(짧은 범위), 전체 히스토리는 3360일(14배).
        engine = PeriodAwareEngine(backtest_days=240, full_days=3360)
        analyzer = WalkForwardAnalyzer(engine)

        # is=84, oos=28 → 표시 기준(240일): (240-84)/28 = 5개 구간 → 실행 가능.
        # 예전엔 period='full'로 강제 확장돼 3360일에서 구간 수가 폭증, 상한 초과로 실패했다.
        result = analyzer.analyze(
            base_request={**_base_request(), "period": "1Y"},
            ranges=_ranges(),
            method="grid",
            is_bars=84,
            oos_bars=28,
        )

        assert result["status"] == "ok"
        assert len(result["windows"]) == 5
        # 날짜 그리드를 얻는 최초 호출은 period를 'full'로 덮어쓰지 않고
        # 백테스트 요청의 기간('1y')을 그대로 사용해야 한다.
        # (이후 창별 IS/OOS 호출은 startDate/endDate로 구간을 지정하므로 별개다.)
        assert engine.requested_periods[0] == "1y"

    def test_first_window_dates_come_from_backtest_range(self):
        engine = PeriodAwareEngine(backtest_days=240, full_days=3360)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request={**_base_request(), "period": "1Y"},
            ranges=_ranges(),
            method="grid",
            is_bars=84,
            oos_bars=28,
        )

        assert result["status"] == "ok"
        # 첫 IS 시작이 전체 히스토리(2010~)가 아니라 백테스트 범위(2020~)에서 나와야 한다.
        assert result["windows"][0]["is_period"].startswith(engine.backtest_dates[0])


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

    def test_anchored_drops_truncated_last_window_like_rolling(self):
        """회귀(2026-08-19): 확장 모드가 검증 길이를 못 채우는 마지막 조각 창을 하나 더 만들어
        롤링·UI 예상 구간 수(floor((T-is)/oos))보다 1개 많았다(1000/500/150 → 롤링 3, 확장 4, UI 3)."""
        analyzer = WalkForwardAnalyzer(SequentialDatesEngine(1000))
        dates = analyzer.engine.total_dates
        index = {d: i for i, d in enumerate(dates)}

        rolling = analyzer._split_windows(dates, 5, 0.7, anchor=False, is_bars=500, oos_bars=150)
        anchored = analyzer._split_windows(dates, 5, 0.7, anchor=True, is_bars=500, oos_bars=150)

        assert len(rolling) == len(anchored) == (1000 - 500) // 150 == 3
        for _, _, oos_s, oos_e in anchored:
            assert index[oos_e] - index[oos_s] + 1 == 150  # 모든 검증 창이 정확히 oos_bars 길이

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
        result["cagr"] = -5.0
        return result


class StationaryEngine(SequentialDatesEngine):
    """매일 같은 수익률(연 12%)을 내는 완전 정상성 전략 — IS/OOS 창 길이가 달라도 CAGR은 동일.

    창 길이에 비례해 총수익률(totalReturn)은 IS가 OOS보다 훨씬 크므로, WFE를 총수익률로
    나누면 정상성 전략조차 '과최적화'로 찍힌다(2026-08-19 감사 재현용).
    """

    ANNUAL_RATE = 0.12

    def run_backtest(self, req):
        result = super().run_backtest(req)
        start, end = req.get("startDate"), req.get("endDate")
        dates = [
            d for d in self.total_dates
            if (start is None or d >= start) and (end is None or d <= end)
        ]
        n = len(dates)
        daily = (1 + self.ANNUAL_RATE) ** (1 / 252) - 1
        total_return = ((1 + daily) ** n - 1) * 100
        years = n / 252
        result["totalReturn"] = total_return
        result["cagr"] = ((1 + total_return / 100) ** (1 / years) - 1) * 100 if years > 0 else 0.0
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

    def test_wfe_uses_annualized_cagr_not_length_biased_total_return(self):
        """정상성 전략(IS CAGR == OOS CAGR)의 WFE는 창 길이 비율과 무관하게 ≈1.0이어야 한다."""
        engine = StationaryEngine(1000)
        analyzer = WalkForwardAnalyzer(engine)

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=500,
            oos_bars=150,
        )

        assert result["status"] == "ok"
        assert result["wfe_valid"] is True
        assert result["wfe_basis"] == "cagr"
        # 총수익률 기준이었다면 150/500 창 비율 탓에 ≈0.28로 나왔다.
        assert abs(result["walk_forward_efficiency"] - 1.0) < 0.01

    def test_wfe_pairs_is_and_oos_per_window(self):
        """OOS가 실패한 창의 IS 수익은 WFE 분모에서도 함께 빠져야 한다 (분자·분모 창 집합 일치)."""

        engine = SequentialDatesEngine(240)
        # 창 1: IS=[0,100) OOS=[100,150) / 창 2: IS=[50,150) OOS=[150,200)
        first_oos_start = engine.total_dates[100]
        first_is_start = engine.total_dates[0]

        class OosFailsFirstWindowEngine(SequentialDatesEngine):
            def run_backtest(self, req):
                start = req.get("startDate")
                if start == first_oos_start:
                    raise RuntimeError("OOS boom")  # 창 1의 OOS만 실패
                result = super().run_backtest(req)
                # 창 1 IS는 CAGR 40, 나머지(창 2 IS·OOS)는 20 — 짝이 어긋나면 값이 달라진다
                result["cagr"] = 40.0 if start == first_is_start else 20.0
                return result

        analyzer = WalkForwardAnalyzer(OosFailsFirstWindowEngine(240))
        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=100,
            oos_bars=50,
        )

        assert result["status"] == "ok"
        assert result["windows"][0].get("error")
        # 창 2만으로 계산(20/20) → 정확히 1.0. 창 1 IS(40)가 분모에 섞였다면 20/30≈0.67.
        assert result["walk_forward_efficiency"] == 1.0


class TestProgressAndCancel:
    def test_progress_callback_receives_window_events(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        events = []

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=120,
            oos_bars=40,
            progress_callback=events.append,
        )

        assert result["status"] == "ok"
        # 창 시작 이벤트는 창당 한 번 (trial 키가 없는 window 이벤트).
        window_start_events = [
            e for e in events if e.get("stage") == "window" and "trial" not in e
        ]
        assert len(window_start_events) == len(result["windows"])
        assert window_start_events[0]["window"] == 1
        assert window_start_events[0]["total"] == len(result["windows"])
        assert "~" in window_start_events[0]["oos_period"]

        # 창 내부 진행률 이벤트는 창 정보 + trial/trial_total을 함께 싣는다.
        trial_events = [e for e in events if e.get("stage") == "window" and "trial" in e]
        assert trial_events, "창 내부 시도(trial) 진행률 이벤트가 없습니다"
        assert trial_events[0]["trial_total"] >= 1
        assert trial_events[0]["window"] == 1
        # 백테스트 단계별 소요 시간(timing)이 진행 이벤트에 실려야 한다.
        assert trial_events[0]["timing"]["total"] == 12.6
        assert trial_events[0]["timing"]["symbols"] == 976

    def test_should_cancel_stops_at_window_boundary(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        seen = []

        def cancel_after_first():
            # 첫 창 완료 후 취소 (첫 호출 False, 이후 True)
            seen.append(True)
            return len(seen) > 1

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=120,
            oos_bars=40,
            should_cancel=cancel_after_first,
        )

        assert result["status"] == "cancelled"
        assert "취소" in result["message"]

    def test_progress_callback_errors_do_not_break_analysis(self):
        engine = SequentialDatesEngine(240)
        analyzer = WalkForwardAnalyzer(engine)

        def broken_callback(_payload):
            raise RuntimeError("boom")

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            is_bars=120,
            oos_bars=40,
            progress_callback=broken_callback,
        )

        assert result["status"] == "ok"


class TestProfitFactorTarget:
    def test_grid_profit_factor_target_survives_no_loss_combination(self):
        """회귀(2026-08-19): 무손실 조합의 profitFactor=None(∞)이 정렬 TypeError를 일으켜 창 전체가
        'IS 최적화 오류'로 실패했다. ∞는 최상값으로 취급돼 그 조합이 선택되어야 한다."""

        class NoLossEngine(SequentialDatesEngine):
            def run_backtest(self, req):
                result = super().run_backtest(req)
                period = req["entry"]["conditions"][0]["params"]["period"]
                result["profitFactor"] = None if period == 20 else 1.2
                return result

        analyzer = WalkForwardAnalyzer(NoLossEngine(240))
        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="grid",
            target_metric="profitFactor",
            is_bars=100,
            oos_bars=50,
        )

        assert result["status"] == "ok"
        for window in result["windows"]:
            assert window.get("error") is None
            assert window["best_params"]["entry.conditions.0.params.period"] == 20


class TestBayesianBacktestBudget:
    def test_bayesian_window_runs_only_trials_plus_oos(self):
        """회귀(2026-08-19): OptunaOptimizer가 창마다 70/30 홀드아웃(_holdout_validate)을 무조건 실행해
        결과도 안 쓰는 백테스트를 창당 2회씩 낭비했다(ETA 산식 n_trials+1과도 불일치).
        워크포워드에서는 창당 정확히 n_trials(IS) + 1(OOS)만 실행되어야 한다."""
        engine = CountingEngine(240)
        analyzer = WalkForwardAnalyzer(engine)
        n_trials = 3

        result = analyzer.analyze(
            base_request=_base_request(),
            ranges=_ranges(),
            method="bayesian",
            n_trials=n_trials,
            is_bars=100,
            oos_bars=50,
        )

        assert result["status"] == "ok"
        n_windows = len(result["windows"])
        assert n_windows == 2
        assert engine.backtest_calls == n_windows * (n_trials + 1)
