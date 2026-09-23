"""전문가형 퀀트 전략 요소(엔진 v16.14) — 대화 레인(검증→컴파일→디컴파일→엔진 요청) 계약.

2026-09-19 사용자 요청 문장(품질 점수 + 12-1 모멘텀 + 저변동성 + 변동성 역비중 + 코스피
200일선 국면 필터 + 손절 안 함)에서 나온 결함들의 회귀:
- 12-1 모멘텀은 ranking.return 하나(lookback 252, skip 21) → ranking_skip_days / skip_days.
- 묶음 점수(group)는 구성 지표에 실려 엔진까지 간다.
- '리스크 패리티' 비중은 변동성 역비중으로 반영되고 근사했다고 알린다.
- 시장 국면 필터: 기간·비율이 다 있으면 엔진 요청에 실리고, 비율이 없으면 되묻기(0/30/50 칩)
  + 값 대기 채널에 오르며 엔진 요청에는 싣지 않는다(조용한 적용·조용한 소실 금지).
- '손절 안 함'은 declined로 나르고 미지원으로 보고하지 않는다.
- 'N일 평균 거래대금'의 N이 엔진 조건 파라미터까지 간다(종전: 20일 고정 — 조용한 왜곡).
- ROIC·FCF 마진은 지원 지표다(종전: 미지원 안내).
- 디컴파일 왕복이 새 필드를 전부 보존한다(수정 턴에서 조용히 풀리지 않게).
"""

import dataclasses

import pytest

from engine.nl_parser import ParsedStrategy
from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation import primary
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _intent(**strategy_overrides):
    strategy = {
        "universe": {"markets": ["KOSPI", "KOSDAQ"], "sectors": [], "symbols": []},
        "entry_conditions": [],
        "exit_conditions": [],
        "ranking": [],
        "portfolio": {"selection_count": 30, "rebalance_frequency": "monthly"},
        "risk_management": {},
        "backtest": {},
    }
    strategy.update(strategy_overrides)
    return StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9, "strategy": strategy,
    })


@pytest.fixture
def data_ready(monkeypatch):
    """적재가 끝난 상태 — 2026-09-21부터 DATA_PENDING_METRICS는 비어 있어 이것이 기본이다.

    집합이 다시 채워져도(다음 지표가 적재를 기다릴 때) 이 픽스처를 쓰는 배선 테스트는 그대로
    지표 자체를 검증한다.
    """
    from strategy_conversation.registry import indicator_registry as reg

    for metric in reg.DATA_PENDING_METRICS:
        monkeypatch.setitem(reg.REGISTRY, metric,
                            dataclasses.replace(reg.REGISTRY[metric], data_pending=False))
    monkeypatch.setattr(reg, "DATA_PENDING_METRICS", frozenset())
    return True


@pytest.fixture
def data_pending(monkeypatch):
    """반대 상태 — ROIC·FCF 마진이 아직 적재를 기다리던 때(2026-09-19~09-21)를 재현한다.

    '준비 중' **채널 자체**의 회귀다: 적재가 끝난 지표로는 이 경로를 더 이상 밟을 수 없지만,
    다음 지표가 같은 자리에 들어올 때 문구·제거·칩 제외가 그대로여야 한다.
    """
    from strategy_conversation.registry import indicator_registry as reg

    pending = frozenset({"fundamental.roic", "fundamental.fcf_margin"})
    for metric in pending:
        monkeypatch.setitem(reg.REGISTRY, metric,
                            dataclasses.replace(reg.REGISTRY[metric], data_pending=True))
    monkeypatch.setattr(reg, "DATA_PENDING_METRICS", pending)
    return pending


def _compile(intent):
    validated, report = run_validation(intent)
    parsed, dropped, pending = compile_partial(validated, report, "")
    return validated, report, parsed, dropped, pending


_QUALITY_MOMENTUM = [
    {"metric": "fundamental.roe_or_gpa", "group": "quality"},
    {"metric": "fundamental.roic", "group": "quality"},
    {"metric": "fundamental.operating_margin", "group": "quality"},
    {"metric": "fundamental.debt_ratio", "group": "quality"},
    {"metric": "fundamental.fcf_margin", "group": "quality"},
    {"metric": "ranking.return", "lookback_days": 252, "skip_days": 21},
    {"metric": "ranking.volatility", "lookback_days": 60, "direction": "bottom"},
]


