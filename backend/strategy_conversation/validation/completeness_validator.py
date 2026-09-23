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
from strategy_conversation.registry.concept_ontology import (
    class_choice,
    is_class_id,
    logger as ontology_logger,
)
from strategy_conversation.registry.indicator_registry import REGISTRY
from strategy_conversation.registry.display_labels import display_label, param_label, unit_label
import ui_language
from ui_language import msg

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


# 적립 종목·현금 하한 되묻기 문구(ko, en) — primary가 "지금 답을 기다리는 질문이 이것인가"를 같은 문자열로
# 판정한다(우리가 낸 문장의 동일성 대조 — 사용자 원문 해석이 아니다).
CONTRIBUTION_SYMBOL_QUESTION = (
    "어떤 종목(또는 ETF)을 적립식으로 사 모을까요?",
    "Which stock(s) or ETF(s) should be accumulated?",
)
CASH_RESERVE_QUESTION = (
    "현금을 얼마나 남겨 둘까요? 초기 자본 대비 비율(%)이나 금액으로 정할 수 있어요.\n\n"
    "남겨 둔 현금 아래로는 매수하지 않습니다.",
    "How much cash should always be kept? You can give a share of the initial capital (%) "
    "or an amount.\n\nNothing is bought once cash would fall below that level.",
)


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
            question=msg("어느 시기에 상장한 종목을 대상으로 할까요?",
                         "Which listing period should the universe cover?"),
            recommended_value=f"{last_year}년 이후 상장",
            recommendation_reason=msg(
                "{year}년 이후 상장 종목을 시작값으로 사용할 수 있습니다",
                "Stocks listed since {year} can be used as a starting point", year=last_year),
        ))

    # ①-2 정액 적립식(엔진 v16.20) — 납입액·주기는 둘 다 있어야 하고, 사 모을 종목이 지정돼야 한다.
    # 말하지 않은 쪽을 기본값으로 채우지 않고 묻는다.
    bt = strategy.backtest
    contribution = bt.contribution_amount is not None or bt.contribution_period is not None
    if contribution:
        if bt.contribution_amount is None:
            missing.append("strategy.backtest.contribution_amount")
            questions.append(ClarificationQuestion(
                field="strategy.backtest.contribution_amount",
                question=msg("정액 적립식으로 한 번에 얼마씩 납입할까요?",
                             "How much should each dollar-cost averaging contribution be?"),
            ))
        if bt.contribution_period is None:
            missing.append("strategy.backtest.contribution_period")
            questions.append(ClarificationQuestion(
                field="strategy.backtest.contribution_period",
                question=msg("얼마나 자주 납입할까요? (매주·매월·격월·분기·매년)",
                             "How often should contributions be made? (weekly, monthly, every two months, "
                             "quarterly, yearly)"),
            ))
        # 사 모을 대상은 지정 종목이거나 **말한 유니버스**다 — "S&P500 ETF"는 국내 S&P500 ETF 전체가
        # 유니버스이고(2026-09-22 사용자 결정, 엔진이 유니버스 전체에 균등 분할), 상품 하나와 정확히
        # 일치하는 이름은 컴파일러가 지정 종목으로 승격한다. 시장만 말했으면(코스피·ETF 전체) 묻는다.
        if not strategy.universe.symbols and not strategy.universe.etf_theme:
            missing.append("strategy.universe.symbols")
            questions.append(ClarificationQuestion(
                field="strategy.universe.symbols",
                question=msg(*CONTRIBUTION_SYMBOL_QUESTION),
            ))

    # ①-3 현금 풀(엔진 v16.22) — 현금을 남겨 두라고 했는데 수준을 말하지 않았으면("일정 수준")
    # 기본값으로 채우지 않고 묻는다(칩: 초기 자본의 10%·20%·30%, 2026-09-21 사용자 결정).
    if contribution and bt.cash_pool is not None and not bt.cash_pool.is_complete():
        missing.append("strategy.backtest.cash_pool.reserve_pct")
        questions.append(ClarificationQuestion(
            field="strategy.backtest.cash_pool.reserve_pct",
            question=msg(*CASH_RESERVE_QUESTION),
            recommended_value=None,
        ))

    # ② 진입 메커니즘 존재 여부 (조건 또는 랭킹) — 적립식은 납입 일정이 곧 매수 규칙이다.
    if intent.intent == "CREATE_STRATEGY" and not contribution \
            and not strategy.entry_conditions and not strategy.ranking:
        missing.append("strategy.entry_conditions")
        questions.append(ClarificationQuestion(
            field="strategy.entry_conditions",
            question=msg(
                "어떤 조건으로 종목을 선택할까요? (예: 재무 지표 기준, 기술적 신호, 기간 수익률 상위)",
                "What criteria should select the stocks? (e.g. fundamentals, a technical signal, "
                "top period return)"),
        ))

    # ③ 조건별 필수값 — 비교 연산 조건인데 임계값이 없으면 질문(추천값은 Registry에서)
    for role, path, conditions in (
        ("진입", "entry_conditions", strategy.entry_conditions),
        ("청산", "exit_conditions", strategy.exit_conditions),
    ):
        for i, cond in enumerate(conditions):
            field_base = f"strategy.{path}[{i}]"
            # ③-0 분류(클래스) 발화 — "모멘텀 지표 하나"처럼 계열만 말한 조건(프롬프트
            # 2.9 계약, factor=class.*). 구체 지표를 대신 고르지 않고 선택지를 들어
            # 되묻는다. 선택지는 온톨로지 정본(직속 지원 잎, 중간 분류면 자식 분류명).
            # 칩은 내지 않는다 — 지표 선택 칩은 값 결속 계약(_bind_chips)이 성립하지
            # 않아 노출 금지이고, 자유 서술 답변은 수정 인터프리터 레인이 처리한다.
            if is_class_id(cond.factor):
                choice = class_choice(cond.factor)
                ontology_logger.info(
                    "분류 되묻기 생성 | %s 조건 %s → 선택지 %s",
                    role, cond.factor,
                    f"{len(choice[1])}개" if choice else "없음(질문 생략)",
                )
                if choice is not None:
                    cls_name, options = choice
                    quoted = (
                        f"'{cond.source_text.strip()}' — "
                        if cond.source_text and cond.source_text.strip() else ""
                    )
                    opts = ", ".join(options)
                    # 역할 라벨은 "매수(진입)"처럼 일상어 먼저, 용어 병기 — 진입/청산
                    # 키워드는 유지한다(답변 패치가 진입/청산 어느 배열에 조건을 추가할지
                    # 이 질문 문구가 유일한 근거다, pending_question 에코 · 규칙 10-4).
                    role_label = msg("매수(진입)", "buy (entry)") if role == "진입" \
                        else msg("매도(청산)", "sell (exit)")
                    missing.append(f"{field_base}.factor")
                    questions.append(ClarificationQuestion(
                        field=f"{field_base}.factor",
                        question=(
                            msg("{quoted}{role} 조건에 어떤 {cls} 지표를 사용할까요?",
                                "{quoted}Which {cls} indicator should the {role} condition use?",
                                quoted=quoted, role=role_label, cls=cls_name)
                            + (msg(" {opts} 중에서 고를 수 있습니다.",
                                   " You can choose from {opts}.", opts=opts) if opts else "")
                        ),
                    ))
                continue
            spec = REGISTRY.get(cond.factor)
            if spec is None or spec.supported == "UNSUPPORTED":
                continue
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
                unit = unit_label(spec.value_type,
                                  {"percent": "%", "ratio": "배", "억원": "억원", "point": ""})
                rec = spec.recommended_value
                role_en = "entry" if role == "진입" else "exit"
                questions.append(ClarificationQuestion(
                    field=f"{field_base}.value",
                    question=msg("{role} 조건의 {name} 기준값을 얼마로 할까요?",
                                 "What threshold should the {role} condition use for {name}?",
                                 role=msg(role, role_en), name=display_label(spec)),
                    recommended_value=rec,
                    recommendation_reason=(
                        msg("일반적인 시작값으로 {rec}{unit}을(를) 사용할 수 있습니다",
                            "A common starting value is {rec}{unit}",
                            rec=f"{rec:g}", unit=unit) if rec is not None else None
                    ),
                ))
            # 이벤트형 지표의 필수 파라미터 (예: 크로스오버 단기/장기)
            for pname, pspec in spec.parameters.items():
                if pspec.required and cond.parameters.get(pname) is None:
                    missing.append(f"{field_base}.parameters.{pname}")
                    questions.append(ClarificationQuestion(
                        field=f"{field_base}.parameters.{pname}",
                        question=msg("{name}의 {param}을(를) 몇으로 할까요?",
                                     "What {param} should {name} use?",
                                     name=display_label(spec),
                                     param=param_label(pname, _PARAM_LABELS.get(pname, pname.replace('_', ' ')))),
                        recommended_value=pspec.default,
                        recommendation_reason=(
                            msg("일반적으로 {d}을(를) 사용합니다", "{d} is commonly used",
                                d=f"{pspec.default:g}") if pspec.default is not None else None
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
        # ④-0 가격 산출 랭킹(변동성·모멘텀)의 산정 기간 — 말하지 않은 값(기본 60거래일)이
        # 조용히 확정되지 않게 묻는다(변동성 2026-08-10 사용자 요청, 모멘텀도 같은 날
        # "60일이라고 강제하지 말고 고를 수 있게" 지시로 합류). 진행 골격 순서상 매수
        # 조건(랭킹 파라미터)이 포트폴리오(종목 수·리밸런싱)보다 앞이므로 이 질문을 먼저 낸다.
        # 복합 순위 합산(FR-BT-063)은 랭킹 항목이 여러 개다 — 가격 산출 지표가 어느 자리에
        # 있든 산정 기간을 묻는다(첫 항목만 보면 뒤 자리의 기간이 조용히 60으로 확정된다).
        # 칩 답('수익률 산정 기간 20일')은 전략 공통 ranking_lookback_days로 결속되고
        # 엔진이 기간 없는 가격 지표에 그 값을 쓴다 — 첫 미정 항목 하나만 묻는다.
        _LOOKBACK_LABELS = {"ranking.volatility": "변동성", "ranking.return": "수익률",
                            "ranking.relative_return": "수익률"}
        for idx, rank in enumerate(strategy.ranking):
            lookback_label = _LOOKBACK_LABELS.get(rank.metric)
            if lookback_label is not None and rank.lookback_days is None:
                missing.append(f"strategy.ranking[{idx}].lookback_days")
                questions.append(ClarificationQuestion(
                    field=f"strategy.ranking[{idx}].lookback_days",
                    question=msg("{what} 산정 기간을 며칠(거래일)로 할까요?",
                                 "Over how many trading days should {what} be measured?",
                                 what=msg(lookback_label,
                                          "volatility" if lookback_label == "변동성" else "return")),
                    recommended_value=60,
                    recommendation_reason=msg("일반적으로 60거래일(약 3개월)을 사용합니다",
                                              "60 trading days (about 3 months) is commonly used"),
                ))
                break
        # ④-0b 잔차 반전 시그널(v16.17)의 개방 파라미터는 이산값만 허용한다. 허용 밖 값은
        # 컴파일러가 싣지 않으므로(임의 값으로 바꿔치지 않는다) 검증기 오류 문장 그대로 허용값을
        # 되묻는다. **말하지 않은 값은 묻지 않는다** — 기본값(회귀 60·누적 5)이 사용자 결정이다
        # (2026-09-20). 칩은 내지 않는다(값 결속 표가 없는 무칩 질문 — 답은 LLM 레인이 해석한다).
        for idx, rank in enumerate(strategy.ranking):
            if rank.metric != "ranking.residual_reversal":
                continue
            from strategy_conversation.validation.parameter_validator import (
                residual_reversal_param_errors,
            )

            param_errors = residual_reversal_param_errors(rank)
            if param_errors:
                from engine import residual_factor as _rf

                bad_lookback = (rank.lookback_days is not None
                                and rank.lookback_days not in _rf.REGRESSION_LOOKBACKS)
                field = "lookback_days" if bad_lookback else "accumulation_days"
                missing.append(f"strategy.ranking[{idx}].{field}")
                questions.append(ClarificationQuestion(
                    field=f"strategy.ranking[{idx}].{field}",
                    question=" ".join(param_errors) + " 며칠로 할까요?",
                ))
            break
        # ④-0c 발표 자격 창(v16.19)도 같은 계약 — 범위 밖 값만 되묻고, 말하지 않은 값은
        # 기본값(편입 2·제외 60거래일)으로 둔다(칩 없는 질문 — 답은 LLM 레인이 해석한다).
        for idx, rank in enumerate(strategy.ranking):
            if rank.metric != "ranking.pead":
                continue
            from strategy_conversation.validation.parameter_validator import pead_param_errors

            param_errors = pead_param_errors(rank)
            if param_errors:
                from strategy_conversation.registry.indicator_registry import resolve as _resolve

                _spec = _resolve("ranking.pead").parameters["entry_delay_days"]
                bad_delay = (rank.entry_delay_days is not None
                             and not (_spec.minimum <= rank.entry_delay_days <= _spec.maximum))
                field = "entry_delay_days" if bad_delay else "expiry_days"
                missing.append(f"strategy.ranking[{idx}].{field}")
                questions.append(ClarificationQuestion(
                    field=f"strategy.ranking[{idx}].{field}",
                    question=" ".join(param_errors) + " 며칠로 할까요?",
                ))
            break
        # 편입 규모가 비율(selection_percent)이나 분위 그룹(quantile_groups)으로 이미
        # 정의된 전략은 종목 수가 성립하지 않는다 — 되묻지 않는다(FR-BT-060).
        has_scale = (
            strategy.portfolio.selection_count is not None
            or strategy.portfolio.selection_percent is not None
            or any(r.quantile_groups for r in strategy.ranking)
        )
        if not has_scale and not strategy.universe.symbols:
            missing.append("strategy.portfolio.selection_count")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.selection_count",
                question=msg("상위 몇 종목을 선택할까요?", "How many top-ranked stocks should be held?"),
                recommended_value=10,
                recommendation_reason=msg("일반적인 시작값으로 10종목을 사용할 수 있습니다",
                                          "10 stocks is a common starting point"),
            ))
        if strategy.portfolio.rebalance_frequency is None:
            missing.append("strategy.portfolio.rebalance_frequency")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.rebalance_frequency",
                question=msg("리밸런싱은 얼마나 자주 할까요? (매월/분기/매년)",
                             "How often should the portfolio rebalance? (monthly/quarterly/yearly)"),
                recommended_value="monthly",
                recommendation_reason=msg("랭킹 전략은 월간 리밸런싱을 시작값으로 흔히 사용합니다",
                                          "Ranking strategies commonly start with monthly rebalancing"),
            ))

    # ④-1 변동성 역비중(v16.14) — 변동성 산정 기간을 말하지 않았으면 묻는다(60을 조용히
    # 확정하지 않는다). 역비중은 리밸런싱일마다 비중을 다시 매기므로 주기가 필요하다 —
    # 랭킹 전략은 위 ④가 이미 묻고, 조건형 전략은 여기서 묻는다.
    _optimizer = strategy.portfolio.weighting in ("min_variance", "risk_parity", "max_sharpe", "min_cvar")
    if strategy.portfolio.weighting == "inverse_volatility" or _optimizer:
        if strategy.portfolio.weighting_lookback_days is None:
            missing.append("strategy.portfolio.weighting_lookback_days")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.weighting_lookback_days",
                question=(msg("비중 최적화에 쓸 수익률은 최근 며칠(거래일)로 계산할까요?",
                              "Over how many trading days should returns be measured for the "
                              "weight optimization?") if _optimizer else
                          msg("변동성 역비중에 쓸 변동성은 최근 며칠(거래일)로 계산할까요?",
                              "Over how many trading days should volatility be measured for "
                              "inverse-volatility weighting?")),
                recommended_value=60,
                recommendation_reason=msg("일반적으로 60거래일(약 3개월)을 사용합니다",
                                          "60 trading days (about 3 months) is commonly used"),
            ))
        if not strategy.ranking and strategy.portfolio.rebalance_frequency is None:
            missing.append("strategy.portfolio.rebalance_frequency")
            questions.append(ClarificationQuestion(
                field="strategy.portfolio.rebalance_frequency",
                question=msg("변동성 역비중은 정해진 주기마다 비중을 다시 맞춥니다. "
                             "리밸런싱은 얼마나 자주 할까요? (매월/분기/매년)",
                             "Inverse-volatility weights are reset on a schedule. How often "
                             "should the portfolio rebalance? (monthly/quarterly/yearly)"),
                recommended_value="monthly",
                recommendation_reason=msg("월간 리밸런싱을 시작값으로 흔히 사용합니다",
                                          "Monthly rebalancing is a common starting point"),
            ))

    # ④-2 시장 국면 필터(v16.14) — 이동평균 기간과 약세 국면의 투자 비중을 말하지 않았으면
    # 묻는다(2026-09-19 사용자 결정: 비율은 되묻기 — 기본값 확정 금지). 변동성 급등 판정
    # (v16.16)의 배수도 같은 계약이다(2026-09-20 결정) — 산정 기간만은 묻지 않고 엔진이 20일로
    # 계산해 결과에 표기한다.
    mf = strategy.market_filter
    if mf is not None:
        index_name = msg("코스피" if mf.index == "KOSPI" else "코스닥", mf.index)
        uses_ma = "below_ma" in mf.triggers
        uses_vol = "volatility_spike" in mf.triggers
        if uses_ma and mf.ma_period is None:
            missing.append("strategy.market_filter.ma_period")
            questions.append(ClarificationQuestion(
                field="strategy.market_filter.ma_period",
                question=msg("{index} 몇 일 이동평균선을 기준으로 할까요?",
                             "Which {index} moving average should be the threshold?",
                             index=index_name),
                recommended_value=200,
                recommendation_reason=msg("200일 이동평균선을 흔히 사용합니다",
                                          "The 200-day moving average is commonly used"),
            ))
        if uses_vol and mf.volatility_multiple is None:
            missing.append("strategy.market_filter.volatility_multiple")
            questions.append(ClarificationQuestion(
                field="strategy.market_filter.volatility_multiple",
                question=msg("{index} 변동성이 평소(직전 1년 평균)의 몇 배 이상이면 급등으로 볼까요?",
                             "How many times its usual level (prior 1-year average) should "
                             "{index} volatility reach to count as a spike?",
                             index=index_name),
                recommended_value=None,
            ))
        if mf.exposure_pct is None:
            missing.append("strategy.market_filter.exposure_pct")
            if uses_ma and uses_vol:
                exposure_question = msg(
                    "{index}가 이동평균선 아래에 있거나 변동성이 급등했을 때 투자 비중을 몇 %로 "
                    "줄일까요? (나머지는 현금으로 보유합니다)",
                    "When {index} is below its moving average or its volatility spikes, what share "
                    "of the portfolio should stay invested? (the rest is held in cash)",
                    index=index_name)
            elif uses_vol:
                exposure_question = msg(
                    "{index} 변동성이 급등했을 때 투자 비중을 몇 %로 줄일까요? "
                    "(나머지는 현금으로 보유합니다)",
                    "When {index} volatility spikes, what share of the portfolio should stay "
                    "invested? (the rest is held in cash)",
                    index=index_name)
            else:
                exposure_question = msg(
                    "{index}가 이동평균선 아래에 있을 때 투자 비중을 몇 %로 줄일까요? "
                    "(나머지는 현금으로 보유합니다)",
                    "When {index} is below its moving average, what share of the "
                    "portfolio should stay invested? (the rest is held in cash)",
                    index=index_name)
            questions.append(ClarificationQuestion(
                field="strategy.market_filter.exposure_pct",
                question=exposure_question,
                recommended_value=None,
            ))

    # ── 경쟁 격차 1차(v16.28) — 개념은 있는데 값이 없으면 묻는다(같은 계약). ──
    _pf = strategy.portfolio
    if _pf.weighting == "fixed" and not _pf.target_weights:
        missing.append("strategy.portfolio.target_weights")
        questions.append(ClarificationQuestion(
            field="strategy.portfolio.target_weights",
            question=msg("종목(자산)별 고정 비중을 몇 %씩 둘까요? (예: 코스피200 ETF 60%, 국채 ETF 40%)",
                         "What fixed weight should each asset get? (e.g. KOSPI200 ETF 60%, bond ETF 40%)"),
            recommended_value=None))
    _rm = strategy.risk_management
    if _rm.position_sizing is not None:
        _ps = _rm.position_sizing
        if _ps.method == "atr_risk" and _ps.risk_per_trade_percent is None:
            missing.append("strategy.risk_management.position_sizing.risk_per_trade_percent")
            questions.append(ClarificationQuestion(
                field="strategy.risk_management.position_sizing.risk_per_trade_percent",
                question=msg("거래당 위험을 자산의 몇 %로 둘까요? (ATR 기준 포지션 사이징)",
                             "What share of equity should each trade risk? (ATR-based sizing)"),
                recommended_value=1,
                recommendation_reason=msg("거래당 1% 위험을 시작값으로 흔히 씁니다",
                                          "1% risk per trade is a common starting point")))
        if _ps.method == "kelly" and _ps.kelly_fraction is None:
            missing.append("strategy.risk_management.position_sizing.kelly_fraction")
            questions.append(ClarificationQuestion(
                field="strategy.risk_management.position_sizing.kelly_fraction",
                question=msg("켈리 비중의 몇 배를 쓸까요? (하프 켈리=0.5, 풀 켈리=1)",
                             "What fraction of the Kelly weight should be used? (half Kelly=0.5, full=1)"),
                recommended_value=0.5,
                recommendation_reason=msg("하프 켈리(0.5)가 변동을 줄이는 일반적 선택입니다",
                                          "Half Kelly (0.5) is the usual choice to dampen swings")))
    for _k, _p in enumerate(_rm.partial_take_profits):
        if _p.profit_percent is None or _p.sell_percent is None:
            _field = f"strategy.risk_management.partial_take_profits.{_k}"
            missing.append(_field)
            questions.append(ClarificationQuestion(
                field=_field,
                question=msg("분할 익절은 수익률 몇 %에서 보유 비중의 몇 %를 매도할까요?",
                             "At what profit and what share of the position should the partial take-profit sell?"),
                recommended_value=None))
            break
    _bt = strategy.backtest
    if _bt.entry_tranches is not None and (_bt.entry_tranches.count is None or _bt.entry_tranches.step_percent is None):
        missing.append("strategy.backtest.entry_tranches")
        questions.append(ClarificationQuestion(
            field="strategy.backtest.entry_tranches",
            question=msg("분할 매수는 몇 회차로, 회차마다 몇 % 낮은 가격에서 살까요?",
                         "How many tranches, and how far below the last fill should each tranche be?"),
            recommended_value=None))

    # 매크로 조건 필터(v16.31) — 시리즈·기준값·기간·비율 중 비어 있는 것을 순서대로 하나씩 묻는다.
    # 칩은 붙이지 않는다(primary의 필드별 칩 표에 없음): 필터가 여러 개면 칩 정본 표기가 어느 필터의
    # 값인지 결속되지 않는다. 무칩 ask는 유효하며 자유 답변은 수정 레인이 패치로 처리한다.
    from engine.macro_data import RATE_SERIES, series_label as _series_label
    for _k, _m in enumerate(strategy.macro_filters):
        _base = f"strategy.macro_filters.{_k}"
        _en = ui_language.get_ui_language() == "en"
        if _m.series is None:
            missing.append(f"{_base}.series")
            _choices = ", ".join(_series_label(s, _en) for s in RATE_SERIES)
            questions.append(ClarificationQuestion(
                field=f"{_base}.series",
                question=msg("어느 금리를 기준으로 할까요? ({choices})",
                             "Which interest rate should the filter use? ({choices})", choices=_choices),
                recommended_value=None))
            break
        _label = _series_label(_m.series, _en)
        if _m.mode == "change" and _m.period is None:
            missing.append(f"{_base}.period")
            questions.append(ClarificationQuestion(
                field=f"{_base}.period",
                question=msg("{label}의 변화율은 며칠(거래일) 기준으로 잴까요?",
                             "Over how many trading days should the change in {label} be measured?", label=_label),
                recommended_value=20))
            break
        if _m.mode == "ma" and _m.period is None:
            missing.append(f"{_base}.period")
            questions.append(ClarificationQuestion(
                field=f"{_base}.period",
                question=msg("{label}의 몇 일 이동평균을 기준으로 할까요?",
                             "Which moving average of {label} should be the threshold?", label=_label),
                recommended_value=200))
            break
        if _m.mode != "ma" and _m.value is None:
            missing.append(f"{_base}.value")
            questions.append(ClarificationQuestion(
                field=f"{_base}.value",
                question=(msg("{label}의 변화율 기준을 몇 %로 할까요?",
                              "What percentage change in {label} should trigger the filter?", label=_label)
                          if _m.mode == "change" else
                          msg("{label} 기준값을 얼마로 할까요?",
                              "What level of {label} should trigger the filter?", label=_label)),
                recommended_value=None))
            break
        if _m.operator is None:
            missing.append(f"{_base}.operator")
            questions.append(ClarificationQuestion(
                field=f"{_base}.operator",
                question=msg("{label}이(가) 기준값보다 높을 때와 낮을 때 중 어느 쪽에서 비중을 줄일까요?",
                             "Should the filter trigger when {label} is above or below the threshold?", label=_label),
                recommended_value=None))
            break
        if _m.exposure_pct is None:
            missing.append(f"{_base}.exposure_pct")
            questions.append(ClarificationQuestion(
                field=f"{_base}.exposure_pct",
                question=msg("{label} 조건이 충족될 때 투자 비중을 몇 %로 줄일까요? (나머지는 현금으로 보유합니다)",
                             "When the {label} condition holds, what share of the portfolio should stay invested? "
                             "(the rest is held in cash)", label=_label),
                recommended_value=None))
            break

    # 전술 자산배분(v16.29) — 자산 목록이 비면 묻는다(상품을 대신 고르지 않는다).
    _taa = strategy.taa
    if _taa is not None:
        _model = str(_taa.model).upper()
        if not _taa.offensive or not _taa.defensive:
            missing.append("strategy.taa.offensive")
            questions.append(ClarificationQuestion(
                field="strategy.taa.offensive",
                question=msg("{model} 전술 자산배분의 공격 자산과 방어 자산으로 어떤 ETF·종목을 쓸까요? "
                             "(예: 공격 KODEX 200·TIGER 미국S&P500, 방어 KODEX 국고채10년)",
                             "Which ETFs or stocks should be the offensive and defensive assets for the "
                             "{model} allocation? (e.g. offensive: KODEX 200, TIGER S&P500; defensive: KODEX KTB 10Y)",
                             model=_model),
                recommended_value=None))
        elif _taa.model == "daa" and not _taa.canary:
            missing.append("strategy.taa.canary")
            questions.append(ClarificationQuestion(
                field="strategy.taa.canary",
                question=msg("DAA의 카나리아(위험 신호) 자산으로 어떤 ETF·종목을 쓸까요?",
                             "Which ETFs or stocks should serve as DAA's canary assets?"),
                recommended_value=None))

    # 목표 변동성(v16.25) — 개념은 있는데 값이 없으면 묻는다(시장 국면 필터의 비율과 같은 계약).
    vt = strategy.volatility_target
    if vt is not None and vt.target_percent is None:
        missing.append("strategy.volatility_target.target_percent")
        questions.append(ClarificationQuestion(
            field="strategy.volatility_target.target_percent",
            question=msg("목표 연변동성을 몇 %로 할까요? (자산곡선 변동성이 이를 넘는 날 노출을 낮춥니다)",
                         "What annual volatility should the strategy target? (exposure is cut on days "
                         "the equity curve's volatility exceeds it)"),
            recommended_value=None,
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
    # 적립식의 진입 조건은 전부 납입액 규칙이다(capability_validator가 섞인 요청을 이미 걸렀다) —
    # 매도가 없는 방식이라 청산 규칙을 묻지 않는다.
    if strategy.entry_conditions and not has_exit_rule and not contribution:
        # 재무 스크리닝만 있는 전략은 정기 리밸런싱 회전이 자연스러운 완성형이다 —
        # 오류가 아니라 질문으로 청산 방식을 확정받는다
        missing.append("strategy.exit_conditions")
        questions.append(ClarificationQuestion(
            field="strategy.exit_conditions",
            question=msg(
                "매수한 종목을 언제 팔지(청산 규칙)가 아직 정해지지 않았습니다. "
                "어떤 방식으로 매도할까요? 예: 일정 기간 보유 후 매도, "
                "정해진 주기로 종목 교체(리밸런싱), 일정 비율 손실/이익에서 매도(손절/익절)",
                "The exit rule (when to sell) isn't set yet. How should positions be sold? "
                "e.g. sell after a holding period, replace stocks on a schedule (rebalancing), "
                "or sell at a loss/profit percentage (stop-loss/take-profit)"),
            recommended_value="monthly",
            recommendation_reason=msg(
                "이런 선별(스크리닝) 전략은 매월 종목을 교체하는 '매월 리밸런싱'을 흔히 사용합니다",
                "Screening strategies like this commonly use monthly rebalancing"),
        ))

    return missing, questions[:MAX_QUESTIONS_PER_TURN]
