"""FX regime regression: preserve crossing events, AND entry and OR liquidation."""

import numpy as np
import pandas as pd
import pytest

from engine.strategy_converter import to_backtest_request
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from test_macro_filters_v16_31 import _compile, _intent, _write_series


SOURCE = (
    "원/달러 환율이 60일 이동평균선을 상향 돌파하고 최근 20일 환율 수익률이 양수일 때를 "
    "원화 약세 국면으로 판단하고, 이 조건이 충족될 때만 코스피 종목 중 최근 6개월 수익률이 "
    "높은 상위 10개 종목에 동일 비중으로 투자한다. 포트폴리오는 매월 리밸런싱하며, "
    "원/달러 환율이 다시 60일 이동평균선 아래로 내려가거나 20일 환율 수익률이 음수로 "
    "전환되면 신규 매수를 중단하고 보유 종목을 정리한다."
)
FILTERS = [
    dict(series="usdkrw", role="entry", mode="ma", operator="crosses_above", period=60,
         source_text="원/달러 환율이 60일 이동평균선을 상향 돌파하고"),
    dict(series="usdkrw", role="entry", mode="change", operator=">", period=20, value=0,
         source_text="최근 20일 환율 수익률이 양수일 때"),
    dict(series="usdkrw", role="exit", mode="ma", operator="<", period=60,
         source_text="원/달러 환율이 다시 60일 이동평균선 아래로 내려가거나"),
    dict(series="usdkrw", role="exit", mode="change", operator="crosses_below", period=20, value=0,
         source_text="20일 환율 수익률이 음수로 전환되면"),
]


def test_source_conditions_survive_validation_compile_and_modify_roundtrip():
    intent = _intent(macro_filters=FILTERS, universe={"markets": ["KOSPI"]},
                     ranking=[{"metric": "ranking.return", "lookback_days": 126}])
    _, report, parsed, dropped, pending = _compile(intent)
    assert not report.unsupported_features and not report.errors and not dropped
    assert not any("macro" in q.field for q in report.clarification_questions)
    request = to_backtest_request(parsed, resolve_symbols=False)
    assert parsed.universe == ["KOSPI"]
    assert request["risk"]["allocation_type"] == "equal"
    assert request["risk"]["max_positions"] == 10
    assert request["risk"]["ranking_lookback_days"] == 126
    expected = [{k: v for k, v in f.items() if k != "source_text"} for f in FILTERS]
    assert request["risk"]["macro_filters"] == expected
    restored = decompile_strategy(parsed)
    from strategy_conversation.conversation.patch_applier import apply_patches
    from strategy_conversation.interpreter.models import PatchOp
    intent.strategy = apply_patches(restored, [PatchOp(
        op="replace", path="/portfolio/selection_count", value=12, source_text="보유 종목 수를 12개로")])
    _, _, modified, _, _ = _compile(intent)
    assert to_backtest_request(modified, resolve_symbols=False)["risk"]["macro_filters"] == expected
    assert modified.max_positions == 12
    assert modified.rebalancing_period == "monthly"
    assert restored.ranking[0].lookback_days == 126


def _engine(tmp_path, monkeypatch, values):
    from backtest_engine import BacktestEngine
    eng = BacktestEngine()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    monkeypatch.setattr(eng.loader, "data_dir", str(ohlcv))
    days = pd.bdate_range("2024-01-01", periods=len(values))
    _write_series(tmp_path, "usdkrw", pd.Series(values, index=days))
    return eng, days