def test_quality_group_and_12_1_momentum_reach_engine_request(data_ready):
    _, report, parsed, _, _ = _compile(_intent(ranking=_QUALITY_MOMENTUM))
    assert not report.unsupported_features, report.unsupported_features
    assert parsed.ranking_metric == "composite"
    comps = {(c.metric, c.group, c.skip_days) for c in parsed.ranking_components}
    assert ("roic", "quality", None) in comps
    assert ("fcf_margin", "quality", None) in comps
    assert ("return", None, 21) in comps
    req = to_backtest_request(parsed, resolve_symbols=False)
    by_metric = {c["metric"]: c for c in req["risk"]["ranking_components"]}
    assert by_metric["return"]["skip_days"] == 21 and by_metric["return"]["lookback_days"] == 252
    assert by_metric["roic"]["group"] == "quality"
    assert by_metric["debt_ratio"]["direction"] == "bottom"   # 자연 방향(낮을수록 선호)


def test_single_return_ranking_carries_skip_days():
    _, _, parsed, _, _ = _compile(_intent(ranking=[
        {"metric": "ranking.return", "lookback_days": 252, "skip_days": 21}]))
    assert parsed.ranking_metric == "return" and parsed.ranking_skip_days == 21
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["ranking_skip_days"] == 21


def test_skip_days_on_non_return_ranking_is_rejected_not_applied():
    _, report, parsed, _, _ = _compile(_intent(ranking=[
        {"metric": "ranking.volatility", "lookback_days": 60, "skip_days": 5}]))
    assert parsed.ranking_skip_days is None
    assert any("최근 기간 제외" in e for e in report.errors)


def test_risk_parity_is_native_erc_weighting():
    """v16.28: 리스크 패리티는 공분산 기반 위험 기여 균등(ERC)을 엔진이 직접 푼다 — 종전(09-19)의
    역변동성 근사·근사 안내는 폐지."""
    _, report, parsed, _, _ = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        portfolio={"selection_count": 30, "rebalance_frequency": "monthly",
                   "weighting": "risk_parity", "weighting_lookback_days": 60},
    ))
    assert parsed.allocation_type == "risk_parity"
    assert parsed.allocation_lookback_days == 60
    assert not any("변동성 역비중" in w for w in report.warnings)
    assert not any("risk_parity" in u for u in report.unsupported_features)
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["allocation_type"] == "risk_parity"
    assert risk["allocation_lookback_days"] == 60


def test_inverse_volatility_without_lookback_asks_with_chips():
    validated, report, parsed, _, _ = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        portfolio={"selection_count": 30, "rebalance_frequency": "monthly",
                   "weighting": "inverse_volatility"},
    ))
    assert "strategy.portfolio.weighting_lookback_days" in report.missing_fields
    items = primary._clarification_items(report, validated)
    chips = [c for i in items for c in i["chips"]]
    assert "비중용 변동성 60일" in chips


def test_market_filter_complete_goes_to_engine():
    _, report, parsed, dropped, pending = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "코스피", "ma_period": 200, "exposure_pct": 30,
                       "source_text": "코스피가 200일 이동평균선 아래에 있으면"},
    ))
    assert not pending and "시장 국면 필터" not in dropped
    regime = to_backtest_request(parsed, resolve_symbols=False)["risk"]["market_regime"]
    assert regime == {"index": "KOSPI", "ma_period": 200, "exposure_pct": 30.0}
    # 종목 이동평균 조건이 생기지 않는다(2026-09-19 사고: 20/60 골든크로스 매수 조건으로 둔갑).
    assert parsed.entry_signals == []


def test_market_filter_without_ratio_asks_and_is_not_silently_applied():
    validated, report, parsed, dropped, pending = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "KOSPI", "ma_period": 200, "exposure_pct": None,
                       "source_text": "코스피가 200일선 아래면 비중 축소"},
    ))
    assert "strategy.market_filter.exposure_pct" in report.missing_fields
    assert "시장 국면 필터" in dropped
    assert any(p["label"] == "시장 국면 필터" for p in pending)
    assert parsed.market_regime is not None and parsed.market_regime.exposure_pct is None
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["market_regime"] is None
    items = primary._clarification_items(report, validated)
    chips = [c for i in items for c in i["chips"]]
    assert "약세 국면 투자 비중 30%" in chips


