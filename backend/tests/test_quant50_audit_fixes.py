"""퀀트 전략 50개 감사(2026-11-09)에서 드러난 조립·검증 결함 회귀 — LLM 출력은 트레이스 형태 고정."""

from __future__ import annotations

import json
import threading

import pytest

from engine import strategy_slots
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.strategy_converter import compute_strategy_id, to_backtest_request
from strategy_conversation.compiler.strategy_compiler import compile_strategy
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter import quote_check
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.primary import (
    _fill_deterministic_condition_params,
    _resolve_filler_conditions,
    _substituted_factor,
)
from strategy_conversation.registry import indicator_registry
from strategy_conversation.validation.pipeline import run_validation


def validate_intent(intent: StrategyIntent):
    normalized, report = run_validation(intent)
    intent.strategy = normalized.strategy
    return report


def _intent(**strategy) -> StrategyIntent:
    base = {
        "universe": {"markets": ["KOSPI200"]},
        "portfolio": {"selection_count": 5},
        "backtest": {"period": "5y"},
        "declined": [{"field": "stop_loss", "source_text": "안 함"}, {"field": "take_profit", "source_text": "안 함"}],
    }
    base.update(strategy)
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": base})


def _cond(factor, op=None, value=None, source="조건", **kw):
    return {"factor": factor, "operator": op, "value": value, "source_text": source,
            "value_source": "USER_PROVIDED" if value is not None else "MISSING", **kw}


def _filler_chat(*kinds):
    """덧붙은 조건 판정의 두 호출에 같은 답을 주는 스텁 — 두 번째 호출은 첫 답의 덧붙은 항목만 받는다."""
    def chat(_system, user, **_kw):
        asked = user.count('   인용: "')
        answers = [k for k in kinds if k in quote_check.FILLER_KINDS] if asked < len(kinds) else list(kinds)
        return json.dumps({"items": [{"kind": k} for k in answers[:asked]]})
    return chat


def _signal(request, role="entry"):
    return request[role]["conditions"][0]["params"]


def test_stochastic_threshold_runs_as_level_with_period():
    intent = _intent(
        entry_conditions=[_cond("technical.stochastic", "<", 20.0, parameters={"period": 14})],
        exit_conditions=[_cond("technical.stochastic", ">", 80.0, parameters={"period": 14})],
    )
    report = validate_intent(intent)
    assert report.errors == []
    request = to_backtest_request(compile_strategy(intent, report, ""), resolve_symbols=False)
    params = _signal(request)
    assert (params["mode"], params["operator"], params["value"], params["period"]) == ("level", "<", 20.0, 14)


def test_twelve_month_lookback_is_accepted():
    intent = _intent(entry_conditions=[_cond("technical.roc", ">", 0.0, parameters={"period": 252})],
                     exit_conditions=[_cond("technical.roc", "<", 0.0, parameters={"period": 252})])
    assert validate_intent(intent).errors == []


def test_obv_exit_cross_allowed_and_wrong_role_rejected():
    ok = _intent(entry_conditions=[_cond("technical.volume_spike", "crosses_above", parameters={"period": 20})],
                 exit_conditions=[_cond("technical.volume_spike", "crosses_below", parameters={"period": 20})])
    assert validate_intent(ok).errors == []
    bad = _intent(entry_conditions=[_cond("technical.volume_spike", "crosses_below", parameters={"period": 20})],
                  exit_conditions=[_cond("technical.rsi", ">", 70.0)])
    assert any("교차 방향" in e for e in validate_intent(bad).errors)


def test_obv_lookback_key_is_normalized_to_period():
    intent = _intent(entry_conditions=[_cond("technical.volume_spike", "crosses_above", parameters={"lookback_period": 20})],
                     exit_conditions=[_cond("technical.volume_spike", "crosses_below", parameters={"lookback_period": 20})])
    assert validate_intent(intent).errors == []
    assert intent.strategy.entry_conditions[0].parameters == {"period": 20}