def test_regime_persists_then_exits_on_negative_return_until_new_cross(tmp_path, monkeypatch):
    values = [100.] * 60 + [110.] * 20 + [109., 111., 90., 115., 95.]
    eng, days = _engine(tmp_path, monkeypatch, values)
    exposure, reasons, _ = eng._macro_exposure(FILTERS, days, 0, 0)
    np.testing.assert_array_equal(exposure[:60], 0)
    np.testing.assert_array_equal(exposure[60:80], 1)
    np.testing.assert_array_equal(exposure[80:], [0, 0, 0, 1, 0])
    assert reasons[80] and reasons[60] is None
    delayed, _, _ = eng._macro_exposure(FILTERS, days, 0, 1)
    np.testing.assert_array_equal(delayed, np.r_[0, exposure[:-1]])
    # A later query window preserves a regime entered before that window.
    window, _, _ = eng._macro_exposure(FILTERS, days[65:], 0, 0)
    np.testing.assert_array_equal(window, exposure[65:])
    # Future observations cannot affect an earlier result.
    prefix, _, _ = eng._macro_exposure(FILTERS, days[:75], 0, 0)
    np.testing.assert_array_equal(prefix, exposure[:75])


def test_ma_exit_alone_closes_regime_with_positive_return(tmp_path, monkeypatch):
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 60 + [200., 101.])
    exposure, _, _ = eng._macro_exposure(FILTERS, days, 0, 0)
    np.testing.assert_array_equal(exposure[-2:], [1, 0])


def test_entry_requires_both_conditions_on_cross_day(tmp_path, monkeypatch):
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 40 + [150.] + [90.] * 19 + [120., 121.])
    exposure, _, _ = eng._macro_exposure(FILTERS, days, 0, 0)
    # Cross at day 60 has negative 20-day return; day 61 is positive but has no cross.
    np.testing.assert_array_equal(exposure, 0)


def test_exit_wins_on_simultaneous_entry(tmp_path, monkeypatch):
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 60 + [110.])
    filters = FILTERS + [dict(series="usdkrw", role="exit", mode="level", operator=">", value=105)]
    exposure, _, _ = eng._macro_exposure(filters, days, 0, 0)
    np.testing.assert_array_equal(exposure, 0)


def test_sparse_level_predicate_and_legacy_reduction_compose(tmp_path, monkeypatch):
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 60 + [110.] * 25)
    # A level published on Sunday is available on subsequent business days.
    _write_series(tmp_path, "vix", pd.Series([20.], index=pd.to_datetime(["2023-12-31"])))
    filters = FILTERS + [dict(series="vix", role="entry", mode="level", operator="<", value=30),
                         dict(series="vix", mode="level", operator=">", value=15, exposure_pct=50)]
    exposure, _, _ = eng._macro_exposure(filters, days, 0, 0)
    np.testing.assert_array_equal(exposure[:60], 0)
    np.testing.assert_array_equal(exposure[60:], .5)


def test_missing_regime_series_keeps_cash(tmp_path, monkeypatch):
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 60 + [110.])
    filters = FILTERS + [dict(series="vix", role="entry", mode="level", operator="<", value=30)]
    exposure, _, _ = eng._macro_exposure(filters, days, 0, 0)
    np.testing.assert_array_equal(exposure, 0)
    assert eng.warnings


def test_unknown_or_incomplete_predicate_does_not_relax_entry_group():
    for extra in (dict(series="코코아 선물", role="entry", mode="level", operator="<", value=30),
                  dict(series="vix", role="entry", mode="level", operator="<")):
        _, _, parsed, dropped, pending = _compile(_intent(macro_filters=FILTERS + [extra]))
        assert dropped and pending
        assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["macro_filters"] is None


def test_recall_does_not_recreate_fx_ma_as_a_stock_condition():
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions
    intent = _intent(macro_filters=FILTERS)
    recovered = recover_missing_conditions(intent, SOURCE, lambda *a, **kw: "{}",
                                            phrases=[f["source_text"] for f in FILTERS])
    assert recovered == []
    assert intent.strategy.entry_conditions == []
    assert intent.strategy.exit_conditions == []


def test_primary_parse_preserves_macro_regime_without_false_unsupported_notice(monkeypatch):
    from test_strategy_conversation import _run_primary_with
    intent = _intent(macro_filters=FILTERS, universe={"markets": ["KOSPI"]},
                     ranking=[{"metric": "ranking.return", "lookback_days": 126}])
    intent.unsupported_features = [FILTERS[0]["source_text"], FILTERS[3]["source_text"]]
    result = _run_primary_with(monkeypatch, intent.model_dump(), SOURCE)
    assert result is not None
    assert len(to_backtest_request(result["parsed"], resolve_symbols=False)["risk"]["macro_filters"]) == 4
    assert not any("반영하지 못" in str(notice) for notice in result.get("notices", []))