def test_market_regime_chip_binds_to_ratio():
    _, _, parsed, _, _ = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "KOSPI", "ma_period": 200, "exposure_pct": None},
    ))
    bound, bindings, _, _ = primary._bind_chips(
        ["약세 국면 투자 비중 0% (전량 현금)", "약세 국면 투자 비중 30%"], parsed, None)
    assert bound == ["약세 국면 투자 비중 0% (전량 현금)", "약세 국면 투자 비중 30%"]
    after = ParsedStrategy.model_validate({**parsed.model_dump(), **bindings["약세 국면 투자 비중 30%"]})
    assert after.market_regime.exposure_pct == 30.0 and after.market_regime.ma_period == 200


def test_market_filter_volatility_spike_asks_multiple_with_chips():
    """v16.16 — '시장 변동성이 급격히 확대될 경우'는 배수를 되묻고 값 대기로 둔다(2026-09-20)."""
    validated, report, parsed, dropped, pending = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "KOSPI", "triggers": ["below_ma", "volatility_spike"],
                       "ma_period": 200, "volatility_multiple": None, "exposure_pct": 30,
                       "source_text": "코스피가 200일선 아래에 있거나 시장 변동성이 급격히 확대될 경우"},
    ))
    assert "strategy.market_filter.volatility_multiple" in report.missing_fields
    assert "strategy.market_filter.ma_period" not in report.missing_fields
    assert "시장 국면 필터" in dropped and any(p["label"] == "시장 국면 필터" for p in pending)
    assert to_backtest_request(parsed, resolve_symbols=False)["risk"]["market_regime"] is None
    items = primary._clarification_items(report, validated)
    chips = [c for i in items for c in i["chips"]]
    assert "시장 변동성 평소의 2배 이상" in chips

    bound, bindings, _, _ = primary._bind_chips(["시장 변동성 평소의 2배 이상"], parsed, None)
    assert bound == ["시장 변동성 평소의 2배 이상"]
    after = ParsedStrategy.model_validate(
        {**parsed.model_dump(), **bindings["시장 변동성 평소의 2배 이상"]})
    regime = to_backtest_request(after, resolve_symbols=False)["risk"]["market_regime"]
    assert regime == {"index": "KOSPI", "triggers": ["below_ma", "volatility_spike"],
                      "ma_period": 200, "volatility_multiple": 2.0, "exposure_pct": 30.0}


def test_market_filter_volatility_spike_alone_does_not_ask_ma_period():
    _, report, parsed, dropped, _ = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "KOSPI", "triggers": ["volatility_spike"],
                       "volatility_multiple": 2, "exposure_pct": 50,
                       "source_text": "시장 변동성이 평소의 2배 이상이면 절반은 현금"},
    ))
    assert not [f for f in report.missing_fields if f.startswith("strategy.market_filter")]
    assert "시장 국면 필터" not in dropped
    regime = to_backtest_request(parsed, resolve_symbols=False)["risk"]["market_regime"]
    assert regime == {"index": "KOSPI", "triggers": ["volatility_spike"],
                      "volatility_multiple": 2.0, "exposure_pct": 50.0}


def test_market_filter_triggers_key_missing_is_filled_from_value_slots():
    """형식 정규화 — triggers를 빠뜨린 출력은 채워진 값 자리로 판정 종류를 정한다."""
    from strategy_conversation.interpreter.models import MarketFilterSpec
    assert MarketFilterSpec.model_validate({"ma_period": 200}).triggers == ["below_ma"]
    assert MarketFilterSpec.model_validate({"volatility_multiple": 2}).triggers == ["volatility_spike"]
    assert MarketFilterSpec.model_validate(
        {"ma_period": 200, "volatility_multiple": 2}).triggers == ["below_ma", "volatility_spike"]


