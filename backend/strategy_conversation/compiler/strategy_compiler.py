"""Strategy Compiler — 검증 완료된 StrategyIntent를 내부 DSL(ParsedStrategy)로 변환.

ParsedStrategy(engine/nl_parser.py)가 백테스트 엔진이 소비하는 내부 DSL이다 —
별도 AST 계층을 두지 않고 직접 컴파일한다(기존 파이프라인·저장 포맷과 호환).

컴파일은 완전히 결정론적이다: 자연어를 다시 해석하지 않고, canonical ID 매핑·
연산자 변환·기본값 적용·엔진 입력 구성만 수행한다. 검증을 통과하지 못한
StrategyIntent는 컴파일을 거부한다(Fail Fast).
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Set, Tuple

from engine.nl_parser import FundamentalFilter, ParsedStrategy, TechnicalSignal
from strategy_conversation.interpreter.models import (
    StrategyCondition,
    StrategyIntent,
    ValidationReport,
)
from strategy_conversation.registry.concept_ontology import (
    logger as ontology_logger,
    natural_ranking_direction,
)
from strategy_conversation.registry.indicator_registry import REGISTRY
from strategy_conversation.registry.universe_resolver import resolve_sectors, resolve_symbols

logger = logging.getLogger("strategy_interpreter.compiler")


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
        # 사용자가 준 값이 Registry 기본값(70)보다 항상 우선한다. _param을 먼저 부르면
        # 기본값이 채워져 cond.value가 영원히 무시된다 — "상승 확률 80% 이상"이 조용히
        # 70%로 백테스트되던 실측 버그(2026-07-26 A/B, 정규식 보정이 가리고 있었다).
        threshold = params.get("threshold")
        if threshold is None:
            threshold = cond.value
        if threshold is None:
            threshold = _param("threshold")
        kwargs["threshold"] = threshold
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
_CONDITION_PARAM_FIELD_RE = re.compile(
    r"strategy\.(entry_conditions|exit_conditions)\[(\d+)\]\.parameters\.(\w+)$"
)


def _param_has_registry_default(field: str, strategy) -> bool:
    """누락 필드가 '표준값이 있는 지표 파라미터'인지 판정한다.

    임계값(value)이 없는 조건은 전략의 의미 자체가 미정이므로 컴파일에서 제외한다.
    반면 이동평균 기간·신고가 룩백 같은 **계산 파라미터**는 Registry에 표준값이 있고
    `_compile_technical`이 그 값을 채운다 — 사용자가 명시한 신호("데드크로스에 청산")를
    기간을 안 말했다는 이유로 통째로 버리면 준 정보를 잃는다(A/B 실측 2026-07-26:
    ma_crossover 28건·breakout 9건이 이 경로로 소실). 되묻기 질문은 그대로 유지되므로
    사용자는 기간을 바꿀 수 있다.
    """
    m = _CONDITION_PARAM_FIELD_RE.search(field)
    if not m:
        return False
    conditions = getattr(strategy, m.group(1), None) or []
    index = int(m.group(2))
    if index >= len(conditions):
        return False
    spec = REGISTRY.get(conditions[index].factor)
    pspec = spec.parameters.get(m.group(3)) if spec else None
    return pspec is not None and pspec.default is not None


def _condition_label(cond: StrategyCondition) -> str:
    """되묻기·안내·요약에 쓰는 **사람이 읽는** 조건 라벨.

    Registry에 있는 팩터는 정본 표시명을 쓴다. 없는 팩터(LLM이 만들어 낸 미지원 지표)는
    표시명이 없는데, 내부 식별자를 그대로 쓰면 사용자에게 코드가 노출된다 — 2026-08-04
    실측: "'technical.beta' 조건은 값 확인 전까지 전략에 반영되지 않았어요." 이 경우
    사용자가 실제로 말한 표현(source_text)을 쓰고, 그것도 없으면 최소한 네임스페이스
    접두는 떼어낸다. 라벨이 source_text와 같아도 프론트 요약은 중복 표기하지 않는다
    (builderProgressPresentation.formatPendingCondition).
    """
    spec = REGISTRY.get(cond.factor)
    if spec:
        return spec.display_name
    source = (cond.source_text or "").strip()
    if source:
        return source
    # 분류(클래스) 발화 조건 — 내부 식별자(oscillator) 대신 한글 분류명을 쓴다
    from strategy_conversation.registry.concept_ontology import class_display_name

    cls_name = class_display_name(cond.factor)
    if cls_name:
        ontology_logger.info("분류 표시명 | %s → %s 지표", cond.factor, cls_name)
        return f"{cls_name} 지표"
    return str(cond.factor).rsplit(".", 1)[-1]


def compile_partial(
    intent: StrategyIntent,
    report: ValidationReport,
    user_input: str,
) -> Tuple[ParsedStrategy, List[str], List[Dict[str, Optional[str]]]]:
    """NEEDS_CLARIFICATION 초안에서 확정된 조건만으로 ParsedStrategy를 구성한다.

    누락값이 지적된(missing_fields) 조건과 미지원/컴파일 불가 조건은 기본값으로
    조용히 확정하지 않고 **제외**한다 — 제외 목록을 함께 반환해 호출부가 되묻기
    질문/안내로 명시한다(침묵 왜곡 방지). 검증 통과 전략이면 compile_strategy와 동일.

    세 번째 반환값은 값 미정으로 제외된 조건의 구조화 목록
    [{"role", "label", "source_text"}] — 라벨 문자열(dropped)만으로는 프론트가
    "이해했지만 값을 기다리는 조건"을 요약에 표시할 수 없다(빈 요약이 '이해 못함'으로
    읽히던 2026-08-03 사고). 컴파일 불가 드롭(미지원 배치)은 값의 문제가 아니므로
    여기 넣지 않는다.
    """
    strategy = intent.strategy
    if strategy is None:
        raise StrategyCompileError("strategy가 없습니다")

    pending: Set[Tuple[str, int]] = set()
    for field in report.missing_fields:
        m = _CONDITION_FIELD_RE.search(field)
        if m and not _param_has_registry_default(field, strategy):
            pending.add((m.group(1), int(m.group(2))))

    buckets = {"fundamental_filters": [], "entry_signals": [], "exit_signals": []}
    dropped: List[str] = []
    pending_conditions: List[Dict[str, Optional[str]]] = []
    for path, role, conditions in (
        ("entry_conditions", "entry", strategy.entry_conditions),
        ("exit_conditions", "exit", strategy.exit_conditions),
    ):
        for i, cond in enumerate(conditions):
            label = _condition_label(cond)
            if (path, i) in pending:
                dropped.append(label)
                pending_conditions.append(
                    {"role": role, "label": label, "source_text": cond.source_text}
                )
                continue
            try:
                name, compiled = _compile_condition(cond, role)
            except StrategyCompileError:
                dropped.append(label)
                continue
            buckets[name].append(compiled)

    return _build_parsed(strategy, buckets, user_input), dropped, pending_conditions


def _build_parsed(strategy, buckets: dict, user_input: str) -> ParsedStrategy:
    ranking_metric = None
    ranking_lookback = None
    ranking_direction = None
    ranking_quantile_groups = None
    if strategy.ranking:
        # 검증기(capability_validator)가 metric을 정본 id로 정규화한 뒤다 —
        # ranking.return(모멘텀) 또는 fundamental.*(재무 팩터 랭킹, 2026-08-03).
        rank = strategy.ranking[0]
        spec = REGISTRY.get(rank.metric)
        binding = spec.engine_binding if spec else None
        if binding is not None and binding[0] == "fundamental_filter":
            ranking_metric = binding[1]
            # 방향을 사용자가 말하지 않았으면(rank.direction=None) 지표의 자연 방향을
            # 쓴다 — 엔진 기본값은 무조건 top이라, PER처럼 낮을수록 저평가인 지표에서
            # 침묵이 '가장 비싼 종목 선정'으로 뒤집힌다(온톨로지 polarity가 정본).
            # 자연 방향이 없는 지표(시가총액·배당성향 등 none)는 None으로 두어 기존
            # 동작을 유지한다 — 억지 방향을 만들지 않는다.
            direction = rank.direction or natural_ranking_direction(rank.metric)
            # top은 엔진 기본값이라 저장하지 않는다(방향 미지정 기존 전략의 해시 불변).
            ranking_direction = "bottom" if direction == "bottom" else None
            ontology_logger.info(
                "랭킹 방향 확정 | metric=%s 사용자명시=%s 최종=%s(저장=%s)",
                rank.metric, rank.direction or "없음(온톨로지 조회)",
                direction or "미정", ranking_direction,
            )
        else:
            ranking_metric = "return"
            ranking_lookback = rank.lookback_days
        # 분위 그룹 비교(FR-BT-060) — 랭킹이 있어야만 성립하므로 여기서만 통과시킨다.
        ranking_quantile_groups = rank.quantile_groups

    # 업종·지정 종목은 LLM이 뽑은 표현('반도체', 'HBM', '삼성전자')을 registry가 정본 값으로
    # 해석한다 — 사용자 원문을 다시 읽지 않는다(nl_interpretation_contract § 3).
    sector_value, unresolved_sectors = resolve_sectors(strategy.universe.sectors)
    target_symbols, unresolved_symbols = resolve_symbols(strategy.universe.symbols)
    if unresolved_sectors or unresolved_symbols:
        # 조용한 소실 방지 — 되묻기/미지원 안내 채널은 상위(primary)가 소유한다.
        logger.info(
            "universe resolve miss | sectors=%s symbols=%s",
            unresolved_sectors, unresolved_symbols,
        )

    # ETF 유니버스의 테마/상품명은 LLM이 해석한 etf_theme만 쓴다(프롬프트 규칙 6-1).
    # 과거의 원문 결정적 추출 폴백(extract_etf_theme)은 사용자 원문을 정규식으로 읽는
    # 계약 위반이라 제거했다(2026-07-26, nl_interpretation_contract § 3) — LLM이 비우면
    # 테마 제한 없는 ETF 유니버스로 두고, 누락은 프롬프트·검증 레이어에서 개선한다.
    # 시장 미언급(markets=[])의 기본값은 **시스템이** 정한다. LLM이 기본값을 지어내면
    # "사용자가 실제로 말했나"(provenance)가 출력에서 지워져, 되묻기 게이트가 그 답을
    # 사용자 원문 정규식으로 복원하게 된다(계약 위반 — response/provenance.py 참조).
    # 값 자체는 종전과 동일하다: 섹터 제한이 있으면 양시장, 아니면 KOSPI200.
    # 신규 상장 종목은 대부분 코스닥에 들어오므로 KOSPI200(시총 상위 200) 기본값이면
    # 유니버스가 거의 비어 버린다 — 섹터 전략과 같은 이유로 양시장을 기본으로 둔다.
    new_listing_only = strategy.universe.new_listing_only
    listing_from = strategy.universe.listing_from
    listing_to = strategy.universe.listing_to
    markets = list(strategy.universe.markets) or (
        ["KOSPI", "KOSDAQ"] if (sector_value or new_listing_only) else ["KOSPI200"]
    )
    etf_theme = strategy.universe.etf_theme if markets == ["ETF"] else None

    portfolio = strategy.portfolio
    risk = strategy.risk_management
    bt = strategy.backtest

    return ParsedStrategy(
        description=user_input,
        universe=markets,
        sector=sector_value,
        target_symbols=target_symbols,
        etf_theme=etf_theme,
        # 테마 출처는 지정 종목이 있을 때만 통과시킨다 — 이 필드는 "이 종목들이 어느
        # 테마에서 왔는가"라는 출처 표기이므로 종목 없이 표기만 남으면 거짓이 된다.
        # (표기를 종목 목록으로 바꾸는 것은 컴파일이 아니라 지식 조회 — primary의 테마 체인.)
        theme_universe=strategy.universe.theme if target_symbols else None,
        new_listing_only=new_listing_only,
        listing_from=listing_from,
        listing_to=listing_to,
        fundamental_filters=buckets["fundamental_filters"],
        entry_signals=buckets["entry_signals"],
        exit_signals=buckets["exit_signals"],
        entry_logic=strategy.entry_logic,
        ranking_metric=ranking_metric,
        ranking_lookback_days=ranking_lookback,
        ranking_direction=ranking_direction,
        ranking_quantile_groups=ranking_quantile_groups,
        max_positions=portfolio.selection_count if portfolio.selection_count is not None else 10,
        # 그룹당 보유 상한(FR-BT-060b) — 분위 그룹 모드에서 사용자가 말한 종목 수는
        # 그룹당 상한이다. selection_count는 사용자가 말했을 때만 non-null이므로
        # (LLM 계약: 지어내기 금지) 물질화 기본값(10)과 달리 provenance가 필요 없다.
        ranking_group_cap=(
            portfolio.selection_count if ranking_quantile_groups else None
        ),
        # 비율 선정 — 있으면 엔진이 max_positions(개수) 대신 후보 수 기준 비율로 선정한다.
        max_positions_pct=portfolio.selection_percent,
        hold_period_days=portfolio.hold_period_days,
        rebalancing_period=portfolio.rebalance_frequency or "none",
        stop_loss_pct=risk.stop_loss,
        take_profit_pct=risk.take_profit,
        trailing_stop_pct=risk.trailing_stop,
        max_mdd_limit_pct=risk.max_mdd_limit,
        backtest_period=bt.period or "5y",
        backtest_start_date=bt.start_date,
        backtest_end_date=bt.end_date,
        execution_timing=bt.execution_timing or "next_open",
        initial_capital=bt.initial_capital if bt.initial_capital is not None else 10_000_000.0,
        fee_rate=bt.fee_rate if bt.fee_rate is not None else 0.015,
        slippage_rate=bt.slippage_rate if bt.slippage_rate is not None else 0.05,
    )
