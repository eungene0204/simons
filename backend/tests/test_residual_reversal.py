"""잔차 반전 시그널 랭킹(residual_reversal, 엔진 v16.17) 배선 전체 회귀.

배경(2026-09-20): 통계적 차익거래 전략 서술("60영업일 수익률을 시장·섹터 평균수익률에 회귀시킨
잔차를 5영업일 누적해 잔차 변동성으로 나누고, 윈저라이즈·z-score·부호 반전한 시그널 상위
50종목")을 엔진이 표현하지 못했다. 1단계로 롱 전용 랭킹 지표를 신설했다.

고정하는 것: ① 계산식(독립 최소제곱 검산)·열 독립성(어떤 종목 묶음으로 계산해도 비트 동일)
② fail-closed(결측·공선·섹터 단독) ③ 횡단면 윈저라이즈·z-score·부호 반전 ④ 허용 파라미터
(이산값, 회귀 룩백 ≥ 누적 기간) ⑤ 사전계산 캐시 = 온디맨드(비트 동일)·데이터 지문 무효화
⑥ 레지스트리·온톨로지·검증기·컴파일러·디컴파일러·정본 DSL(strategy_id).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine import residual_factor as rf
from engine.nl_parser import ParsedStrategy
from engine.strategy_converter import compute_strategy_id, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent, ValidationReport
from strategy_conversation.registry import concept_ontology, indicator_registry
from strategy_conversation.validation.capability_validator import validate_capability
from strategy_conversation.validation.pipeline import run_validation


def _synthetic(rows: int = 140, cols: int = 7, seed: int = 3):
    rng = np.random.default_rng(seed)
    m = rng.normal(0.0, 0.010, size=(rows, 1)).repeat(cols, axis=1)
    s = m * 0.6 + rng.normal(0.0, 0.008, size=(rows, cols))
    y = 0.0002 + 0.9 * m + 0.4 * s + rng.normal(0.0, 0.012, size=(rows, cols))
    return y, m, s


# ── ① 계산식 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lookback,accumulation", [(60, 5), (60, 3), (120, 20)])
def test_raw_score_matches_independent_least_squares(lookback, accumulation):
    y, m, s = _synthetic()
    scores = rf.raw_scores(y, m, s, lookback, accumulation)
    for col in (0, 4):
        for row in (lookback - 1, 130):
            window = slice(row - lookback + 1, row + 1)
            design = np.column_stack([np.ones(lookback), m[window, col], s[window, col]])
            beta, *_ = np.linalg.lstsq(design, y[window, col], rcond=None)
            resid = y[window, col] - design @ beta
            expected = resid[-accumulation:].sum() / np.sqrt((resid ** 2).sum() / (lookback - 3))
            assert scores[row, col] == pytest.approx(expected, rel=1e-5)
    # 회귀 구간이 차기 전에는 값이 없다.
    assert np.isnan(scores[:lookback - 1]).all()


def test_raw_score_is_column_independent_bitwise():
    """사전계산(전 종목 묶음)과 온디맨드(전략 유니버스 묶음)의 값이 같아야 하는 근거."""
    y, m, s = _synthetic(cols=9)
    full = rf.raw_scores(y, m, s, 60, 5)
    picked = [7, 2, 5]
    subset = rf.raw_scores(y[:, picked], m[:, picked], s[:, picked], 60, 5)
    assert np.array_equal(full[:, picked], subset, equal_nan=True)
    assert full.dtype == np.float32


# ── ② fail-closed ───────────────────────────────────────────────────────────

def test_missing_observation_blanks_every_window_that_contains_it():
    y, m, s = _synthetic()
    y[100, 0] = np.nan
    scores = rf.raw_scores(y, m, s, 60, 5)
    assert np.isnan(scores[100:160, 0]).all()
    assert np.isfinite(scores[99, 0]) and np.isfinite(scores[100, 1])


def test_collinear_regressors_are_undefined_not_zero():
    y, m, _s = _synthetic()
    scores = rf.raw_scores(y, m, m * 2.0, 60, 5)      # 섹터 수익률 = 시장 수익률의 배수
    assert np.isnan(scores).all()


def test_sector_return_excludes_self_and_needs_another_member():
    y = np.array([[0.02], [np.nan]])
    alone = rf.leave_one_out_sector_return(y, np.array([[0.02], [0.0]]), np.array([[1.0], [0.0]]))
    assert np.isnan(alone).all()                       # 섹터에 자기뿐 → 값 없음
    three = rf.leave_one_out_sector_return(
        np.array([[0.02]]), np.array([[0.02 + 0.01 + 0.03]]), np.array([[3.0]]))
    assert three[0, 0] == pytest.approx(0.02)          # (0.01 + 0.03) / 2


# ── ③ 횡단면 ────────────────────────────────────────────────────────────────

def test_cross_section_winsorizes_standardizes_and_flips_sign():
    values = np.arange(1.0, 202.0)                     # 1..201 → 1%/99% 분위 = 3, 199
    values[-1] = 10_000.0                              # 극단값은 199로 잘린다
    raw = pd.DataFrame([values, np.full(201, np.nan)], index=pd.date_range("2024-01-02", periods=2))
    signal = rf.cross_sectional_signal(raw)
    row = signal.iloc[0]
    assert row.iloc[-1] == pytest.approx(row.iloc[-3])             # 10000과 199가 같은 값
    assert row.iloc[0] == pytest.approx(row.iloc[2])               # 1·2도 3으로 잘린다
    assert row.iloc[0] > 0 > row.iloc[-1]                          # 부호 반전: 낮은 원점수가 상위
    assert row.mean() == pytest.approx(0.0, abs=1e-12)
    assert row.std(ddof=1) == pytest.approx(1.0)
    assert signal.iloc[1].isna().all()                             # 유효 종목 없는 날


# ── ④ 파라미터 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lookback,accumulation", [(90, 5), (60, 7), (60, 60)])
def test_engine_rejects_parameters_outside_the_allowed_sets(lookback, accumulation):
    with pytest.raises(ValueError):
        rf.validate_params(lookback, accumulation)


def test_lookback_shorter_than_accumulation_is_blocked(monkeypatch):
    """허용값만으로는 생기지 않는 조합이지만, 허용 목록이 바뀌어도 막히도록 고정한다."""
    monkeypatch.setattr(rf, "REGRESSION_LOOKBACKS", (10, 60))
    with pytest.raises(ValueError, match="짧을 수 없습니다"):
        rf.validate_params(10, 20)
    from strategy_conversation.interpreter.models import RankingSpec
    from strategy_conversation.validation.parameter_validator import residual_reversal_param_errors

    errors = residual_reversal_param_errors(RankingSpec(
        metric="ranking.residual_reversal", lookback_days=10, accumulation_days=20))
    assert any("짧을 수 없습니다" in e for e in errors), errors


# ── ⑤ 사전계산 캐시 ─────────────────────────────────────────────────────────

_SECTORS = {"A": "반도체", "B": "반도체", "C": "반도체", "D": "은행", "E": "은행", "F": "해운"}


@pytest.fixture()
def factor_data(tmp_path, monkeypatch):
    """종목 6개(섹터 3개 — '해운'은 단독)·지수 1개의 합성 데이터 디렉터리."""
    from engine import market_index

    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    (tmp_path / "index").mkdir()
    rng = np.random.default_rng(11)
    dates = pd.date_range("2023-01-02", periods=150, freq="B")
    market = 1000.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, len(dates)))
    pl.DataFrame({"date": list(dates), "open": market, "high": market, "low": market,
                  "close": market, "volume": [1.0] * len(dates),
                  "source": ["t"] * len(dates)}).write_parquet(tmp_path / "index" / "KOSPI.parquet")
    for sym in _SECTORS:
        close = 10_000.0 * np.cumprod(1.0 + rng.normal(0.0, 0.015, len(dates)))
        pl.DataFrame({"date": list(dates), "close": close,
                      "volume": [1000.0] * len(dates)}).write_parquet(data_dir / f"{sym}.parquet")
    monkeypatch.setattr(rf, "_sector_by_symbol", lambda: dict(_SECTORS))
    monkeypatch.setattr(market_index, "market_for_symbol", lambda s: "KOSPI" if s in _SECTORS else None)
    market_index._load_cached.cache_clear()
    rf._MEMO.clear()
    yield str(data_dir)
    market_index._load_cached.cache_clear()
    rf._MEMO.clear()


def test_precomputed_default_equals_on_demand_bitwise(factor_data):
    symbols = ["D", "A", "C"]
    on_demand = rf.raw_score_panel(factor_data, symbols, 60, 5)      # 캐시 없음 → 온디맨드
    assert not (rf.cache_dir_for(factor_data) / "score_60_5.parquet").exists()
    rf.build_default_score_cache(factor_data)
    rf._MEMO.clear()
    cached = rf.raw_score_panel(factor_data, symbols, 60, 5)         # 사전계산 캐시
    assert cached.notna().any().all()
    assert np.array_equal(cached.to_numpy(), on_demand.to_numpy(), equal_nan=True)


def test_single_member_sector_and_unknown_symbols_are_excluded(factor_data):
    panel = rf.raw_score_panel(factor_data, ["A", "F", "ZZZ"], 60, 5)
    assert panel["A"].notna().any()
    assert panel["F"].isna().all()         # 섹터에 자기뿐
    assert panel["ZZZ"].isna().all()       # 섹터·시장 미상


def test_cache_is_ignored_when_the_data_fingerprint_changes(factor_data):
    rf.build_default_score_cache(factor_data)
    before = rf.data_fingerprint(factor_data)
    path = os.path.join(factor_data, "A.parquet")
    frame = pl.read_parquet(path)
    frame.with_columns(pl.col("close") * 1.5).head(len(frame) - 1).write_parquet(path)
    assert rf.data_fingerprint(factor_data) != before
    assert not rf._cache_valid(factor_data, "score_default", rf.data_fingerprint(factor_data),
                               "score_60_5.parquet")
    rf._MEMO.clear()
    fresh = rf.raw_score_panel(factor_data, ["A", "B"], 60, 5)      # 낡은 캐시를 읽지 않고 재계산
    assert fresh["B"].notna().any()
    assert rf._cache_valid(factor_data, "materials", rf.data_fingerprint(factor_data), "returns.parquet")


def test_engine_panel_has_price_frame_shape_and_masks_prelisting(factor_data):
    dates = pd.date_range("2023-01-02", periods=150, freq="B")
    prices = pd.DataFrame(100.0, index=dates, columns=["A", "B", "C", "D", "E"])
    prices.loc[dates[:120], "E"] = np.nan              # 엔진이 보기에 상장 전
    signal = rf.residual_reversal_panel(prices, 60, 5, factor_data)
    assert signal.shape == prices.shape and list(signal.columns) == list(prices.columns)
    assert signal.loc[dates[100], "E"] != signal.loc[dates[100], "E"]      # NaN
    row = signal.loc[dates[-1]].dropna()
    assert len(row) >= 4 and row.mean() == pytest.approx(0.0, abs=1e-9)


def test_panel_is_none_without_index_history(tmp_path):
    (tmp_path / "ohlcv").mkdir()
    from engine import market_index

    market_index._load_cached.cache_clear()
    prices = pd.DataFrame(1.0, index=pd.date_range("2024-01-02", periods=3), columns=["A"])
    assert rf.residual_reversal_panel(prices, 60, 5, str(tmp_path / "ohlcv")) is None


# ── ⑥ 대화 레인 ─────────────────────────────────────────────────────────────

def _intent(ranking, markets=("KOSPI", "KOSDAQ")) -> StrategyIntent:
    return StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": list(markets)},
        "ranking": ranking,
        "portfolio": {"selection_count": 50, "weighting": "equal", "rebalance_frequency": "daily"},
    })


def _compile(ranking, **kw) -> ParsedStrategy:
    intent, report = run_validation(_intent(ranking, **kw))
    return compile_partial(intent, report, "잔차 반전 시그널 상위 50종목")[0]


def test_registry_and_ontology_register_the_ranking():
    spec = indicator_registry.resolve("residual_reversal")
    assert spec is not None and spec.id == "ranking.residual_reversal"
    assert spec.engine_binding == ("ranking", "residual_reversal")
    onto = concept_ontology.get_ontology()
    assert onto.members["ranking.residual_reversal"] == "class.ranking"
    assert concept_ontology.natural_ranking_direction("ranking.residual_reversal") == "top"


def test_unspoken_parameters_compile_to_the_default_combination():
    parsed = _compile([{"metric": "residual_reversal"}])
    assert (parsed.ranking_metric, parsed.ranking_lookback_days,
            parsed.ranking_accumulation_days) == ("residual_reversal", 60, 5)
    assert parsed.ranking_direction is None


def test_spoken_parameters_reach_engine_request_and_canonical_dsl():
    from engine.strategy_converter import to_backtest_request

    parsed = _compile([{"metric": "ranking.residual_reversal", "lookback_days": 120,
                        "accumulation_days": 10}])
    assert (parsed.ranking_lookback_days, parsed.ranking_accumulation_days) == (120, 10)
    canonical = to_canonical_strategy_dsl(parsed)
    assert (canonical["ranking_lookback_days"], canonical["ranking_accumulation_days"]) == (120, 10)
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert (risk["ranking_metric"], risk["ranking_lookback_days"],
            risk["ranking_accumulation_days"]) == ("residual_reversal", 120, 10)


def test_each_parameter_combination_has_its_own_strategy_id():
    ids = {
        compute_strategy_id(_compile([{"metric": "residual_reversal", "lookback_days": lb,
                                       "accumulation_days": acc}]))
        for lb in rf.REGRESSION_LOOKBACKS for acc in rf.ACCUMULATION_DAYS
    }
    assert len(ids) == len(rf.REGRESSION_LOOKBACKS) * len(rf.ACCUMULATION_DAYS)
    # 말하지 않은 값 = 기본 조합과 같은 전략이다.
    assert compute_strategy_id(_compile([{"metric": "residual_reversal"}])) == compute_strategy_id(
        _compile([{"metric": "residual_reversal", "lookback_days": 60, "accumulation_days": 5}]))


def test_other_rankings_keep_their_strategy_id():
    """새 필드는 값이 없으면 정본 DSL에서 빠진다 — 기존 전략의 해시 불변."""
    parsed = _compile([{"metric": "ranking.return", "lookback_days": 60}])
    assert parsed.ranking_accumulation_days is None
    assert "ranking_accumulation_days" not in to_canonical_strategy_dsl(parsed)


@pytest.mark.parametrize("ranking,needle,field", [
    ({"metric": "residual_reversal", "lookback_days": 90}, "60·120·250", "lookback_days"),
    ({"metric": "residual_reversal", "accumulation_days": 7}, "3·5·10·20", "accumulation_days"),
])
def test_value_outside_the_allowed_set_is_asked_not_replaced(ranking, needle, field):
    intent, report = run_validation(_intent([ranking]))
    assert any(needle in e for e in report.errors), report.errors
    questions = [q for q in report.clarification_questions if q.field.endswith(field)]
    assert questions and needle in questions[0].question
    parsed = compile_partial(intent, report, "x")[0]
    # 허용 밖 값은 싣지 않는다 — 기본값으로 바꿔치지도 않는다.
    assert getattr(parsed, "ranking_lookback_days" if field == "lookback_days"
                   else "ranking_accumulation_days") is None


def test_unspoken_parameters_are_not_asked():
    _intent_out, report = run_validation(_intent([{"metric": "residual_reversal"}]))
    assert not [q for q in report.clarification_questions if "ranking[" in q.field], \
        report.clarification_questions


def test_accumulation_days_on_another_ranking_is_rejected():
    intent, report = run_validation(_intent([{"metric": "ranking.return", "lookback_days": 60,
                                              "accumulation_days": 5}]))
    assert any("잔차 누적 기간" in e for e in report.errors), report.errors
    assert intent.strategy.ranking[0].accumulation_days is None


def test_validator_rejects_the_signal_on_us_and_etf_universes():
    for markets, needle in ((["SP500"], "미국 시장"), (["ETF"], "ETF")):
        intent = _intent([{"metric": "ranking.residual_reversal"}], markets=markets)
        errors, _w, unsupported, _f = validate_capability(intent)
        assert intent.strategy.ranking == []
        assert any(needle in e for e in errors), errors
        assert any("잔차 반전 시그널" in u for u in unsupported), unsupported


def test_validator_rejects_combining_the_signal_with_other_rankings():
    intent = _intent([{"metric": "ranking.residual_reversal"},
                      {"metric": "fundamental.per", "direction": "bottom"}])
    errors, _w, unsupported, _f = validate_capability(intent)
    assert [r.metric for r in intent.strategy.ranking] == ["fundamental.per"]
    assert any("합산할 수 없습니다" in e for e in errors), errors
    assert any("복합 순위" in u for u in unsupported), unsupported


def test_decompile_round_trips_both_parameters():
    parsed = _compile([{"metric": "residual_reversal", "lookback_days": 250, "accumulation_days": 20}])
    rank = decompile_strategy(parsed).ranking[0]
    assert (rank.metric, rank.lookback_days, rank.accumulation_days) == (
        "ranking.residual_reversal", 250, 20)
    again = _compile([rank.model_dump()])
    assert compute_strategy_id(again) == compute_strategy_id(parsed)


# ── ⑦ primary 레인 end-to-end(스텁 LLM) ─────────────────────────────────────

def test_primary_lane_builds_the_long_leg_and_reports_the_short_leg(monkeypatch):
    """사고 문장의 골격: 시그널 상위 50종목 동일가중 매일 리밸런싱은 전략이 되고, 공매도·달러 중립은
    미지원 안내로 남는다(1단계 — 롱 전용)."""
    import json

    import llm_backend
    from strategy_conversation import primary
    from strategy_conversation.interpreter import condition_recall
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    sentence = (
        "매일 각 종목의 지난 60영업일 일간 수익률을 시장수익률과 소속 섹터 평균수익률에 회귀시켜 잔차를 "
        "구하고, 최근 5영업일 잔차를 누적한 뒤 잔차 변동성으로 나눈다. z-score로 표준화하고 부호를 뒤집어 "
        "시그널로 쓴다. 시그널 상위 50종목을 동일가중 매수, 하위 50종목을 동일가중 매도하여 달러 중립 "
        "포트폴리오를 구성한다. 다음 날 시가에 체결한다."
    )
    raw = json.dumps({
        "intent": "CREATE_STRATEGY",
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"]},
            "ranking": [{"metric": "residual_reversal", "lookback_days": 60, "accumulation_days": 5,
                         "source_text": "시그널 상위 50종목을 동일가중 매수"}],
            "portfolio": {"selection_count": 50, "weighting": "equal", "rebalance_frequency": "daily"},
            "backtest": {"execution_timing": "next_open"},
        },
        "unsupported_features": ["하위 50종목을 동일가중 매도", "달러 중립"],
        "confidence": 0.9,
    }, ensure_ascii=False)

    def chat(system, user, **_kw):
        if system == condition_recall.build_system_prompt():
            return '{"phrases": []}'
        if system == condition_recall.build_period_system_prompt():
            return '{"quote": null, "period": null}'
        return raw

    monkeypatch.setattr(llm_backend, "is_openrouter", lambda: False)
    monkeypatch.setattr(primary, "_interpreter_singleton",
                        StrategyInterpreter(chat_fn=chat, model="stub"))

    result = primary.run_primary_parse(sentence)

    parsed = result["parsed"]
    assert (parsed.ranking_metric, parsed.ranking_lookback_days,
            parsed.ranking_accumulation_days) == ("residual_reversal", 60, 5)
    assert (parsed.max_positions, parsed.rebalancing_period, parsed.execution_timing) == (
        50, "daily", "next_open")
    joined = " ".join(result["notices"])
    assert "달러 중립" in joined and "지원하지 않아" in joined
    # 말하지 않은 값이 아니므로(둘 다 말했다) 랭킹 기간을 되묻지 않는다.
    assert "며칠" not in (result.get("clarification_question") or "")