def test_market_filter_on_us_universe_is_reported_unsupported():
    _, report, parsed, _, _ = _compile(_intent(
        universe={"markets": ["SP500"], "sectors": [], "symbols": []},
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        market_filter={"index": "KOSPI", "ma_period": 200, "exposure_pct": 30,
                       "source_text": "S&P가 200일선 아래면"},
    ))
    assert parsed.market_regime is None
    assert "S&P가 200일선 아래면" in report.unsupported_features


def test_declined_stop_loss_is_not_unsupported():
    validated, report, _, _, _ = _compile(_intent(
        ranking=[{"metric": "ranking.volatility", "lookback_days": 60}],
        declined=["stop_loss"],
    ))
    assert validated.strategy.declined == ["stop_loss"]
    assert not report.unsupported_features


def test_trading_value_average_period_reaches_engine_condition():
    _, _, parsed, _, _ = _compile(_intent(entry_conditions=[{
        "factor": "fundamental.trading_value", "operator": ">=", "value": 20,
        "parameters": {"period": 20}, "source_text": "최근 20일 평균 거래대금이 20억 원 이상",
    }, {
        "factor": "fundamental.trading_value", "operator": ">=", "value": 50,
        "parameters": {"period": 60},
    }], ranking=[{"metric": "ranking.volatility", "lookback_days": 60}]))
    periods = sorted(f.period for f in parsed.fundamental_filters)
    assert periods == [20, 60]
    conds = to_backtest_request(parsed, resolve_symbols=False)["entry"]["conditions"]
    assert sorted(c["params"].get("period") for c in conds) == [20, 60]


def test_roic_and_fcf_margin_are_supported_filters(data_ready):
    _, report, parsed, _, _ = _compile(_intent(entry_conditions=[
        {"factor": "fundamental.roic", "operator": ">=", "value": 10},
        {"factor": "fundamental.fcf_margin", "operator": ">=", "value": 5},
    ], ranking=[{"metric": "ranking.volatility", "lookback_days": 60}]))
    assert not report.unsupported_features
    assert {f.metric for f in parsed.fundamental_filters} == {"roic", "fcf_margin"}


def test_decompile_roundtrip_preserves_new_fields(data_ready):
    _, _, parsed, _, _ = _compile(_intent(
        entry_conditions=[{"factor": "fundamental.trading_value", "operator": ">=", "value": 20,
                           "parameters": {"period": 60}}],
        ranking=_QUALITY_MOMENTUM,
        portfolio={"selection_count": 30, "rebalance_frequency": "monthly",
                   "weighting": "inverse_volatility", "weighting_lookback_days": 60},
        market_filter={"index": "KOSPI", "ma_period": 200, "exposure_pct": 30},
    ))
    spec = decompile_strategy(parsed)
    again = StrategyIntent(intent="CREATE_STRATEGY", strategy=spec, confidence=1.0)
    validated, report = run_validation(again)
    reparsed, _, _ = compile_partial(validated, report, "")
    assert to_canonical_strategy_dsl(reparsed) == to_canonical_strategy_dsl(parsed)


def test_new_fields_absent_keep_legacy_strategy_hash():
    """새 필드가 비어 있으면 기존 전략의 strategy_id(캐시 키)가 변하지 않는다."""
    _, _, parsed, _, _ = _compile(_intent(ranking=[
        {"metric": "fundamental.per", "direction": "bottom"},
        {"metric": "fundamental.roe_or_gpa"},
    ]))
    dsl = to_canonical_strategy_dsl(parsed)
    for key in ("ranking_skip_days", "allocation_type", "allocation_lookback_days", "market_regime"):
        assert key not in dsl
    for comp in dsl["ranking_components"]:
        assert "skip_days" not in comp and "group" not in comp


# ── 2026-09-19 120B 원출력 재현(프롬프트 6.2 첫 실측) ─────────────────────────────

