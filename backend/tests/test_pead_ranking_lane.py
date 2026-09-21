"""실적 서프라이즈 랭킹·유니버스 사전 필터의 해석 레인 관통(엔진 v16.19).

계산 자체는 `test_earnings_factor.py`가 고정한다. 여기서는 사용자가 말한 값이 해석 →
검증 → 컴파일 → 정본 DSL·엔진 요청까지 **그대로** 도착하는지, 말하지 않은 값이 지어내지지
않는지, 범위 밖 값이 기본값으로 바꿔치기되지 않고 되묻는지를 본다(잔차 반전과 같은 계약).
"""

from __future__ import annotations

import pytest

from engine.strategy_converter import to_backtest_request, to_canonical_strategy_dsl
from strategy_conversation.compiler.strategy_compiler import compile_partial
from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.validation.pipeline import run_validation


def _compile(*, ranking=None, universe=None, portfolio=None):
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"], **(universe or {})},
        "ranking": [ranking or {"metric": "ranking.pead", "entry_delay_days": 2, "expiry_days": 60}],
        "portfolio": {"selection_count": 50, "rebalance_frequency": "daily", **(portfolio or {})},
    }))
    return compile_partial(intent, report, "실적 서프라이즈 상위 50종목")[0], report


# ── 랭킹 ────────────────────────────────────────────────────────────────────

def test_pead_ranking_reaches_engine_request_and_canonical_dsl():
    parsed, report = _compile()

    assert report.errors == []
    assert parsed.ranking_metric == "pead"
    assert (parsed.ranking_entry_delay_days, parsed.ranking_expiry_days) == (2, 60)
    dsl = to_canonical_strategy_dsl(parsed)
    assert dsl["ranking_entry_delay_days"] == 2 and dsl["ranking_expiry_days"] == 60
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["ranking_metric"] == "pead"
    assert (risk["ranking_entry_delay_days"], risk["ranking_expiry_days"]) == (2, 60)


def test_unspoken_window_falls_back_to_defaults_without_asking():
    """말하지 않은 자격 창은 기본값(2·60)으로 확정한다 — 잔차 반전과 같은 사용자 결정."""
    parsed, report = _compile(ranking={"metric": "ranking.pead"})

    assert (parsed.ranking_entry_delay_days, parsed.ranking_expiry_days) == (2, 60)
    assert not [q for q in report.clarification_questions if "ranking" in (q.field or "")]


def test_out_of_range_window_is_asked_not_silently_replaced():
    parsed, report = _compile(ranking={"metric": "ranking.pead", "expiry_days": 9999})

    assert parsed.ranking_expiry_days is None          # 기본값으로 바꿔치지 않는다
    assert any("제외까지의 기간" in message for message in report.errors)
    assert any(q.field.endswith("expiry_days") for q in report.clarification_questions)


def test_entry_delay_must_be_shorter_than_expiry():
    _parsed, report = _compile(
        ranking={"metric": "ranking.pead", "entry_delay_days": 20, "expiry_days": 5})

    assert any("짧아야 합니다" in message for message in report.errors)


def test_pead_round_trips_through_decompiler():
    parsed, _report = _compile()
    spec = decompile_strategy(parsed)

    assert spec.ranking[0].metric == "ranking.pead"
    assert (spec.ranking[0].entry_delay_days, spec.ranking[0].expiry_days) == (2, 60)


def test_pead_cannot_be_combined_with_another_ranking():
    """복합 순위 합산 대상이 아니다 — 조용히 합산하지 않고 알린 뒤 뺀다."""
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["KOSPI"]},
        "ranking": [{"metric": "ranking.pead"}, {"metric": "fundamental.per", "direction": "bottom"}],
        "portfolio": {"selection_count": 20},
    }))

    assert [r.metric for r in intent.strategy.ranking] == ["fundamental.per"]
    assert any("합산할 수 없습니다" in message for message in report.errors)


def test_pead_is_rejected_for_etf_universe():
    intent, report = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"markets": ["ETF"], "etf_theme": "반도체"},
        "ranking": [{"metric": "ranking.pead"}],
        "portfolio": {"selection_count": 5},
    }))

    assert intent.strategy.ranking == []
    assert any("분기 실적" in message for message in report.errors)


# ── 유니버스 사전 필터 ──────────────────────────────────────────────────────

def test_universe_filters_reach_engine_request():
    parsed, report = _compile(universe={
        "market_cap_top_n": 500,
        "liquidity_exclude_bottom_percent": 20,
        "liquidity_lookback_days": 20,
    })

    assert report.errors == []
    assert parsed.universe_market_cap_top_n == 500
    assert parsed.universe_liquidity_exclude_bottom_pct == 20
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["universe_market_cap_top_n"] == 500
    assert risk["universe_liquidity_exclude_bottom_pct"] == 20
    assert risk["universe_liquidity_lookback_days"] == 20


