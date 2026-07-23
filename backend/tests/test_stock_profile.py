"""단일 종목 연구 프로파일 (FR-STR-068b).

StockProfileService의 결정론 통계·캐시·질문 템플릿 필터링·전략 사전 리뷰를 검증한다.
실데이터에 의존하지 않는다 — 합성 parquet(tmp_path)과 직접 구성한 프로파일만 사용.
"""
import json
import os
import time

import numpy as np
import pandas as pd
import polars as pl
import pytest

from engine.stock_profile import (
    PROFILE_VERSION,
    DataCoverage,
    StockProfileRepository,
    StockProfileService,
    StockResearchProfile,
    compute_signal_stats,
    compute_technical_stats,
)
from engine.stock_question_templates import (
    QUESTION_TEMPLATES,
    select_stock_questions,
    strategy_category_options,
)
from engine.single_asset_review import profile_summary_payload, review_single_asset_strategy
from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal


# ─── 합성 데이터 ─────────────────────────────────────────────────────────────────

def _synthetic_ohlcv(rows: int = 1300, with_fundamentals: bool = True) -> pd.DataFrame:
    """진동 + 완만한 추세 가격 시계열(교차·과매도·돌파 신호가 자연 발생하도록)."""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2020-01-02", periods=rows)
    t = np.arange(rows)
    close = 10_000 * (1 + 0.0002 * t + 0.15 * np.sin(t / 17) + 0.05 * np.sin(t / 5))
    close = close * (1 + rng.normal(0, 0.01, rows))
    close = np.maximum(close, 100.0)
    open_ = close * (1 + rng.normal(0, 0.005, rows))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    volume = rng.integers(50_000, 150_000, rows).astype(float)
    volume[rows // 3] *= 10  # 급증 하루
    df = pd.DataFrame({
        "date": dates, "open": open_, "high": high, "low": low,
        "close": close, "volume": volume,
    })
    if with_fundamentals:
        # 후반 60%에만 존재하는 PIT 재무(공시 이전 구간 결측을 흉내).
        per = np.full(rows, np.nan)
        pbr = np.full(rows, np.nan)
        start = int(rows * 0.4)
        per[start:] = 12.0 + 3.0 * np.sin(t[start:] / 40)
        pbr[start:] = 1.1 + 0.3 * np.sin(t[start:] / 40)
        df["per"] = per
        df["pbr"] = pbr
        df["sector"] = "반도체"
    return df


@pytest.fixture()
def service(tmp_path):
    data_dir = tmp_path / "ohlcv"
    data_dir.mkdir()
    pl.from_pandas(_synthetic_ohlcv()).write_parquet(data_dir / "999990.parquet")
    pl.from_pandas(_synthetic_ohlcv(with_fundamentals=False)).write_parquet(
        data_dir / "999991.parquet"
    )
    repo = StockProfileRepository(cache_dir=str(tmp_path / "cache"))
    return StockProfileService(data_dir=str(data_dir), repository=repo)


def _profile_with(signal_overrides=None, coverage_overrides=None,
                  categories=("trend_following", "mean_reversion", "breakout", "volume"),
                  features=("ohlcv", "moving_average", "rsi", "macd", "bollinger",
                            "stochastic", "cci", "breakout", "volume", "trading_value"),
                  warnings=()) -> StockResearchProfile:
    """테스트용 프로파일을 직접 구성한다(데이터 불필요)."""
    stats = {
        "rsi_below_30_count": 40, "rsi_below_30_per_year": 8.0,
        "rsi_below_20_count": 3, "rsi_below_20_per_year": 0.6,
        "golden_cross_5_20_count": 50, "golden_cross_5_20_per_year": 10.0,
        "macd_buy_cross_count": 60, "macd_buy_cross_per_year": 12.0,
        "bollinger_lower_touch_count": 30, "bollinger_lower_touch_per_year": 6.0,
        "breakout_60d_count": 25, "breakout_60d_per_year": 5.0,
        "volume_spike_3x_count": 12, "volume_spike_3x_per_year": 2.4,
        "drop_10pct_from_60d_high_count": 20, "drop_10pct_from_60d_high_per_year": 4.0,
        "stochastic_buy_cross_count": 300, "stochastic_buy_cross_per_year": 60.0,
        "cci_below_minus_100_count": 80, "cci_below_minus_100_per_year": 16.0,
    }
    stats.update(signal_overrides or {})
    coverage = {
        "ohlcv": DataCoverage(True, "2015-01-02", "2026-07-22", 0.01),
        "pbr": DataCoverage(True, "2018-01-02", "2026-07-22", 0.2, True),
    }
    coverage.update(coverage_overrides or {})
    return StockResearchProfile(
        profile_version=PROFILE_VERSION,
        mode="single_stock",
        symbol="999990",
        name="테스트전자",
        market="KOSPI",
        sector="반도체",
        generated_at="2026-07-24T00:00:00+00:00",
        source_updated_at={"ohlcv": None, "financials": None, "investor_flow": None},
        data_coverage=coverage,
        historical_characteristics={"annualized_volatility": 0.3},
        signal_statistics=stats,
        supported_features=frozenset(features)
        | ({"pbr"} if coverage.get("pbr", DataCoverage(False)).available else frozenset()),
        supported_strategy_categories=frozenset(categories)
        | ({"valuation_timeseries"} if coverage.get("pbr", DataCoverage(False)).available else frozenset()),
        unsupported_features=frozenset({"foreign_flow", "short_interest", "earnings_events", "market_index"}),
        data_quality_warnings=tuple(warnings),
    )


# ─── 프로파일 생성 (정상 케이스) ──────────────────────────────────────────────────

def test_build_profile_schema_and_stats(service):
    profile = service.build_profile("999990")
    assert profile is not None
    assert profile.mode == "single_stock"
    assert profile.profile_version == PROFILE_VERSION
    assert profile.sector == "반도체"

    cov = profile.data_coverage["ohlcv"]
    assert cov.available and cov.start_date == "2020-01-02"
    # 진동 시계열이라 대표 신호가 실제로 발생해야 한다(정확 횟수는 고정하지 않음).
    stats = profile.signal_statistics
    assert stats["golden_cross_5_20_count"] > 0
    assert stats["rsi_below_30_count"] >= 0
    assert stats["volume_spike_3x_count"] >= 1
    hist = profile.historical_characteristics
    assert hist["annualized_volatility"] > 0
    assert hist["maximum_drawdown"] < 0
    # 시장지수 데이터가 없으므로 상관계수는 null(임의 추정 금지).
    assert hist["market_correlation"] is None
    assert "market_index" in profile.unsupported_features


def test_fundamental_coverage_pit_flag(service):
    profile = service.build_profile("999990")
    pbr = profile.data_coverage["pbr"]
    assert pbr.available and pbr.point_in_time_safe is True
    # 재무는 후반 60%에만 존재 → OHLCV보다 늦게 시작 + 경고 발생.
    assert pbr.start_date > profile.data_coverage["ohlcv"].start_date
    assert any("재무 지표는" in w for w in profile.data_quality_warnings)
    assert "valuation_timeseries" in profile.supported_strategy_categories


def test_profile_without_fundamentals(service):
    profile = service.build_profile("999991")
    assert not profile.data_coverage["pbr"].available
    assert "valuation_timeseries" not in profile.supported_strategy_categories
    assert "pbr" not in profile.supported_features


def test_missing_symbol_returns_none(service):
    assert service.build_profile("000000") is None
    assert service.get_profile("000000") is None


def test_no_best_value_anywhere(service):
    """과최적화 방지: 프로파일·템플릿 어디에도 사후 최적값(best value)이 없어야 한다."""
    profile = service.build_profile("999990")
    dumped = json.dumps(profile.to_dict())
    assert "best_value" not in dumped and "optimal" not in dumped
    for template in QUESTION_TEMPLATES:
        rng = template.suggested_search_range
        if rng is not None:
            assert rng.get("best_value") is None


# ─── 캐시 ───────────────────────────────────────────────────────────────────────

def test_cache_roundtrip_and_invalidation(service, tmp_path):
    p1 = service.get_profile("999990")
    assert p1 is not None
    # 파일 캐시 생성 확인 + 동일 fingerprint 재조회는 캐시를 쓴다.
    cache_file = os.path.join(service.repository.cache_dir, "999990.json")
    assert os.path.exists(cache_file)
    assert service.get_profile("999990") is p1  # 메모리 캐시 동일 객체

    # 소스 parquet 갱신(mtime 변경) → fingerprint 불일치 → 재계산.
    src = os.path.join(service.data_dir, "999990.parquet")
    st = os.stat(src)
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    p2 = service.get_profile("999990")
    assert p2 is not p1


def test_cache_version_mismatch_rebuilds(service, monkeypatch):
    p1 = service.get_profile("999990")
    assert p1 is not None
    # 저장된 payload의 버전을 구버전으로 조작 → 조회 미스.
    cache_file = os.path.join(service.repository.cache_dir, "999990.json")
    with open(cache_file, encoding="utf-8") as f:
        payload = json.load(f)
    payload["profile_version"] = PROFILE_VERSION - 1
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    fp = service._fingerprints("999990")
    assert service.repository.get("999990", fp) is None


# ─── 질문 템플릿 필터링 ───────────────────────────────────────────────────────────

def _by_id(items, qid):
    return next((x for x in items if x.question_id == qid), None)


def test_pipeline_unsupported_questions_excluded_with_reason():
    profile = _profile_with()
    sel = select_stock_questions(profile)
    rec_ids = {q.question_id for q in sel.recommended}
    # 수급·공매도·실적발표·시장지수 질문은 노출되지 않고 이유와 함께 제외된다.
    for qid, keyword in (
        ("foreign_flow_entry", "외국인"),
        ("short_interest_entry", "공매도"),
        ("earnings_event_entry", "실적 발표일"),
        ("market_regime_filter", "시장지수"),
    ):
        assert qid not in rec_ids
        excluded = _by_id(sel.excluded, qid)
        assert excluded is not None and keyword in excluded.reason


def test_screening_questions_absent_and_valuation_advanced_only():
    """종목 선별용(횡단면) 질문은 기본 목록에 없고, 재무는 고급 시계열로만 제공된다."""
    profile = _profile_with()
    sel = select_stock_questions(profile)
    # 기본 노출 질문은 전부 시계열 진입/청산 조건(advanced 아님).
    assert all(not q.advanced for q in sel.recommended)
    assert _by_id(sel.recommended, "historical_pbr_entry") is None
    excluded = _by_id(sel.excluded, "historical_pbr_entry")
    assert excluded is not None and "고급" in excluded.reason

    # 명시 요청(고급 모드)에서는 PIT 데이터가 있는 재무 질문이 노출된다.
    sel_adv = select_stock_questions(profile, include_advanced=True)
    pbr_q = _by_id(sel_adv.recommended, "historical_pbr_entry")
    assert pbr_q is not None and pbr_q.advanced
    # 데이터가 없는 재무 질문(PER)은 고급 모드에서도 데이터 사유로 제외된다.
    per_excluded = _by_id(sel_adv.excluded, "historical_per_entry")
    assert per_excluded is not None and "제공되지" in per_excluded.reason


def test_sparse_signal_warning_in_templates():
    profile = _profile_with(signal_overrides={
        "rsi_below_30_count": 3, "rsi_below_30_per_year": 0.5,
    })
    sel = select_stock_questions(profile)
    q = _by_id(sel.recommended, "rsi_oversold_entry")
    assert q is not None and q.warning is not None
    assert "3회만" in q.warning and "완화" in q.warning


def test_frequent_signal_warning_in_templates():
    profile = _profile_with(signal_overrides={
        "volume_spike_3x_count": 500, "volume_spike_3x_per_year": 45.0,
    })
    sel = select_stock_questions(profile)
    q = _by_id(sel.recommended, "volume_spike_entry")
    assert q is not None and q.warning is not None
    assert "거래비용" in q.warning and "슬리피지" in q.warning


def test_category_options_reasons_are_factual():
    options = strategy_category_options(_profile_with())
    assert 3 <= len(options) <= 5
    for o in options:
        # reason은 데이터 사실만 — 추천·보장·우월 표현 금지(규제 안전).
        for banned in ("추천", "보장", "유리", "우수", "최고"):
            assert banned not in o["reason"]


# ─── 전략 사전 리뷰(파스 흐름 배선) ────────────────────────────────────────────────

def test_review_sparse_entry_signal():
    profile = _profile_with(signal_overrides={
        "rsi_below_20_count": 3, "rsi_below_20_per_year": 0.3,
    })
    parsed = ParsedStrategy(
        description="테스트전자 RSI 20 이하 매수", target_symbols=["999990"],
        entry_signals=[TechnicalSignal(indicator="rsi", signal_type="buy",
                                       period=14, operator="<=", value=20)],
    )
    notices = review_single_asset_strategy(parsed, profile)
    assert any("3회만 발생" in n for n in notices)


def test_review_frequent_entry_signal():
    profile = _profile_with()
    parsed = ParsedStrategy(
        description="스토캐스틱", target_symbols=["999990"],
        entry_signals=[TechnicalSignal(indicator="stochastic", signal_type="buy", mode="crossover")],
    )
    notices = review_single_asset_strategy(parsed, profile)
    assert any("거래비용" in n and "슬리피지" in n for n in notices)


def test_review_missing_fundamental_blocks_with_alternative():
    profile = _profile_with(coverage_overrides={"pbr": DataCoverage(False)})
    parsed = ParsedStrategy(
        description="PBR 매수", target_symbols=["999990"],
        fundamental_filters=[FundamentalFilter(metric="pbr", operator="<=", value=1)],
    )
    notices = review_single_asset_strategy(parsed, profile)
    assert any("지원할 수 없습니다" in n for n in notices)
    assert any("기술적 지표" in n for n in notices)  # 대안 제시


def test_review_available_fundamental_gets_pit_notice():
    profile = _profile_with()
    parsed = ParsedStrategy(
        description="PBR 매수", target_symbols=["999990"],
        fundamental_filters=[FundamentalFilter(metric="pbr", operator="<=", value=1)],
    )
    notices = review_single_asset_strategy(parsed, profile)
    assert any("공시 반영 시점" in n and "미래 참조" in n for n in notices)


def test_review_noop_for_universe_strategy():
    parsed = ParsedStrategy(description="유니버스 전략")
    assert review_single_asset_strategy(parsed, _profile_with()) == []


def test_review_data_quality_warning_passthrough():
    profile = _profile_with(warnings=("거래일 대비 데이터 누락 비율이 12%로 높습니다 — 주의.",))
    parsed = ParsedStrategy(
        description="골든크로스", target_symbols=["999990"],
        entry_signals=[TechnicalSignal(indicator="ma_crossover", signal_type="buy",
                                       short_period=5, long_period=20)],
    )
    notices = review_single_asset_strategy(parsed, profile)
    assert any("누락 비율" in n for n in notices)


# ─── API payload 계약 ────────────────────────────────────────────────────────────

def test_profile_summary_payload_contract():
    payload = profile_summary_payload(_profile_with())
    assert payload["stock"] == {"symbol": "999990", "name": "테스트전자"}
    assert payload["profile_summary"]["data_period"] == "2015-01-02 ~ 2026-07-22"
    assert isinstance(payload["profile_summary"]["available_categories"], list)
    assert payload["recommended_questions"], "노출 질문이 있어야 한다"
    for q in payload["recommended_questions"]:
        assert q["reason"]  # 제안 이유 설명 가능해야 한다
    for q in payload["excluded_questions"]:
        assert q["reason"]  # 제외 이유 설명 가능해야 한다
