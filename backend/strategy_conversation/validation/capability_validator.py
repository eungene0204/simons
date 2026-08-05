"""Capability Validator — LLM이 추출한 지표/기능이 시스템에서 실행 가능한지 판정.

LLM이 이해하는 지표라고 해서 실행 가능한 것은 아니다. Registry가 최종 판정하며,
지원하지 않는 지표를 비슷한 지표로 조용히 대체하지 않는다 — 대체 후보가 있으면
suggested_fixes로 명시 제안만 한다(사용자 확인 필요).

부수 효과: 해석에 성공한 조건의 factor를 canonical ID로 정규화한다(컴파일 준비).
"""

from __future__ import annotations

from typing import List, Tuple

from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry import capability_registry as caps
from strategy_conversation.registry.indicator_registry import REGISTRY, resolve


def validate_capability(intent: StrategyIntent) -> Tuple[List[str], List[str], List[str], List[str]]:
    """(errors, warnings, unsupported_features, suggested_fixes)를 반환한다.

    intent.strategy의 조건 factor를 canonical ID로 제자리 정규화한다.
    """
    errors: List[str] = []
    warnings: List[str] = []
    unsupported: List[str] = []
    fixes: List[str] = []

    strategy = intent.strategy
    if strategy is None:
        return errors, warnings, unsupported, fixes

    for role, attr in (("진입", "entry_conditions"), ("청산", "exit_conditions")):
        conditions = getattr(strategy, attr)
        kept = []
        for cond in conditions:
            spec = resolve(cond.factor)
            if spec is None:
                unsupported.append(cond.factor)
                errors.append(
                    f"{role} 조건 '{cond.factor}'은(는) 알 수 없는 지표입니다"
                    + (f" (원문: {cond.source_text!r})" if cond.source_text else "")
                )
                kept.append(cond)
                continue
            cond.factor = spec.id
            if spec.engine_binding is not None and spec.engine_binding[0] == "ranking":
                # 4B 드리프트 실측(2026-07-16): 랭킹을 ranking 배열과 entry 조건에 중복
                # 출력 — 랭킹은 조건이 아니라 선정 방식이므로 ranking 배열로 이동/중복 제거
                # (구조 정규화, 의미 변경 없음)
                if not strategy.ranking:
                    from strategy_conversation.interpreter.models import RankingSpec
                    lookback = cond.parameters.get("lookback_days") or cond.parameters.get("period")
                    strategy.ranking.append(RankingSpec(
                        metric=spec.id,
                        lookback_days=int(lookback) if lookback else None,
                        source_text=cond.source_text,
                    ))
                continue
            kept.append(cond)
            if spec.supported == "UNSUPPORTED":
                unsupported.append(spec.display_name)
                errors.append(
                    f"{role} 조건 '{spec.display_name}'은(는) 현재 데이터 파이프라인/엔진에서 지원되지 않습니다"
                )
                if spec.alternatives:
                    alt_names = ", ".join(
                        REGISTRY[a].display_name for a in spec.alternatives if a in REGISTRY
                    )
                    fixes.append(
                        f"'{spec.display_name}' 대신 {alt_names} 조건으로 변경할 수 있습니다 (사용자 확인 필요)"
                    )
                continue
            if role == "청산" and spec.engine_binding is not None \
                    and spec.engine_binding[0] != "technical_signal":
                # 컴파일러의 청산 역할 규칙(technical_signal만)을 검증 단계에서 미리 지적한다.
                # 여기서 에러가 없으면 report READY→전량 컴파일이 StrategyCompileError로
                # 전략 전체를 던져 "해석 실패"로 강등된다(2026-08-05 사고: 9B가 손절을
                # 재무 팩터 청산 조건으로 미러링). 에러면 부분 컴파일이 이 조건만 제외하고
                # 나머지 전략을 살린 뒤 '반영하지 못했어요' 안내가 붙는다.
                mirrors_entry = any(
                    c.factor == spec.id for c in strategy.entry_conditions
                )
                if mirrors_entry and not (cond.source_text or "").strip():
                    # 진입에 이미 있는 팩터를 원문 근거(source_text) 없이 복제한 청산은
                    # 9B 미러 드리프트다 — 청산 역할로는 어차피 컴파일 불가이고 새 정보도
                    # 없으므로 안내 없이 정규화로 제거한다. 안내를 내면 진입에 정상 반영된
                    # 같은 지표가 "반영하지 못했어요"로 읽힌다(2026-08-05 실측 혼란: ROE
                    # 진입은 적용됐는데 미러 드롭 안내가 ROE 전체 미반영처럼 보였다).
                    kept.pop()
                    continue
                # 원문 근거가 있거나 진입에 없는 팩터 = 사용자가 실제로 말한 청산 조건일 수
                # 있다 — 조용히 버리지 않고 에러로 남겨 부분 컴파일 제외+안내로 흐르게 한다.
                errors.append(
                    f"청산 조건 '{spec.display_name}'은(는) 청산 신호로 쓸 수 없습니다 "
                    "(기술적 신호만 가능)"
                )
                continue
            # PARTIALLY_SUPPORTED(재무 지표 전반)에 대한 사전 커버리지 경고는 내지 않는다 —
            # 모든 재무 전략에 매번 붙는 블랭킷 노이즈였고(사고 2026-07-17), 실측 커버리지는
            # 백테스트 시점의 데이터 커버리지 로그(engine/data_coverage.py, FR-BT-016)가 정본.
            if cond.operator is not None and spec.allowed_operators \
                    and cond.operator not in spec.allowed_operators:
                errors.append(
                    f"'{spec.display_name}'에 연산자 '{cond.operator}'은(는) 허용되지 않습니다 "
                    f"(허용: {', '.join(spec.allowed_operators)})"
                )
        setattr(strategy, attr, kept)

    for rank in strategy.ranking:
        spec = resolve(rank.metric)
        # 랭킹 가능 지표: ranking.*(모멘텀) + fundamental.*(재무 팩터 랭킹, 2026-08-03 —
        # as-of 재무 컬럼 순위 선정). trading_value는 파케이 컬럼이 아니라 엔진 즉석 계산이라
        # 랭킹 수집 경로에 없어 제외한다(engine.nl_parser.RankingMetricLiteral과 동일 계약).
        rankable = (
            spec is not None and spec.engine_binding is not None
            and (spec.engine_binding[0] == "ranking"
                 or (spec.engine_binding[0] == "fundamental_filter"
                     and spec.engine_binding[1] != "trading_value"))
        )
        if not rankable:
            unsupported.append(rank.metric)
            errors.append(
                f"랭킹 지표 '{rank.metric}'은(는) 지원되지 않습니다 "
                "(지원: 기간 수익률 랭킹, 재무 지표 랭킹 — 예: 영업이익률 상위)"
            )
        else:
            rank.metric = spec.id

    # 유니버스별 팩터 검증 — ETF는 여러 기업을 묶은 상품이라 기업 재무지표를 조건으로 쓸
    # 수 없다(engine/universe_capabilities와 동일 계약). 조용히 제거하지 않고 오류+대안
    # 제안으로 사용자 확인을 받는다. 거래대금(trading_value)은 가격·거래량 파생이라 허용.
    if "ETF" in strategy.universe.markets:
        etf_conflicts: List[str] = []
        for role, attr in (("진입", "entry_conditions"), ("청산", "exit_conditions")):
            for cond in getattr(strategy, attr):
                if (cond.factor.startswith("fundamental.")
                        and cond.factor != "fundamental.trading_value"):
                    spec = resolve(cond.factor)
                    name = spec.display_name if spec else cond.factor
                    etf_conflicts.append(name)
                    unsupported.append(f"ETF 유니버스 × {name}")
                    errors.append(
                        f"ETF는 여러 종목을 묶은 상품이라 {role} 조건 '{name}'"
                        f"(기업 재무지표)을 사용할 수 없습니다"
                    )
        # 재무 팩터 랭킹도 같은 이유로 ETF에서 성립하지 않는다 — 조건 검사와 동일하게
        # 오류+제거(컴파일에 흘려보내지 않는다)+대안 제시.
        for rank in strategy.ranking:
            if rank.metric.startswith("fundamental."):
                spec = resolve(rank.metric)
                name = spec.display_name if spec else rank.metric
                etf_conflicts.append(name)
                unsupported.append(f"ETF 유니버스 × {name} 랭킹")
                errors.append(
                    f"ETF는 여러 종목을 묶은 상품이라 '{name}' 랭킹(기업 재무지표)을 "
                    "사용할 수 없습니다"
                )
        strategy.ranking = [
            r for r in strategy.ranking if not r.metric.startswith("fundamental.")
        ]
        if etf_conflicts:
            fixes.append(
                "이동평균·RSI·MACD·모멘텀 등 가격·기술 지표 조건으로 변경할 수 있습니다 "
                "(사용자 확인 필요)"
            )
        if strategy.universe.new_listing_only:
            # ETF 마스터에는 상장일이 없고, '신규 상장 ETF'는 IPO와 성격이 다르다 —
            # 조용히 무시하지 않고 명시적 미지원으로 알린다.
            unsupported.append("ETF 유니버스 × 신규 상장 종목")
            errors.append("ETF 유니버스에는 신규 상장(IPO) 제한을 적용할 수 없습니다")
            strategy.universe.new_listing_only = False
            strategy.universe.listing_from = None
            strategy.universe.listing_to = None
        if strategy.universe.sectors:
            # ETF엔 종목 업종 분류가 적용되지 않는다 — 테마는 상품명 키워드(etf_theme)가
            # 담당한다. LLM이 테마를 sectors에 넣는 드리프트가 있으면 조용히 버리지 않고
            # etf_theme로 승격한 뒤 sectors를 비운다(컴파일 단계 오폭 방지).
            if not strategy.universe.etf_theme:
                strategy.universe.etf_theme = strategy.universe.sectors[0]
            strategy.universe.sectors = []

    # 유니버스 섹터 — 정본 섹터명 화이트리스트로 판정(조용한 왜곡 방지)
    if strategy.universe.sectors:
        from engine.universe_pit import expand_legacy_sector

        normalized_sectors: List[str] = []
        for sector in strategy.universe.sectors:
            # 분할 전 구 묶음명('증권/보험')은 신규 두 섹터로 펴서 통과시킨다 —
            # 저장된 전략이 미지원 섹터로 판정돼 유니버스를 잃지 않도록.
            canonical = expand_legacy_sector(sector)
            if not canonical:
                unsupported.append(f"섹터 '{sector}'")
                errors.append(f"'{sector}'은(는) 지원 섹터 목록에 없습니다")
                continue
            normalized_sectors.extend(c for c in canonical if c not in normalized_sectors)
        strategy.universe.sectors = normalized_sectors

    # 포트폴리오 기능
    if strategy.portfolio.weighting is not None:
        weighting = caps.normalize_weighting(strategy.portfolio.weighting)
        if weighting is None:
            unsupported.append(f"비중 방식 '{strategy.portfolio.weighting}'")
            errors.append(
                f"비중 방식 '{strategy.portfolio.weighting}'은(는) 지원되지 않습니다 (지원: 동일비중)"
            )
        else:
            strategy.portfolio.weighting = weighting

    if strategy.portfolio.rebalance_frequency is not None:
        freq = caps.normalize_rebalance_frequency(strategy.portfolio.rebalance_frequency)
        if freq is None:
            errors.append(
                f"리밸런싱 주기 '{strategy.portfolio.rebalance_frequency}'을(를) 해석할 수 없습니다 "
                f"(지원: {', '.join(caps.SUPPORTED_REBALANCE_FREQUENCIES)})"
            )
        else:
            strategy.portfolio.rebalance_frequency = freq

    if strategy.backtest.period is not None \
            and strategy.backtest.period not in caps.SUPPORTED_BACKTEST_PERIODS:
        errors.append(f"백테스트 기간 '{strategy.backtest.period}'은(는) 지원되지 않습니다")

    if strategy.risk_management.max_position_weight is not None:
        unsupported.append("종목당 최대 비중 제한")
        errors.append("종목당 최대 비중 제한은 아직 엔진에서 지원되지 않습니다 (동일비중만 지원)")

    return errors, warnings, unsupported, fixes