def test_120b_raw_output_shape_defects_are_normalized(data_ready):
    """① 추정치 상향 → relative_return 바꿔치기 + 미지원 동시 보고 ② technical.volatility 랭킹
    ③ 랭킹 지표를 값 없는 매수 조건으로 중복 ④ FCF 마진 가짜 '가깝게 반영' 안내."""
    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.85,
        "unsupported_features": ["최근 3개월 실적 추정치 상향 여부"],
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"]},
            "entry_conditions": [
                {"factor": "fundamental.trading_value", "operator": ">=", "value": 20,
                 "parameters": {"period": 20}},
                {"factor": "fundamental.roe_or_gpa", "operator": None, "value": None, "source_text": "ROE"},
                {"factor": "fundamental.fcf_margin", "operator": None, "value": None,
                 "source_text": "잉여현금흐름(FCF) 마진"},
            ],
            "ranking": [
                {"metric": "fundamental.roe_or_gpa", "group": "quality"},
                {"metric": "fundamental.fcf_margin", "group": "quality"},
                {"metric": "return", "lookback_days": 252, "skip_days": 21},
                {"metric": "technical.relative_return", "source_text": "최근 3개월 실적 추정치 상향 여부"},
                {"metric": "technical.volatility", "lookback_days": 60, "direction": "bottom"},
            ],
            "portfolio": {"selection_count": 30, "rebalance_frequency": "monthly"},
        },
    })
    validated, report, parsed, dropped, pending = _compile(intent)
    metrics = [c.metric for c in parsed.ranking_components]
    assert "relative_return" not in metrics                    # ① 바꿔치기 제거
    assert "volatility" in metrics                              # ② 저변동성 보존
    assert [f.metric for f in parsed.fundamental_filters] == ["trading_value"]   # ③
    assert not pending
    assert "알 수 없는 랭킹 기준" not in " ".join(report.unsupported_features)
    assert primary._approximation_notices(validated.strategy) == []               # ④


def test_fcf_margin_condition_quote_is_not_a_substitution(data_ready):
    from strategy_conversation.registry import indicator_registry as reg
    from strategy_conversation.interpreter.models import StrategyCondition

    cond = StrategyCondition(factor="fundamental.fcf_margin", operator=">=", value=5,
                             source_text="잉여현금흐름(FCF) 마진 5% 이상")
    assert not primary._substituted_factor(cond, reg.resolve("fundamental.fcf_margin"), reg)


def test_recall_pass_does_not_resurrect_ranking_or_regime_phrases():
    """2026-09-19 120B: 조건 구절 나열이 랭킹·국면 필터·미지원 구절을 조건으로 되살렸다."""
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions

    intent = StrategyIntent.model_validate({
        "intent": "CREATE_STRATEGY", "confidence": 0.9,
        "unsupported_features": ["최근 3개월 실적 추정치 상향 여부"],
        "strategy": {
            "universe": {"markets": ["KOSPI", "KOSDAQ"]},
            "entry_conditions": [],
            "ranking": [
                {"metric": "fundamental.roe_or_gpa", "group": "quality"},
                {"metric": "return", "lookback_days": 252, "skip_days": 21},
                {"metric": "technical.volatility", "lookback_days": 60, "direction": "bottom"},
            ],
            "market_filter": {"index": "KOSPI", "ma_period": 200,
                              "source_text": "코스피가 200일 이동평균선 아래에 있으면 투자 비중을 줄여"},
        },
    })
    validated, _ = run_validation(intent)
    text = ("ROE 품질 점수, 최근 12개월 수익률에서 최근 1개월을 제외한 모멘텀과 최근 3개월 실적 추정치 "
            "상향 여부, 최근 60일 변동성이 낮은 종목, 코스피가 200일 이동평균선 아래에 있으면 투자 비중을 줄여")
    phrases = ["ROE 품질 점수", "최근 12개월 수익률에서 최근 1개월을 제외한 모멘텀",
               "최근 3개월 실적 추정치 상향 여부", "최근 60일 변동성이 낮은",
               "코스피가 200일 이동평균선 아래에 있으면"]
    recovered = recover_missing_conditions(validated, text, lambda *a, **k: "", phrases=phrases)
    assert recovered == []
    assert validated.strategy.entry_conditions == []


def test_ranking_quoting_only_unsupported_concept_is_not_substituted():
    """120B: '실적 추정치 상향' 인용으로 시장 대비 수익률 랭킹을 만든 바꿔치기 — 제거+미지원."""
    _, report, parsed, _, _ = _compile(_intent(ranking=[
        {"metric": "ranking.volatility", "lookback_days": 60},
        {"metric": "technical.relative_return", "source_text": "최근 3개월 실적 추정치 상향 여부"},
    ]))
    assert parsed.ranking_metric == "volatility"
    assert "최근 3개월 실적 추정치 상향 여부" in report.unsupported_features


