"""엔진 v16.31 — 매크로 조건 필터(금리·환율·VIX) 회귀.

- 시계열 저장소: 별칭 정규화·로더·월간 시계열 월말 이동.
- 엔진: 수준/변화율/이동평균 조건의 노출 배열(ffill·지연·OR 최소 노출), 자료 없는 시리즈 경고.
- 레인: MacroFilterSpec → ParsedStrategy → 엔진 요청(완결만) → 디컴파일 왕복, 값 없는 칸 되묻기,
  애매한 '금리'는 시리즈 되묻기, 모르는 지표는 미지원 안내.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import macro_data
from engine import result_warnings as rw
from engine import trade_reason as tr
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


@pytest.mark.parametrize("raw,expected", [
    ("VIX", "vix"), ("환율", "usdkrw"), ("원/달러 환율", "usdkrw"), ("미국 10년물 금리", "us10y"),
    ("달러 인덱스", "dxy"), ("유가", "wti"), ("연준 기준금리", "fed_funds"), ("장단기 금리차", "us_spread"),
    ("금리", None), ("코코아 선물", None),
])
def test_series_alias_normalization(raw, expected):
    assert macro_data.normalize_series(raw) == expected


def _load_sync_module():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "sync_macro_series.py"
    spec = importlib.util.spec_from_file_location("sync_macro_series", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_series(tmp_path, sid, series: pd.Series):
    d = tmp_path / "macro"
    d.mkdir(exist_ok=True)
    pd.DataFrame({"date": pd.DatetimeIndex(series.index).astype("datetime64[us]"),
                  "value": series.values.astype(float), "source": "test"}).to_parquet(d / f"{sid}.parquet", index=False)


@pytest.fixture
def engine_with_macro(tmp_path, monkeypatch):
    from backtest_engine import BacktestEngine
    eng = BacktestEngine()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    monkeypatch.setattr(eng.loader, "data_dir", str(ohlcv))
    days = pd.bdate_range("2024-01-01", periods=40)
    vix = pd.Series(np.r_[np.full(20, 15.0), np.full(20, 35.0)], index=days)      # 21번째 날부터 35
    _write_series(tmp_path, "vix", vix)
    fx = pd.Series(np.linspace(1300, 1450, 40), index=days)
    _write_series(tmp_path, "usdkrw", fx)
    return eng, days


def test_macro_exposure_level_change_ma_and_or(engine_with_macro):
    eng, days = engine_with_macro
    ext = pd.DatetimeIndex(days)
    exp, reasons, stats = eng._macro_exposure(
        [{"series": "vix", "mode": "level", "operator": ">", "value": 30, "exposure_pct": 0}], ext, 0, 0)
    assert exp[19] == 1.0 and exp[20] == 0.0 and exp[-1] == 0.0
    assert reasons[20] and tr.MACRO_REDUCE in reasons[20] and reasons[19] is None
    assert stats[0][2] == 20                                   # 충족 거래일 수
    # next_open 지연 1 — 하루 뒤부터
    exp_d, _, _ = eng._macro_exposure(
        [{"series": "vix", "mode": "level", "operator": ">", "value": 30, "exposure_pct": 50}], ext, 0, 1)
    assert exp_d[20] == 1.0 and exp_d[21] == 0.5
    # 변화율: 환율 10일 변화율 > 2%
    exp_c, _, _ = eng._macro_exposure(
        [{"series": "usdkrw", "mode": "change", "operator": ">", "value": 2, "period": 10, "exposure_pct": 30}], ext, 0, 0)
    assert exp_c[0] == 1.0 and exp_c[-1] == 0.3
    # 이동평균 위: 상승 추세라 20일선 위
    exp_m, _, _ = eng._macro_exposure(
        [{"series": "usdkrw", "mode": "ma", "operator": ">", "period": 20, "exposure_pct": 0}], ext, 0, 0)
    assert exp_m[10] == 1.0 and exp_m[-1] == 0.0
    # 이격도를 말하면 그 폭이 임계다 — 20일선 대비 +5% 위는 완만한 상승에서 한 번도 닿지 않는다.
    exp_gap, gap_reasons, _ = eng._macro_exposure(
        [{"series": "usdkrw", "mode": "ma", "operator": ">", "value": 5, "period": 20, "exposure_pct": 0}], ext, 0, 0)
    assert (exp_gap == 1.0).all()
    assert all(r is None for r in gap_reasons)
    exp_gap2, gap2_reasons, _ = eng._macro_exposure(
        [{"series": "usdkrw", "mode": "ma", "operator": ">", "value": 1, "period": 20, "exposure_pct": 0}], ext, 0, 0)
    assert exp_gap2[-1] == 0.0 and tr.MACRO_COND_MA_GAP in gap2_reasons[-1]
    # OR: 둘 다 충족하는 날은 더 낮은 노출·그 사유
    exp_or, reasons_or, _ = eng._macro_exposure(
        [{"series": "vix", "mode": "level", "operator": ">", "value": 30, "exposure_pct": 50},
         {"series": "usdkrw", "mode": "level", "operator": ">", "value": 1400, "exposure_pct": 0}], ext, 0, 0)
    assert exp_or[25] == 0.5 and exp_or[-1] == 0.0 and "원/달러" in reasons_or[-1]


def test_period_means_trading_days_regardless_of_series_frequency(tmp_path, monkeypatch):
    """월간 시계열의 period 20은 20개월이 아니라 20거래일이다 — 영업일 축에 ffill한 뒤 계산한다."""
    from backtest_engine import BacktestEngine
    eng = BacktestEngine()
    ohlcv = tmp_path / "ohlcv"
    ohlcv.mkdir()
    monkeypatch.setattr(eng.loader, "data_dir", str(ohlcv))
    # 월간 기준금리: 2023-12-31=3.0, 2024-01-31=4.0(한 달 새 +33%)
    monthly = pd.Series([3.0, 4.0, 4.0], index=pd.to_datetime(["2023-12-31", "2024-01-31", "2024-02-29"]))
    _write_series(tmp_path, "fed_funds", monthly)
    days = pd.bdate_range("2024-02-01", periods=30)
    exp, reasons, stats = eng._macro_exposure(
        [{"series": "fed_funds", "mode": "change", "operator": ">", "value": 10, "period": 20,
          "exposure_pct": 0}], pd.DatetimeIndex(days), 0, 0)
    # 20거래일 전(1월 초)은 3.0, 지금은 4.0 → +33% > 10% → 조건 충족. 20개월로 읽었다면 자료가 없어 False다.
    assert exp is not None and exp[0] == 0.0
    assert stats[0][2] > 0


def test_missing_series_warns_and_skips(engine_with_macro):
    eng, days = engine_with_macro
    exp, reasons, stats = eng._macro_exposure(
        [{"series": "gold", "mode": "level", "operator": ">", "value": 2000, "exposure_pct": 0}], pd.DatetimeIndex(days), 0, 0)
    assert exp is None and stats == []
    assert any(rw.MACRO_SERIES_MISSING.split("{")[0] in w for w in eng.warnings)


def test_monthly_series_moves_to_month_end(tmp_path):
    write_series = _load_sync_module().write_series
    s = pd.Series([1.0, 1.25], index=pd.to_datetime(["2024-01-01", "2024-02-01"]))
    path = write_series("fed_funds", s, tmp_path)
    df = pd.read_parquet(path)
    assert [d.strftime("%Y-%m-%d") for d in pd.to_datetime(df["date"])] == ["2024-01-31", "2024-02-29"]


# ── 대화 레인 ────────────────────────────────────────────────────────────────

def _intent(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [], "symbols": []},
        "entry_conditions": [], "exit_conditions": [],
        "ranking": [{"metric": "ranking.return", "lookback_days": 120}],
        "portfolio": {"selection_count": 10, "rebalance_frequency": "monthly"},
        "risk_management": {}, "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({"intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy})


def _compile(intent):
    validated, report = run_validation(intent)
    parsed, dropped, pending = compile_partial(validated, report, "")
    return validated, report, parsed, dropped, pending


def test_macro_filter_round_trip_and_engine_request():
    _, report, parsed, _, _ = _compile(_intent(macro_filters=[
        {"series": "VIX", "mode": "level", "operator": ">", "value": 30, "exposure_pct": 0, "source_text": "VIX가 30을 넘으면 현금"},
        {"series": "환율", "mode": "change", "operator": "crosses_above", "value": 5, "period": 20, "exposure_pct": 50,
         "source_text": "환율이 20일 새 5% 넘게 오르면 절반"},
    ]))
    assert not report.unsupported_features and not report.errors
    assert [m.series for m in parsed.macro_filters] == ["vix", "usdkrw"]
    assert parsed.macro_filters[1].operator == ">" and parsed.macro_filters[1].mode == "change"
    req = to_backtest_request(parsed, resolve_symbols=False)
    assert req["risk"]["macro_filters"] == [
        {"series": "vix", "mode": "level", "operator": ">", "value": 30.0, "exposure_pct": 0.0},
        {"series": "usdkrw", "mode": "change", "operator": ">", "value": 5.0, "period": 20, "exposure_pct": 50.0},
    ]
    assert "macro_filters" in to_canonical_strategy_dsl(parsed)
    spec = decompile_strategy(parsed)
    assert [m.series for m in spec.macro_filters] == ["vix", "usdkrw"] and spec.macro_filters[1].period == 20


def test_ambiguous_rate_asks_series_and_incomplete_filter_is_not_sent():
    _, report, parsed, dropped, pending = _compile(_intent(macro_filters=[
        {"series": "금리", "operator": ">", "value": 4, "exposure_pct": 0, "source_text": "금리가 4%를 넘으면 현금"}]))
    fields = {q.field for q in report.clarification_questions}
    assert "strategy.macro_filters.0.series" in fields
    assert parsed.macro_filters[0].series is None
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["macro_filters"] is None
    assert any(p.get("label") == "매크로 조건 필터" for p in pending)

    _, report2, parsed2, _, _ = _compile(_intent(macro_filters=[
        {"series": "VIX", "operator": ">", "value": 30, "source_text": "VIX가 30을 넘으면"}]))
    assert "strategy.macro_filters.0.exposure_pct" in {q.field for q in report2.clarification_questions}


def test_unknown_macro_series_is_reported_unsupported():
    _, report, parsed, _, _ = _compile(_intent(macro_filters=[
        {"series": "코코아 선물", "operator": ">", "value": 10000, "exposure_pct": 0, "source_text": "코코아 선물이 급등하면"}]))
    assert parsed.macro_filters == []
    assert any("코코아" in u for u in report.unsupported_features)