def test_universe_filters_round_trip_through_decompiler():
    parsed, _report = _compile(universe={"market_cap_top_n": 500})

    assert decompile_strategy(parsed).universe.market_cap_top_n == 500


def test_absent_universe_filters_leave_keys_out_of_canonical_dsl():
    """말하지 않으면 정본 DSL에 키가 남지 않는다(기존 전략 해시 불변)."""
    parsed, _report = _compile()
    dsl = to_canonical_strategy_dsl(parsed)

    assert "universe_market_cap_top_n" not in dsl
    assert "universe_liquidity_exclude_bottom_pct" not in dsl


def test_sector_cap_and_universe_filters_coexist():
    parsed, report = _compile(
        universe={"market_cap_top_n": 500, "liquidity_exclude_bottom_percent": 20},
        portfolio={"max_sector_weight_percent": 25},
    )

    assert report.errors == []
    risk = to_backtest_request(parsed, resolve_symbols=False)["risk"]
    assert risk["max_sector_weight_pct"] == 25
    assert risk["universe_market_cap_top_n"] == 500
    assert risk["ranking_metric"] == "pead"


# ── 시그널 계산 과정을 풀어 말한 서술(2026-09-21 사고, 9B 레인) ───────────────────
# 값은 전부 제 칸에 들어갔는데(유니버스 500·하위 20% 제외·pead 2/60·섹터 25%·익일 시가·0.15%),
# 같은 구절이 ① 회수 패스에서 값 없는 시가총액·거래대금 조건 ② 계열 껍데기(class.*) 근사 조건
# ③ 미지원 보고로 한 번씩 더 나가 엉뚱한 되묻기와 거짓 안내 다섯 줄이 붙었다.

_INCIDENT_INPUT = (
    "시가총액 상위 500종목 중 최근 20일 평균 거래대금 하위 20%를 제외하고, 직전 8개 분기 이상의 EPS "
    "데이터가 있는 종목을 유니버스로 한다. 각 종목의 가장 최근 분기 EPS에서 전년 동기 EPS를 뺀 값을 "
    "직전 8개 분기 동일 계산값의 표준편차로 나눠 SUE를 구한다. 동시에 실적 발표일 직전일부터 발표 후 "
    "2영업일까지의 수익률에서 같은 기간 시장수익률을 뺀 초과수익률을 구한다. 두 값을 각각 전 종목 대상 "
    "z-score로 표준화하고 상하위 1% 윈저라이즈한 뒤 평균 낸 값을 시그널로 쓴다. 매일 시그널 상위 "
    "50종목을 동일가중 보유하되, 발표일로부터 2영업일이 지난 종목만 편입하고 발표일로부터 60영업일이 "
    "지나면 제외한다. 섹터별 비중은 총자산의 25%를 상한으로 하고, 편입 시점은 익일 시가, 편도 "
    "거래비용 15bp를 적용한다."
)
_INCIDENT_INTENT = {
    "intent": "CREATE_STRATEGY", "confidence": 0.85,
    "strategy": {
        "universe": {"market_cap_top_n": 500, "liquidity_exclude_bottom_percent": 20,
                     "liquidity_lookback_days": 20},
        "entry_conditions": [
            {"factor": "class.fundamental", "source_text": "직전 8개 분기 이상의 EPS 데이터가 있는",
             "approximated": True},
            {"factor": "class.risk", "source_text": "SUE 시그널 상위 1%", "approximated": True},
            {"factor": "class.risk", "source_text": "초과수익률 시그널 상위 1%", "approximated": True},
        ],
        "exit_conditions": [
            {"factor": "class.risk", "source_text": "발표일로부터 60영업일이 지나면 제외",
             "approximated": True},
        ],
        "ranking": [{"metric": "pead", "entry_delay_days": 2, "expiry_days": 60,
                     "source_text": "SUE와 초과수익률을 z-score로 표준화해 평균한 시그널 상위 1%"}],
        "portfolio": {"selection_count": 50, "weighting": "equal", "max_sector_weight_percent": 25,
                      "rebalance_frequency": "daily", "rebalance_method": "weights_only"},
        "backtest": {"execution_timing": "next_open", "fee_rate": 0.15},
    },
    "unsupported_features": [
        "SUE 계산 (실적 서프라이즈 시그널은 ranking.pead 로 지원되나, 사용자 정의 SUE 공식 및 z-score "
        "평균화 로직은 엔진 기본 로직과 다를 수 있음)",
        "실적 발표일 전후 초과수익률 계산 (PEAD 지표 내부 로직과 일치하지 않을 수 있음)",
        "윈저라이즈 (Winzorize) 처리",
        "편도 거래비용 15bp 적용 (fee_rate 에 반영됨)",
        "섹터별 비중 상한 25% (max_sector_weight_percent 에 반영됨)",
    ],
}
_INCIDENT_PHRASES = ('{"phrases": ["시가총액 상위 500종목", "최근 20일 평균 거래대금 하위 20%", '
                     '"직전 8개 분기 이상의 EPS 데이터"]}')