def test_class_shell_mirroring_ranking_group_is_dropped(data_ready):
    _, report, parsed, _, pending = _compile(_intent(
        entry_conditions=[{"factor": "class.quality", "operator": None, "value": None,
                           "source_text": "ROE, ROIC, 영업이익률, 부채비율, 잉여현금흐름(FCF) 마진 등을 종합한 품질 점수"}],
        ranking=_QUALITY_MOMENTUM,
    ))
    assert not pending and not report.missing_fields


def test_recall_reports_phrase_naming_only_unsupported_concept():
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions

    validated, _ = run_validation(_intent(ranking=[{"metric": "ranking.volatility", "lookback_days": 60}]))
    text = "최근 3개월 실적 추정치 상향 여부를 반영하고 변동성이 낮은 종목"
    recover_missing_conditions(validated, text, lambda *a, **k: "",
                               phrases=["최근 3개월 실적 추정치 상향 여부"])
    assert validated.unsupported_features == ["최근 3개월 실적 추정치 상향 여부"]
    assert validated.strategy.entry_conditions == []


# ── 데이터 적재 대기(2026-09-20 사용자 지시) ─────────────────────────────────────

def test_data_pending_metrics_are_reported_as_preparing_not_unsupported(data_pending):
    """ROIC·FCF 마진은 데이터 적재 전까지 조건·랭킹에서 빠지고 '준비 중'으로 알린다.

    종전(적재 전 지원 표기)에는 조건이 그대로 엔진에 가서 fail-closed로 **거래 0건**
    백테스트가 나갔고, 그 사실은 결과 화면 경고 한 줄로만 남았다(2026-09-20 실측).
    """
    validated, report, parsed, _, pending = _compile(_intent(
        entry_conditions=[
            {"factor": "fundamental.roic", "operator": ">=", "value": 10, "source_text": "ROIC 10% 이상"},
            {"factor": "fundamental.per", "operator": "<=", "value": 10},
        ],
        ranking=[{"metric": "fundamental.fcf_margin"}, {"metric": "fundamental.roe_or_gpa"}],
    ))
    assert [f.metric for f in parsed.fundamental_filters] == ["per"]
    assert parsed.ranking_metric == "roe_or_gpa"
    assert report.preparing_features == ["ROIC 10% 이상", "FCF 마진(잉여현금흐름÷매출액)"]
    # 미지원과 섞이지 않는다 — 문구가 다르다(곧 쓸 수 있음 vs 계획 없음).
    assert not report.unsupported_features
    assert not pending
    notices = primary._preparing_notice(report)
    assert len(notices) == 1 and "준비 중" in notices[0] and "ROIC 10% 이상" in notices[0]


def test_preparing_metrics_are_not_offered_as_chips(data_pending):
    """준비 중 지표는 되묻기 칩으로 제안하지 않는다(누르면 다시 빠질 선택지)."""
    chips = " ".join(_chip_fixture()["condition_values"])
    assert "ROIC" not in chips and "FCF 마진" not in chips


def test_backfilled_metrics_are_offered_as_chips_again():
    """적재가 끝나면(2026-09-21) 같은 지표가 칩으로 되살아난다 — 집합 한 줄이 정본이라는 계약."""
    chips = " ".join(_chip_fixture()["condition_values"])
    assert "ROIC" in chips and "FCF 마진" in chips


def _chip_fixture() -> dict:
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "export_chips", root / "scripts" / "export_clarification_chips.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_fixture()


def test_backfilled_data_turns_the_metrics_on(data_ready):
    """적재가 끝나면(DATA_PENDING_METRICS에서 제거) 같은 요청이 그대로 반영된다."""
    _, report, parsed, _, _ = _compile(_intent(
        entry_conditions=[{"factor": "fundamental.roic", "operator": ">=", "value": 10}],
        ranking=[{"metric": "fundamental.fcf_margin"}, {"metric": "fundamental.roe_or_gpa"}],
    ))
    assert [f.metric for f in parsed.fundamental_filters] == ["roic"]
    assert {c.metric for c in parsed.ranking_components} == {"fcf_margin", "roe_or_gpa"}
    assert not report.preparing_features