@pytest.mark.parametrize("signal_driven", [False, True])
def test_monthly_portfolio_liquidates_immediately_and_blocks_new_buys(tmp_path, monkeypatch, signal_driven):
    from engine.simulator import Simulator
    from test_seasonal_and_vol_target import _frames, _risk, _OPTS
    values = [100.] * 60 + [110.] * 20 + [109., 111., 90., 115., 95.]
    eng, days = _engine(tmp_path, monkeypatch, values)
    exposure, reasons, _ = eng._macro_exposure(FILTERS, days, 0, 0)
    _, prices, entries, exits, rank = _frames([100.] * len(days), start="2024-01-01")
    sim = Simulator()
    pf = sim.run(prices, prices, entries, exits, _risk(entry_signal_driven=signal_driven),
                 _OPTS, rank_df=rank, exposure=exposure, exposure_reasons=reasons)
    invested = 1 - pf.cash().to_numpy() / pf.value().to_numpy()
    np.testing.assert_allclose(invested[80:83], 0, atol=1e-9)
    assert invested[79] > .99 and invested[83] > .99
    assert invested[84] == pytest.approx(0)
    assert reasons[80] in {r for dates in sim.exit_reason_overrides.values() for r in dates.values()}


@pytest.mark.parametrize("missing_role", ["entry", "exit"])
def test_incomplete_regime_asks_for_counterpart_and_is_not_executed(missing_role):
    _, report, parsed, _, _ = _compile(_intent(
        macro_filters=[f for f in FILTERS if f["role"] != missing_role]))
    assert any("macro_filters" in q.field for q in report.clarification_questions)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["macro_filters"] is None


def test_regime_reasons_name_fx_without_heading_or_date_and_triggered_exit(tmp_path, monkeypatch):
    from engine import trade_reason as tr
    eng, days = _engine(tmp_path, monkeypatch, [100.] * 60 + [110.] * 20 + [109.])
    _, reasons, _ = eng._macro_exposure(FILTERS, days, 0, 1)
    entries = eng.macro_entry_context
    text = tr.text(entries[days[62].strftime("%Y-%m-%d")])
    assert "원/달러 환율" in text
    assert "상향 돌파" in text
    assert "매크로 진입 허용" not in text
    assert "판정일" not in text
    assert days[60].strftime("%Y-%m-%d") not in text
    assert days[62].strftime("%Y-%m-%d") not in text
    assert "20일 변화율" in text
    _, reasons, _ = eng._macro_exposure(FILTERS, days, 0, 0)
    assert "원/달러 환율" in tr.text(reasons[80])
    assert "20일 변화율" in tr.text(reasons[80])
    assert "하향 돌파" in tr.text(reasons[80])
    assert "60일" not in tr.text(reasons[80])
    eng._macro_exposure([], days, 0, 0)
    assert eng.macro_entry_context == {}


def test_macro_buy_context_uses_execution_date_and_preserves_override():
    from engine.result_handler import ResultHandler
    from engine import trade_reason as tr
    from test_result_handler import _Portfolio
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    context = tr.encode([tr.part("원/달러 환율")])
    result = ResultHandler.format_results(
        _Portfolio(), ["005930"], None, None, {}, {}, idx, {}, "next_open", 10_000_000,
        entry_reason_overrides={"005930": {"2024-01-03": "종목 교체 편입"}},
        entry_context={"2024-01-03": context})
    buys = [row for row in result["signals"] if row["type"] == "buy"]
    assert "원/달러 환율" not in buys[0]["condition"]
    assert "원/달러 환율" in buys[1]["condition"]
    assert "종목 교체 편입" in buys[1]["condition"]
    assert "판정일" not in buys[1]["condition"]