def test_spelled_out_signal_description_gets_no_false_notice_or_question(monkeypatch):
    from strategy_conversation import primary
    from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterResult

    class _Interpreter:
        def interpret(self, user_input, **kwargs):
            return InterpreterResult(
                intent=StrategyIntent.model_validate(_INCIDENT_INTENT), raw_output="{}",
                repair_attempts=0, latency_ms=1.0, model_name="stub", unreflected_numbers=None)

        def _chat(self, system, user, **kwargs):
            return _INCIDENT_PHRASES if "조건을 말한 구절" in system else '{"quote": null, "period": null}'

    monkeypatch.setattr(primary, "_interpreter_singleton", _Interpreter())
    out = primary.run_primary_parse(_INCIDENT_INPUT)

    assert out["notices"] == []
    assert out["pending_conditions"] == []
    assert out["clarification_question"] is None
    parsed = out["parsed"]
    assert parsed.ranking_metric == "pead"
    assert (parsed.universe_market_cap_top_n, parsed.universe_liquidity_exclude_bottom_pct) == (500, 20)
    assert parsed.max_sector_weight_pct == 25
    assert not parsed.fundamental_filters and not parsed.entry_signals


def test_recall_keeps_conditions_the_universe_fields_do_not_carry():
    """유니버스 칸과 같은 말(이름+수치)만 건너뛴다 — 같은 지표의 **다른** 조건은 되살린다."""
    from strategy_conversation.interpreter.condition_recall import recover_missing_conditions

    intent, _ = run_validation(StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"market_cap_top_n": 500},
        "ranking": [{"metric": "ranking.pead"}],
    }))
    text = "시가총액 상위 500종목 중 시가총액 3000억 이상이고 실적 서프라이즈 상위 50종목"
    recovered = recover_missing_conditions(
        intent, text, lambda *a, **k: "", phrases=["시가총액 상위 500종목", "시가총액 3000억 이상"])

    assert recovered == ["fundamental.market_cap"]
    assert [c.source_text for c in intent.strategy.entry_conditions] == ["시가총액 3000억 이상"]


def test_ranking_covers_only_what_the_ranking_holds():
    from strategy_conversation.registry.indicator_registry import ranking_covers

    assert ranking_covers("윈저라이즈 (Winzorize) 처리", ["ranking.pead"])
    assert ranking_covers("실적 발표일 전후 초과수익률 계산 (PEAD 지표 내부 로직)", ["ranking.pead"])
    assert not ranking_covers("PER 윈저라이즈", ["ranking.pead"])          # 다른 지표를 부른다
    assert not ranking_covers("윈저라이즈 처리", ["ranking.return"])        # 그 랭킹에 없는 처리
    assert not ranking_covers("실적 추정치 상향 여부", ["ranking.pead"])


def test_class_shell_is_not_announced_as_an_approximation():
    """계열 껍데기는 반영된 지표가 없다 — '가깝게 반영' 안내도, 내부 식별자 노출도 없어야 한다."""
    from strategy_conversation import primary

    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={"entry_conditions": [
        {"factor": "class.fundamental", "source_text": "재무가 탄탄한", "approximated": True}]})

    assert primary._approximation_notices(intent.strategy) == []


def test_market_cap_top_n_is_a_stated_universe_over_the_whole_market():
    """'시가총액 상위 500종목'을 말한 사용자에게 유니버스를 다시 묻지 않고, 모집단은 양시장이다.

    2026-09-21 실측: 명시 판정 목록에 이 칸이 없어 "먼저 어떤 시장·종목을 대상으로 할지
    정해볼까요?"가 나갔고, 시장 미언급 기본값 KOSPI200 때문에 상위 500이 201종목이 됐다.
    """
    from strategy_conversation.response.provenance import UNIVERSE, explicit_fields_from_spec

    parsed, _report = _compile(universe={"markets": [], "market_cap_top_n": 500})
    assert parsed.universe == ["KOSPI", "KOSDAQ"]

    intent = StrategyIntent(intent="CREATE_STRATEGY", strategy={"universe": {"market_cap_top_n": 500}})
    assert UNIVERSE in explicit_fields_from_spec(intent.strategy)
    # 거르는 조건만 말한 것은 모집단을 말한 것이 아니다 — 유니버스 질문이 그대로 나간다.
    only_filter = StrategyIntent(intent="CREATE_STRATEGY", strategy={
        "universe": {"liquidity_exclude_bottom_percent": 20}})
    assert UNIVERSE not in explicit_fields_from_spec(only_filter.strategy)
