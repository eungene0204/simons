"""Capability Validator — LLM이 추출한 지표/기능이 시스템에서 실행 가능한지 판정.

LLM이 이해하는 지표라고 해서 실행 가능한 것은 아니다. Registry가 최종 판정하며,
지원하지 않는 지표를 비슷한 지표로 조용히 대체하지 않는다 — 대체 후보가 있으면
suggested_fixes로 명시 제안만 한다(사용자 확인 필요).

부수 효과: 해석에 성공한 조건의 factor를 canonical ID로 정규화한다(컴파일 준비).
"""

from __future__ import annotations

import re
from typing import List, Tuple

import ui_language
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.registry import capability_registry as caps
from strategy_conversation.registry.concept_ontology import (
    concept_spec,
    is_class_id,
    logger as ontology_logger,
)
from strategy_conversation.registry.indicator_registry import (
    REGISTRY, factor_ids_named_in, resolve, with_same_name_variants,
)

# 스키마 필드 경로 꼴의 factor(concept.time_based_exit·technical.beta …)는 LLM이 지어낸
# **내부 식별자**다 — 사용자 안내에 그대로 인용하면 쓴 적 없는 영문 경로가 화면에 나간다
# (잔여 미지원 안내의 field_path_rx와 같은 판정). 사람이 읽는 이름('미지의지표')은 그대로 쓴다.
_IDENTIFIER_FACTOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
# 우리 네임스페이스를 접두로 단 표기도 식별자다("concept.없는개념" — 뒤가 한글이어도
# 'concept.'은 사용자가 쓴 말이 아니다). 목록은 우리 스키마의 이름들이다.
_INTERNAL_NAMESPACES = frozenset({
    "technical", "fundamental", "ranking", "concept", "class",
    "risk_management", "portfolio", "backtest", "time",
})


def _is_internal_factor_name(factor: str) -> bool:
    name = (factor or "").strip()
    if not name:
        return True
    if _IDENTIFIER_FACTOR_RE.match(name):
        return True
    return "." in name and name.split(".", 1)[0].strip().lower() in _INTERNAL_NAMESPACES

_COMPARISON_OPS = ("<", "<=", ">", ">=")
# 교차 연산자 → 같은 방향의 수준 비교(오실레이터 전용 정규화, 위 주석 참조)
_CROSS_TO_COMPARISON = {"crosses_above": ">", "crosses_below": "<"}

# 교차 방향이 역할(signal_type)로만 정해지는 지표 — 엔진 signals.py의 crossover(direction)이
# buy=golden/sell=dead로 고정한다. 매수 칸의 crosses_below는 표현 불가(컴파일러도 같은 판정).
_DIRECTIONAL_CROSS_LEAVES = frozenset({"technical.ma_crossover", "technical.ema", "technical.macd"})
_ROLE_CROSS_DIRECTION = {"진입": "crosses_above", "청산": "crosses_below"}


def _condition_identity(cond) -> tuple:
    """정규화가 끝난 조건의 **구조 동일성** 키 — 값이 None인 파라미터는 없는 것으로 본다."""
    params = tuple(sorted(
        (name, float(value)) for name, value in cond.parameters.items() if value is not None
    ))
    return (cond.factor, cond.operator, cond.value, cond.unit, params)


def _dedupe_identical_conditions(role: str, conditions: list) -> list:
    """같은 역할 안에서 정규화 결과가 **완전히 같은** 조건은 한 번만 남긴다(첫 항목 유지).

    9B 드리프트 실측(2026-08-18, 프롬프트 3.9): "5일 EMA가 20일 EMA를 위로 돌파할 때 매수…
    EMA 데드크로스가 나오면 청산"에서 청산을 두 조각으로 냈다 — 사용자가 말한
    `concept.dead_cross`(인용 'EMA 데드크로스가 나오면 청산하고')와, 진입 인용을 그대로 단
    `technical.ma_crossover crosses_below 1/20` 미러. 둘 다 각자 정당한 경로(개념 전개·
    인용 기반 EMA 착지·기간 교정)를 거쳐 `technical.ema crosses_below 5/20`이 되므로
    미러 가드(반대 방향은 보존)로는 걸러지지 않고, 요약 카드에 'EMA 데드크로스'가 두 줄로
    나갔다. 같은 조건의 반복은 의미가 0이라(AND/OR 어느 쪽이든 항등) 지우는 것이 정규화다
    — 원문을 읽지 않고 LLM 출력 두 조각의 구조만 대조한다(§ 3-1). 기간·연산자·값이 하나라도
    다르면 다른 신호이므로 남긴다(예: EMA 5/20 데드크로스와 20/60 데드크로스).
    """
    seen: set = set()
    kept = []
    for cond in conditions:
        key = _condition_identity(cond)
        if key in seen:
            ontology_logger.info(
                "동일 조건 중복 제거 | %s 조건 factor=%s operator=%s parameters=%s 원문=%r",
                role, cond.factor, cond.operator, cond.parameters, cond.source_text,
            )
            continue
        seen.add(key)
        kept.append(cond)
    return kept


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


_LOWER_OPERATORS = ("<", "<=")
_HIGHER_OPERATORS = (">", ">=")
# 조건 지표를 랭킹 자리에 낸 출력의 정본 랭킹 지표 — validate_capability의 랭킹 정규화와 거울
# 대조가 같은 표를 본다(랭킹만 먼저 정규화되면 같은 개념의 조건 껍데기가 거울로 안 잡힌다).
_RANKING_CANONICAL = {
    "technical.volatility": "ranking.volatility",
    "technical.relative_return": "ranking.relative_return",
}


