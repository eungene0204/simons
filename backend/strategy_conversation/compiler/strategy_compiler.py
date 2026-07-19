"""Strategy Compiler — 검증 완료된 StrategyIntent를 내부 DSL(ParsedStrategy)로 변환.

ParsedStrategy(engine/nl_parser.py)가 백테스트 엔진이 소비하는 내부 DSL이다 —
별도 AST 계층을 두지 않고 직접 컴파일한다(기존 파이프라인·저장 포맷과 호환).

컴파일은 완전히 결정론적이다: 자연어를 다시 해석하지 않고, canonical ID 매핑·
연산자 변환·기본값 적용·엔진 입력 구성만 수행한다. 검증을 통과하지 못한
StrategyIntent는 컴파일을 거부한다(Fail Fast).
"""

from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategyIntent,
    ValidationReport,
)
from strategy_conversation.registry.indicator_registry import REGISTRY


class StrategyCompileError(ValueError):
    pass


def _compile_fundamental(cond: StrategyCondition, metric: str) -> FundamentalFilter:
    if cond.operator not in ("<", "<=", ">", ">=") or cond.value is None:
        raise StrategyCompileError(
            f"재무 조건 '{cond.factor}'에 연산자/임계값이 없습니다 (검증 누락?)"
        )
    return FundamentalFilter(metric=metric, operator=cond.operator, value=cond.value)


def _compile_technical(
    cond: StrategyCondition, indicator: str, signal_type: str
) -> TechnicalSignal:
    params = cond.parameters
    spec = REGISTRY.get(cond.factor)

    def _param(name: str) -> Optional[float]:
        value = params.get(name)
        if value is None and spec is not None:
            pspec = spec.parameters.get(name)
            value = pspec.default if pspec else None
        return value

    def _int_param(name: str) -> Optional[int]:
        value = _param(name)
        return int(value) if value is not None else None

    kwargs: dict = {"indicator": indicator, "signal_type": signal_type}

    if indicator in ("ma_crossover", "ema"):
        kwargs["short_period"] = _int_param("short_period")
        kwargs["long_period"] = _int_param("long_period")
        if indicator == "ema" and cond.operator in (">", "<"):
            # 가격 vs EMA 지속 상태 추세 필터
            kwargs["mode"] = "above" if cond.operator == ">" else "below"
            kwargs["short_period"] = None
            kwargs["long_period"] = _int_param("long_period") or _int_param("short_period")
    elif indicator == "macd":
        kwargs["mode"] = "crossover"
    elif indicator == "breakout":
        kwargs["lookback_period"] = _int_param("lookback_period")
    elif indicator in ("ai_model", "ai_drop_model"):
        threshold = _param("threshold")
        kwargs["threshold"] = threshold if threshold is not None else cond.value
    elif indicator == "trading_value":
        kwargs["operator"] = cond.operator
        kwargs["value"] = cond.value
    else:
        # rsi/stochastic/cci/adx/williams_r/mfi/roc/volume_spike/bollinger_bands
        kwargs["period"] = _int_param("period")
        if cond.operator in ("<", "<=", ">", ">="):
            kwargs["operator"] = cond.operator
            kwargs["value"] = cond.value

    return TechnicalSignal(**kwargs)


def _compile_condition(cond: StrategyCondition, role: str):
    """단일 조건 → (대상 리스트 이름, 엔진 객체). 컴파일 불가면 StrategyCompileError."""
    spec = REGISTRY.get(cond.factor)
    if spec is None or spec.engine_binding is None:
        raise StrategyCompileError(f"엔진 연결 정보가 없는 지표입니다: {cond.factor}")
    kind, engine_key = spec.engine_binding
    if role == "entry":
        if kind == "fundamental_filter":
            return "fundamental_filters", _compile_fundamental(cond, engine_key)
        if kind == "technical_signal":
            return "entry_signals", _compile_technical(cond, engine_key, "buy")
        raise StrategyCompileError(f"진입 조건으로 쓸 수 없는 지표입니다: {cond.factor}")
    if kind != "technical_signal":
        raise StrategyCompileError(
            f"'{cond.factor}'은(는) 청산 신호로 쓸 수 없습니다 (기술적 신호만 가능)"
        )
    return "exit_signals", _compile_technical(cond, engine_key, "sell")


def compile_strategy(
    intent: StrategyIntent,
    report: ValidationReport,
    user_input: str,
) -> ParsedStrategy:
    """검증 통과(READY) intent만 ParsedStrategy로 컴파일한다."""
    if not report.is_valid:
        raise StrategyCompileError(
            f"검증을 통과하지 않은 전략은 컴파일할 수 없습니다 (status={report.status})"
        )
    strategy = intent.strategy
    if strategy is None:
        raise StrategyCompileError("strategy가 없습니다")

    fundamental_filters: List[FundamentalFilter] = []
    entry_signals: List[TechnicalSignal] = []
    exit_signals: List[TechnicalSignal] = []
    buckets = {
        "fundamental_filters": fundamental_filters,
        "entry_signals": entry_signals,
        "exit_signals": exit_signals,
    }

    for cond in strategy.entry_conditions:
        name, compiled = _compile_condition(cond, "entry")
        buckets[name].append(compiled)
    for cond in strategy.exit_conditions:
        name, compiled = _compile_condition(cond, "exit")
        buckets[name].append(compiled)

    return _build_parsed(strategy, buckets, user_input)