def test_touching_open_bounds_are_a_conflict():
    intent = _intent(entry_conditions=[_cond("technical.rsi", ">", 30.0), _cond("technical.rsi", "<=", 30.0)],
                     exit_conditions=[_cond("technical.rsi", ">", 70.0)])
    assert any("모순" in e for e in validate_intent(intent).errors)
    closed = _intent(entry_conditions=[_cond("technical.rsi", ">=", 30.0), _cond("technical.rsi", "<=", 30.0)],
                     exit_conditions=[_cond("technical.rsi", ">", 70.0)])
    assert not any("모순" in e for e in validate_intent(closed).errors)


def test_cash_branch_complement_is_not_an_entry_condition():
    intent = _intent(
        universe={"markets": ["ETF"], "symbols": ["KODEX 200", "KODEX 단기채권"]},
        entry_conditions=[_cond("technical.roc", ">", 0.0, parameters={"period": 252}),
                          _cond("technical.ai_drop_model", source="그렇지 않으면 전액 KODEX 단기채권으로 옮기는")],
        portfolio={"rebalance_frequency": "monthly", "cash_asset": "KODEX 단기채권",
                   "absolute_momentum_threshold_percent": 0.0},
    )
    _resolve_filler_conditions(intent, "12개월 수익률이 0 초과면 KODEX 200, 그렇지 않으면 전액 KODEX 단기채권으로 옮기는",
                               _filler_chat("condition", "cash_switch"))
    report = validate_intent(intent)
    assert not any("모순" in e for e in report.errors)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.roc"]


def test_real_condition_quoting_cash_asset_is_kept():
    intent = _intent(
        entry_conditions=[_cond("technical.rsi", "<=", 70.0, source="RSI 70 이하이면 KODEX 200, 아니면 KODEX 단기채권")],
        portfolio={"rebalance_frequency": "monthly", "cash_asset": "KODEX 단기채권"},
    )
    _resolve_filler_conditions(intent, "RSI 70 이하이면 KODEX 200, 아니면 KODEX 단기채권", _filler_chat("condition"))
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.rsi"]