def _ranking_id(metric: str) -> str:
    spec = resolve(metric)
    factor_id = spec.id if spec is not None else metric
    return _RANKING_CANONICAL.get(factor_id, factor_id)


def ranking_mirrored_by(cond, ranking):
    """값 없는 조건이 같은 표현을 담은 랭킹 항목의 거울이면 그 랭킹 항목을 돌려준다.

    입력은 둘 다 LLM 구조화 출력이다(사용자 원문을 읽지 않는다). 거울 조건: 비교 값이 없고,
    ① 같은 지표가 랭킹에 있으며 방향이 어긋나지 않거나(연산자 없음·랭킹 방향 미지정은 어긋남
    없음) ② 계열(class.*) 껍데기인데 인용이 이름으로 부른 지원 지표가 전부 랭킹에 있는 경우.
    """
    if cond.value is not None:
        return None
    by_metric = {}
    for rank in ranking:
        by_metric.setdefault(_ranking_id(rank.metric), rank)
    rank = by_metric.get(_ranking_id(cond.factor))
    if rank is not None:
        if cond.operator in _LOWER_OPERATORS and rank.direction == "top":
            return None
        if cond.operator in _HIGHER_OPERATORS and rank.direction == "bottom":
            return None
        return rank
    if cond.operator is not None or not str(cond.factor).startswith("class."):
        return None
    # 계열(class.*) 껍데기 — 인용이 이름으로 부른 지원 지표가 전부 랭킹에 있으면 같은
    # 표현의 거울이다(120B 실측: '…종합한 품질 점수'가 품질 묶음 랭킹과 '어떤 퀄리티
    # 지표를 쓸까요?' 계열 질문 양쪽으로 나갔다). 인용↔레지스트리 대조, 원문 미사용.
    ranked = set(by_metric)
    named = {n for n in factor_ids_named_in(cond.source_text or "")
             if REGISTRY.get(n) is not None and REGISTRY[n].supported != "UNSUPPORTED"}
    # 부분 문자열 별칭('영업이익률' 안의 '영업이익')이 섞이므로 전부 포함 대신
    # 랭킹 지표 둘 이상을 부르면 거울로 본다.
    if named and (named <= ranked or len(named & ranked) >= 2):
        return next(iter(by_metric.values()))
    return None


def carry_approximation(cond, rank) -> None:
    """거울로 걷는 조건의 인용이 **다른 지표를 이름으로 불렀다면**(FCF Yield → FCF 마진 대체)
    그 사실을 랭킹 항목으로 옮긴다 — 조건이 사라지면 대체 안내(근사 반영)도 함께 사라져
    조용한 대체가 되기 때문이다. 인용↔factor 대조(LLM 출력끼리)이며 원문을 읽지 않는다."""
    if rank.approximated or not cond.source_text:
        return
    spec = resolve(cond.factor)
    named = factor_ids_named_in(cond.source_text)
    if spec is not None and named and spec.id not in with_same_name_variants(named):
        rank.approximated = True
        if not rank.source_text:
            rank.source_text = cond.source_text



# 산정 기간(lookback_days)이 의미 있는 가격 산출 랭킹 — 완결성 검증이 이 지표에만 산정 기간을
# 묻는다(completeness_validator ④-0). 재무 지표의 period(예: 3년 평균)는 거래일 산정 기간이
# 아니므로 옮기지 않는다.
_LOOKBACK_RANKING_METRICS = frozenset({
    "ranking.volatility", "ranking.return", "ranking.relative_return",
})