# 검증 리포트의 조건 경로("strategy.entry_conditions[0].value")에서 (역할, 인덱스) 추출
_CONDITION_FIELD_RE = re.compile(r"strategy\.(entry_conditions|exit_conditions)\[(\d+)\]")


def compile_partial(
    intent: StrategyIntent,
    report: ValidationReport,
    user_input: str,
) -> Tuple[ParsedStrategy, List[str]]:
    """NEEDS_CLARIFICATION 초안에서 확정된 조건만으로 ParsedStrategy를 구성한다.

    누락값이 지적된(missing_fields) 조건과 미지원/컴파일 불가 조건은 기본값으로
    조용히 확정하지 않고 **제외**한다 — 제외 목록을 함께 반환해 호출부가 되묻기
    질문/안내로 명시한다(침묵 왜곡 방지). 검증 통과 전략이면 compile_strategy와 동일.
    """
    strategy = intent.strategy
    if strategy is None:
        raise StrategyCompileError("strategy가 없습니다")

    pending: Set[Tuple[str, int]] = set()
    for field in report.missing_fields:
        m = _CONDITION_FIELD_RE.search(field)
        if m:
            pending.add((m.group(1), int(m.group(2))))

    buckets = {"fundamental_filters": [], "entry_signals": [], "exit_signals": []}
    dropped: List[str] = []
    for path, role, conditions in (
        ("entry_conditions", "entry", strategy.entry_conditions),
        ("exit_conditions", "exit", strategy.exit_conditions),
    ):
        for i, cond in enumerate(conditions):
            spec = REGISTRY.get(cond.factor)
            label = spec.display_name if spec else cond.factor
            if (path, i) in pending:
                dropped.append(label)
                continue
            try:
                name, compiled = _compile_condition(cond, role)
            except StrategyCompileError:
                dropped.append(label)
                continue
            buckets[name].append(compiled)

    return _build_parsed(strategy, buckets, user_input), dropped


def _build_parsed(strategy, buckets: dict, user_input: str) -> ParsedStrategy:
    ranking_metric = None
    ranking_lookback = None
    if strategy.ranking:
        rank = strategy.ranking[0]
        ranking_metric = "return"
        ranking_lookback = rank.lookback_days

    sectors = strategy.universe.sectors
    sector_value = None if not sectors else (sectors[0] if len(sectors) == 1 else sectors)

    # ETF 유니버스의 테마/상품명. LLM이 이해한 etf_theme를 우선 사용한다 — "반도체 종목 ETF"
    # 처럼 테마어가 'ETF'와 인접하지 않으면 어순 기반 결정적 추출이 놓치기 때문이다. LLM이
    # 비웠을 때만 규칙 파서와 동일한 자기검증 매칭(extract_etf_theme)으로 폴백한다.
    etf_theme = None
    if strategy.universe.markets == ["ETF"]:
        etf_theme = strategy.universe.etf_theme
        if not etf_theme:
            from engine.universe_pit import extract_etf_theme
            etf_theme = extract_etf_theme(user_input)

    portfolio = strategy.portfolio
    risk = strategy.risk_management
    bt = strategy.backtest

    return ParsedStrategy(
        description=user_input,
        universe=strategy.universe.markets,
        sector=sector_value,
        etf_theme=etf_theme,
        fundamental_filters=buckets["fundamental_filters"],
        entry_signals=buckets["entry_signals"],
        exit_signals=buckets["exit_signals"],
        ranking_metric=ranking_metric,
        ranking_lookback_days=ranking_lookback,
        max_positions=portfolio.selection_count if portfolio.selection_count is not None else 10,
        hold_period_days=portfolio.hold_period_days,
        rebalancing_period=portfolio.rebalance_frequency or "none",
        stop_loss_pct=risk.stop_loss,
        take_profit_pct=risk.take_profit,
        trailing_stop_pct=risk.trailing_stop,
        max_mdd_limit_pct=risk.max_mdd_limit,
        backtest_period=bt.period or "5y",
        backtest_start_date=bt.start_date,
        backtest_end_date=bt.end_date,
        initial_capital=bt.initial_capital if bt.initial_capital is not None else 10_000_000.0,
        fee_rate=bt.fee_rate if bt.fee_rate is not None else 0.015,
        slippage_rate=bt.slippage_rate if bt.slippage_rate is not None else 0.05,
    )
