"""Strategy Completeness Validator — 누락 필수값 탐지 + 되묻기 질문 생성.

사용자가 말하지 않은 값을 조용히 기본값으로 확정하지 않는다. 가능한 동작은
① 질문 ② 추천값 제시(확인 필요) ③ 사용자가 자동 설정을 명시 허용한 경우에만
기본값 — 이 셋뿐이다. 질문은 실제 전략 실행에 필요한 것만, 중요한 순서로
최대 MAX_QUESTIONS_PER_TURN개까지 생성한다.
"""

from __future__ import annotations

from datetime import date
from typing import List, Tuple

from strategy_conversation.interpreter.models import (
    ClarificationQuestion,
    StrategyIntent,
)
from strategy_conversation.registry.indicator_registry import REGISTRY

MAX_QUESTIONS_PER_TURN = 3

_COMPARISON_OPS = ("<", "<=", ">", ">=")

# 되묻기 질문에 내부 파라미터 이름 대신 노출할 사용자 친화 라벨
_PARAM_LABELS = {
    "short_period": "단기 기간",
    "long_period": "장기 기간",
    "period": "기간",
    "lookback_period": "기준 기간",
    "lookback_days": "조회 기간",
    "threshold": "기준값",
}


def validate_completeness(intent: StrategyIntent) -> Tuple[List[str], List[ClarificationQuestion]]:
    """(missing_fields, clarification_questions)를 반환한다.

    질문은 진행 골격 순(유니버스 → 진입 조건 → 청산/보유 → 포트폴리오)으로 생성하고
    MAX_QUESTIONS_PER_TURN개로 자른다(missing_fields는 전부 보고).
    """
    missing: List[str] = []
    questions: List[ClarificationQuestion] = []

    if intent.intent not in ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY"):
        return missing, questions

    strategy = intent.strategy
    if strategy is None:
        if intent.intent == "CREATE_STRATEGY":
            missing.append("strategy")
        return missing, questions

    # ① 유니버스 제한의 대상 시기 — "신규 상장 종목"에는 시기가 없으므로 날짜를 지어내지
    # 않고 되묻는다(FR-STR-073). 개념은 universe.new_listing_only가 보존한다. 진행 골격
    # 순서(유니버스 → 매수 조건)를 따라 진입 조건 질문보다 먼저 낸다.
    if (strategy.universe.new_listing_only
            and strategy.universe.listing_from is None
            and strategy.universe.listing_to is None):
        last_year = date.today().year - 1
        missing.append("strategy.universe.listing_from")
        questions.append(ClarificationQuestion(
            field="strategy.universe.listing_from",
            question="어느 시기에 상장한 종목을 대상으로 할까요?",
            recommended_value=f"{last_year}년 이후 상장",
            recommendation_reason=f"{last_year}년 이후 상장 종목을 시작값으로 사용할 수 있습니다",
        ))

    # ② 진입 메커니즘 존재 여부 (조건 또는 랭킹)
    if intent.intent == "CREATE_STRATEGY" \
            and not strategy.entry_conditions and not strategy.ranking:
        missing.append("strategy.entry_conditions")
        questions.append(ClarificationQuestion(
            field="strategy.entry_conditions",
            question="어떤 조건으로 종목을 선택할까요? (예: 재무 지표 기준, 기술적 신호, 기간 수익률 상위)",
        ))

    # ③ 조건별 필수값 — 비교 연산 조건인데 임계값이 없으면 질문(추천값은 Registry에서)
    for role, path, conditions in (
        ("진입", "entry_conditions", strategy.entry_conditions),
        ("청산", "exit_conditions", strategy.exit_conditions),
    ):
        for i, cond in enumerate(conditions):
            spec = REGISTRY.get(cond.factor)
            if spec is None or spec.supported == "UNSUPPORTED":
                continue
            field_base = f"strategy.{path}[{i}]"
            # 자기 선(線)을 둘 가진 지표(이동평균·EMA)에서 비교 연산자는 **두 선의 관계**를
            # 뜻한다("5일 EMA가 20일 EMA 위에 있으면") — 사용자가 줄 숫자 임계값이 없고,
            # 컴파일러도 값 없이 mode(above/below)로 바인딩한다(_compile_technical).
            # 이걸 임계값 누락으로 보면 조건이 값 미정으로 제외돼 사용자가 명시한 진입·청산
            # 규칙이 통째로 사라진다(2026-08-05 전수 QA 치명 2건: EMA 추세 진입/청산).
            compares_own_lines = {"short_period", "long_period"} <= set(spec.parameters)
            needs_value = not compares_own_lines and (
                cond.operator in _COMPARISON_OPS
                or (cond.operator is None and spec.category != "event"
                    and spec.value_type != "event" and not spec.parameters)
                or (cond.operator is None and _COMPARISON_OPS == spec.allowed_operators)
            )
            if needs_value and cond.value is None:
                missing.append(f"{field_base}.value")
                unit = {"percent": "%", "ratio": "배", "억원": "억원", "point": ""}.get(
                    spec.value_type or "", ""
                )
                rec = spec.recommended_value
                questions.append(ClarificationQuestion(
                    field=f"{field_base}.value",
                    question=f"{role} 조건의 {spec.display_name} 기준값을 얼마로 할까요?",
                    recommended_value=rec,
                    recommendation_reason=(
                        f"일반적인 시작값으로 {rec:g}{unit}을(를) 사용할 수 있습니다" if rec is not None else None
                    ),
                ))
            # 이벤트형 지표의 필수 파라미터 (예: 크로스오버 단기/장기)
            for pname, pspec in spec.parameters.items():
                if pspec.required and cond.parameters.get(pname) is None:
                    missing.append(f"{field_base}.parameters.{pname}")
                    questions.append(ClarificationQuestion(
                        field=f"{field_base}.parameters.{pname}",
                        question=f"{spec.display_name}의 {_PARAM_LABELS.get(pname, pname.replace('_', ' '))}을(를) 몇으로 할까요?",
                        recommended_value=pspec.default,
                        recommendation_reason=(
                            f"일반적으로 {pspec.default:g}을(를) 사용합니다" if pspec.default is not None else None
                        ),
                    ))

    # ④ 랭킹 전략은 회전 규칙이 필요 — 종목 수·리밸런싱 주기
    #
    # 지정 종목 전략은 '몇 종목을 고를지'가 성립하지 않는다 — 종목이 이미 정해져 있다
    # (2026-07-31 실측: '삼성전자만으로 전략'에 "상위 몇 종목을 선택할까요?"가 나갔다.
    # 이 검증기가 유니버스를 보지 않아 KOSPI·ETF·단일 종목에 **바이트 동일한** 질문을
    # 냈다). 진행 골격의 NOT_APPLICABLE(validation/field_state.py)이 같은 판정을 이미
    # 계산하지만 그건 표시 전용이라 되묻기 게이트가 소비하지 않는다 — 여기서 묻지 않는
    # 것이 되묻기 쪽의 대응이다. FR-STR-068(지정 종목 '최대 보유 N종목' 표시 금지)과
    # 같은 계약이다.
    if strategy.ranking:
        if strategy.portfolio.selection_count is None and not strategy.universe.symbols:
            missing.append("strategy.portfolio.selection_count")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.selection_count",
                question="상위 몇 종목을 선택할까요?",
                recommended_value=10,
                recommendation_reason="일반적인 시작값으로 10종목을 사용할 수 있습니다",
            ))
        if strategy.portfolio.rebalance_frequency is None:
            missing.append("strategy.portfolio.rebalance_frequency")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.rebalance_frequency",
                question="리밸런싱은 얼마나 자주 할까요? (매월/분기/매년)",
                recommended_value="monthly",
                recommendation_reason="랭킹 전략은 월간 리밸런싱을 시작값으로 흔히 사용합니다",
            ))

    # ⑤ 청산 규칙 부재 — 진입 조건형 전략인데 청산·보유기간·리밸런싱·리스크가 모두 없으면
    risk = strategy.risk_management
    has_exit_rule = bool(
        strategy.exit_conditions
        or strategy.portfolio.hold_period_days
        or strategy.portfolio.rebalance_frequency
        or strategy.ranking
        or risk.stop_loss or risk.take_profit or risk.trailing_stop or risk.max_mdd_limit
    )
    if strategy.entry_conditions and not has_exit_rule:
        # 재무 스크리닝만 있는 전략은 정기 리밸런싱 회전이 자연스러운 완성형이다 —
        # 오류가 아니라 질문으로 청산 방식을 확정받는다
        missing.append("strategy.exit_conditions")
        questions.append(ClarificationQuestion(
            field="strategy.exit_conditions",
            question="청산 규칙이 없습니다. 어떻게 매도할까요? (보유 기간 제한, 정기 리밸런싱, 손절/익절 등)",
            recommended_value="monthly",
            recommendation_reason="스크리닝 전략은 정기 리밸런싱(매월)으로 회전하는 방식을 흔히 사용합니다",
        ))

    return missing, questions[:MAX_QUESTIONS_PER_TURN]