def carry_lookback(cond, rank) -> None:
    """거울로 걷는 조건이 산정 기간을 담고 있었다면 랭킹 항목으로 옮긴다.

    2026-09-20 실측(120B): '최근 60일 주가 변동성이 낮은'을 값 없는 조건(period=60)과 랭킹
    (기간 없음) 양쪽에 냈고, 거울 정리가 조건을 걷으며 60을 버려 "변동성 산정 기간을 며칠로
    할까요?"가 사용자가 이미 말한 값을 다시 물었다. 둘 다 LLM 구조화 출력이며 원문을 읽지
    않는다 — 조건→랭킹 이동 분기(아래 ranking 바인딩)와 같은 자리 배정이다.
    """
    if rank.lookback_days is not None or rank.metric not in _LOOKBACK_RANKING_METRICS:
        return
    lookback = cond.parameters.get("lookback_days") or cond.parameters.get("period")
    if lookback:
        rank.lookback_days = int(lookback)


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
            concept = concept_spec(cond.factor)
            if concept is not None and concept.expansion:
                # 합성 개념 결정적 전개(Phase C, 프롬프트 3.0) — LLM은 관용 표현을
                # 개념 ID로만 착지시키고(골든크로스 → concept.golden_cross), 연산자·
                # 정본 기간(5/20)의 조립은 여기서 선언대로 물질화한다. 연산자는 선언이
                # 정본이라 LLM 출력을 덮어쓰고(골든크로스는 crosses_above다 — 드리프트
                # 정규화), 파라미터는 **사용자가 말한 값이 우선**이며 빈 자리만 채운다.
                # 전개 후에는 일반 잎 경로(canonical 정규화·지원 판정)로 계속 간다.
                exp = concept.expansion
                before = (cond.operator, dict(cond.parameters))
                cond.factor = exp["factor"]
                if exp.get("operator"):
                    cond.operator = exp["operator"]
                for pname, pvalue in (exp.get("default_parameters") or {}).items():
                    if cond.parameters.get(pname) is None:
                        cond.parameters[pname] = pvalue
                # 전개 대상 잎에 선언되지 않은 파라미터는 개념 계약 밖이다 — 정리한다.
                # 단 값이 엔진 고정값(fixed_parameters, 예: MACD 12/26/9)과 다르면
                # 사용자가 커스텀 기간을 말한 것이므로 조용히 버리지 않고 안내한다
                # (침묵 왜곡 방지). 고정값과 같으면 의미 손실이 0이라 안내하지 않는다
                # (9B가 고정 기본값을 습관적으로 echo하는 드리프트 — 2.7부터 실측).
                target_spec = REGISTRY.get(exp["factor"])
                allowed_params = set(target_spec.parameters) if target_spec else set()
                fixed = concept.fixed_parameters or {}
                custom_dropped = False
                for pname in [p for p in cond.parameters if p not in allowed_params]:
                    pvalue = cond.parameters.pop(pname)
                    if pvalue is not None and fixed.get(pname) != pvalue:
                        custom_dropped = True
                if custom_dropped:
                    warnings.append(
                        f"'{concept.name}'의 기간은 커스텀이 지원되지 않아 표준 설정으로 "
                        "실행됩니다 — 말씀하신 기간 값은 반영되지 않았어요."
                    )
                ontology_logger.info(
                    "개념 전개 | %s 조건 %s(%s) → factor=%s operator=%s(LLM=%s) "
                    "parameters=%s(LLM=%s) 커스텀기간드롭=%s",
                    role, concept.name, concept.id, cond.factor, cond.operator,
                    before[0], cond.parameters, before[1], custom_dropped,
                )
            if is_class_id(cond.factor):
                # 분류(클래스) 발화 — 사용자가 "모멘텀 지표 하나"처럼 계열만 말해
                # LLM이 온톨로지 분류 ID를 낸 조건(프롬프트 2.9 계약). 오류·미지원이
                # 아니라 **선택 대기**다: completeness_validator가 구체 지표 되묻기를
                # 만들고, compile_partial이 pending_conditions로 제외한다.
                ontology_logger.info(
                    "분류 발화 통과(선택 대기) | %s 조건 factor=%s 원문=%r",
                    role, cond.factor, cond.source_text,
                )
                kept.append(cond)
                continue
            spec = resolve(cond.factor)
            if spec is None:
                # 안내에는 **사용자 표현**을 담는다 — LLM이 지어낸 내부 식별자
                # (concept.time_based_exit 등)를 그대로 인용하면 사용자가 쓴 적 없는
                # 영문 필드 경로가 화면에 나간다(내부명 노출 금지, 레드팀 QA 20-5 —
                # 미지원 랭킹 기준과 같은 계약). 식별자는 로그에만 남긴다.
                quoted = (cond.source_text or "").strip()
                label = quoted or (
                    ui_language.msg("알 수 없는 지표", "an unrecognized indicator")
                    if _is_internal_factor_name(cond.factor) else cond.factor
                )
                unsupported.append(label)
                errors.append(f"{role} 조건 '{label}'은(는) 알 수 없는 지표입니다")
                ontology_logger.info(
                    "미해석 factor | %s 조건 factor=%s 원문=%r", role, cond.factor, cond.source_text,
                )
                kept.append(cond)
                continue
            cond.factor = spec.id
            if spec.id in ("fundamental.trading_value", "technical.trading_value") \
                    and cond.value is None and cond.parameters.get("period") is not None:
                # 금액 없이 평균 기간만 실린 거래대금 조건은 '자기 N일 평균과 비교'의 옛 자리다
                # (실측 2026-09-16, '최근 거래대금이 30일 평균보다 높은' → trading_value
                # period=30 value=null). 금액 임계 지표는 기간 파라미터를 쓰지 않으므로 정본인
                # 거래대금 배수(v16.13)로 지표만 옮긴다 — 값·기간·연산자는 그대로이고 표기만
                # 보고 결정하는 정규화다(원문을 읽지 않는다). 금액이 인용에 있으면 앞 단계
                # (primary ④ 금액 검산)가 value를 채워 이 분기에 오지 않는다.
                ontology_logger.info(
                    "거래대금 배수 정본 착지 | %s 조건 %s(period=%s) → trading_value_ratio 원문=%r",
                    role, spec.id, cond.parameters.get("period"), cond.source_text,
                )
                spec = resolve("technical.trading_value_ratio")
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
                # 백분위 드리프트 실측(2026-08-10, '변동성 하위 10%만 편입'): LLM이 편입
                # 비율을 portfolio.selection_percent가 아니라 랭킹 조건의 value(unit
                # percentile)로 실어 보낸다 — 조건은 여기서 이동·소거되므로 그대로 두면
                # 사용자가 말한 편입 규모가 조용히 사라진다. unit이 백분위임이 명시된
                # 값만, 편입 규모가 비어 있을 때만 selection_percent로 옮긴다(자리
                # 배정이지 재해석이 아니다). 맨 값(unit 없음)은 연환산 % 임계값과 구별할
                # 수 없어 옮기지 않는다.
                if (
                    cond.value is not None
                    and str(cond.unit or "").strip().lower() == "percentile"
                    and strategy.portfolio.selection_percent is None
                    and strategy.portfolio.selection_count is None
                ):
                    strategy.portfolio.selection_percent = float(cond.value)
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
            # 임계값 비교만 허용하는 지표(RSI·ADX·CCI 등 오실레이터)에 9B가 교차 연산자를
            # 낸다("ADX 20 하향 이탈" → crosses_below, 2026-09-02 전수 QA 실측). 재무 지표의
            # 교차 연산자는 종전대로 오류다(기술 지표 전용 정규화). 프롬프트
            # 5-5가 지시하는 표현은 부등호이고 엔진도 수준 비교만 표현하므로, 교차 방향을
            # 같은 방향의 부등호로 정규화한다(LLM 출력 표기 정규화 — 원문을 읽지 않는다).
            # 종전엔 여기서 오류만 남기고 컴파일러가 연산자·값을 조용히 버려 엔진 기본값
            # (ADX ≥ 25)으로 백테스트됐다 — 사용자가 말한 값이 반대 방향 기본값으로 바뀐다.
            if spec.id == "technical.volume_spike" and cond.value is not None:
                # 배수가 실린 거래량 조건('평소보다 1.5배')의 정본은 v16.10부터 거래량 배수
                # 지표(technical.volume_ratio, 당일 거래량 ÷ 직전 N일 평균)다. LLM이 옛 자리
                # (volume_spike + value)에 내면 지표만 옮긴다 — 값·기간은 그대로이고 표기만
                # 보고 결정하는 정규화다(원문을 읽지 않는다). 연산자가 없으면 '이상'.
                ontology_logger.info(
                    "거래량 배수 정본 착지 | %s 조건 volume_spike(value=%s) → volume_ratio 원문=%r",
                    role, cond.value, cond.source_text,
                )
                spec = resolve("technical.volume_ratio")
                cond.factor = spec.id
                if cond.operator not in _COMPARISON_OPS:
                    cond.operator = ">="
            elif spec.id == "technical.volume_spike" and cond.operator in _COMPARISON_OPS:
                # 값 없는 부등호('거래대금이 늘어난' → volume_spike '>')는 배수가 아니라 근사
                # 표기 드리프트다 — 연산자만 걷는다(OBV 교차에는 연산자가 없다). 종전엔 이
                # 연산자가 '허용되지 않는 연산자' 오류로 조건을 통째로 탈락시켰다.
                cond.operator = None
            if spec.category == "technical" and spec.allowed_operators == _COMPARISON_OPS \
                    and cond.operator in _CROSS_TO_COMPARISON:
                cond.operator = _CROSS_TO_COMPARISON[cond.operator]
            if cond.operator is not None and spec.allowed_operators \
                    and cond.operator not in spec.allowed_operators:
                errors.append(
                    f"'{spec.display_name}'에 연산자 '{cond.operator}'은(는) 허용되지 않습니다 "
                    f"(허용: {', '.join(spec.allowed_operators)})"
                )
            # 교차 방향과 역할의 모순 — 엔진은 이동평균·EMA·MACD의 교차 방향을 signal_type으로만
            # 정한다(매수=상향, 매도=하향). 매수 칸의 crosses_below·매도 칸의 crosses_above는
            # 표현할 수 없고, 종전 컴파일러는 연산자를 읽지 않아 "20일선 이탈 시 청산"이 매수
            # 칸에 앉으면 상향 돌파 매수로 조용히 뒤집혔다(2026-09-08 예시 81 실측). 위 청산
            # 역할 규칙과 같은 이유로 검증 단계에서 에러를 남긴다 — READY→전량 컴파일이
            # 전략 전체를 던지지 않고 부분 컴파일이 이 조건만 제외+안내로 흐르게.
            expected_cross = _ROLE_CROSS_DIRECTION.get(role)
            if spec.id in _DIRECTIONAL_CROSS_LEAVES and expected_cross is not None \
                    and cond.operator in ("crosses_above", "crosses_below") \
                    and cond.operator != expected_cross:
                errors.append(
                    f"{role} 조건 '{spec.display_name}'의 교차 방향 '{cond.operator}'은(는) "
                    f"{role} 신호로 표현할 수 없습니다 ({role}은 {expected_cross}만 가능)"
                )
        setattr(strategy, attr, _dedupe_identical_conditions(role, kept))

    kept_ranking = []
    # 같은 표현을 랭킹과 unsupported_features 양쪽에 낸 모순 출력(LLM ↔ LLM 표기 대조) —
    # 모델 스스로 표현할 수 없다고 한 개념이므로 랭킹을 만들지 않는다. 2026-09-19 실측:
    # '최근 3개월 실적 추정치 상향'이 미지원 보고와 동시에 시장 대비 수익률 랭킹으로 들어가
    # 사용자가 말하지 않은 선정 기준이 생겼다.
    _unsupported_quotes = {_compact_text(f) for f in (intent.unsupported_features or [])}
    for rank in strategy.ranking:
        if rank.source_text and _compact_text(rank.source_text) in _unsupported_quotes:
            continue
        spec = resolve(rank.metric)
        # 인용이 **미지원 개념만** 이름으로 부르는데 다른 지원 지표를 랭킹에 넣은 바꿔치기
        # (인용↔factor 대조 — 조건의 _substituted_factor와 같은 레인, LLM 출력끼리 비교).
        # 2026-09-19 실측 120B 2/3: '최근 3개월 실적 추정치 상향 여부' 인용으로 시장 대비
        # 수익률 랭킹을 만들고 미지원 보고도 하지 않았다 — 근사 안내로 넘길 대상이 아니라
        # 사용자가 말하지 않은 선정 기준이므로 제거하고 미지원으로 알린다.
        named = factor_ids_named_in(rank.source_text or "")
        if named and spec is not None and spec.id not in named and all(
            REGISTRY.get(n) is not None and REGISTRY[n].supported == "UNSUPPORTED" for n in named
        ):
            unsupported.append(rank.source_text)
            continue
        if spec is not None and spec.id in _RANKING_CANONICAL:
            # 조건 지표(technical.relative_return·technical.volatility)를 랭킹 자리에 낸 출력은
            # 랭킹 정본(ranking.relative_return — v16.10 종목 수익률 − 자기 시장 지수 순위 /
            # ranking.volatility — 저변동성 랭킹)으로 옮긴다(2026-09-14~19 실측: '최근 60일 변동성이
            # 낮은 종목'이 알 수 없는 랭킹 기준으로 버려졌다). 표기만 보고 옮기는 LLM 출력 정규화다.
            spec = resolve(_RANKING_CANONICAL[spec.id])
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
            # 미지원 랭킹 항목은 **제거**한다(진입 조건의 kept와 같은 계약) — 남겨 두면
            # 컴파일러가 모르는 지표를 임의 지표로 바꿔치는 폴백을 타서 사용자가 말하지
            # 않은 랭킹이 생긴다(2026-08-17 'composite_score' → 수익률 랭킹 둔갑 사고).
            # 미지원 보고에는 LLM이 지어낸 내부 식별자(metric 원문)를 담지 않는다 —
            # 그 문자열이 안내문에 그대로 노출됐다(내부명 노출 금지, 레드팀 QA 20-5).
            # 사용자 표현(source_text)이 있으면 그것을, 없으면 평이한 일반 표기를 쓴다.
            # 인용이 없으면: 레지스트리가 아는 미지원 개념은 그 표시명으로, 모르는 이름은 —
            # 1차가 이미 미지원 보고를 냈으면 그 보고가 같은 표현을 다룬다(2026-09-19 실측:
            # '실적 추정치 상향'이 보고와 '알 수 없는 랭킹 기준' 두 번 나갔다) — 일반 표기로.
            if rank.source_text:
                unsupported.append(rank.source_text)
            elif spec is not None and spec.supported == "UNSUPPORTED":
                unsupported.append(spec.display_name)
            elif not intent.unsupported_features:
                unsupported.append(
                    ui_language.msg("알 수 없는 랭킹 기준", "an unrecognized ranking metric"))
            errors.append(ui_language.msg(
                "랭킹 기준 '{name}'은(는) 지원되지 않습니다 "
                "(지원: 기간 수익률 랭킹, 재무 지표 랭킹 — 예: 영업이익률 상위, 여러 지표 순위 합산)",
                "The ranking metric '{name}' isn't supported "
                "(supported: period-return ranking and fundamental rankings — e.g. top operating "
                "margin, or a combined rank across several metrics)",
                name=rank.source_text or ui_language.msg("알 수 없는 지표", "an unrecognized metric"),
            ))
            continue
        rank.metric = spec.id
        kept_ranking.append(rank)
    strategy.ranking = kept_ranking

    # 랭킹으로 이미 표현된 지표를 **값 없는** 매수 조건으로 한 번 더 낸 껍데기
    # (2026-09-19 실측 120B: 품질 점수 5개 지표가 랭킹과 값 없는 조건 양쪽에 나와 "ROE 기준값을
    # 얼마로?"가 먼저 물어졌다. 같은 날 '낮은/높은' 방향 연산자(<=·>=)만 달고 값이 없는 껍데기는
    # 거울로 못 잡아 "EV/EBITDA 기준값을 얼마로?"가 물어졌다). 비교할 값이 없는 조건은 조건이
    # 아니고 개념은 랭킹이 보존한다 — 청산 미러 가드(_drop_mirrored_valueless_exits)와 같은
    # 구조 정리다.
    if kept_ranking:
        kept_conditions = []
        for c in strategy.entry_conditions:
            mirrored = ranking_mirrored_by(c, kept_ranking)
            if mirrored is None:
                kept_conditions.append(c)
                continue
            carry_approximation(c, mirrored)
            carry_lookback(c, mirrored)
        strategy.entry_conditions = kept_conditions

    # 유니버스별 팩터 검증 — ETF는 여러 기업을 묶은 상품이라 기업 재무지표를 조건으로 쓸
    # 수 없다(engine/universe_capabilities와 동일 계약). 조용히 제거하지 않고 오류+대안
    # 제안으로 사용자 확인을 받는다. 거래대금(trading_value)은 가격·거래량 파생이라 허용.
    if set(strategy.universe.markets) & {"ETF", "US_ETF"}:
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
        # 잔차 반전 시그널(v16.17)도 ETF에서 성립하지 않는다 — 회귀 설명변수인 소속 섹터가 없어
        # 전 종목이 NaN(후보 0)이 된다. 0거래 백테스트로 흘려보내지 않고 오류+제거+안내한다.
        for rank in strategy.ranking:
            if rank.metric == "ranking.residual_reversal":
                name = resolve(rank.metric).display_name
                etf_conflicts.append(name)
                unsupported.append(f"ETF 유니버스 × {name}")
                errors.append(
                    f"ETF는 소속 섹터가 없어 '{name}'(시장·섹터 회귀 잔차)을 사용할 수 없습니다"
                )
        strategy.ranking = [
            r for r in strategy.ranking
            if not r.metric.startswith("fundamental.") and r.metric != "ranking.residual_reversal"
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

    # ── 미국 시장 제약 (US 레인 Phase 2, 2026-08-25) ──
    # 엔진 US 레인이 지원하지 않는 조합을 컴파일 전에 명시적으로 걸러 되묻기/안내로
    # 보낸다 — 조용히 제거하지 않는다(엔진에서 늦게 터지면 원인 설명이 어려워진다).
    #
    # [지역 격리, 2026-08-26] /us 요청(표시 언어 en — 지역이 곧 언어)은 미국 시장
    # 전용이다: ① 한국 시장 명시는 거절 안내(조용한 제거 금지 — 접근 불가를 알린다)
    # ② 시장 미언급도 미국 문맥으로 보고 아래 US 제약·테마 전개를 적용한다(컴파일
    # 기본값도 S&P500 — strategy_compiler). markets를 여기서 채우지는 않는다 —
    # provenance(explicit_fields_from_spec)가 '사용자 명시'로 오인한다.
    _en_region = ui_language.get_ui_language() == "en"
    _kr_markets_named = set(strategy.universe.markets) - set(caps.US_MARKETS)
    if _en_region and _kr_markets_named:
        errors.append(ui_language.msg(
            "이 서비스는 미국 시장 전용입니다 — 한국 시장(코스피·코스닥·국내 ETF) "
            "백테스트는 한국 서비스에서 이용할 수 있어요. 미국 유니버스(S&P500·"
            "나스닥100·나스닥·다우·미국 전체·미국 ETF) 중 하나로 진행해 주세요.",
            "This service covers US markets only — Korean markets (KOSPI, KOSDAQ, "
            "Korean ETFs) are available on the Korean service. Please choose a US "
            "universe: S&P 500, Nasdaq-100, Nasdaq, Dow 30, the entire US market, "
            "or US ETFs.",
        ))
    _us_markets = set(strategy.universe.markets) & set(caps.US_MARKETS)
    if _us_markets or (_en_region and not strategy.universe.markets):
        _kr_markets = set(strategy.universe.markets) - set(caps.US_MARKETS)
        if _kr_markets:
            # US 블록의 안내는 ui_language.msg로 — errors는 되묻기 문장에 이어 붙거나 목록이
            # 섞여 나가므로 프론트 사전(정확 일치)으로는 옮길 수 없다(위 지역 거절과 같은 레인).
            errors.append(ui_language.msg(
                "한국 시장과 미국 시장은 한 전략에서 혼합할 수 없습니다 — "
                "어느 시장으로 백테스트할지 선택해 주세요",
                "Korean and US markets can't be mixed in one strategy — "
                "please choose which market to backtest",
            ))
        # 시장 대비 초과수익률(technical.relative_return)은 한국 지수(코스피·코스닥) 시계열로만
        # 계산된다 — 미국 지수 시계열은 아직 수집하지 않는다(별도 과제). 조용히 제거하면
        # 엔진이 NaN 조건으로 0거래를 내므로, ETF×재무 랭킹과 같은 계약으로 오류+제거+안내한다.
        for _role, _attr in (("진입", "entry_conditions"), ("청산", "exit_conditions")):
            _kept_conds = []
            for _cond in getattr(strategy, _attr):
                if _cond.factor != "technical.relative_return":
                    _kept_conds.append(_cond)
                    continue
                _spec = resolve(_cond.factor)
                _name = _spec.display_name if _spec else _cond.factor
                unsupported.append(f"미국 시장 × {_name}")
                errors.append(ui_language.msg(
                    "미국 시장에서는 {role} 조건 '{name}'을(를) 아직 사용할 수 없습니다 "
                    "(미국 지수 시계열 미수집) — 기간 수익률 랭킹 등으로 바꿔 주세요",
                    "The {role} condition '{name}' isn't available for US markets yet "
                    "(US index history isn't collected) — try a period-return ranking instead",
                    role=ui_language.msg(_role, "entry" if _role == "진입" else "exit"), name=_name,
                ))
            setattr(strategy, _attr, _kept_conds)
        _kept_ranks = []
        for _rank in strategy.ranking:
            _rspec = resolve(_rank.metric)
            if _rspec is None or _rspec.id not in ("ranking.relative_return",
                                                   "ranking.residual_reversal"):
                _kept_ranks.append(_rank)
                continue
            unsupported.append(f"미국 시장 × {_rspec.display_name}")
            errors.append(ui_language.msg(
                "미국 시장에서는 '{name}'을(를) 아직 사용할 수 없습니다 "
                "(미국 지수 시계열 미수집) — 기간 수익률 랭킹으로 바꿔 주세요",
                "'{name}' isn't available for US markets yet "
                "(US index history isn't collected) — try a period-return ranking instead",
                name=_rspec.display_name,
            ))
        strategy.ranking = _kept_ranks
        if len(_us_markets) > 1:
            errors.append(ui_language.msg(
                "미국 시장/지수는 한 전략에 하나만 지정할 수 있습니다 "
                "(S&P500·나스닥100·나스닥·다우·미국 전체·미국 ETF 중 하나)",
                "Only one US market or index can be set per strategy "
                "(S&P 500, Nasdaq-100, Nasdaq, Dow 30, the entire US market, or US ETFs)",
            ))
        if strategy.universe.sectors:
            # 미국 테마 카탈로그(registry) 해석 — 카탈로그 정본 테마는 '테마 유래 지정
            # 종목'으로 전개한다(구성 티커 → universe.symbols, 출처는 theme 표기 계약).
            # 카탈로그 밖 테마만 명시적 미지원 안내(조용한 제거 금지).
            from engine.universe_pit import (
                resolve_us_company_related,
                resolve_us_theme,
                us_industry_label,
            )

            _kept_sectors: List[str] = []
            _us_theme_resolved = False
            for _sector_term in strategy.universe.sectors:
                # [축 순서] 분류(정본) → 카탈로그·시드 테마 → 공시 학습. 업종 이름이면
                # 업종 분류가 답한다 — 시드의 산업형 테마는 표본 수준이라 실측에서
                # 'airlines' 4곳 vs 분류 18곳이었다. 분류는 유니버스 **필터**이므로
                # 종목으로 전개하지 않고 표현을 남겨 컴파일러가 us_industry로 옮긴다.
                if us_industry_label(_sector_term) is not None:
                    _kept_sectors.append(_sector_term)
                    continue
                # 테마 축이 비면 회사 앵커 축('X 관련주')을 본다 — **학습분 결정론
                # 조회만** 한다(그라운딩 검색은 해석 체인 소관이다. 검증기는 네트워크·
                # LLM을 부르지 않는다). 이미 아는 집합까지 미지원으로 알리면 모순이다.
                _theme = resolve_us_theme(_sector_term)
                _axis = "theme_catalog"
                if _theme is None:
                    _theme = resolve_us_company_related(_sector_term)
                    _axis = "company_related"
                if _theme is None:
                    _kept_sectors.append(_sector_term)
                    continue
                _us_theme_resolved = True
                _theme_name, _theme_symbols = _theme
                for _sym in _theme_symbols:
                    if _sym not in strategy.universe.symbols:
                        strategy.universe.symbols.append(_sym)
                if not strategy.universe.theme:
                    strategy.universe.theme = _theme_name
                    strategy.universe.theme_source = _axis
            if _us_theme_resolved:
                # 상류(한국 테마 전개)가 같은 테마어를 한국 종목으로 먼저 확장했을 수 있다
                # ("크립토" → 미국 6티커 + 한국 61코드 실측, 2026-08-26). 미국 시장 문맥의
                # 테마에서 한국 코드(숫자 시작)는 시스템이 넣은 잘못된 시장의 전개이지
                # 사용자 지정이 아니므로 제거한다 — 두면 한·미 혼합으로 엔진이 거절한다.
                _kr_expanded = [s for s in strategy.universe.symbols
                                if str(s)[:1].isdigit()]
                if _kr_expanded:
                    strategy.universe.symbols = [
                        s for s in strategy.universe.symbols if not str(s)[:1].isdigit()
                    ]
                    warnings.append(ui_language.msg(
                        "미국 테마 유니버스에서 한국 종목 전개 {n}건을 제외했습니다(미국 시장 전략).",
                        "Excluded {n} Korean stocks expanded from the theme (US market strategy).",
                        n=len(_kr_expanded),
                    ))
            strategy.universe.sectors = _kept_sectors
            # 분류 라벨은 필터로 살아남는다 — 미지원 안내 대상은 '분류도 테마도 아닌' 표현뿐.
            _unknown_sectors = [t for t in _kept_sectors if us_industry_label(t) is None]
            if _unknown_sectors:
                unsupported.append("미국 유니버스 × 업종 필터")
                errors.append(ui_language.msg(
                    "미국 유니버스의 업종/테마 필터 중 카탈로그에 없는 항목은 아직 "
                    "지원되지 않습니다: {items}",
                    "Industry/theme filters not in the US catalog aren't supported yet: {items}",
                    items=", ".join(_unknown_sectors),
                ))
                strategy.universe.sectors = [
                    t for t in _kept_sectors if us_industry_label(t) is not None
                ]
        if strategy.universe.new_listing_only:
            unsupported.append("미국 유니버스 × 신규 상장 종목")
            errors.append(ui_language.msg(
                "미국 유니버스에는 신규 상장(IPO) 제한을 아직 적용할 수 없습니다",
                "A new-listing (IPO) filter can't be applied to US universes yet",
            ))
            strategy.universe.new_listing_only = False
            strategy.universe.listing_from = None
            strategy.universe.listing_to = None
        # AI 예측 신호는 한국 시장 데이터로 학습된 모델 — 미국 유니버스에서 미지원
        # (engine/backtest_engine.py US 분기의 거절과 동일 계약, 여기서 먼저 안내).
        _ai_used = [
            cond for attr in ("entry_conditions", "exit_conditions")
            for cond in getattr(strategy, attr)
            if cond.factor in ("technical.ai_model", "technical.ai_drop_model")
        ]
        if _ai_used:
            unsupported.append("미국 유니버스 × AI 예측 신호")
            errors.append(ui_language.msg(
                "AI 예측 신호는 한국 시장 데이터로 학습된 모델이라 "
                "미국 유니버스에서는 사용할 수 없습니다",
                "The AI prediction signal is a model trained on Korean market data "
                "and isn't available for US universes",
            ))
            strategy.entry_conditions = [
                c for c in strategy.entry_conditions
                if c.factor not in ("technical.ai_model", "technical.ai_drop_model")
            ]
            strategy.exit_conditions = [
                c for c in strategy.exit_conditions
                if c.factor not in ("technical.ai_model", "technical.ai_drop_model")
            ]

    # 유니버스 섹터 — 정본 섹터명 화이트리스트로 판정(조용한 왜곡 방지).
    # [축 구분, FR-STR-074 ⑩] 이 화이트리스트는 **한국 섹터 정본**이다 — 미국 문맥에서는
    # 위 US 블록이 이미 분류/테마를 갈라 두었으므로 여기서 다시 재단하지 않는다(미국
    # 분류 라벨 'Airlines'가 "지원 섹터 목록에 없습니다"로 거절되던 경로).
    if strategy.universe.sectors and not (_us_markets or (_en_region and not strategy.universe.markets)):
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
        raw_weighting = strategy.portfolio.weighting
        weighting = caps.normalize_weighting(raw_weighting)
        if weighting is None:
            unsupported.append(f"비중 방식 '{raw_weighting}'")
            errors.append(
                f"비중 방식 '{raw_weighting}'은(는) 지원되지 않습니다 "
                "(지원: 동일 비중, 변동성 역비중)"
            )
            strategy.portfolio.weighting = None
        else:
            strategy.portfolio.weighting = weighting
            if raw_weighting.strip().lower().replace(" ", "_") in caps.RISK_PARITY_WEIGHTING_ALIASES:
                # 판정 입력은 LLM이 낸 비중 방식 라벨(표기 대조) — 원문을 읽지 않는다.
                warnings.append(ui_language.msg(
                    "리스크 패리티는 변동성 역비중(최근 변동성이 낮을수록 큰 비중, 종목 간 상관관계 "
                    "미반영)으로 가깝게 반영했어요.",
                    "Risk parity was approximated with inverse-volatility weighting (lower recent "
                    "volatility gets a larger weight; correlations between stocks are not used).",
                ))
        if strategy.portfolio.weighting != "inverse_volatility":
            strategy.portfolio.weighting_lookback_days = None
    else:
        strategy.portfolio.weighting_lookback_days = None

    # 잔차 반전 시그널(v16.17)은 단독 랭킹 전용이다 — 엔진의 복합 순위 합산 구성 지표가 아니다.
    # 다른 순위 기준과 함께 오면 시그널 쪽을 빼고 알린다(조용한 합산·조용한 소실 둘 다 금지).
    if len(strategy.ranking) >= 2 and any(
            r.metric == "ranking.residual_reversal" for r in strategy.ranking):
        _residual_name = resolve("ranking.residual_reversal").display_name
        unsupported.append(f"복합 순위 × {_residual_name}")
        errors.append(ui_language.msg(
            "'{name}'은(는) 다른 순위 기준과 합산할 수 없습니다 — 단독 순위 기준으로만 지원됩니다",
            "'{name}' can't be combined with other ranking criteria — it is only supported "
            "as a standalone ranking",
            name=_residual_name,
        ))
        strategy.ranking = [r for r in strategy.ranking
                            if r.metric != "ranking.residual_reversal"]

    # 12-1 모멘텀 제외 기간(v16.14)은 수익률 랭킹에서만 성립한다 — 다른 지표에 붙은 값은
    # 표현할 자리가 없으므로 오류로 알리고 버린다(조용한 적용·조용한 소실 둘 다 금지).
    for rank in strategy.ranking:
        if rank.skip_days is not None and rank.metric != "ranking.return":
            errors.append(ui_language.msg(
                "최근 기간 제외는 수익률 랭킹에서만 지원됩니다",
                "Excluding the most recent period is only supported for return rankings",
            ))
            rank.skip_days = None

    # 시장 국면 필터(v16.14) — 한국 지수(KOSPI·KOSDAQ)만 지원한다. 미국 전략의 지수 국면은
    # 지수 시계열 파이프라인이 아직 없어 미지원으로 알린다(조용한 제거 금지).
    mf = strategy.market_filter
    if mf is not None:
        if set(strategy.universe.markets) & set(caps.US_MARKETS) or ui_language.get_ui_language() == "en":
            unsupported.append(mf.source_text or ui_language.msg(
                "시장 지수 이동평균 필터", "a market-index moving-average filter"))
            errors.append(ui_language.msg(
                "미국 지수 기준 시장 국면 필터는 아직 지원되지 않습니다",
                "A market regime filter on US indexes isn't supported yet",
            ))
            strategy.market_filter = None
        elif mf.exposure_pct is not None and mf.exposure_pct >= 100:
            # 100%는 '줄이지 않음'이라 필터가 아니다 — 값을 비워 되묻는다.
            mf.exposure_pct = None

    if strategy.portfolio.rebalance_frequency is not None:
        freq = caps.normalize_rebalance_frequency(strategy.portfolio.rebalance_frequency)
        if freq is None:
            errors.append(
                f"리밸런싱 주기 '{strategy.portfolio.rebalance_frequency}'을(를) 해석할 수 없습니다 "
                f"(지원: {', '.join(caps.SUPPORTED_REBALANCE_FREQUENCIES)})"
            )
            # 오류만 내고 값을 두면 부분 컴파일이 ParsedStrategy Literal에서 크래시해
            # 해석 실패(빈 전략)로 둔갑한다(2026-08-26 실측, /us 영어 게이트 41 —
            # "every 2 weeks"→"biweekly"). 위 오류가 안내를 담당하므로 조용한 소실이
            # 아니다. 비슷한 지원 값으로 바꿔치지는 않는다(2주≠2개월).
            strategy.portfolio.rebalance_frequency = None
        else:
            strategy.portfolio.rebalance_frequency = freq

    if strategy.portfolio.rebalance_method is not None \
            and strategy.portfolio.rebalance_method not in caps.SUPPORTED_REBALANCE_METHODS:
        errors.append(
            f"리밸런싱 방식 '{strategy.portfolio.rebalance_method}'을(를) 해석할 수 없습니다 "
            f"(지원: 종목 교체(reconstitute), 비중 조정(weights_only))"
        )
        # 주기와 같은 계약 — 값을 남기면 부분 컴파일이 ParsedStrategy Literal에서 크래시해
        # 해석 실패(빈 전략)로 둔갑한다. 오류가 안내를 담당하므로 조용한 소실이 아니다.
        strategy.portfolio.rebalance_method = None

    if strategy.backtest.period is not None \
            and strategy.backtest.period not in caps.SUPPORTED_BACKTEST_PERIODS:
        errors.append(f"백테스트 기간 '{strategy.backtest.period}'은(는) 지원되지 않습니다")

    if strategy.risk_management.max_position_weight is not None:
        unsupported.append("종목당 최대 비중 제한")
        errors.append("종목당 최대 비중 제한은 아직 엔진에서 지원되지 않습니다 (동일비중만 지원)")

    return errors, warnings, unsupported, fixes