@pytest.mark.parametrize("chat", [
    lambda *_a, **_k: "깨진 응답",
    None,
])
def test_filler_verdict_failure_keeps_the_condition(chat):
    intent = _intent(
        entry_conditions=[_cond("technical.rsi", "<=", None, source="RSI가 낮을 때만")],
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    _resolve_filler_conditions(intent, "RSI가 낮을 때만 매달 100만 원씩", chat)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.rsi"]


def test_filler_needs_two_matching_verdicts():
    answers = iter(["plan", "condition"])
    intent = _intent(
        entry_conditions=[_cond("fundamental.trading_value", ">=", None, source="매달 100만 원씩")],
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    _resolve_filler_conditions(intent, "매달 100만 원씩", lambda *_a, **_k: json.dumps({"items": [{"kind": next(answers)}]}))
    assert [c.factor for c in intent.strategy.entry_conditions] == ["fundamental.trading_value"]


def test_real_condition_beside_plan_is_kept_and_reported_as_mixed():
    intent = _intent(
        universe={"markets": ["ETF"], "symbols": ["TIGER 미국S&P500"]},
        entry_conditions=[_cond("technical.rsi", "<=", None, source="RSI가 낮을 때만")],
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    _resolve_filler_conditions(intent, "RSI가 낮을 때만 매달 100만 원씩", _filler_chat("condition"))
    validate_intent(intent)
    assert [c.factor for c in intent.strategy.entry_conditions] == ["technical.rsi"]
    assert intent.strategy.backtest.contribution_amount is None


def test_cash_branch_without_asset_name_in_quote_is_still_asked():
    intent = _intent(
        entry_conditions=[_cond("technical.roc", ">", 0.0, source="12개월 수익률이 0보다 크면", parameters={"period": 252}),
                          _cond("technical.roc", "<=", 0.0, source="그렇지 않으면", parameters={"period": 252})],
        portfolio={"rebalance_frequency": "monthly", "cash_asset": "KODEX 단기채권"},
    )
    _resolve_filler_conditions(intent, "12개월 수익률이 0보다 크면 보유, 그렇지 않으면 KODEX 단기채권", _filler_chat("condition", "cash_switch"))
    assert [c.source_text for c in intent.strategy.entry_conditions] == ["12개월 수익률이 0보다 크면"]


def test_vwap_condition_reported_unsupported_becomes_approximation():
    intent = _intent(entry_conditions=[_cond("technical.vwap", "crosses_above", source="장중 VWAP 위로 올라오면 매수",
                                             parameters={"period": 20})])
    intent.unsupported_features = ["장중 VWAP"]
    _fill_deterministic_condition_params(intent)
    assert intent.strategy.entry_conditions[0].approximated is True


def test_intraday_quote_keeps_vwap_as_user_decided_approximation():
    cond = _intent(entry_conditions=[_cond("technical.vwap", "crosses_above", source="장중 VWAP 돌파",
                                           parameters={"period": 20})]).strategy.entry_conditions[0]
    verdicts = quote_check.QuoteVerdicts([(cond, quote_check.Verdict("yes", "intraday"))])
    assert not quote_check.quote_describes_intraday(verdicts, cond)


def test_limit_order_survives_invented_close_execution():
    intent = _intent(
        entry_conditions=[_cond("technical.ma_crossover", "crosses_above", parameters={"short_period": 5, "long_period": 20})],
        exit_conditions=[_cond("technical.ma_crossover", "crosses_below", parameters={"short_period": 5, "long_period": 20})],
        backtest={"period": "5y", "execution_timing": "current_close", "entry_limit_percent": 2.0},
    )
    report = validate_intent(intent)
    assert intent.strategy.backtest.entry_limit_percent == 2.0
    assert intent.strategy.backtest.execution_timing is None
    assert any("다음 날" in w for w in report.warnings)


def test_contribution_plan_survives_self_reported_approximation():
    intent = _intent(
        universe={"markets": ["ETF"], "symbols": ["TIGER 미국S&P500"]},
        entry_conditions=[_cond("fundamental.trading_value", ">=", 100.0, source="매달 100만 원씩", approximated=True)],
        portfolio={"selection_count": None, "rebalance_frequency": "monthly"},
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    _resolve_filler_conditions(intent, "TIGER 미국S&P500을 매달 100만 원씩 적립", _filler_chat("plan"))
    validate_intent(intent)
    assert intent.strategy.backtest.contribution_amount == 1000000
    assert intent.strategy.entry_conditions == []


def test_contribution_plan_survives_valueless_filler_conditions():
    intent = _intent(
        universe={"markets": ["ETF"], "symbols": ["TIGER 미국S&P500"]},
        entry_conditions=[_cond("technical.buy_at_start", source="사서 계속 보유"),
                          _cond("fundamental.trading_value", ">=", None, source="TIGER 미국S&P500")],
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    # 시작일 매수는 후보가 아니라(제한이 없다) 값 없는 거래대금 한 건만 묻는다.
    _resolve_filler_conditions(intent, "TIGER 미국S&P500을 사서 계속 보유, 매달 100만 원씩", _filler_chat("plan"))
    validate_intent(intent)
    assert intent.strategy.backtest.contribution_amount == 1000000
    assert intent.strategy.entry_conditions == []


def test_contribution_plan_with_user_threshold_stays_mixed():
    intent = _intent(
        universe={"markets": ["ETF"], "symbols": ["TIGER 미국S&P500"]},
        entry_conditions=[_cond("technical.rsi", "<=", 30.0, source="RSI 30 이하일 때만")],
        backtest={"period": "5y", "contribution_amount": 1000000, "contribution_period": "monthly"},
    )
    validate_intent(intent)
    assert intent.strategy.backtest.contribution_amount is None


def test_valueless_condition_overlapping_longer_report_is_dropped():
    intent = _intent(entry_conditions=[
        _cond("fundamental.ebit", ">=", None, source="최근 3개월 영업이익 컨센서스가 10% 이상 상향된"),
        _cond("technical.breakout", "crosses_above", None, source="장 시작 후 첫 30분 고가 돌파 시 매수")])
    intent.unsupported_features = ["영업이익 컨센서스 상향(실적 추정치)", "5분봉 매매, 장 시작 후 첫 30분 고가 기준"]
    _resolve_filler_conditions(intent, "문장", _filler_chat("unsupported", "unsupported"))
    assert intent.strategy.entry_conditions == []


def test_volatility_breakout_reaches_engine_without_entry_conditions():
    intent = _intent(backtest={"period": "5y", "volatility_breakout_k": 0.5})
    report = validate_intent(intent)
    assert "strategy.entry_conditions" not in report.missing_fields
    assert compile_strategy(intent, report, "").volatility_breakout_k == 0.5


def test_volatility_breakout_out_of_range_is_excluded_before_compile():
    intent = _intent(backtest={"period": "5y", "volatility_breakout_k": 3})
    assert any("변동성 돌파" in e for e in validate_intent(intent).errors)
    assert intent.strategy.backtest.volatility_breakout_k is None


def test_average_price_notice_stays_inside_the_next_avg_branch():
    """갭 고지 삽입으로 평균가 고지가 next_open 분기로 밀려 시가 체결 전략 전부에 붙던 사고."""
    import ast
    from pathlib import Path

    import backtest_engine

    source = Path(backtest_engine.__file__).read_text(encoding="utf-8")
    branches = {ast.get_source_segment(source, n.test): ast.get_source_segment(source, n)
                for n in ast.walk(ast.parse(source)) if isinstance(n, ast.If)}
    assert "rw.EXEC_AVG_PRICE" in branches["exec_type in ('next_avg', 'next_average')"]
    assert "rw.EXEC_AVG_PRICE" not in branches["exec_type == 'next_open'"]


def test_volatility_breakout_counts_as_the_entry_slot():
    assert strategy_slots._has_value(ParsedStrategy(description="x", universe=["KOSPI200"],
                                                    volatility_breakout_k=0.5), strategy_slots.ENTRY)
    assert not strategy_slots._has_value(ParsedStrategy(description="x", universe=["KOSPI200"]),
                                         strategy_slots.ENTRY)


def test_obv_cross_keeps_exit_through_decompile_round_trip():
    intent = _intent(
        entry_conditions=[_cond("technical.volume_spike", "crosses_above", None, parameters={"period": 20})],
        exit_conditions=[_cond("technical.volume_spike", "crosses_below", None, parameters={"period": 20})],
    )
    parsed = compile_strategy(intent, validate_intent(intent), "")
    spec = decompile_strategy(parsed)
    assert [c.operator for c in spec.entry_conditions] == ["crosses_above"]
    assert [c.operator for c in spec.exit_conditions] == ["crosses_below"]
    round_trip = StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "strategy": spec.model_dump()})
    assert "strategy.exit_conditions" not in validate_intent(round_trip).missing_fields
    assert [c.factor for c in round_trip.strategy.exit_conditions] == ["technical.volume_spike"]


def test_obv_downward_cross_in_entry_is_rejected_by_validation():
    intent = _intent(entry_conditions=[_cond("technical.volume_spike", "crosses_below", None,
                                             parameters={"period": 20})])
    assert any("교차 방향" in e for e in validate_intent(intent).errors)


@pytest.mark.parametrize("field,first,second", [("days", 5, 3), ("within_days", 5, 10)])
def test_strategy_id_tells_apart_day_count_parameters(field, first, second):
    indicator = "ma_rising" if field == "days" else "bollinger_squeeze"
    def strategy_id(value):
        signal = TechnicalSignal(indicator=indicator, signal_type="buy", period=20, **{field: value})
        return compute_strategy_id(ParsedStrategy(description="x", universe=["KOSPI200"], entry_signals=[signal]))
    assert strategy_id(first) != strategy_id(second)


@pytest.mark.parametrize("factor,source", [
    ("technical.ma_rising", "20일 이동평균선이 5거래일 연속 상승"),
    ("technical.ma_falling", "이평선 기울기가 하락하면"),
    ("technical.bollinger_squeeze", "볼린저 밴드폭이 최근 120일 중 가장 좁아지면"),
    ("technical.bollinger_bandwidth", "볼린저 밴드폭이 10% 이하"),
])
def test_exact_new_indicator_is_not_called_a_substitution(factor, source):
    cond = _intent(entry_conditions=[_cond(factor, source=source)]).strategy.entry_conditions[0]
    assert not _substituted_factor(cond, indicator_registry.resolve(factor), indicator_registry)


def test_condition_quoting_its_own_unsupported_subject_is_dropped():
    intent = _intent(
        entry_conditions=[_cond("fundamental.roe_or_gpa", ">=", 10.0, source="ROE가 10% 이상"),
                          _cond("fundamental.debt_ratio", "<=", None, source="이자보상배율이 3배 이상")],
    )
    intent.unsupported_features = ["이자보상배율"]
    _resolve_filler_conditions(intent, "ROE가 10% 이상, 이자보상배율이 3배 이상", _filler_chat("unsupported"))
    assert [c.factor for c in intent.strategy.entry_conditions] == ["fundamental.roe_or_gpa"]


def test_double_entry_and_own_name_report_keep_condition():
    intent = _intent(
        entry_conditions=[_cond("fundamental.operating_margin", ">=", None, source="영업이익률 높은")],
        exit_conditions=[_cond("technical.ma_crossover", "crosses_below", None, source="20일선이 60일선을 하향 돌파",
                               parameters={"short_period": 20, "long_period": 60})])
    intent.unsupported_features = ["영업이익률", "20일선이 60일선을 하향 돌파하면 청산"]
    _fill_deterministic_condition_params(intent)
    assert len(intent.strategy.entry_conditions) == 1 and len(intent.strategy.exit_conditions) == 1


def test_compound_quote_with_unsupported_tail_keeps_condition():
    intent = _intent(entry_conditions=[
        _cond("technical.ma_crossover", "crosses_above", None, source="5일선이 20일선을 돌파하고 외국인 순매수",
              parameters={"short_period": 5, "long_period": 20})])
    intent.unsupported_features = ["외국인 순매수"]
    _fill_deterministic_condition_params(intent)
    assert len(intent.strategy.entry_conditions) == 1


def test_exact_yoy_growth_quote_is_not_called_a_substitution():
    cond = _intent(entry_conditions=[_cond("fundamental.operating_income_growth_yoy", ">=", 30.0,
                                           source="분기 영업이익이 전년 동기 대비 30% 이상 늘고")]).strategy.entry_conditions[0]
    spec = indicator_registry.resolve(cond.factor)
    assert not _substituted_factor(cond, spec, indicator_registry)


def test_obv_moving_average_quote_is_not_called_a_substitution():
    cond = _intent(entry_conditions=[_cond("technical.volume_spike", "crosses_above", None,
                                           source="OBV가 OBV의 20일 이동평균 위로 올라오면 매수",
                                           parameters={"period": 20})]).strategy.entry_conditions[0]
    spec = indicator_registry.resolve(cond.factor)
    assert not _substituted_factor(cond, spec, indicator_registry)


def test_unresolved_taa_asset_is_reported(monkeypatch):
    monkeypatch.setattr("strategy_conversation.registry.universe_resolver.resolve_symbols",
                        lambda refs: ([], list(refs)) if refs == ["없는 ETF"] else (["000001"], []))
    intent = _intent(universe={"markets": ["ETF"]},
                     taa={"model": "vaa", "offensive": ["KODEX 200"], "defensive": ["없는 ETF"], "source_text": "VAA"})
    assert "없는 ETF" in validate_intent(intent).unsupported_features


def test_backtest_warnings_do_not_cross_threads():
    from backtest_engine import BacktestEngine

    engine = BacktestEngine.__new__(BacktestEngine)
    engine.warnings = {"main"}
    seen = {}

    def other():
        engine.warnings = {"other"}
        seen["other"] = set(engine.warnings)

    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    assert seen["other"] == {"other"}
    assert engine.warnings == {"main"}


def _hold_trades(hold_days, execution_type):
    import pandas as pd

    from engine.simulator import Simulator

    index = pd.date_range("2024-01-02", periods=8, freq="B")
    close = pd.DataFrame({"AAA": [100.0] * 8}, index=index)
    entries = pd.DataFrame({"AAA": [False] * 8}, index=index)
    exits = entries.copy()
    entries.iloc[1, 0] = True
    risk = {"init_cash": 10000.0, "max_holding_days": hold_days}
    opts = dict(execution_type=execution_type, fee_rate=0.0, sell_tax_rate=0.0, slippage_rate=0.0)
    trades = Simulator().run(close, close, entries, exits, risk, opts,
                             high_df=close, low_df=close).trades.records_readable
    return trades, index


@pytest.mark.parametrize("hold_days", [1, 2, 5])
def test_next_open_holding_is_exactly_n_trading_days(hold_days):
    trades, index = _hold_trades(hold_days, "next_open")
    assert trades.iloc[0]["Entry Timestamp"] == index[1]
    assert trades.iloc[0]["Exit Timestamp"] == index[1 + hold_days]


def test_same_close_holding_keeps_n_trading_days():
    trades, index = _hold_trades(3, "same_close")
    assert trades.iloc[0]["Exit Timestamp"] == index[4]


@pytest.mark.parametrize("period,expected", [
    ("5Y", "2021-11-09"), ("10Y", "2016-11-09"), ("3Y", "2023-11-09"), ("6M", "2026-05-09")])
def test_period_window_is_exact_offset_from_reference_date(period, expected):
    import pandas as pd

    from backtest_engine import _period_start_for

    assert _period_start_for(period, pd.Timestamp("2026-11-09")) == pd.Timestamp(expected)


def test_seasonal_buy_at_start_flags_first_bar_of_invested_months():
    from engine.phase1 import _window_start_flags

    dates = ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-03-01", "2024-03-04", "2024-04-01"]
    next_open = _window_start_flags(len(dates), 1, dates=dates, seasonal_months=[2, 4], delay=1)
    assert next_open.tolist() == [0, 1, 0, 0, 0, 1, 0]
    same_close = _window_start_flags(len(dates), 1, dates=dates, seasonal_months=[2, 4], delay=0)
    assert same_close.tolist() == [0, 1, 1, 0, 0, 0, 1]
    assert _window_start_flags(len(dates), 1).tolist() == [0, 1, 0, 0, 0, 0, 0]


def test_ranking_lookback_floor_is_five_days():
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums

    parsed = ParsedStrategy(description="x", ranking_metric="return", ranking_lookback_days=5)
    enforce_strategy_minimums(parsed)
    assert parsed.ranking_lookback_days == 5
    short = ParsedStrategy(description="x", ranking_metric="return", ranking_lookback_days=3)
    notices = enforce_strategy_minimums(short)
    assert short.ranking_lookback_days == 5 and any("최소 5일" in n for n in notices)


def test_intraday_quote_is_excluded_with_notice():
    from strategy_conversation.interpreter import quote_check
    from strategy_conversation.primary import _drop_fabricated_conditions

    quote = "장 시작 후 첫 30분 고가를 돌파하면 매수"
    intent = _intent(entry_conditions=[_cond("technical.breakout", "crosses_above", None, source=quote,
                                             parameters={"lookback_period": 30})])
    cond = intent.strategy.entry_conditions[0]
    verdicts = quote_check.QuoteVerdicts([(cond, quote_check.Verdict(expresses="yes", describes="intraday"))])
    notices = _drop_fabricated_conditions(intent, f"KOSPI200에서 {quote}", verdicts)
    assert intent.strategy.entry_conditions == []
    assert any("장중" in n for n in notices)


@pytest.mark.parametrize("old,new", [
    ("KOSEF 국고채10년", "KIWOOM 국고채10년"), ("KBSTAR 200", "RISE 200"),
    ("TIGER 200", "TIGER 200"), ("KOSEF", "KOSEF")])
def test_old_etf_brand_maps_to_current_brand(old, new):
    from strategy_conversation.registry.universe_resolver import _current_etf_brand

    assert _current_etf_brand(old) == new
