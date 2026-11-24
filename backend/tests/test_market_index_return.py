"""시장 지수 등락률 조건(엔진 v16.52) 회귀 테스트.

배경: "코스피가 하루에 5% 이상 빠진 다음 날 매수"를 표현할 칸이 없어, 해석기가 조건을 '알 수 없는 지표'로
버리거나 시장 대비 초과수익률(period=1, 최소 2 위반)로 바꿔 넣다 검증에서 떨어졌다(2026-11-24 실측).
2026-11-24 사용자 결정: 지수는 사용자가 말한 지수(말하지 않았으면 코스피/코스닥 되묻기), 기간·값은 말하지
않으면 되묻기(기간 칩 1·5·20거래일, 하락 폭 칩 -3·-5·-7%), 매수·매도 조건 모두.

이 파일은 ① 지수 달력 위 등락률 계산·조인 ② 벡터/행별 평가 일치 ③ 변환기·매매 사유·전략 ID ④ 컴파일·디컴파일
왕복 ⑤ 지수·기간·값 되묻기와 칩 결속 ⑥ 표기 정규화·미국 시장 거절 ⑦ 인터프리터 어휘 노출을 고정한다.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import polars as pl
import pytest

from engine import market_index, strategy_slots, trade_reason
from engine.nl_parser import ParsedStrategy, TechnicalSignal
from engine.signals import SignalEngine
from engine.strategy_converter import _tech_signal_to_condition, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import _decompile_technical
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.response.output_guard import guard_text
from strategy_conversation.validation.pipeline import run_validation

FACTOR = "technical.market_index_return"
COL = market_index.market_index_return_column("KOSPI", 1)


@pytest.fixture
def data_dir(tmp_path):
    """data/ohlcv의 형제 data/index에 가짜 코스피 지수(5거래일)를 둔다."""
    (tmp_path / "index").mkdir()
    (tmp_path / "ohlcv").mkdir()
    pl.DataFrame({
        "date": [datetime(2024, 1, d) for d in (2, 3, 4, 5, 8)],
        "open": [100.0] * 5, "high": [100.0] * 5, "low": [100.0] * 5,
        "close": [100.0, 94.0, 94.0, 99.0, 93.06],
        "volume": [1.0] * 5, "source": ["test"] * 5,
    }).write_parquet(tmp_path / "index" / "KOSPI.parquet")
    market_index._load_cached.cache_clear()
    return str(tmp_path / "ohlcv")


def _stock(dates):
    return pl.DataFrame({"date": [datetime(2024, 1, d) for d in dates], "close": [1.0] * len(dates)})


def _cond(**params):
    return {"type": "indicator", "id": "market_index_return",
            "params": {"index": "KOSPI", "period": 1, "operator": "<=", "value": -5, **params}}


def test_return_is_computed_on_the_index_calendar_and_not_forward_filled(data_dir):
    # 종목은 1/4(지수 -0%)에 거래정지 — 종목 프레임 위에서 계산하면 1/5의 '하루 등락률'이 1/3→1/5 두 날치가 된다.
    out = market_index.attach_market_index_returns(_stock([2, 3, 5, 8, 9]), [_cond()], data_dir)
    values = out[COL].to_list()
    assert values[0] is None                                   # 첫날은 전날이 없다
    assert values[1] == pytest.approx(-6.0)                   # 100 → 94
    assert values[2] == pytest.approx(99 / 94 * 100 - 100)    # 1/4(94) → 1/5(99), 지수 달력 기준
    assert values[3] == pytest.approx(-6.0)                   # 99 → 93.06
    assert values[4] is None                                   # 지수 값이 없는 날(실시간 봉 등)은 채우지 않는다


def test_column_survives_the_indicator_engine(data_dir):
    """지표 엔진은 열 이름을 소문자로 바꾼다 — 열 이름에 'KOSPI'를 그대로 쓰면 신호 평가가 열을 못 찾아
    실데이터 백테스트가 거래 0건이 됐다(2026-11-24 구현 중 실측, 단위 테스트는 엔진을 거치지 않아 못 잡았다)."""
    from engine.data_resolver import DataResolver
    from engine.indicators import IndicatorEngine

    stock = _stock([2, 3, 5]).with_columns(
        pl.lit(1.0).alias("open"), pl.lit(1.0).alias("high"), pl.lit(1.0).alias("low"), pl.lit(1.0).alias("volume"))
    cond = _cond(signalType="buy")
    frame = IndicatorEngine.calculate(market_index.attach_market_index_returns(stock, [cond], data_dir), [cond])
    assert frame[COL].to_list()[1] == pytest.approx(-6.0)
    _, logs = DataResolver().resolve("005930", frame, {"conditions": [cond], "logic": "AND"}, None)
    assert not any("미해결" in str(line) for line in logs)


def test_unknown_index_or_missing_file_gives_null_column(data_dir):
    out = market_index.attach_market_index_returns(_stock([2, 3]), [_cond(index="KOSDAQ")], data_dir)
    assert out[market_index.market_index_return_column("KOSDAQ", 1)].to_list() == [None, None]
    untouched = _stock([2, 3])
    assert market_index.attach_market_index_returns(untouched, [{"id": "rsi", "params": {}}], data_dir) is untouched


def test_vector_and_row_evaluators_agree():
    df = pl.DataFrame({COL: [None, -6.0, 1.2, -5.0, -4.99]}, schema={COL: pl.Float64})
    engine = SignalEngine()
    cond = _cond(signalType="buy")
    vec = engine._eval_vec(cond, df).tolist()
    assert vec == [False, True, False, True, False]
    assert [engine.evaluate_condition(cond, i, df) for i in range(len(df))] == vec
    # 연산자·값이 없으면 기본값으로 대체하지 않고 신호가 없다.
    bare = {"type": "indicator", "id": "market_index_return", "params": {"index": "KOSPI", "period": 1}}
    assert engine._eval_vec(bare, df).tolist() == [False] * 5


def test_converter_trade_reason_and_strategy_id():
    sig = TechnicalSignal(indicator="market_index_return", signal_type="buy", index="KOSPI",
                          period=1, operator="<=", value=-5)
    cond = _tech_signal_to_condition(sig)
    assert cond["params"] == {"signalType": "buy", "index": "KOSPI", "period": 1, "operator": "<=", "value": -5.0}
    engine = SignalEngine()
    assert trade_reason.render_kr(engine._base_condition_segments(cond)) == "코스피 1거래일 등락률 -5.0% 이하"
    assert trade_reason.render_kr(engine.get_condition_segments(cond, measured=-6.123)) == "코스피 1거래일 등락률 -6.12%"

    def dsl(index):
        return to_canonical_strategy_dsl(ParsedStrategy(
            universe=["KOSPI"], entry_signals=[sig.model_copy(update={"index": index})]))

    assert dsl("KOSPI") != dsl("KOSDAQ")


def _intent(role="entry", operator="<=", value=-5, **params):
    other = "exit" if role == "entry" else "entry"
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {
            "universe": {"markets": ["KOSPI200"], "sectors": []},
            f"{role}_conditions": [{
                "factor": FACTOR, "operator": operator, "value": value,
                "parameters": params, "source_text": "코스피가 하루에 5% 이상 빠지면"}],
            f"{other}_conditions": [{
                "factor": "technical.rsi", "operator": "<=" if other == "entry" else ">=",
                "value": 30 if other == "entry" else 70,
                "parameters": {"period": 14}, "source_text": "RSI"}],
        },
    })


@pytest.mark.parametrize("role, operator, value", [("entry", "<=", -5), ("exit", ">=", 3)])
def test_compile_and_decompile_round_trip(role, operator, value):
    validated, report = run_validation(_intent(role, operator, value, index="코스피", period=1))
    assert not report.missing_fields, report.missing_fields
    parsed, _, pending = compile_partial(validated, report, None)
    assert not pending
    signals = parsed.entry_signals if role == "entry" else parsed.exit_signals
    sig = next(s for s in signals if s.indicator == "market_index_return")
    assert (sig.index, sig.period, sig.operator, sig.value) == ("KOSPI", 1, operator, value)  # '코스피' 표기 정규화
    back = _decompile_technical(sig)
    assert (back.factor, back.operator, back.value) == (FACTOR, operator, value)
    assert back.parameters == {"index": "KOSPI", "period": 1.0}


@pytest.mark.parametrize("params, value, field, chips", [
    ({"period": 1}, -4, "parameters.index",
     ["코스피 1거래일 등락률이 -4% 이하일 때 매수", "코스닥 1거래일 등락률이 -4% 이하일 때 매수"]),
    ({"index": "KOSDAQ"}, -5, "parameters.period",
     [f"코스닥 {n}거래일 등락률이 -5% 이하일 때 매수" for n in (1, 5, 20)]),
    ({"index": "KOSPI", "period": 1}, None, "value",
     [f"코스피 1거래일 등락률이 {v}% 이하일 때 매수" for v in (-3, -5, -7)]),
])
def test_missing_piece_is_asked_with_whole_condition_chips_and_held_back(params, value, field, chips):
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_intent(value=value, **params))
    full_field = f"strategy.entry_conditions[0].{field}"
    assert report.missing_fields == [full_field]
    question = next(q for q in report.clarification_questions if q.field == full_field)
    assert question.recommended_value is None                  # 기본값을 정하지 않는다(사용자 결정)
    assert guard_text(question.question) == question.question
    parsed, _, pending = compile_partial(validated, report, None)
    assert not any(s.indicator == "market_index_return" for s in parsed.entry_signals)  # 값 확정 전 엔진에 보내지 않음
    assert pending
    item = next(i for i in _clarification_items(report, validated) if i["chips"])
    assert item["chips"] == chips


def test_no_chips_when_another_piece_is_also_missing():
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_intent(value=None))   # 지수·기간·값 모두 없음
    assert len(report.missing_fields) == 3
    assert all(not item["chips"] for item in _clarification_items(report, validated))


def test_rise_threshold_question_has_no_drop_chips():
    from strategy_conversation.primary import _clarification_items

    validated, report = run_validation(_intent(operator=">=", value=None, index="KOSPI", period=1))
    assert all(not item["chips"] for item in _clarification_items(report, validated))


def test_chip_binding_appends_signal_once_and_round_trips_the_template():
    base = ParsedStrategy(description="지수").model_dump()
    chip = strategy_slots.market_index_return_chip("exit", "KOSDAQ", 5, "<", -3.5)
    assert chip == "코스닥 5거래일 등락률이 -3.5% 미만일 때 매도"
    patch = strategy_slots.market_index_return_chip_patch(chip, base)
    sig = patch["exit_signals"][-1]
    assert sig == {"indicator": "market_index_return", "signal_type": "sell", "index": "KOSDAQ",
                   "period": 5, "operator": "<", "value": -3.5}
    ParsedStrategy.model_validate({**base, **patch})
    assert strategy_slots.market_index_return_chip_patch(chip, {**base, **patch}) is None
    assert strategy_slots.market_index_return_chip_patch("코스피 01거래일 등락률이 -5% 이하일 때 매수", base) is None
    assert strategy_slots.market_index_return_chip_patch("손절 -10%", base) is None


def test_index_parameter_is_dropped_from_other_indicators():
    validated, _ = run_validation(StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 1.0,
        "strategy": {"universe": {"markets": ["KOSPI"]},
                     "entry_conditions": [{"factor": "technical.rsi", "operator": "<=", "value": 30,
                                           "parameters": {"period": 14, "index": "KOSPI"}, "source_text": "RSI"}]}}))
    assert "index" not in validated.strategy.entry_conditions[0].parameters


def test_us_market_rejects_the_condition():
    intent = _intent(index="KOSPI", period=1)
    intent.strategy.universe.markets = ["SP500"]
    validated, report = run_validation(intent)
    assert not any(c.factor == FACTOR for c in validated.strategy.entry_conditions)
    assert any("시장 지수 등락률" in e for e in report.errors)


def test_condition_is_exposed_to_the_interpreter_vocabulary():
    from strategy_conversation.interpreter.prompts import build_system_prompt

    assert FACTOR in build_system_prompt()
