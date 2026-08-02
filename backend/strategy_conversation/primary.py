"""Primary Mode (Phase 2) — LLM Interpreter를 초기 파스의 기본 경로로 승격.

STRATEGY_INTERPRETER_MODE=primary일 때 main.py 초기 파스가 이 모듈을 먼저 시도한다.
None은 실패 보고다 — 호출부는 규칙 파서로 재해석하지 않고 되묻기(interpretation_failed)로
끝낸다(계약 § 8 "폴백은 자연어 재해석이 아니라 실패 보고", 1c 폴백 차단, 2026-07-26):
  - LLM 호출/JSON 복구 실패
  - 전략 파이프라인 대상이 아닌 intent(비전략·설명·추천 요청 — 상류 분류기 소관)
  - strategy 본문 없음 / 컴파일 실패
LLM 서버 연결 장애는 None으로 삼키지 않고 던진다(main의 503 경로 소관).

READY면 전체 컴파일, NEEDS_CLARIFICATION이면 **미확정 조건을 제외한 부분 컴파일**
(조용한 기본값 확정 금지) + 되묻기 질문·추천값 칩을 기존 clarification 채널로 전달.
칩 텍스트("영업이익률 10% 이상")는 클릭 시 일반 수정 메시지로 재전송되어 기존
modify 경로(결정적 병합)가 조건을 채운다 — condition_builder와 동일한 무상태 패턴.

수정(modify) 경로는 Phase 2에서 기존 하이브리드를 유지한다(QA 실측 26/26 경로 보존,
대화 상태는 기존 아키텍처대로 프론트의 previous_parsed가 소유).
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Dict, Iterable, List, Optional

from engine import strategy_slots
from strategy_conversation import config
from strategy_conversation.conversation.change_log import changed_field_names
from strategy_conversation.interpreter.llm_strategy_interpreter import _log_llm
from strategy_conversation.interpreter.models import StrategyIntent, ValidationReport
from strategy_conversation.registry.indicator_registry import REGISTRY
from strategy_conversation.response.output_guard import finalize_user_response

logger = logging.getLogger("strategy_interpreter.primary")

_STRATEGY_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def primary_enabled() -> bool:
    return config.interpreter_mode() == "primary"


def _prune_clarifications_filled_by_overrides(
    report: ValidationReport, parsed: Any
) -> None:
    """결정적 보정(_apply_prompt_overrides)이 채운 조건의 되묻기 질문을 제거한다(제자리).

    완결성 검증은 인터프리터 LLM이 낸 intent(보정 전)에 대해 돌기 때문에, LLM이 '흑자
    기업'을 빠뜨렸다가 _apply_prompt_overrides가 eps>0 필터로 결정적으로 되살린 경우
    parsed에는 진입 조건이 있는데도 "어떤 조건으로 종목을 선택할까요?" 질문이 남는다 —
    확정된 완성 전략을 다시 되묻는 사고. 보정 후 parsed가 실제로 채운 조건 질문만 지운다.
    """
    if not report.clarification_questions:
        return
    has_entry = bool(
        getattr(parsed, "entry_signals", None)
        or getattr(parsed, "fundamental_filters", None)
        or getattr(parsed, "ranking_metric", None)
        or getattr(parsed, "target_symbols", None)
    )
    rebal = getattr(parsed, "rebalancing_period", None)
    has_exit = bool(
        getattr(parsed, "exit_signals", None)
        or getattr(parsed, "hold_period_days", None)
        or (rebal and rebal != "none")
        or getattr(parsed, "stop_loss_pct", None)
        or getattr(parsed, "take_profit_pct", None)
        or getattr(parsed, "trailing_stop_pct", None)
    )
    filled_fields = set()
    if has_entry:
        filled_fields.add("strategy.entry_conditions")
    if has_exit:
        filled_fields.add("strategy.exit_conditions")
    # 결정적 섹터 보정(_extract_sector — 지식그래프·검색 그라운딩 학습분 포함)이 업종을
    # 채웠으면 인터프리터의 업종 질문은 이미 답이 있다("마운자로 관련주" — LLM은 모르지만
    # 검색 학습으로 해석된 테마를 다시 되묻는 사고 방지).
    if getattr(parsed, "sector", None):
        filled_fields.add("strategy.universe.sectors")
    if filled_fields:
        report.clarification_questions = [
            q for q in report.clarification_questions if q.field not in filled_fields
        ]


# 이동평균 크로스 기간 질문 병합 — 사용자 결정(2026-07-26): "골든크로스로 매수해줘"처럼
# 기간 미지정 크로스는 조용한 기본값 확정 대신 **옵션을 보여주며 되묻는다**. completeness가
# 내는 파라미터별 질문(단기/장기 각각)을 조건당 1개 질문으로 병합하고, 칩은 조건 전체를
# 담아 무상태 재전송 가능하게 만든다(condition_builder 칩 패턴 — "골든크로스(5일/20일)
# 발생 시 매수"는 재전송 시 수치 대조·결정적 추출 모두 통과하는 정본 표기).
_CROSS_PERIOD_FIELD_RE = re.compile(
    r"^strategy\.(entry|exit)_conditions\[(\d+)\]\.parameters\.(short_period|long_period)$"
)
_CROSS_PERIOD_OPTIONS = ((5, 20), (20, 60), (60, 120))


def _cross_period_chip(role: str, short: int, long: int) -> str:
    if role == "entry":
        return f"골든크로스({short}일/{long}일) 발생 시 매수"
    return f"데드크로스({short}일/{long}일) 발생 시 매도"


def _new_listing_period_chips() -> List[str]:
    """신규 상장 대상 시기 되묻기 칩(FR-STR-073) — 최근 연도 코호트 + 상대 기간.

    사용자 어휘 그대로라 그대로 재전송하면 인터프리터가 상장 구간으로 해석한다.
    연도는 오늘 기준으로 만든다(해가 바뀌면 칩도 따라간다).
    """
    from datetime import date

    year = date.today().year
    return [f"{year}년 상장", f"{year - 1}년 상장", "최근 1년 내 상장", "최근 3년 내 상장"]


def _numeric_options(recommended: Any, *alternates: int) -> List[int]:
    """추천값을 맨 앞에 둔 중복 없는 선택지. 추천값이 수치가 아니면 대안만 쓴다."""
    values: List[int] = []
    if isinstance(recommended, (int, float)) and not isinstance(recommended, bool):
        values.append(int(recommended))
    for alt in alternates:
        if alt not in values:
            values.append(alt)
    return values


# 조건(entry/exit)이 아닌 슬롯 질문의 칩 — 되묻기에 결속을 붙이기 위한 정본 표기.
#
# 인터프리터는 이 슬롯들에도 recommended_value를 제대로 낸다(종목 수 10, 리밸런싱
# monthly, 손절 8 …). 그런데 칩 생성이 **조건 임계값 질문에만** 있어서 그 추천값이
# 전부 버려졌고, 칩이 0개면 _pending_ask_payload가 None을 낸다 — 즉 포트폴리오·리스크·
# 청산 질문은 구조적으로 영원히 결속되지 않았다(2026-07-31 실측: 고정 파이프라인 경로
# 결속 0/7턴). 그 구멍을 메운다.
#
# **표기는 _bind_chips(=_apply_prompt_overrides) 결속이 실증된 것만 쓴다** — 결속되지
# 않는 칩은 발행 시점에 탈락해 사용자에게 보이지도 않으므로(칩=값 결속 계약), 지어낸
# 문구를 넣으면 이 수정이 무효가 된다. 회귀는 test_slot_clarification_chips가 잡는다.
# topic은 engine.strategy_slots.SLOT_LABELS와 맞춘다 — 물질화 기본값과 같은 값을 가리키는
# 칩을 확정 칩(§ 7 CONFIRM)으로 살리는 _confirm_target이 이 라벨로 필드를 찾는다.
_SLOT_CHIP_BUILDERS: Dict[str, Any] = {
    "strategy.portfolio.selection_count": (
        "최대 보유",
        lambda rec: [f"최대 {n}종목" for n in _numeric_options(rec, 5, 20)],
    ),
    "strategy.portfolio.rebalance_frequency": (
        "리밸런싱",
        lambda rec: ["매월 리밸런싱", "분기 리밸런싱", "매년 리밸런싱"],
    ),
    "strategy.portfolio.hold_period_days": (
        "보유 기간",
        lambda rec: [f"{n}일 보유" for n in _numeric_options(rec, 20, 60)],
    ),
    "strategy.risk_management.stop_loss": (
        "손절",
        lambda rec: [f"손절 -{n}%" for n in _numeric_options(rec, 5, 15)],
    ),
    "strategy.risk_management.take_profit": (
        "익절",
        lambda rec: [f"익절 {n}%" for n in _numeric_options(rec, 20, 30)],
    ),
    "strategy.risk_management.trailing_stop": (
        "트레일링 스탑",
        lambda rec: [f"트레일링 스탑 {n}%" for n in _numeric_options(rec, 10, 15)],
    ),
    # 청산 규칙 부재 — 회전 방식 자체를 고르는 질문이라 성격이 다른 선택지를 함께 낸다.
    "strategy.exit_conditions": (
        "청산",
        lambda rec: ["매월 리밸런싱", "분기 리밸런싱", "20일 보유", "손절 -10%"],
    ),
}


def _build_clarification(
    report: ValidationReport, intent: StrategyIntent
) -> tuple[Optional[str], Optional[List[str]], Optional[str]]:
    """검증 리포트의 질문들을 기존 clarification 채널(질문 텍스트 + 칩)로 변환한다.

    반환: (질문 텍스트, 칩, topic). topic은 칩이 어느 슬롯의 것인지 — pending_ask의
    확정 판정(_confirm_target)이 쓴다. 조건 임계값 칩은 슬롯이 아니므로 None이다.
    """
    if not report.clarification_questions:
        return None, None, None
    lines: List[str] = []
    chips: List[str] = []
    slot_topic: Optional[str] = None
    strategy = intent.strategy
    conditions_by_field: Dict[str, Any] = {}
    if strategy is not None:
        for path, conds in (("entry_conditions", strategy.entry_conditions),
                            ("exit_conditions", strategy.exit_conditions)):
            for i, cond in enumerate(conds):
                conditions_by_field[f"strategy.{path}[{i}].value"] = cond
                conditions_by_field[f"strategy.{path}[{i}]"] = cond
    coalesced_cross_roles: List[str] = []
    for q in report.clarification_questions:
        cross_match = _CROSS_PERIOD_FIELD_RE.match(q.field)
        if cross_match:
            role, idx = cross_match.group(1), cross_match.group(2)
            cond = conditions_by_field.get(f"strategy.{role}_conditions[{idx}]")
            if cond is not None and cond.factor == "technical.ma_crossover":
                if role not in coalesced_cross_roles:
                    coalesced_cross_roles.append(role)
                continue  # 파라미터별 질문은 아래에서 병합 질문 1개로 대체
        line = q.question
        if q.recommended_value is not None and q.recommendation_reason:
            line += f" ({q.recommendation_reason})"
        lines.append(line)
        # 조건 임계값 질문 → "영업이익률 10% 이상" 칩(수정 메시지로 재전송 가능한 형태)
        cond = conditions_by_field.get(q.field)
        if cond is not None and q.recommended_value is not None:
            spec = REGISTRY.get(cond.factor)
            if spec is not None:
                unit = {"percent": "%", "ratio": "배", "억원": "억원"}.get(spec.value_type or "", "")
                direction = "이하" if (cond.operator or "").startswith("<") else "이상"
                # display_name의 괄호 설명은 칩에서 제거해 수정 파서 어휘와 맞춘다
                name = spec.display_name.split("(")[0]
                chips.append(f"{name} {q.recommended_value:g}{unit} {direction}")
        elif q.field == "strategy.universe.listing_from":
            # 신규 상장 대상 시기(FR-STR-073) — 사용자 어휘 그대로 되보낼 수 있는 칩.
            chips.extend(_new_listing_period_chips())
        elif not chips and q.field in _SLOT_CHIP_BUILDERS:
            # 조건이 아닌 슬롯(포트폴리오·리스크·청산) 질문의 칩. **한 슬롯만** 낸다 —
            # pending_ask 하나에 topic 하나가 계약이라, 여러 슬롯 칩을 섞으면 확정 판정
            # (_confirm_target)이 엉뚱한 필드를 보게 된다. 나머지 질문은 문구로 남는다.
            topic, build = _SLOT_CHIP_BUILDERS[q.field]
            chips.extend(build(q.recommended_value))
            slot_topic = topic
    for role in coalesced_cross_roles:
        role_label = "매수(진입)" if role == "entry" else "매도(청산)"
        lines.append(
            f"{role_label} 이동평균 크로스의 기간(단기/장기)은 몇 일로 할까요? "
            "(일반적으로 20일/60일을 많이 사용합니다)"
        )
        chips.extend(_cross_period_chip(role, s, l) for s, l in _CROSS_PERIOD_OPTIONS)
    return "\n".join(lines), (chips or None), slot_topic


def _modify_clarification(
    report: ValidationReport, intent: StrategyIntent, prev: Any
) -> tuple[Optional[str], Optional[List[str]], Optional[Dict[str, Any]]]:
    """수정 경로의 되묻기 — 질문·칩에 결속(pending_ask)을 덧붙인다.

    수정 경로의 되묻기 세 곳(CLARIFY_STRATEGY·자기 의심 패치·패치 값 미확정)은 전부
    질문과 칩만 내보내고 결속을 내지 않았다. 그래서 "이전 결정을 고치려다 흐름이
    깨진다"는 증상이 났다 — 되묻기에 답해도 그 답이 어느 질문의 답인지 근거가 없다.

    칩 목록은 **줄이지 않는다**(초기 파스 경로와 다른 점). 여기 칩은 이미 사용자에게
    노출돼 온 것이라, 결속 실패를 이유로 지우면 오늘 동작하던 선택지가 사라진다.
    결속된 칩만 pending_ask에 실리고, 결속 안 된 칩 클릭은 지금처럼 수정 LLM이 받는다.
    """
    from observability import span
    from observability.agent_trace import ask_binding_gate

    question, chips, topic = _build_clarification(report, intent)
    ask = _pending_ask_payload(question, chips, topic, prev)
    # 초기 파스와 같은 게이트 판정을 남긴다 — 이 span이 없으면 Trace에서 수정 턴의
    # 결속 유무를 세지 못한다(실측: create 7턴만 게이트가 잡히고 modify 7턴은 공백).
    gate = ask_binding_gate(
        question=question, priority="modify_unapplied", chips_offered=chips,
        pending_ask=ask, planner_mode_primary=config.dag_planner_mode() == "primary",
        planner_ran=False, lane="modify",
    )
    if gate["gate"] != "no_question":
        with span("Ask 결속", "state", inputs={"question": question},
                  metadata={"ask_gate": gate["gate"], "lane": "modify"}) as _trace:
            _trace.output(**gate)
        if not gate["bound"]:
            _log_llm("🔗 결속 소실(수정)", (
                f"gate={gate['gate']} 칩={gate['chips_bound']}/{gate['chips_offered']}"
            ))
    return question, chips, ask


# 인터프리터가 unsupported_features에 내부 식별자(strategy_evaluation 등)를 그대로 담는
# 실측 드리프트 — 사용자 안내 문구에 내부명이 노출되지 않게 치환한다(레드팀 QA 20-5).
_INTERNAL_FEATURE_LABELS = {
    "strategy_evaluation": "전략 우열 평가",
    "strategy_recommendation": "전략 추천",
    "stock_recommendation": "종목 추천",
    "market_forecast": "시장 전망",
}
def _reported_features_echo_input(features: List[str], user_input: str) -> bool:
    """인터프리터가 미지원 항목에 발화 전체를 그대로 담았는지(오라벨 감지).

    입력은 LLM 출력과 사용자 입력의 **대조**다 — 표기를 지우고 같은 문자열인지만 본다.
    원문의 의미를 읽지 않으므로 해석이 아니다(계약 § 3-1 (b), 수치 대조와 같은 형태).
    """
    from engine.nl_parser import _compact

    compact_input = _compact(user_input or "")
    if not compact_input:
        return False
    return any(_compact(f or "") == compact_input for f in features)


def _humanize_features(features: List[str]) -> List[str]:
    """내부 식별자(strategy_evaluation 등)만 사람이 읽는 라벨로 치환한다. 그 외(FCF·
    technical.beta 등)는 기존 표기를 그대로 둔다 — 매핑에 없는 토큰까지 뭉뚱그린 표현으로
    바꾸면 정보가 사라진다(레드팀 QA 20-5는 매핑된 이름만 대상)."""
    return list(dict.fromkeys(
        _INTERNAL_FEATURE_LABELS.get(f, f) for f in dict.fromkeys(features)
    ))


# ── 수정 패치 환각 게이트(출처 대조) ──────────────────────────────────────────
# "다른 예는 없어?"라는 후속 질문에 인터프리터가 손절·리밸런싱·백테스트 날짜 패치를
# 지어내 전략을 임의 변형한 실측 사고(레드팀 QA 20-3) 방지. 판정은 해석이 아니라
# **대조**다(nl_interpretation_contract § 3-1) — 과거의 필드별 한국어 어휘 목록 스캔은
# 계약이 금지한 발화 어휘 스캔이라 폐기했다(2026-07-26). 남은 판정 근거 셋:
#   ① 출처 인용 대조 — LLM이 patch.source_text로 인용한 원문 조각이 실제 입력에
#      존재하는지 표기 정규화(_compact) 후 문자열 포함으로 확인한다. 어휘도 의미도
#      판단하지 않는다 — LLM의 출처 주장(인용)이 실재하는지만 본다. 단, 인용문에 숫자가
#      있는데 패치 값과 자릿수가 어긋나면 인용은 근거가 아니라 오류의 증거이므로
#      통과시키지 않는다(_quote_contradicts_value — 인용 ↔ 값, 둘 다 LLM 출력이다).
#   ② 수치 대조 — 패치 값의 숫자가 입력의 숫자 표기(단위 환산 포함)와 일치하면
#      근거 있음(recall_validator와 같은 § 3-1 대조).
#   ③ 지정 종목 — 해석 가능성(§ 3-2 지식 조회): 마스터에 없는 이름은 환각.


def _patch_value_numbers(value: Any) -> set:
    """패치가 **실제로 넣는** 숫자. 인용문(source_text)의 숫자는 세지 않는다.

    인용문은 사용자 원문 조각이라 언제나 입력의 숫자를 포함한다 — 값에 남겨 두면 값이
    틀려도 인용이 대신 대조를 통과시킨다(recall_validator._reflected_numbers가 같은
    이유로 인용을 제외한다. 실측 2026-08-02: `{value: 30000000, source_text: "3억원"}`의
    인용에서 3이 잡혀 3천만원이 '입력과 일치'로 통과했다).
    """
    from strategy_conversation.validation.recall_validator import _collect_numbers

    acc: set = set()
    _collect_numbers(_without_quotes(value), acc)
    return acc


def _without_quotes(value: Any) -> Any:
    """값 트리에서 인용문(`source_text`)만 걷어낸다(수치 대조용 — 원본 불변)."""
    if isinstance(value, dict):
        return {k: _without_quotes(v) for k, v in value.items() if k != "source_text"}
    if isinstance(value, (list, tuple)):
        return [_without_quotes(item) for item in value]
    return value


def _is_power_of_ten_apart(a: float, b: float) -> bool:
    """두 수가 10의 거듭제곱 배수만큼(≠1배) 어긋나는가 — 자릿수 오류의 표식."""
    if a == 0 or b == 0:
        return False
    ratio = abs(a) / abs(b)
    if ratio < 1:
        ratio = 1 / ratio
    exponent = round(math.log10(ratio))
    return exponent >= 1 and abs(ratio - 10 ** exponent) < ratio * 1e-9


def _quote_contradicts_value(quote: Optional[str], value: Any) -> bool:
    """LLM이 단 인용문의 숫자와 패치 값이 **자릿수만큼** 어긋나는가.

    입력을 해석하지 않는다 — **LLM 자신의 출력 두 조각(인용문 ↔ 값)을 대조**할 뿐이다.
    숫자가 없는 인용("데드크로스 나오면 팔아")은 대조 대상이 아니므로 False(모순 아님).
    값에 숫자가 여럿이면(조건 객체의 기본 파라미터 등) 하나라도 맞으면 모순이 아니다 —
    "RSI 30 이하"의 `{value: 30, parameters: {period: 14}}`에서 14는 인용에 없는 게 정상이다.
    (값 안의 `source_text`는 _patch_value_numbers가 이미 제외한다 — 그대로 두면 인용이
    자기 자신과 대조돼 이 검사가 영구히 침묵한다.)

    **10의 거듭제곱 배수로 좁히는 이유**: 단위 환산에는 하나로 정해지지 않은 관례가
    있다. "최근 3개월"을 9B가 `lookback_days=90`(달력일)으로, 우리 환산표는 63(거래일)로
    잡는 식이다 — 둘 다 옳고 어느 쪽인지는 의미 판단이라 여기서 하지 않는다. 반면 10배·
    100배 어긋남은 관례 차이로 설명되지 않는 표기 오류다(실측 두 건 모두 정확히 10배:
    "1000억원"→1e10, "3억원"→3e7).
    """
    from strategy_conversation.validation.recall_validator import _candidates, _input_anchors

    quote_numbers: set = set()
    for _label, anchor, unit in _input_anchors(quote or ""):
        quote_numbers |= _candidates(anchor, unit)
    if not quote_numbers:
        return False
    patch_numbers = _patch_value_numbers(value)
    if not patch_numbers:
        return False
    if any(abs(abs(p) - abs(c)) < 1e-6 for p in patch_numbers for c in quote_numbers):
        return False  # 그대로 맞는 숫자가 있으면 모순이 아니다
    return any(
        _is_power_of_ten_apart(p, c) for p in patch_numbers for c in quote_numbers
    )


def _input_number_candidates(user_input: str) -> set:
    """입력의 숫자 앵커와 그 단위 환산 후보 집합(§ 3-1 — 표기 변환일 뿐 의미 판단 아님)."""
    from strategy_conversation.validation.recall_validator import _candidates, _input_anchors

    out: set = set()
    for _label, value, unit in _input_anchors(user_input):
        out |= _candidates(value, unit)
    return out


def _patch_provenance_supported(patch, compact_input: str, input_numbers: set) -> bool:
    tokens = [t for t in patch.path.split("/") if t]
    # 지정 종목은 열린 집합이라 인용·수치로 판정하지 않는다 — **해석 가능성**으로 거른다
    # (§ 3-2 지식 조회): 마스터에 없는 이름을 LLM이 지어냈으면 거부, 실재 종목이면 통과.
    if "symbols" in tokens:
        values = patch.value if isinstance(patch.value, list) else [patch.value]
        values = [v for v in values if isinstance(v, str) and v.strip()]
        if not values:
            return True  # 지정 해제(빈 배열)는 값 검증 대상이 아니다
        from strategy_conversation.registry.universe_resolver import resolve_symbols

        codes, unresolved = resolve_symbols(values)
        return bool(codes) and not unresolved
    from engine.nl_parser import _compact

    # ① 출처 인용 대조: 인용문이 입력에 실재하면 근거 있음.
    #    인용은 **두 자리** 중 하나에 온다 — 패치 자신(PatchOp.source_text)과, 조건을 통째로
    #    넣는 패치의 값 안(StrategyCondition.source_text). 둘 다 스키마가 인정하는 자리라
    #    모델이 어디에 쓸지는 정해져 있지 않다. 패치 쪽만 보면 조건 객체 안에 인용한
    #    패치가 근거 없음으로 거부된다 — '데드크로스 나오면 팔아'가 인용을 정확히 달고도
    #    통째로 버려지던 2026-07-31 QA 실측이 이것이다(수치가 없어 ②도 못 구제한다).
    quotes = [patch.source_text]
    if isinstance(patch.value, dict):
        quotes.append(patch.value.get("source_text"))
    for raw_quote in quotes:
        quote = _compact(raw_quote) if raw_quote else ""
        if not quote or quote not in compact_input:
            continue
        # 인용이 **수치 대조를 대신 통과시키지는 않는다**(2026-08-02). 인용문에 숫자가
        # 있는데 패치 값의 숫자와 자릿수가 어긋나면, 그 인용은 값의 근거가 아니라 값이
        # 틀렸다는 증거다 — 실측: "1000억원"(1e11)에 9B가 `value=10000000000`(1e10, 10배
        # 오차) + `source_text="1000억원"`을 냈고, 인용이 실재해 여기서 통과해 100억이
        # 조용히 확정됐다(재요청 1회 후에도 같은 값). recall_validator._reflected_numbers가
        # 인용문을 대조에서 제외하는 것과 같은 이유이며(같은 유형의 "3억원"→3천만원 사고),
        # 그 교훈이 이 게이트에는 적용돼 있지 않았다.
        if _quote_contradicts_value(raw_quote, patch.value):
            continue
        return True
    # ② 수치 대조: 패치 값의 숫자가 입력 숫자(단위 환산 포함)에 나타나면 근거 있음.
    #    크기만 대조한다(부호 무시 — recall_validator와 동일, 어느 필드의 값인지는 판단하지 않음).
    patch_numbers = _patch_value_numbers(patch.value)
    if patch_numbers and any(
        any(abs(abs(p) - abs(c)) < 1e-6 for c in input_numbers) for p in patch_numbers
    ):
        return True
    # 인용도 수치도 근거가 없으면 환각으로 거부한다. LLM이 인용을 아예 생략한
    # 무수치 패치도 거부 대상이다 — 프롬프트가 인용을 계약으로 요구한다(규칙 10).
    return False


_CONDITION_LIST_FIELDS = ("entry_conditions", "exit_conditions")


def _patch_group_key(path: str) -> Optional[str]:
    """같은 조건 객체를 겨냥한 형제 패치를 묶는 그룹 키(`/entry_conditions/0`).

    조건 객체의 **필드**를 가리키는 경로일 때만 키를 낸다 — 조건 자체를 통째로
    교체·삭제하는 경로(`/entry_conditions/0`)나 다른 슬롯(`/portfolio/...`)은 None이라
    개별 판정된다(그룹을 슬롯 단위로 넓히면 무관한 필드까지 근거를 나눠 갖는다).
    """
    tokens = [t for t in path.split("/") if t]
    if len(tokens) >= 3 and tokens[0] in _CONDITION_LIST_FIELDS and tokens[1].isdigit():
        return f"/{tokens[0]}/{tokens[1]}"
    return None


def _explicit_breakout_lookback(text: Optional[str]) -> Optional[int]:
    """신고가/고점 돌파 조건의 source_text(LLM이 인용한 조각)에서 명시적 기준 기간(거래일)을
    추출한다. 없으면 None.

    입력은 LLM 출력(source_text)이지 사용자 원문이 아니다 — 범위가 LLM이 이미 '이 조건의
    출처'라고 판정한 짧은 인용으로 한정되므로 § 3-2 지식 조회에 해당한다(2026-07-26 원문
    폴백 제거). '52주'는 거래일로 환산(52주=252, N주=N×5), 'N일'은 그대로, 단위 없는 '52'만
    1년(252). 기간 언급이 아예 없으면(예: 그냥 '신고가 돌파') None — 조용한 기본값 확정
    금지 원칙에 따라 되묻기에 맡긴다.
    """
    if not text:
        return None
    from engine.nl_parser import _compact

    match = re.search(r"(\d+)\s*(주|일)?\s*(?:신고가|최고가|고점|저점)", _compact(text))
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "주":
        return value * 5 if value < 52 else 252
    if unit == "일":
        return value
    return 252 if value == 52 else value


def _fill_deterministic_condition_params(intent: StrategyIntent) -> None:
    """LLM 인터프리터가 놓치거나 오분류한 조건을 **그 조건의 source_text**로 교정한다.

    입력은 사용자 원문이 아니라 LLM 출력이다 — LLM이 '이 조건의 출처'라고 인용한 짧은
    조각 안에서만 정본을 식별하므로 § 3-2 지식 조회에 해당한다(2026-07-26 전체 입력 폴백
    제거 — 원문 스캔은 계약 위반). LLM이 인용하지 않았으면 교정하지 않고 되묻기에 맡긴다.

    완결성 검증은 raw LLM intent에 대해 돌기 때문에, LLM의 누락/오분류가 '이미 사용자가
    말한 값'을 되묻는 사고로 이어진다. 여기서 인용에 남은 확실한 것을 미리 채워 헛질문을 막는다.

    ① breakout(신고가 돌파) lookback_period: LLM이 '52주 신고가'의 기간을 파라미터로 옮기지
       못하고 비우는 드리프트(프롬프트 규칙 5-1이 1차 방어) → 인용에 명시적 기간이 있을
       때만 채운다(없으면 그대로 두어 되묻기에 맡김).
    ② trading_value 오분류: '거래량이 평균보다 늘어난' 같은 동적 급증 표현을 LLM이 종종
       거래대금 임계 신호(trading_value=절대 억원 값 필요)로 오분류(프롬프트 규칙 5-2가
       1차 방어) → 인용이 급증 표현이면 volume_spike(임계값 불필요)로 고쳐 헛질문을 막는다.
    """
    from engine.nl_parser import _compact, _mentions_volume_surge

    strategy = intent.strategy
    if strategy is None:
        return
    for cond in list(strategy.entry_conditions) + list(strategy.exit_conditions):
        spec = REGISTRY.get(cond.factor)
        if spec is None:
            continue
        if spec.id == "technical.breakout" and cond.parameters.get("lookback_period") is None:
            lookback = _explicit_breakout_lookback(cond.source_text)
            if lookback is not None:
                cond.parameters["lookback_period"] = float(lookback)
        elif spec.id in ("technical.trading_value", "fundamental.trading_value"):
            if cond.source_text and _mentions_volume_surge(_compact(cond.source_text)):
                cond.factor = "technical.volume_spike"
                cond.operator = "crosses_above"
                cond.value = None


# ── 관측 로그 헬퍼 — dev 콘솔 [LLM-INTERPRETER] 흐름 추적용 ────────────────────
def _short(value: Any) -> str:
    """로그용 값 축약 — 긴 목록(symbols 1747개 등)은 개수로, 그 외는 100자 repr."""
    if isinstance(value, list) and len(value) > 5:
        return f"[{len(value)}개 목록]"
    text = repr(value)
    return text if len(text) <= 100 else text[:100] + "…"


def _value_diff(before: Any, after: Any) -> str:
    """값 쌍을 '이전 → 이후'로 요약한다. dict·같은 길이 목록은 다른 부분만 파고든다 —
    100자 절단 repr이 차이 지점 앞에서 잘리면 diff가 무의미해지는 것 방지(rsi mode 등)."""
    if isinstance(before, dict) and isinstance(after, dict):
        return ", ".join(
            f"{k}: {_value_diff(before.get(k), after.get(k))}"
            for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)
        )
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return "; ".join(
            f"[{i}] {_value_diff(b, a)}"
            for i, (b, a) in enumerate(zip(before, after)) if b != a
        )
    return f"{_short(before)} → {_short(after)}"


def _diff_fields(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """두 model_dump의 값이 다른 최상위 필드를 '필드: 이전 → 이후'로 요약한다."""
    return [
        f"{key}: {_value_diff(before.get(key), after.get(key))}"
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]


def fast_path_can_handle(user_input: str, previous_parsed: dict) -> bool:
    """결정론 fast-path(_modify_rule_based)가 이 수정 발화를 완전히 해석하는가?

    예외는 "내 소관 아님"으로 강등한다 — 해석 레이어의 예외가 요청을 죽이지 못하게 한다
    (오염된 previous_parsed 하나가 이후 모든 수정을 500으로 만들던 2026-07-26 사고).
    """
    from engine.nl_parser import _modify_rule_based

    try:
        return _modify_rule_based(user_input, previous_parsed) is not None
    except Exception as exc:  # noqa: BLE001
        logger.warning("modify fast-path raised, treating as not-applicable | err=%r", exc)
        return False


def _explicit_fields(strategy: Any, previous: Optional[List[str]]) -> List[str]:
    """이번 턴 LLM 출력의 명시 필드 + 이전 턴 에코를 누적한다(provenance 단일 진실 소스)."""
    from strategy_conversation.response.provenance import (
        explicit_fields_from_spec,
        merge_explicit_fields,
    )

    return merge_explicit_fields(previous, explicit_fields_from_spec(strategy))


def _modify_explicit_fields(patches: Any, previous: Optional[List[str]]) -> List[str]:
    """수정 턴의 명시 필드 — 근거는 이번 턴이 바꾼 패치다(초안 State가 아니다).

    최초 파스(_explicit_fields)와 근거가 다른 이유는 spec의 출처가 다르기 때문이다:
    최초 파스의 spec은 LLM이 사용자 발화에서 뽑은 것이지만, 수정 턴의 spec은
    **이전 전략 디컴파일 초안 + 패치**라 물질화 기본값이 이미 들어 있다.
    """
    from strategy_conversation.response.provenance import (
        explicit_fields_from_patches,
        merge_explicit_fields,
    )

    return merge_explicit_fields(previous, explicit_fields_from_patches(patches))


def derive_field_states(
    parsed: Any, explicit_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, str]]:
    """파이프라인 불변조건 — **어느 레인이 응답을 만들었든** 파생 상태를 매 턴 재계산한다.

    파생 상태는 저장되지 않는다. 그래서 "이번 턴에 계산하지 않았다"는 곧 프론트가 직전
    턴의 사본을 계속 들고 있다는 뜻이고, 전략이 바뀐 턴에서는 그것이 틀린 표시가 된다
    (실측: 칩 답변으로 최대 보유가 10→5로 바뀌어도 상태 맵은 이전 턴 것이 그대로 남았다).
    그래서 이 계산은 planner·인터프리터의 출력 여부와 무관하게 항상 돈다.

    ParsedStrategy만으로 시작해 StrategySpec을 되짚고(decompile) 검증기를 돌려 파생 축을
    채운다 — 인터프리터 레인이 이미 (strategy, report)를 들고 있으면 그쪽을 쓰는 것이 싸므로
    `_field_states`를 직접 호출한다. 되짚기·검증 실패는 오버라이드 없음으로 강등한다
    (값 축과 NOT_APPLICABLE은 ParsedStrategy만으로 성립하므로 계산 자체는 살아남는다).

    입력은 ParsedStrategy로 정규화한다 — 응답 payload의 `parsed`는 dict(model_dump)라
    호출부(main._ensure_field_states)가 그대로 넘긴다. dict를 그냥 흘리면 되짚기가
    AttributeError로 죽고 값 축까지 전부 UNKNOWN으로 무너져(모든 슬롯 실측), 인터프리터
    레인 밖의 모든 턴이 빈 상태 표시를 받는다(2026-07-31 실측).
    """
    from engine.nl_parser import ParsedStrategy

    if isinstance(parsed, dict):
        parsed = ParsedStrategy.model_validate(parsed)
    strategy = report = None
    try:
        from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
        from strategy_conversation.interpreter.models import StrategyIntent
        from strategy_conversation.validation.pipeline import run_validation

        strategy = decompile_strategy(parsed)
        _, report = run_validation(
            StrategyIntent(intent="CREATE_STRATEGY", strategy=strategy, confidence=1.0))
    except Exception:  # noqa: BLE001 — 되짚기 실패는 파생 축의 범위를 좁힐 뿐이다
        logger.warning("파생 상태 재검증 실패 — 오버라이드 없이 계산", exc_info=True)
        strategy = report = None
    return _field_states(parsed, strategy, report, explicit_fields)


def _field_states(
    parsed: Any, strategy: Any, report: Any, explicit_fields: Optional[Iterable[str]],
) -> Dict[str, Dict[str, str]]:
    """진행 골격 8칸의 두 상태 축(설계 스펙 § 5)을 계산해 응답에 실을 형태로 만든다.

    `filled_slots`(완료/미완료)가 뭉개던 것을 나눠 준다 — 해당 없음(단독 종목의 최대
    보유·리밸런싱), 값은 있으나 미확인(기본값 물질화), 확인 필요(미지원 지표·모순).
    되묻기 게이트와 실행 버튼은 이 값을 쓰지 않는다(표시 전용 — 흐름 동작 불변).

    반환 형태는 슬롯 → {"value": …, "derived": …}. 두 축을 하나로 줄이지 않는 이유는
    "값은 확정인데 지금 유니버스에서 못 쓴다"가 표현돼야 하기 때문이다.

    검증 실패로 리포트·spec이 없어도 진행은 막지 않는다 — 상태 축은 부가 정보다.
    strategy·report가 없는 레인(칩 답변 등)에서도 값 축은 계산되고, 파생 축은
    오버라이드 없이 ParsedStrategy만으로 산출된다(계산의 누락이 아니라 입력의 범위).
    """
    from strategy_conversation.validation.field_state import slot_status_overrides

    try:
        overrides = slot_status_overrides(strategy, report)
        return {
            slot: state.as_payload()
            for slot, state in strategy_slots.slot_statuses(
                parsed,
                explicit_fields=explicit_fields,
                require_explicit=True,
                status_overrides=overrides,
            ).items()
        }
    except Exception:  # noqa: BLE001 — 표시용 부가 정보가 파스를 깨면 안 된다
        logger.warning("필드 상태 축 계산 실패 — 생략", exc_info=True)
        return {}


def run_primary_parse(
    user_input: str, on_stage=None,
    previous_explicit_fields: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """LLM Interpreter 기본 경로 실행. 성공 시 결과 dict, 해석 실패 시 None.

    None은 "규칙 파서로 재해석하라"가 아니라 실패 보고다 — 호출부(main)는 되묻기
    (interpretation_failed)로 끝낸다(계약 § 8, 1c 폴백 차단, 2026-07-26). LLM 서버
    연결 장애는 None으로 삼키지 않고 그대로 던진다 — 인프라 장애가 "입력을 바꿔라"로
    위장되지 않게 main의 503 경로(_is_llm_connection_error)가 처리한다.

    반환: {"parsed": ParsedStrategy, "clarification_question": str|None,
           "clarification_suggestions": [str]|None, "notices": [str],
           "interpreter": 관측 메타}
    """
    from strategy_conversation.compiler.strategy_compiler import StrategyCompileError
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.tools import call as call_tool

    if on_stage is not None:
        on_stage("thinking")
    # Phase 5(2026-07-28): 제어 역전 — planner가 파스 최선두에서 실행된다(Universe-first).
    # 유니버스 표현의 추출·분류·해석을 planner가 소유해, 인터프리터 sectors 필드 누락이
    # 유니버스 해석 체인 전체를 침묵시키던 '보안주' 사고를 구조적으로 차단한다.
    # 실패(None)·비활성(off/shadow)은 현행 고정 파이프라인 그대로 — 폴백 레인 보존.
    planner_first: Optional[Any] = None
    if config.dag_planner_mode() == "primary":
        planner_first = _plan_first(user_input)
    # Phase 4 shadow: DAG planner 관측 실행(기본 off, STRATEGY_DAG_PLANNER_MODE=shadow)
    # — 대화 턴 전체를 DAG로 계획하는 실험 레인. 비차단·응답 불변, 로그만 남긴다.
    try:
        from strategy_conversation.planner.dag_shadow import maybe_shadow_plan_dag

        maybe_shadow_plan_dag(user_input)
    except Exception:  # noqa: BLE001 — 관측 실행 실패가 파스를 깨면 안 된다
        logger.debug("dag planner shadow launch failed", exc_info=True)
    try:
        interpreter = _get_interpreter(StrategyInterpreter)
        result = interpreter.interpret(user_input)
    except InterpreterError as exc:
        logger.warning("interpreter primary failed, reporting failure | err=%s",
                       str(exc)[:200])
        return None

    _fill_deterministic_condition_params(result.intent)
    # 검증 전 스냅샷: capability validator는 정본 목록 밖 섹터 표현('이재명 관련주')을
    # 미지원으로 판정하며 universe.sectors에서 제거한다. term-in 해석 체인(§ 11-3)의
    # 입력은 'LLM이 뽑은 표현'이므로 제거 전 값을 보존해야 한다 — 검증 후 값을 읽으면
    # 미지 테마가 체인에 도달하지 못하고 미지원 안내로 소실된다(2026-07-26 회귀).
    pre_validation_sectors: List[str] = (
        list(result.intent.strategy.universe.sectors)
        if result.intent.strategy is not None else []
    )
    validation = call_tool("validate_intent", intent=result.intent)
    validated, report = validation.intent, validation.report
    _log_llm("✓ 검증", (
        f"status={report.status} 오류={len(report.errors)} 누락={len(report.missing_fields)} "
        f"질문={len(report.clarification_questions)} 미지원={report.unsupported_features or '[]'}"
    ))
    if validated.intent not in _STRATEGY_INTENTS or validated.strategy is None:
        _log_llm("↩ 실패 보고", f"전략 파이프라인 대상이 아닌 intent={validated.intent} — 되묻기로")
        logger.info("interpreter primary non-strategy intent=%s, reporting failure",
                    validated.intent)
        return None

    notices: List[str] = list(report.warnings)
    try:
        compiled = call_tool("compile_strategy", intent=validated, report=report,
                             user_input=user_input, partial=not report.is_valid)
        parsed, dropped = compiled.parsed, compiled.dropped
    except StrategyCompileError as exc:
        logger.warning("interpreter primary compile failed, reporting failure | err=%s", exc)
        return None
    _log_llm("✓ 컴파일", (
        f"{'전체' if report.is_valid else '부분'} 컴파일 — 제외 조건: {', '.join(dropped) or '없음'}"
    ))
    # 레거시 파서와 동일한 결정적 보정 전체를 적용한다 — 명시적 날짜·지정 종목만 부분
    # 적용하던 시절, '최근 3년'→MA 365일 오귀속(QA 11-1), 익절 0.0001% 드롭(14-5),
    # 시총 100조→100억 단위 오류(24-2), 슬리피지 드롭(24-10) 등 인터프리터 LLM의 수치
    # 드리프트가 그대로 노출됐다. 프롬프트에 명시된 값만 덮어쓰므로 인터프리터 해석과
    # 충돌하지 않는다(레거시 LLM 폴백과 같은 계약).
    if config.prompt_overrides_enabled():
        from engine.nl_parser import _apply_prompt_overrides
        compiled_dump = parsed.model_dump()
        parsed = _apply_prompt_overrides(parsed, user_input)
        override_diff = _diff_fields(compiled_dump, parsed.model_dump())
        if override_diff:
            _log_llm("✓ 결정적 보정", "; ".join(override_diff))
    # 보정이 결정적으로 되살린 진입/청산 조건의 되묻기 질문을 지운다 — 완성 전략을 다시
    # 되묻는 사고 방지(흑자 기업 등 LLM 누락 → eps>0 필터로 복원됐는데 진입 질문 잔존).
    _prune_clarifications_filled_by_overrides(report, parsed)
    # Phase 5: planner-first 관찰값의 결정론 적용 — planner가 최선두에서 해석한
    # 유니버스(테마 상장사·학습 섹터)를 확정값으로 병합한다(관찰값에서만 채택,
    # 적용은 고정 체인과 동일한 결정론 경로 재사용).
    planner_resolved_terms: set = set()
    planner_unresolved_terms: set = set()
    if planner_first is not None:
        planner_resolved_terms, planner_unresolved_terms = _apply_planner_first_universe(
            planner_first, parsed, notices
        )
    # 범위 모호성(카탈로그 후보 2개 이상) 되묻기는 **결정론이 소유한다** — planner가
    # 유니버스 ask를 계획하지 않고 조건 ask로 드리프트해도('미용기기' 사고 2026-07-28)
    # 관찰된 후보가 있으면 여기서 범위 질문을 확정한다(질문 문구는 planner 유니버스
    # ask가 있으면 그것을, 없으면 고정 템플릿).
    planner_scope_question: Optional[str] = None
    planner_scope_chips: Optional[List[str]] = None
    planner_scope_terms: set = set()
    if planner_first is not None and planner_unresolved_terms:
        scope = _planner_scope_ask(planner_first, planner_unresolved_terms)
        if scope is not None:
            planner_scope_question, planner_scope_chips, planner_scope_terms = scope
            # 범위 질문이 나가는 표현의 미지원 안내는 지운다 — 질문이 그 표현을 다루는데
            # "반영되지 않았어요" 안내가 함께 나가면 모순.
            if report.unsupported_features:
                report.unsupported_features = [
                    f for f in report.unsupported_features
                    if not any(t and t in f for t in planner_scope_terms)
                ]
    # § 11-3 (1c′, 2026-07-26): 미해결 업종/테마 표현의 term-in 해석 체인.
    # 입력은 원문이 아니라 LLM이 universe.sectors로 뽑은 표현 중 리졸버가 못 푼 것만
    # (§ 3-2 지식 조회). 체인: KG 테마 상장사 → 검색 그라운딩 학습 → 되묻기/종결 안내.
    # 레거시 레인의 원문 스캔(apply_theme_universe·detect_unresolved_sector_clarification·
    # 파싱 전 어휘집 학습)은 off/shadow 기본 경로에만 남는다(1d 이관 대상).
    # 이 위치(미지원 프루닝·target_symbols 질문 프루닝 앞)여야 학습된 섹터·적용된 테마
    # 종목이 아래 프루닝에 반영된다.
    sector_question: Optional[str] = None
    sector_suggestions: Optional[List[str]] = None
    unresolved_sector_terms: List[str] = []
    # ETF 유니버스는 제외 — validator가 테마를 etf_theme로 승격하고 sectors를 비운다.
    if pre_validation_sectors and "ETF" not in validated.strategy.universe.markets:
        unresolved_sector_terms = _sector_terms_for_chain(pre_validation_sectors)
    # 체인 제외는 planner가 **실제로 종결한** 표현만: 해석 완료분 + 범위 질문이 나가는
    # 모호 표현. planner가 건드리고도 못 푼 나머지 표현은 반드시 체인으로 흘려보낸다 —
    # 무조건 제외하면 planner 드리프트 시 표현이 어느 레인에도 속하지 않고 증발한다
    # ('미용기기' 사고: KG에 상장사 19곳이 있는데 검색·되묻기 없이 미지원 안내만 남음).
    if planner_resolved_terms or planner_scope_terms:
        handled_keys = {
            t.replace(" ", "").lower()
            for t in (planner_resolved_terms | planner_scope_terms)
        }
        unresolved_sector_terms = [
            t for t in unresolved_sector_terms
            if t.replace(" ", "").lower() not in handled_keys
        ]
    if unresolved_sector_terms:
        if config.planner_mode() == "primary":
            # Phase 3 승격(2026-07-26): 미해석 표현 구간을 planner가 담당 —
            # planner 실패는 표현 단위로 아래 고정 체인 폴백(단독 실패 지점 불가).
            sector_question, sector_suggestions = _resolve_sector_terms_planner_primary(
                parsed, unresolved_sector_terms, notices, on_stage=on_stage,
            )
        else:
            # Phase 3 shadow: mini-planner 관측 실행(기본 off, STRATEGY_PLANNER_MODE=
            # shadow) — 학습 전 상태를 관측하도록 term-in 체인보다 먼저 띄운다(비차단).
            try:
                from strategy_conversation.planner.shadow import maybe_shadow_plan

                maybe_shadow_plan(unresolved_sector_terms)
            except Exception:  # noqa: BLE001 — 관측 실행 실패가 파스를 깨면 안 된다
                logger.debug("planner shadow launch failed", exc_info=True)
            sector_question, sector_suggestions = _resolve_sector_terms_term_in(
                parsed, unresolved_sector_terms, notices, on_stage=on_stage,
            )
    # 보정·term-in 체인이 섹터를 해석했으면(검색 그라운딩 학습분·테마 상장사 적용 포함)
    # 같은 테마를 가리키는 미지원 안내도 지운다 — "'마운자로 관련주'는 반영되지 않았어요"가
    # 반영된 전략과 모순.
    if (parsed.sector or parsed.target_symbols) and report.unsupported_features:
        from engine.nl_parser import _extract_sector
        # 체인이 전부 해석했으면(sector_question 없음) 그 표현들의 미지원 항목도 지운다 —
        # 검증기가 걸렀던 '섹터 X'가 테마 상장사로 반영됐는데 안내가 남으면 모순.
        resolved_theme_terms = unresolved_sector_terms if sector_question is None else []
        report.unsupported_features = [
            f for f in report.unsupported_features
            if _extract_sector(f) is None
            and not any(t and t in f for t in resolved_theme_terms)
        ]
    # ETF 테마가 반영됐으면 같은 테마를 가리키는 미지원 안내도 지운다 — 실측 사고
    # (2026-07-27): etf_theme="배당"으로 반영된 전략에 "'배당 조건'은 아직 지원되지 않아요"
    # 안내가 함께 나갔다(모델이 테마를 etf_theme와 unsupported_features 양쪽에 넣은 드리프트).
    if parsed.etf_theme and report.unsupported_features:
        theme_key = parsed.etf_theme.replace(" ", "").lower()
        report.unsupported_features = [
            f for f in report.unsupported_features
            if theme_key not in (f or "").replace(" ", "").lower()
        ]
    if parsed.target_symbols:
        # 지정 종목 전략의 청산 누락은 호출부 공유 보정(apply_single_asset_adjustments)이
        # 반대 신호 청산 추천/기간 종료 보유 안내(비차단 notices)로 처리한다(FR-STR-068) —
        # 정기 리밸런싱을 추천하는 유니버스형 되묻기 질문은 지정 종목에 맞지 않아 제거한다.
        report.clarification_questions = [
            q for q in report.clarification_questions
            if q.field != "strategy.exit_conditions"
        ]

    # 종목명 오타 되묻기(term-in) — 입력은 원문이 아니라 LLM이 universe.symbols로 뽑았는데
    # 리졸버가 못 푼 표현뿐이다(계약 § 3-2). 원문 토큰을 마스터에 근접 매칭하던 레거시
    # 스캔은 "20일 고점을 넘기는 날"의 '넘기는'을 '삼기'로 오탐했다(2026-07-29).
    symbol_question, symbol_suggestions = _symbol_typo_term_in(validated.strategy, parsed, user_input)

    clarification_question, clarification_suggestions, fallback_topic = _build_clarification(
        report, validated)
    clarification_priority = None
    pending_ask: Optional[Dict[str, Any]] = None
    # 결속 체인 관찰용 — 어느 게이트에서 pending_ask가 끊겼는지 이름 붙이기 위한 값들.
    ask_reject_reason: Optional[str] = None
    chips_offered: Optional[List[str]] = None
    # 슬롯 판정(engine.strategy_slots)은 provenance를 함께 본다 — 값만 보면 기본값
    # 물질화가 '이미 채워짐'이 돼 planner가 그 슬롯을 영영 묻지 않는다(FR-STR-019k).
    turn_explicit_fields = _explicit_fields(validated.strategy, previous_explicit_fields)
    if planner_scope_question is not None:
        # Phase 5: 범위 모호성 되묻기(결정론 소유) — 유니버스 범위는 모든 조건보다
        # 선행 결정 사항이라 어떤 질문보다 먼저 나간다. 칩은 관찰된 카탈로그 후보
        # 표기 그대로라 클릭 시 결정론 귀속(카탈로그 정확 일치)이 성립한다.
        clarification_question, clarification_suggestions = (
            planner_scope_question, planner_scope_chips
        )
        clarification_priority = "dag_planner"
        chips_offered = list(clarification_suggestions or [])
        pending_ask = _pending_ask_payload(
            clarification_question, clarification_suggestions, "유니버스"
        )
    elif sector_question is not None:
        # 종목 범위(유니버스/섹터)는 진입 조건보다 선행 결정 사항 — 미해결 업종 질문이
        # 조건 질문보다 우선하고, 우선순위 마커로 프론트 explicit 게이트 삼킴을 막는다
        # (레거시 sector_reask와 동일 계약).
        clarification_question, clarification_suggestions = sector_question, sector_suggestions
        clarification_priority = "sector_unresolved"
    elif symbol_question is not None:
        # 종목 범위는 조건보다 선행 결정 사항 — 조용히 전체 시장으로 강등하지 않는다.
        clarification_question, clarification_suggestions = symbol_question, symbol_suggestions
        clarification_priority = "sector_unresolved"
    elif planner_first is not None:
        # Phase 5: planner는 이 턴 최선두에서 이미 실행됐다 — 재계획 재호출 없이 그
        # ask를 소비한다. 유니버스 ask는 위 범위 되묻기(결정론)가 소유하므로 여기서는
        # 조건 슬롯 ask만, 결정론 게이트가 공백을 인정할 때 채택한다(완성 전략
        # 재질문·관찰과 모순되는 질문 방지). 채택 불가면 검증 리포트의 고정 질문 유지.
        planner_ask, ask_reject_reason = _planner_first_ask(
            planner_first, parsed, user_input, turn_explicit_fields)
        if planner_ask is not None:
            clarification_question, clarification_suggestions, dag_topic = planner_ask
            clarification_priority = "dag_planner"
            pending_ask, clarification_suggestions = _bound_ask_with_slot_fallback(
                clarification_question, clarification_suggestions, dag_topic, parsed
            )
            chips_offered = list(clarification_suggestions or [])
            # 결속된 칩만 보인다 — 전부 탈락하면 질문은 남기고 자유 서술로 받는다.
            clarification_suggestions = pending_ask["chips"] if pending_ask else None
    # planner-first가 실패(None)한 턴의 '재계획' 분기는 제거됐다(2026-07-29). planner는
    # mode=primary인 모든 턴에서 이미 최선두로 돌기 때문에, 그 분기는 **실패한 계획을
    # 처음부터 다시 세우는 재시도 전용**이었다 — 값은 거의 못 얻으면서 LLM 턴 예산을 한 벌
    # 더 쓴다(실측: 예산 소진 → 재계획으로 planner가 한 파스에서 6회 호출, 148초 + 84초).
    # 예산 소진은 실패가 아니라 검증 리포트의 고정 질문으로 폴백하는 정상 경로다.
    # (_dag_planner_clarification 자체는 칩 답변 턴의 재계획 _replan_next_question이 계속 쓴다.)
    # 고정 파이프라인 질문의 결속(2026-07-31). 지금까지 pending_ask는 planner 분기
    # 두 곳에서만 발행됐다 — planner가 실패하거나(예산 소진) 가드가 그 ask를 거부하면
    # (_is_filled_slot_topic) 폴백인 검증 리포트 질문에는 결속이 없었고, 사용자의 다음
    # 답변은 "어느 질문의 답인지" 근거를 잃고 일반 분류 레인으로 떨어졌다. 가드 판단은
    # 옳다 — 잃지 말아야 할 것은 **폴백의 결속**이다.
    # 미해결 업종·종목 질문(sector_unresolved)은 제외한다: 그 칩은 값이 아니라 후보
    # 표기라 값 결속 계약(_bind_chips)의 대상이 아니다.
    if pending_ask is None and clarification_priority != "sector_unresolved":
        chips_offered = list(clarification_suggestions or [])
        pending_ask = _pending_ask_payload(
            clarification_question, clarification_suggestions, fallback_topic, parsed
        )
        if pending_ask is not None:
            # 결속된 칩만 보인다 — planner 분기와 같은 계약.
            clarification_suggestions = pending_ask["chips"]

    # 인터프리터의 unsupported_features를 그대로 인용하던 안내는 폐지했다(2026-08-01,
    # 사용자 판단). LLM이 자유 서술로 쓰는 채널이라 내부 사정("unsupported_features에
    # 기록합니다")·지원되는 필드명(risk_management.stop_loss)·발화 조각이 그대로 노출됐고,
    # 정작 미지원 개념 안내는 결정론 게이트(build_unsupported_concept_notice)가 이미 낸다.
    # 조용한 누락 방지는 아래 두 결정론 대조(제외 조건·미반영 수치)가 계속 담당한다.
    # 제외됐지만 질문이 다루지 않는 조건이 있으면 정직하게 알린다
    unexplained_drops = [d for d in dropped if d not in " ".join(
        [clarification_question or ""] + notices
    )]
    if unexplained_drops:
        notices.append(
            f"'{', '.join(unexplained_drops)}' 조건은 값 확인 전까지 전략에 반영되지 않았어요."
        )
    # 미반영 수치 **안내**는 폐지했다(2026-08-01, 사용자 판단) — 로그로만 남긴다.
    # 대조는 크기만 보는 수치 대조라 라벨이 맥락 없는 숫자 나열("'1, 20일' 수치는…")이 되고,
    # 정작 '월 1회 리밸런싱'·'20일 평균 거래대금'처럼 **이미 반영된** 표현이 자주 걸린다
    # (표현형이 달라 숫자가 남지 않을 뿐이다). 사용자가 무엇을 다시 말해야 하는지 알 수 없는
    # 안내라 정보값이 없다. 재요청 증거로서의 쓰임(_recall_gap → 인터프리터 재생성)은 그대로다.
    if result.unreflected_numbers:
        from strategy_conversation.validation.recall_validator import labels_absent_from

        # description은 사용자 원문 그대로라 대조 대상에서 뺀다 — 넣으면 입력에 있는 모든
        # 수치가 자기 자신과 매칭돼(원문 에코) 대조가 영구히 침묵한다.
        strategy_payload = parsed.model_dump()
        strategy_payload.pop("description", None)
        still_missing = labels_absent_from(result.unreflected_numbers, strategy_payload)
        if still_missing:
            _log_llm("△ 미반영(안내 없음)", f"{', '.join(still_missing)}")

    # 결속 체인 판정 — 되묻기로 끝나는 턴인데 pending_ask가 없으면 다음 턴의 답변은
    # 귀속 근거 없이 일반 분류 레인으로 떨어진다. 그 손실이 어느 게이트에서 났는지를
    # 남긴다(관찰 전용 — 응답도 실행도 바꾸지 않는다).
    from observability import span
    from observability.agent_trace import ask_binding_gate

    ask_gate = ask_binding_gate(
        question=clarification_question,
        priority=clarification_priority,
        chips_offered=chips_offered,
        pending_ask=pending_ask,
        planner_mode_primary=config.dag_planner_mode() == "primary",
        planner_ran=planner_first is not None,
        ask_reason=ask_reject_reason,
    )
    if ask_gate["gate"] != "no_question":
        with span("Ask 결속", "state", inputs={"question": clarification_question},
                  metadata={"ask_gate": ask_gate["gate"]}) as _trace:
            _trace.output(**ask_gate)
        if not ask_gate["bound"]:
            _log_llm("🔗 결속 소실", (
                f"gate={ask_gate['gate']} 칩={ask_gate['chips_bound']}/"
                f"{ask_gate['chips_offered']}"
                + (f" 탈락={ask_gate['chips_dropped']}" if ask_gate.get("chips_dropped") else "")
            ))

    return finalize_user_response({
        "parsed": parsed,
        "clarification_question": clarification_question,
        "clarification_suggestions": clarification_suggestions,
        "clarification_priority": clarification_priority,
        "pending_ask": pending_ask,
        "explicit_fields": turn_explicit_fields,
        "field_states": _field_states(
            parsed, validated.strategy, report, turn_explicit_fields
        ),
        "notices": notices,
        "interpreter": {
            "mode": "primary",
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
            "repair_attempts": result.repair_attempts,
            "llm_latency_ms": result.latency_ms,
            "validation_status": report.status,
            "confidence": validated.confidence,
        },
    })


def _self_doubt_patch_fields(patches: List[Any], questions: List[Any]) -> List[str]:
    """패치 대상 필드와 인터프리터 자신의 질문 필드가 겹치는 필드 목록(형식 비교만).

    입력은 전부 LLM 구조화 출력이다 — 패치 경로("/universe/markets/0")와 질문 필드
    ("universe.markets" 또는 "strategy.universe.markets")를 정규화해 비교한다.
    """
    def _norm_path(path: str) -> str:
        parts = [p for p in (path or "").strip("/").split("/")
                 if p and not p.isdigit() and p != "-"]
        return ".".join(parts)

    def _norm_field(field: str) -> str:
        f = field or ""
        if f.startswith("strategy."):
            f = f[len("strategy."):]
        return re.sub(r"\[\d+\]", "", f)

    question_fields = {
        _norm_field(getattr(q, "field", "") or "") for q in (questions or [])
    }
    question_fields.discard("")
    overlaps: List[str] = []
    for p in patches or []:
        patch_field = _norm_path(getattr(p, "path", "") or "")
        if patch_field and any(
            patch_field == qf or patch_field.startswith(qf + ".")
            or qf.startswith(patch_field + ".")
            for qf in question_fields
        ):
            overlaps.append(patch_field)
    return overlaps



def _symbol_typo_term_in(
    strategy: Any, parsed: Any, user_input: str
) -> tuple[Optional[str], Optional[List[str]]]:
    """LLM이 종목명이라고 판정한 표현 중 리졸버가 못 푼 것만 오타 되묻기 후보로 넘긴다.

    이미 종목이 해석됐으면(target_symbols) 되묻지 않는다 — 일부만 실패한 경우는
    해석된 종목으로 진행하고, 미해석 표현은 상위의 미반영 안내가 다룬다.
    """
    if getattr(parsed, "target_symbols", None):
        return None, None
    refs = list(getattr(getattr(strategy, "universe", None), "symbols", None) or [])
    if not refs:
        return None, None
    from strategy_conversation.registry.universe_resolver import resolve_symbols

    _codes, unresolved = resolve_symbols(refs)
    if not unresolved:
        return None, None
    from engine.nl_parser import detect_symbol_typo_clarification

    return detect_symbol_typo_clarification(parsed, user_input, terms=unresolved)


def _dag_state_summary(
    parsed: Any, explicit_fields: Optional[Iterable[str]] = None
) -> Dict[str, Any]:
    """DAG planner에 넘길 '이미 결정된 전략 State' 요약 — 재질문 방지 근거.

    입력은 결정론 파이프라인 산출물(ParsedStrategy)이며 원문 해석이 아니다.
    신호는 타입만 요약한다(planner의 판단 근거로 충분 — 프롬프트 비대 방지).
    explicit_fields는 provenance(사용자가 실제로 말한 설정) — 없으면 기본값 물질화가
    '이미 채워짐'으로 보여 planner가 그 슬롯을 영영 묻지 않는다(FR-STR-019k).
    """
    def _signal_types(signals: Any) -> List[str]:
        types: List[str] = []
        for s in signals or []:
            t = (s.get("indicator") if isinstance(s, dict)
                 else getattr(s, "indicator", None))
            if t:
                types.append(str(t))
        return types

    summary: Dict[str, Any] = {}
    for field in ("universe", "sector", "etf_theme", "target_symbols",
                  "new_listing_only", "listing_from", "listing_to", "max_positions",
                  "rebalancing_period", "ranking_metric", "ranking_lookback_days",
                  "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
                  "hold_period_days", "backtest_period", "initial_capital"):
        value = getattr(parsed, field, None)
        if value:
            summary[field] = value
    entry_types = _signal_types(getattr(parsed, "entry_signals", None))
    exit_types = _signal_types(getattr(parsed, "exit_signals", None))
    filters = getattr(parsed, "fundamental_filters", None) or []
    if entry_types:
        summary["entry_signal_types"] = entry_types
    if exit_types:
        summary["exit_signal_types"] = exit_types
    if filters:
        summary["fundamental_filter_count"] = len(filters)
    # 골격 슬롯 충족 판정은 결정론으로 계산해 내려준다 — 9B가 원시 필드에서 추론하게
    # 두면 랭킹(ranking_metric)이 매수 조건 슬롯을 채운다는 것을 놓친다("최근 3개월
    # 수익률 상위 매수" 후 매수 조건 재질문 사고). 판정의 정본은 engine.strategy_slots
    # 하나이며, 되묻기 게이트·프론트 진행률도 같은 술어를 쓴다.
    filled_slots = strategy_slots.filled_slots(
        parsed, explicit_fields=explicit_fields, require_explicit=True,
    )
    summary["filled_slots"] = filled_slots
    return summary


def _dag_planner_clarification(
    user_input: str, parsed: Any, explicit_fields: Optional[Iterable[str]] = None
) -> Optional[tuple[str, Optional[List[str]], Optional[str]]]:
    """DAG planner primary — 다음 되묻기 질문·칩을 planner가 계획한다(Phase 4).

    planner 질문은 내부에서 이미 output_guard를 통과했고, 반환 후 finalize_user_response
    관문을 한 번 더 지난다. 실패(None)·예외·ask 아닌 결과는 기존 고정 질문 유지 —
    planner는 단독 실패 지점이 될 수 없다.
    반환: (질문, 칩, ask 노드의 topic) — topic은 pending_ask(칩 답변 귀속 근거)로 노출된다.
    """
    try:
        from strategy_conversation.planner.dag_planner import plan_strategy_dag
        from strategy_conversation.planner.shadow import _default_chat

        result = plan_strategy_dag(
            user_input, _default_chat(),
            state_summary=_dag_state_summary(parsed, explicit_fields),
        )
    except Exception:  # noqa: BLE001 — planner 장애가 파스를 깨면 안 된다(기존 질문 유지)
        logger.warning("dag planner primary 실행 실패 — 기존 질문 유지", exc_info=True)
        return None
    if result is None or result.outcome != "ask" or not result.question:
        return None
    _log_llm("? DAG planner 질문", result.question)
    return result.question, (list(result.chips) or None), result.topic


# 칩 결속에서 '값'으로 세지 않는 필드 — description은 발화 원문 보관용이라 전략을
# 바꾸지 않는다. 이 필드만 달라진 칩은 결속 실패다(무변경을 반영으로 오보고하던 구멍).
_CHIP_BINDING_IGNORED_FIELDS = frozenset({"description"})

# 확정 판정용 프로브 — 필드 ↔ (ParsedStrategy 속성, 현재값과 반드시 다른 유효 대체값).
# 대체값은 스키마가 허용하는 값 중 현재값이 아닌 것을 고른다(Literal은 다른 멤버, 수치는
# 범위 안의 다른 값). 물질화 기본값과 같은 칩을 눌렀을 때 "이 칩이 정말 이 필드를
# 그 값으로 정하는가"를 확인하는 데만 쓰인다.
_CONFIRM_PROBES: Dict[str, tuple[str, Any, Any]] = {
    strategy_slots.MAX_POSITIONS: ("max_positions", 1, 2),
    strategy_slots.REBALANCING: ("rebalancing_period", "monthly", "quarterly"),
    strategy_slots.BACKTEST_PERIOD: ("backtest_period", "1y", "3y"),
    strategy_slots.INITIAL_CAPITAL: ("initial_capital", 5_000_000.0, 30_000_000.0),
}


def _confirm_target(base: Dict[str, Any], chip_text: str, topic: Optional[str]) -> Optional[str]:
    """값을 바꾸지 않는 칩이 '현재값 확정'인지 판정한다(설계 스펙 § 7 CONFIRM).

    값이 안 바뀌는 칩에는 두 가지가 섞여 있다 — ① 엔진이 표현할 수 없는 칩(결속 실패)과
    ② **이미 물질화된 기본값과 같은 값을 가리키는 칩**이다. 둘을 구분하지 않고 전부
    떨어뜨리면, 우리가 물어놓고 화면에 보여준 그 값을 사용자가 선택할 방법이 사라진다
    (실측: "최대 몇 종목?"에서 '최대 10종목', "초기 자금?"에서 '1,000만원'이 사라짐 —
    현재값과 같다는 이유로 "표현할 수 없어 노출 제외"로 기록되고 있었다).

    구분은 프로브로 한다: 그 필드를 **현재값이 아닌 값**으로 바꿔 둔 State에 칩을 적용해
    현재값으로 되돌아오면, 그 칩은 그 필드를 그 값으로 정하는 칩이다(② 확정). 되돌아오지
    않으면 그 필드를 정하지 못하는 칩이다(① 결속 실패 — 기존대로 탈락).
    "패치가 비었으니 topic의 확정"으로 추정하지 않는 이유는, 그 추정이 아무 뜻도 결속되지
    않은 칩을 사용자 확정으로 둔갑시켜 되묻기를 삼키기 때문이다(말하지 않은 값 확정 금지).
    """
    field = strategy_slots.confirmable_field_for_topic(topic)
    probe = _CONFIRM_PROBES.get(field or "")
    if probe is None:
        return None
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    attr, first, second = probe
    current = base.get(attr)
    probe_value = second if first == current else first
    try:
        after = _apply_prompt_overrides(
            ParsedStrategy.model_validate({**base, attr: probe_value}), chip_text,
            skip_signal_validation=True, preserve_universe=True,
        )
    except Exception:  # noqa: BLE001 — 프로브 실패는 확정 불가일 뿐 파스 실패가 아니다
        logger.warning("확정 칩 프로브 실패 | chip=%s field=%s", chip_text, field, exc_info=True)
        return None
    return field if getattr(after, attr, None) == current else None


def _bind_chips(
    chips: List[str], parsed: Any, topic: Optional[str]
) -> tuple[List[str], Dict[str, Dict[str, Any]], Dict[str, str]]:
    """칩이 뜻하는 State 변경을 **발행 시점에** 확정한다(칩=값 결속 계약).

    칩은 우리 agent가 만들어 보여준 열거형 선택지다 — 값은 보여주는 순간 이미 알고
    있어야 하고, 클릭은 그 값을 꺼내 쓰는 행위여야 한다(재해석 금지). 그래서
    ① 결속되는 칩만 사용자에게 보이고 ② 클릭은 여기서 저장한 값을 그대로 적용한다.
    여기서 결속하지 못한 칩은 엔진이 표현할 수 없는 조건이므로 애초에 내보내지 않는다
    (2026-07-29 사고: planner가 지어낸 '거래량 급감(전일 대비 1/2 이하) 시 매도'가
    그대로 노출됐고, 클릭하면 volume 하락은 registry에 없어 미해석 안내로 끝났다).
    미지원 개념을 언급하는 칩은 **부분 결속에 성공해도** 내보내지 않는다
    (2026-08-02 사고: '거래량 급증(전일 대비 3배) 시 매수'는 '거래량 급증'만
    volume_spike로 결속돼 필터를 통과했고, 배수 조건은 조용히 소실된 채 노출됐다 —
    칩 텍스트는 planner LLM 출력이므로 미지원 개념 검사는 결정론 레인이다).

    유니버스 범위 칩은 여기서 다루지 않는다 — 칩이 카탈로그 후보 표기 그대로라 결속이
    이미 보장돼 있고(_planner_scope_ask), 결속 시도가 테마 상장사 조회를 칩 수만큼
    반복해 발행 지연을 키운다. 클릭 시 _apply_universe_chip이 결정론으로 적용한다.

    값을 바꾸지 않는 칩 중 현재값을 그대로 가리키는 것은 탈락시키지 않고 **확정 칩**으로
    결속한다(_confirm_target, § 7 CONFIRM) — 값은 그대로 두고 상태만 PROVISIONAL →
    CONFIRMED로 올린다.
    반환: (보여줄 칩, {칩: {필드: 값}}, {칩: 확정 필드})."""
    if _is_universe_topic(topic):
        return list(chips), {}, {}
    from engine.nl_parser import (
        ParsedStrategy, _apply_prompt_overrides, _mentioned_unsupported_concepts,
    )

    try:
        base = ParsedStrategy.model_validate(
            parsed.model_dump() if hasattr(parsed, "model_dump") else parsed
        ).model_dump()
    except Exception:  # noqa: BLE001 — 비정상 State는 결속 없이 기존 동작 유지
        return list(chips), {}, {}

    bound: List[str] = []
    bindings: Dict[str, Dict[str, Any]] = {}
    confirms: Dict[str, str] = {}
    for chip in chips:
        text = (chip or "").strip()
        if not text:
            continue
        unsupported = _mentioned_unsupported_concepts(text)
        if unsupported:
            _log_llm("↩ 칩 노출 제외",
                     f"칩 '{text}' 미지원 개념 언급({', '.join(unsupported)}) — 부분 결속 여부와 무관")
            continue
        try:
            after = _apply_prompt_overrides(
                ParsedStrategy.model_validate(base), text,
                skip_signal_validation=True, preserve_universe=True,
            ).model_dump()
        except Exception:  # noqa: BLE001 — 결속 실패는 칩 탈락이지 파스 실패가 아니다
            logger.warning("칩 결속 실패 — 칩 제외 | chip=%s", text, exc_info=True)
            continue
        patch = {
            key: value for key, value in after.items()
            if key not in _CHIP_BINDING_IGNORED_FIELDS and base.get(key) != value
        }
        if not patch:
            confirm_field = _confirm_target(base, text, topic)
            if confirm_field is not None:
                _log_llm("✓ 확정 칩 결속", f"칩 '{text}' = 현재값 — {confirm_field} 확정용으로 노출")
                bound.append(text)
                confirms[text] = confirm_field
                continue
            _log_llm("↩ 칩 결속 실패", f"칩 '{text}' 값 미결속 — 표현할 수 없어 노출 제외")
            continue
        bound.append(text)
        bindings[text] = patch
    return bound, bindings, confirms


def _pending_ask_payload(
    question: Optional[str], chips: Optional[List[str]], topic: Optional[str],
    parsed: Any = None,
) -> Optional[Dict[str, Any]]:
    """planner ask를 프론트가 다음 턴에 에코할 pending_ask로 만든다(FR 칩 답변 귀속).

    previous_coach_text(FR-STR-019e)와 같은 무상태 컨텍스트 에코 계약 — 백엔드는
    세션을 들지 않고, 프론트가 이 blob을 다음 파스 요청에 그대로 실어 보낸다.
    칩이 없는 질문은 에코해도 결정론 귀속(정확 일치)이 성립하지 않으므로 내지 않는다.
    parsed가 주어지면 칩을 값에 결속해(_bind_chips) 결속된 칩만 싣는다 — 호출자는
    payload["chips"]를 사용자에게 보일 칩 목록의 정본으로 삼아야 한다.
    """
    if not question or not chips:
        return None
    if parsed is None:
        return {"topic": topic, "question": question, "chips": list(chips)}
    bound, bindings, confirms = _bind_chips(list(chips), parsed, topic)
    if not bound:
        return None
    payload = {
        "topic": topic, "question": question, "chips": bound,
        "chip_bindings": bindings,
    }
    if confirms:
        # 값이 아니라 상태만 올리는 칩(§ 7 CONFIRM) — chip_bindings와 섞으면 무변경
        # 패치가 되어 '반영 없음'으로 떨어진다. 채널을 나눠 클릭 시 확정으로 처리한다.
        payload["chip_confirms"] = confirms
    return payload


def _plan_first(user_input: str) -> Optional[Any]:
    """Phase 5 제어 역전(2026-07-28) — 파스 최선두에서 대화 턴을 DAG로 계획한다.

    인터프리터보다 먼저 실행되어 유니버스 표현의 추출·분류·해석(Universe-first,
    CONCEPT 후보 되묻기 포함)을 planner가 소유한다. 실패는 전부 None — 현행 고정
    파이프라인이 그대로 담당한다(planner는 단독 실패 지점이 될 수 없다)."""
    try:
        from strategy_conversation.planner.dag_planner import plan_strategy_dag
        from strategy_conversation.planner.shadow import _default_chat

        result = plan_strategy_dag(user_input, _default_chat())
    except Exception:  # noqa: BLE001 — planner 장애가 파스를 깨면 안 된다(폴백)
        logger.warning("planner-first 실행 실패 — 고정 파이프라인 폴백", exc_info=True)
        return None
    if result is not None:
        executed_tools = [e.node.tool for e in result.executed.values()
                          if e.node.type == "tool"]
        _log_llm("▶ planner-first", (
            f"outcome={result.outcome} 도구={executed_tools or '없음'} "
            f"턴={result.llm_turns} ({result.latency_ms}ms)"
        ))
    return result


def _is_filled_slot_topic(
    topic: Optional[str], parsed: Any, explicit_fields: Optional[Iterable[str]] = None
) -> bool:
    """ask의 topic이 이미 채워진 골격 슬롯을 가리키는가(결정론 판정).

    dag_planner 내부 가드(채워진 슬롯 ask 건너뛰기)와 동일 계약 — topic↔슬롯 라벨의
    공백 무시 비교뿐이며 의미 판단은 없다. 내부 가드만으로는 부족한 이유: planner-first
    (Phase 5)는 인터프리터보다 **먼저** 실행돼 state_summary가 없다(filled_slots가 빈
    상태로 계획한다). 그래서 채워진 슬롯 판정은 파스 결과가 존재하는 채택 시점,
    즉 여기서 한 번 더 해야 한다.
    """
    normalized = (topic or "").replace(" ", "")
    if not normalized:
        return False
    filled = {
        slot.replace(" ", "")
        for slot in strategy_slots.filled_slots(
            parsed, explicit_fields=explicit_fields, require_explicit=True,
        )
    }
    return normalized in filled


def _is_universe_topic(topic: Optional[str]) -> bool:
    """유니버스 범위 ask 판정 — 9B가 '유니버스 범위'처럼 topic을 변주하는 실측 드리프트
    때문에 정확 일치가 아니라 포함으로 본다(표기 정규화 — 의미 판단 없음)."""
    return "유니버스" in (topic or "")


def _planner_observations(result: Any) -> List[tuple[str, Dict[str, Any]]]:
    """실행된 tool 노드·자동 에필로그의 (표현, 관찰값) 목록(실행 순서 보존)."""
    observations: List[tuple[str, Dict[str, Any]]] = []
    for entry in result.executed.values():
        if entry.node.type == "tool" and entry.observation is not None:
            observations.append(
                ((entry.node.args or {}).get("text") or "", entry.observation))
    for step in result.auto_steps:
        observations.append(
            ((step.get("args") or {}).get("text") or "", step.get("observation") or {}))
    return observations


def _ambiguous_candidate_terms(result: Any) -> Dict[str, List[str]]:
    """표현별 카탈로그 범위 후보(2개 이상만) — '범위가 갈리는 표현' 결정론 판정 근거."""
    ambiguous: Dict[str, List[str]] = {}
    for term, obs in _planner_observations(result):
        term = (term or "").strip()
        candidates = [
            c.get("term") for c in (obs.get("candidates") or [])
            if isinstance(c, dict) and c.get("term")
        ]
        if term and len(candidates) >= 2:
            ambiguous[term] = candidates
    return ambiguous


def _apply_planner_first_universe(
    result: Any, parsed: Any, notices: List[str]
) -> tuple[set, set]:
    """planner-first 도구 관찰값을 결정론으로 parsed에 병합한다(관찰값에서만 채택).

    적용은 고정 체인과 동일한 결정론 경로(apply_theme_companies·_merge_learned_sector)
    재사용 — planner의 역할은 실행 흐름 계획이고 확정값 채택 규칙은 기존 계약 그대로다.
    범위 후보가 2개 이상인 표현은 planner ask 여부와 무관하게 자동 적용을 차단한다 —
    범위 되묻기는 결정론(_planner_scope_ask)이 항상 표면화하므로, 여기서 적용하면
    '보안주'에 '보안' 테마를 조용히 적용하면서 범위 질문이 함께 나가는 모순이 생긴다
    (실측 사고 2026-07-28 — 조용한 확정 금지는 결정론이 지킨다).
    반환: (해석된 표현, 미해결 표현 — 모호 표현은 범위 되묻기, 나머지는 term-in 체인
    소관)."""
    from engine.nl_parser import apply_theme_companies

    resolved: set = set()
    unresolved: set = set()
    ambiguous_terms = _ambiguous_candidate_terms(result)
    for term, obs in _planner_observations(result):
        term = (term or "").strip()
        if not term:
            continue
        if term in ambiguous_terms:
            # 범위 질문이 나가는 표현 — 사용자가 고르기 전까지 어떤 해석도 확정하지 않는다
            unresolved.add(term)
            continue
        if term in resolved:
            unresolved.discard(term)
            continue
        # MARKET/SECTOR/SINGLE_STOCK/ETF 분류는 그 자체로 해석 완료 — 인터프리터가
        # 원래 필드(universe/sector/target_symbols)로 표현하므로 병합할 것이 없다.
        if obs.get("universe_type") not in (None, "CONCEPT"):
            resolved.add(term)
            unresolved.discard(term)
            continue
        if obs.get("found") and obs.get("companies"):
            # 적용 안내는 사용자 notices에 싣지 않는다(2026-08-02 사용자 지시 —
            # 요약 카드가 유니버스를 이미 표시, 반환 문구는 적용 신호 전용).
            if apply_theme_companies(parsed, term):
                _log_llm("✓ planner-first 테마",
                         f"'{term}' → 지정 종목 {len(parsed.target_symbols)}곳")
                resolved.add(term)
                unresolved.discard(term)
                continue
        if obs.get("sector"):
            _merge_learned_sector(parsed, obs["sector"])
            _log_llm("✓ planner-first 섹터", f"'{term}' → 섹터 '{obs['sector']}'")
            notices.append(
                f"'{term}'은(는) '{obs['sector']}' 업종 관련으로 해석했어요. "
                "다른 업종을 원하시면 말씀해 주세요."
            )
            resolved.add(term)
            unresolved.discard(term)
            continue
        unresolved.add(term)
    return resolved, unresolved


def _planner_scope_ask(
    result: Any, unresolved_terms: set
) -> Optional[tuple[str, List[str], set]]:
    """범위 모호성(카탈로그 후보 2개 이상) 되묻기의 결정론 확정.

    모호성 판정은 후보 수(관찰값)로만 한다 — planner가 유니버스 ask를 계획했는지에
    의존하지 않는다('미용기기' 사고 2026-07-28: planner가 조건 ask로 드리프트하면
    모호 표현이 어느 레인에도 속하지 않고 증발했다). 질문 문구는 planner의 유니버스
    ask가 있으면 재사용(이미 output_guard 통과), 없으면 고정 템플릿. 칩은 항상
    관찰된 카탈로그 후보 표기 그대로다(9B 칩 지어내기 드리프트 차단 — 후보 표기여야
    칩 클릭의 결정론 귀속이 성립한다).
    반환: (질문, 칩, 질문이 다루는 표현들) | None(모호 표현 없음)."""
    ambiguous = _ambiguous_candidate_terms(result)
    scope_terms = {t for t in unresolved_terms if t in ambiguous}
    if not scope_terms:
        return None
    chips: List[str] = []
    for term in sorted(scope_terms):
        chips.extend(c for c in ambiguous[term] if c not in chips)
    if result.outcome == "ask" and _is_universe_topic(result.topic) and result.question:
        question = result.question
    else:
        term_label = ", ".join(f"'{t}'" for t in sorted(scope_terms))
        question = f"{term_label}의 범위를 어떻게 정할까요?"
    return question, chips, scope_terms


def _planner_first_ask(
    result: Any, parsed: Any, user_input: str = "",
    explicit_fields: Optional[Iterable[str]] = None,
) -> tuple[Optional[tuple[str, Optional[List[str]], Optional[str]]], Optional[str]]:
    """planner-first가 표면화한 조건 슬롯 ask의 채택 판정(결정론 게이트가 최종 권한).

    유니버스 범위 ask는 _planner_scope_ask(결정론)가 소유하므로 여기서는 다루지
    않는다. 조건 슬롯 ask는 결정론 게이트(detect_incomplete_backtest_conditions)가
    공백을 인정할 때만 채택한다 — planner 계획이 인터프리터 해석 결과와 모순되면
    (이미 채워진 슬롯 재질문 등) 게이트가 이긴다. 채택 불가는 None(검증 리포트
    고정 질문 유지).

    반환: (ask, 거부 사유). 채택되면 (ask, None), 거부되면 (None, 사유) — 사유는
    관찰 계층(ask_binding_gate)이 "왜 결속이 없나"를 이름 붙이는 데 쓴다. 거부가 전부
    None 하나로 뭉개져 있으면 Trace에서 원인을 구분할 수 없다."""
    if result.outcome != "ask" or not result.question:
        return None, "not_ask"
    if _is_universe_topic(result.topic):
        return None, "universe_topic"
    # 슬롯 단위 재질문 차단 — 게이트가 "어딘가 비었다"고만 답하므로(첫 공백 하나),
    # 그것만으로 채택하면 **다른** 슬롯의 공백을 근거로 이미 채워진 슬롯을 다시 묻게 된다
    # (2026-07-29 사고: 매수 조건 '20일 고점 돌파'가 반영됐는데 리밸런싱·기간이 비었다는
    # 이유로 "박스권 돌파 시 매수할까요?"가 채택됨 — planner-first는 파스 전에 계획하므로
    # 자기 filled_slots를 볼 수 없다).
    if _is_filled_slot_topic(result.topic, parsed, explicit_fields):
        logger.info("planner-first ask 채택 거부 — 이미 채워진 슬롯 | topic=%s", result.topic)
        return None, "filled_slot"
    from engine.nl_parser import detect_incomplete_backtest_conditions

    gate_question, _gate_chips = detect_incomplete_backtest_conditions(parsed, user_input)
    if gate_question is None:
        return None, "gate_says_complete"
    return (result.question, (list(result.chips) or None), result.topic), None


def _bound_ask_with_slot_fallback(
    question: Optional[str], chips: Optional[List[str]], topic: Optional[str], parsed: Any
) -> tuple[Optional[Dict[str, Any]], Optional[List[str]]]:
    """planner ask의 질문은 쓰되, 칩은 **항상** 슬롯 SOT의 정본 칩으로 발행한다.

    반환: (pending_ask, 발행 시도한 칩 목록 — 관찰용).

    planner 칩(LLM 출력)을 그대로 노출하는 경로는 폐지했다(2026-08-02 사용자 결정 —
    모든 옵션 칩은 하드코딩 정본이어야 지원을 확신할 수 있다). 결속 게이트만으로는
    지원을 보증할 수 없다: '거래량 급증(전일 대비 3배) 시 매수'는 '거래량 급증'만
    부분 결속돼 게이트를 통과했고, 배수 조건은 조용히 소실된 채 노출됐다.
    planner 칩은 여기서 버려지고 로그로만 남는다.

    정본 칩은 진행 골격 슬롯 SOT(engine.strategy_slots._QUESTIONS)에서 가져온다 —
    어휘를 새로 만들지 않는다(복제하면 반드시 어긋난다, strategy_slots 도입 배경).
    그 칩들은 결속이 실증돼 있고(test_slot_clarification_chips), ETF 유니버스에는
    재무 칩(PER·ROE)이 제외된다(universe_capabilities — ETF는 기업 재무 사용 불가).
    topic이 슬롯에 매칭되지 않으면 칩 없이 질문만 남는다(자유 서술 — LLM 칩으로
    메우지 않는다).
    """
    canonical = strategy_slots.suggestions_for_topic(
        topic, universe=getattr(parsed, "universe", None))
    discarded = [c for c in (chips or []) if c not in canonical]
    if discarded:
        _log_llm("↩ planner 칩 폐기", (
            f"LLM 생성 칩 {len(discarded)}개 — topic={topic!r} 정본 칩 "
            f"{len(canonical)}개로 대체"
        ))
    if not canonical:
        return None, None
    ask = _pending_ask_payload(question, canonical, topic, parsed)
    if ask is None:
        return None, canonical
    return ask, canonical


def _replan_next_question(
    user_input: str, parsed: Any, explicit_fields: Optional[Iterable[str]] = None
) -> tuple[Optional[str], Optional[List[str]], Optional[str], Optional[Dict[str, Any]]]:
    """State 변경 후 다음 질문을 DAG planner로 재계획한다(§4 — 수정·칩 답변 공용).

    골격 공백 여부는 결정론 게이트(detect_incomplete_backtest_conditions)가 판정하고,
    planner 실패 시 질문 없음 유지(기존 프론트 게이트 폴백).
    반환: (질문, 칩, 우선순위 마커, pending_ask)."""
    if config.dag_planner_mode() != "primary":
        return None, None, None, None
    from engine.nl_parser import detect_incomplete_backtest_conditions

    gate_question, _gate_chips = detect_incomplete_backtest_conditions(parsed, user_input)
    if gate_question is None:
        return None, None, None, None
    dag_clarification = _dag_planner_clarification(user_input, parsed, explicit_fields)
    if dag_clarification is None:
        return None, None, None, None
    from observability import span
    from observability.agent_trace import ask_binding_gate

    question, chips, topic = dag_clarification
    next_ask, chips = _bound_ask_with_slot_fallback(question, chips, topic, parsed)
    # 결속된 칩만 보인다(_bind_chips) — 재계획 질문의 칩도 같은 계약을 따른다.
    gate = ask_binding_gate(
        question=question, priority="dag_planner", chips_offered=chips,
        pending_ask=next_ask, planner_mode_primary=True, planner_ran=True,
    )
    if gate["gate"] != "no_question":
        with span("Ask 결속", "state", inputs={"question": question},
                  metadata={"ask_gate": gate["gate"], "lane": "replan"}) as _trace:
            _trace.output(**dict(gate, lane="replan"))
        if not gate["bound"]:
            _log_llm("🔗 결속 소실(재계획)", (
                f"gate={gate['gate']} 칩={gate['chips_bound']}/{gate['chips_offered']}"
            ))
    return question, (next_ask["chips"] if next_ask else None), "dag_planner", next_ask


def run_chip_answer(
    user_input: str,
    previous_parsed: Optional[Dict[str, Any]],
    pending_ask: Optional[Dict[str, Any]],
    previous_explicit_fields: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """직전 planner ask의 옵션 칩 클릭을 결정론으로 State에 반영한다(Phase 4 후속 ①).

    판정은 형식 비교뿐이다: 입력이 직전 ask의 칩 문자열과 정확히 일치하면(공백 정규화)
    그 입력은 자연어 해석 대상이 아니라 시스템이 생성한 열거형 옵션의 '선택'이다.
    칩 텍스트는 planner LLM 출력(자기완결 정본 표기)이므로 결정적 추출로 적용하는 것은
    원문 해석이 아니라 LLM 출력 정규화다(계약 § 판정 기준). 효과:
    ① 오귀속 제거 — 어느 ask의 답인지 프론트 에코(pending_ask)가 확정한다
    ② 수정 인터프리터 LLM 턴 생략(지연 절감)
    칩 값은 발행 시점에 이미 결속돼 pending_ask.chip_bindings로 에코된다(_bind_chips)
    — 클릭은 그 값을 꺼내 쓰는 것이지 칩 문구를 다시 해석하는 것이 아니다. 결속이 없는
    구(舊) 에코만 칩 문구 결정적 추출로 강등한다(하위 호환 안전망).
    결정적으로 적용되지 않는 칩(추출 실패)은 None — 기존 수정 인터프리터 경로가
    처리한다(칩 자기완결 계약의 안전망). 정확 일치가 아닌 자유 서술 답변도 None —
    §4(답변 강제 귀속 금지)에 따라 Interpreter가 State 변경을 판정한다.

    확정 칩(chip_confirms, § 7 CONFIRM)은 값이 아니라 상태를 바꾼다 — 전략은 그대로 두고
    그 필드를 explicit_fields에 넣어 PROVISIONAL → CONFIRMED로 올린다.
    """
    if not previous_parsed or not isinstance(pending_ask, dict):
        return None
    chips = pending_ask.get("chips")
    if not isinstance(chips, list):
        return None
    text = (user_input or "").strip()
    chip_texts = {str(c).strip() for c in chips if isinstance(c, str) and str(c).strip()}
    if not text or text not in chip_texts:
        return None
    from engine.nl_parser import ParsedStrategy, _apply_prompt_overrides

    try:
        prev = ParsedStrategy.model_validate(previous_parsed)
    except Exception:  # noqa: BLE001 — 비정상 previous는 기존 경로가 처리
        return None
    if _is_universe_topic(pending_ask.get("topic")):
        # Phase 5: 유니버스 범위 칩(CONCEPT 후보) 결정론 귀속 — 칩 텍스트는
        # list_concept_candidates 관찰의 카탈로그 정본 표기 그대로라 정확 일치 해석
        # (테마 카탈로그 정합)이 성립한다. 원문 해석이 아니라 시스템 생성 선택지의
        # 적용이다(계약 § 판정 기준). 적용 실패는 None — 수정 인터프리터가 처리.
        return _apply_universe_chip(user_input, prev, text)
    confirm_field = (pending_ask.get("chip_confirms") or {}).get(text)
    if isinstance(confirm_field, str) and confirm_field:
        # § 7 CONFIRM — 값은 그대로, 상태 축만 PROVISIONAL → CONFIRMED.
        # 값 패치 경로로 보내면 "변경 없음"이 되어 미해석 안내로 끝난다(확정도 응답이다).
        from strategy_conversation.response.provenance import merge_explicit_fields

        explicit = merge_explicit_fields(previous_explicit_fields, [confirm_field])
        _log_llm("✓ 확정 칩 클릭", f"칩 '{text}' — {confirm_field} 현재값 확정(값 불변)")
        question, suggestions, priority, next_ask = _replan_next_question(
            user_input, prev, explicit)
        return finalize_user_response({
            "parsed": prev,
            "clarification_question": question,
            "clarification_suggestions": suggestions,
            "clarification_priority": priority,
            "pending_ask": next_ask,
            "explicit_fields": explicit,
            "notices": [],
            "interpreter": {
                "mode": "primary_chip_confirm",
                "llm_latency_ms": 0,
                "patch_count": 0,
                "confirmed_fields": [confirm_field],
            },
        })
    prev_dump = prev.model_dump()
    binding = (pending_ask.get("chip_bindings") or {}).get(text)
    if isinstance(binding, dict) and binding:
        # 발행 때 결속한 값을 그대로 적용한다 — 칩 문구 재해석 없음(칩=값 결속 계약).
        try:
            parsed = ParsedStrategy.model_validate({**prev_dump, **binding})
        except Exception:  # noqa: BLE001 — 오염된 에코는 기존 경로가 처리
            logger.warning("칩 결속값 적용 실패 — 기존 경로로 | chip=%s", text, exc_info=True)
            return None
    else:
        # 하위 호환: 결속 없는 구 에코는 칩 문구 결정적 추출로 강등한다(수정 레인과 동일
        # 계약 — 신호 재검증 생략·universe 보존). 칩은 조건 추가/값 확정이지 유니버스
        # 변경이 아니다.
        parsed = _apply_prompt_overrides(
            prev, text, skip_signal_validation=True, preserve_universe=True
        )
    diff = [
        d for d in _diff_fields(prev_dump, parsed.model_dump())
        if d.split(":", 1)[0] not in _CHIP_BINDING_IGNORED_FIELDS
    ]
    if not diff:
        # description만 달라진 것은 '반영'이 아니다 — 전략은 그대로인데 확정으로
        # 보고하면 사용자는 답했는데 아무것도 안 바뀐 화면을 본다(2026-07-29 사고).
        _log_llm("↩ 칩 결정론 미적용", f"칩 '{text}' 결정적 추출 무변경 — 수정 인터프리터로")
        return None
    _log_llm("✓ 칩 답변 확정", f"칩 '{text}' 결정적 반영(LLM 생략): {'; '.join(diff)}")

    question, suggestions, priority, next_ask = _replan_next_question(user_input, parsed)
    return finalize_user_response({
        "parsed": parsed,
        "clarification_question": question,
        "clarification_suggestions": suggestions,
        "clarification_priority": priority,
        "pending_ask": next_ask,
        "notices": [],
        "interpreter": {
            "mode": "primary_chip_answer",
            "llm_latency_ms": 0,
            "patch_count": 0,
            "applied_fields": diff,
        },
    })


def _apply_universe_chip(
    user_input: str, prev: Any, chip_text: str
) -> Optional[Dict[str, Any]]:
    """유니버스 범위 칩 하나를 결정론으로 적용한다(Phase 5 — 칩 답변 결정론 계약 확장).

    정본 섹터 표기는 sector 병합, 카탈로그 테마 표기는 테마 상장사 적용(고정 체인과
    동일한 결정론 경로). 어느 쪽도 성립하지 않으면 None — 기존 수정 인터프리터가
    처리한다('직접 입력' 등 자유 서술 안전망)."""
    from engine.universe_pit import normalize_sector
    from engine.nl_parser import replace_theme_universe

    prev_dump = prev.model_dump()
    notices: List[str] = []
    sector = normalize_sector(chip_text)
    if sector:
        _merge_learned_sector(prev, sector)
    else:
        # replace_theme_universe: 테마 확인·범위 칩은 **교체**일 수도 있다(테마 전략의
        # "쿠팡 관련주로" 되묻기에 답하는 칩) — 이전 테마에서 온 종목만 비우고 재조회한다.
        # 사용자가 직접 지목한 종목은 그대로 두므로 기존 가드(테마가 지정 종목을 덮지
        # 않는다)는 유지된다.
        # 적용 안내는 사용자 notices에 싣지 않는다(2026-08-02 사용자 지시 — 요약
        # 카드가 유니버스를 이미 표시, 반환 문구는 적용 신호 전용).
        if replace_theme_universe(prev, chip_text) is None:
            _log_llm("↩ 유니버스 칩 미적용",
                     f"칩 '{chip_text}' 카탈로그 정합 실패 — 수정 인터프리터로")
            return None
    diff = _diff_fields(prev_dump, prev.model_dump())
    if not diff:
        return None
    _log_llm("✓ 유니버스 칩 확정", f"칩 '{chip_text}' 결정적 반영(LLM 생략): {'; '.join(diff)}")
    question, suggestions, priority, next_ask = _replan_next_question(user_input, prev)
    return finalize_user_response({
        "parsed": prev,
        "clarification_question": question,
        "clarification_suggestions": suggestions,
        "clarification_priority": priority,
        "pending_ask": next_ask,
        "notices": notices,
        "interpreter": {
            "mode": "primary_chip_answer",
            "llm_latency_ms": 0,
            "patch_count": 0,
            "applied_fields": diff,
        },
    })


def _sector_terms_for_chain(pre_validation_sectors: List[str]) -> List[str]:
    """검증기가 미지원으로 제거하는 섹터 표현만 체인에 넘긴다(게이트 판정 기준 통일).

    'LCD 부품' 사고 2차(2026-07-27): 게이트가 resolve_sectors(KG 층 포함)를 쓰면 검색
    학습 노드가 섹터를 해석하는 표현('LCD 부품'→디스플레이/부품)이 '해석 성공'으로
    게이트를 통과해 체인에 도달하지 못한다 — 그런데 검증기(capability_validator)는
    정본 사전(normalize_sector)만 알아 그 표현을 이미 sectors에서 제거했고 게이트의
    해석값은 쓰이지 않아, 유니버스가 통째로 소실됐다. 게이트 기준은 검증기와 동일하게
    normalize_sector만 본다 — KG 섹터 해석·테마 상장사 적용은 체인(§ 11-3) 소관이다."""
    from engine.universe_pit import normalize_sector

    terms = [
        t.strip() for t in pre_validation_sectors
        if isinstance(t, str) and t.strip() and normalize_sector(t.strip()) is None
    ]
    return list(dict.fromkeys(terms))


def _resolve_sector_terms_term_in(
    parsed: Any,
    unresolved_terms: List[str],
    notices: List[str],
    on_stage=None,
) -> tuple[Optional[str], Optional[List[str]]]:
    """미해결 업종/테마 표현(LLM 추출)을 지식 조회 체인으로 해석한다(§ 11-3 term-in).

    표현별 체인: ① KG 테마 상장사(apply_theme_companies) — 검증 상장사를 지정 종목으로
    자동 적용(FR-STR-071 ④와 동일 계약, 입력만 원문→표현) ② 검색 그라운딩 학습
    (ground_term 도구) 후 테마 재조회→섹터 병합 ③ 끝까지 미해결이면 되묻기 —
    검색이 실제 수행됐지만 실패한 테마는 종결 안내(THEME_NOT_FOUND).
    parsed는 제자리 변형(target_symbols/sector), 안내는 notices에 덧붙인다.
    반환: (질문, 칩) — 전부 해석됐으면 (None, None)."""
    from engine.nl_parser import (
        SECTOR_REASK_QUESTION,
        SECTOR_REASK_SUGGESTIONS,
        THEME_NOT_FOUND_QUESTION,
        THEME_NOT_FOUND_SUGGESTIONS,
        apply_theme_companies,
    )

    still_unresolved: List[str] = []
    for term in unresolved_terms:
        # 테마 적용 안내는 사용자 notices에 싣지 않는다(2026-08-02 사용자 지시 —
        # 요약 카드가 유니버스를 이미 표시, 반환 문구는 적용 신호 전용).
        if apply_theme_companies(parsed, term):
            _log_llm("✓ 테마 상장사", f"'{term}' → 지정 종목 {len(parsed.target_symbols)}곳")
            continue
        learned = _ground_sector_term(term, on_stage=on_stage)
        if learned:
            # 학습이 테마 앵커를 만들었으면 상장사 적용이 우선(레거시 학습→테마 순서와 동일),
            # 아니면 업종 근사로 병합한다.
            if apply_theme_companies(parsed, term):
                _log_llm("✓ 검색 학습→테마", f"'{term}' → 지정 종목 {len(parsed.target_symbols)}곳")
            else:
                _merge_learned_sector(parsed, learned)
                _log_llm("✓ 검색 학습", f"'{term}' → 섹터 '{learned}'")
                notices.append(
                    f"'{term}'은(는) 인터넷 검색으로 확인해 '{learned}' 업종 관련으로 "
                    "해석했어요. 다른 업종을 원하시면 말씀해 주세요."
                )
            continue
        still_unresolved.append(term)
    if not still_unresolved:
        return None, None
    term = still_unresolved[0]
    entry = _searched_unresolved_lexicon_entry(term)
    if entry is not None:
        _log_llm("✗ 테마 종결", f"'{term}' — 검색 소진, 전략 불가 안내")
        return (
            THEME_NOT_FOUND_QUESTION.format(term=entry.get("term") or term),
            list(THEME_NOT_FOUND_SUGGESTIONS),
        )
    _log_llm("? 업종 되묻기", f"미해결 표현: {', '.join(still_unresolved)}")
    return SECTOR_REASK_QUESTION, list(SECTOR_REASK_SUGGESTIONS)


def _resolve_sector_terms_planner_primary(
    parsed: Any,
    unresolved_terms: List[str],
    notices: List[str],
    on_stage=None,
) -> tuple[Optional[str], Optional[List[str]]]:
    """미해결 표현을 mini-planner가 담당한다(STRATEGY_PLANNER_MODE=primary, Phase 3 승격).

    planner의 결정은 '검색할 가치 vs 되묻기'뿐이고 적용은 고정 체인과 같은 결정론
    경로를 재사용한다(apply_theme_companies·_merge_learned_sector). planner 실패(None)·
    예외는 표현 단위로 고정 체인(_resolve_sector_terms_term_in) 폴백 — planner는
    단독 실패 지점이 될 수 없다(Phase 3 안전 계약). 반환: (질문, 칩)."""
    from engine.nl_parser import SECTOR_REASK_SUGGESTIONS, apply_theme_companies

    fallback_terms: List[str] = []
    clarify: Optional[tuple] = None
    for term in unresolved_terms:
        if on_stage is not None:
            on_stage("searching")
        try:
            from strategy_conversation.planner.mini_planner import plan_universe_resolution
            from strategy_conversation.planner.shadow import _default_chat

            result = plan_universe_resolution(term, _default_chat())
        except Exception:  # noqa: BLE001 — planner 장애가 파스를 깨면 안 된다(폴백)
            logger.warning("planner primary 실행 실패 — 고정 체인 폴백 | term=%r",
                           term, exc_info=True)
            result = None
        finally:
            if on_stage is not None:
                on_stage("thinking")
        if result is None:
            fallback_terms.append(term)
            continue
        if result.outcome == "clarify":
            # 되묻기 질문은 planner 내부에서 이미 output_guard를 통과했다
            _log_llm("? planner 되묻기", f"'{term}': {result.question}")
            if clarify is None:
                clarify = (result.question, list(SECTOR_REASK_SUGGESTIONS))
            continue
        # resolved — planner의 ground_term 학습이 어휘집·KG에 반영된 뒤라 고정 체인과
        # 같은 결정적 적용이 성립한다. 적용 안내는 사용자 notices에 싣지 않는다
        # (2026-08-02 사용자 지시 — 요약 카드가 유니버스를 이미 표시, 반환 문구는 신호 전용).
        if apply_theme_companies(parsed, term):
            _log_llm("✓ planner 테마", f"'{term}' → 지정 종목 {len(parsed.target_symbols)}곳")
            continue
        if result.sector:
            _merge_learned_sector(parsed, result.sector)
            _log_llm("✓ planner 해석", f"'{term}' → 섹터 '{result.sector}'")
            notices.append(
                f"'{term}'은(는) '{result.sector}' 업종 관련으로 해석했어요. "
                "다른 업종을 원하시면 말씀해 주세요."
            )
            continue
        if result.companies:
            symbols = [c.get("symbol") for c in result.companies
                       if isinstance(c, dict) and c.get("symbol")]
            if symbols:
                parsed.target_symbols = list(dict.fromkeys(
                    [*(parsed.target_symbols or []), *symbols]))
                _log_llm("✓ planner 상장사", f"'{term}' → 지정 종목 {len(symbols)}곳")
                notices.append(
                    f"'{term}'은(는) 관련 상장사 {len(symbols)}곳으로 해석해 "
                    "지정 종목에 반영했어요."
                )
                continue
        fallback_terms.append(term)  # resolved인데 관찰값 적용 실패 — 도달 불가 안전망
    if fallback_terms:
        question, suggestions = _resolve_sector_terms_term_in(
            parsed, fallback_terms, notices, on_stage=on_stage,
        )
        if clarify is None and question:
            clarify = (question, suggestions)
    return clarify if clarify is not None else (None, None)


def _ground_sector_term(term: str, on_stage=None) -> Optional[str]:
    """표현 하나를 검색 그라운딩으로 학습한다(ground_term 도구 — 어휘집→KG→내부 LLM→검색).

    레거시 파싱 전 학습(_learn_unknown_sector_term)과 달리 원문 큐 게이트가 없다 —
    '미해결 업종 표현'이라는 판정을 리졸버가 이미 내렸다. 검색 자격 증명이 없으면
    침묵한다(레거시와 동일 게이트). 실패는 None(되묻기 소관)."""
    from engine.term_grounding import search_available

    if not search_available():
        return None
    if on_stage is not None:
        on_stage("searching")
    try:
        from strategy_conversation.planner.shadow import _default_chat
        from strategy_conversation.tools import call as call_tool

        return call_tool("ground_term", text=term, chat=_default_chat()).sector
    except Exception:  # noqa: BLE001 — 그라운딩 실패가 파스를 깨면 안 된다
        logger.debug("sector term grounding failed | term=%r", term, exc_info=True)
        return None
    finally:
        if on_stage is not None:
            on_stage("thinking")


def _merge_learned_sector(parsed: Any, sector: str) -> None:
    """학습된 정본 섹터를 sector 필드 계약(None/str/list, FR-STR-066 ⑦)대로 병합한다.

    시장(universe)은 건드리지 않는다 — 시장 선택은 인터프리터 LLM 소유(universe.markets)로
    해석 시점에 이미 결정됐고, 표현의 해석 성공 여부와 무관하다."""
    current = getattr(parsed, "sector", None)
    if current is None:
        parsed.sector = sector
    elif isinstance(current, str):
        if current != sector:
            parsed.sector = [current, sector]
    elif sector not in current:
        parsed.sector = [*current, sector]


def _searched_unresolved_lexicon_entry(term: str) -> Optional[dict]:
    """검색이 실제 수행됐지만(searched_at 원장) 업종 매핑에 실패한 어휘집 항목(term-in)."""
    try:
        from engine.term_grounding import lexicon_entry

        entry = lexicon_entry(term)
    except Exception:  # noqa: BLE001 — 어휘집 조회 실패가 되묻기 흐름을 막으면 안 된다
        return None
    if entry is not None and entry.get("searched_at") and not entry.get("sector"):
        return entry
    return None


def _changed_universe_terms(patched: Any, previous: Any) -> List[str]:
    """이번 수정이 **새로 넣은** 유니버스 표현(초안에 없던 sectors 항목).

    수정 인터프리터는 테마 교체를 universe.sectors 패치로 표현한다(실측 2026-07-30:
    '쿠팡 관련주로 수정해줘' → replace /universe/sectors/- = '쿠팡'). 생성 경로 규칙
    6-0-2('X 관련주'→sectors)와 같은 출력이라 별도 필드를 두는 것보다 안전하다 —
    형태에 없는 키는 9B가 채우지 않는다는 성질([[project_interpreter_output_shape_authority]]).
    이미 초안에 있던 표현은 제외한다(이번 턴의 변경만이 해석 대상)."""
    before = {t.strip() for t in (previous.sectors or []) if isinstance(t, str)}
    return [
        t.strip() for t in (patched.sectors or [])
        if isinstance(t, str) and t.strip() and t.strip() not in before
    ]


def _resolve_theme_change(
    parsed: Any, term: str, notices: List[str], on_stage=None,
) -> Optional[tuple[str, List[str]]]:
    """수정 턴의 테마 교체 표현을 지식 조회 체인으로 해석한다(§ 11-3 term-in, 수정 레인).

    생성 경로(planner Universe-first)와 **같은 계약**을 따른다 — 수정 턴만 다르게
    판정하면 "생성 때는 되는데 수정 때는 안 되는" 비대칭이 다시 생긴다(2026-07-30 사고의
    본체는 수정 레인에 이 체인 자체가 없었다는 것):
      ① 카탈로그 후보 2개 이상 = 범위가 갈리는 표현 → 조용히 확정하지 않고 범위 되묻기
      ② 후보 1개 → 그 정본 표기를 칩 하나로 제시해 확인받는다(자동 확정 금지)
      ③ 후보 0개 → 지식그래프 직접 조회 → 미해석이면 검색 학습 후 재조회 → 그래도
         미해석이면 되묻기(검색이 소진된 표현은 종결 안내)
    적용은 replace_theme_universe — 이전 **테마에서 온** 종목만 교체하고, 사용자가 직접
    지목한 종목은 건드리지 않는다. parsed는 제자리 변형, 안내는 notices에 덧붙인다.
    반환: None(적용 완료) | (질문, 칩) — 되묻기(호출부가 전략을 무변경으로 유지한다)."""
    from engine.knowledge_graph import catalog_theme_candidates
    from engine.nl_parser import (
        SECTOR_REASK_QUESTION,
        SECTOR_REASK_SUGGESTIONS,
        THEME_NOT_FOUND_QUESTION,
        THEME_NOT_FOUND_SUGGESTIONS,
        replace_theme_universe,
    )

    try:
        candidates = [c["term"] for c in catalog_theme_candidates(term) if c.get("term")]
    except Exception:  # noqa: BLE001 — 후보 열거 실패가 교체 자체를 막으면 안 된다
        logger.warning("테마 후보 열거 실패 | term=%r", term, exc_info=True)
        candidates = []
    if len(candidates) >= 2:
        _log_llm("? 테마 범위 되묻기", f"'{term}' 후보 {len(candidates)}개 — 조용한 확정 금지")
        return f"'{term}'의 범위를 어떻게 정할까요?", candidates
    if len(candidates) == 1:
        _log_llm("? 테마 확인 되묻기", f"'{term}' → 카탈로그 '{candidates[0]}' 확인 요청")
        return (
            f"'{term}' 관련주는 '{candidates[0]}' 테마로 정리되어 있어요. "
            "이 범위로 바꿀까요?",
            candidates,
        )
    notice = replace_theme_universe(parsed, term)
    if notice is None:
        learned = _ground_sector_term(term, on_stage=on_stage)
        if learned:
            notice = replace_theme_universe(parsed, term)
            if notice is None:
                _merge_learned_sector(parsed, learned)
                _log_llm("✓ 검색 학습(테마 교체)", f"'{term}' → 섹터 '{learned}'")
                notices.append(
                    f"'{term}'은(는) 인터넷 검색으로 확인해 '{learned}' 업종 관련으로 "
                    "해석했어요. 다른 업종을 원하시면 말씀해 주세요."
                )
                return None
    if notice is None:
        entry = _searched_unresolved_lexicon_entry(term)
        if entry is not None:
            _log_llm("✗ 테마 교체 종결", f"'{term}' — 검색 소진, 전략 불가 안내")
            return (
                THEME_NOT_FOUND_QUESTION.format(term=entry.get("term") or term),
                list(THEME_NOT_FOUND_SUGGESTIONS),
            )
        _log_llm("? 테마 교체 되묻기", f"'{term}' 미해석 — 전략 유지")
        return SECTOR_REASK_QUESTION, list(SECTOR_REASK_SUGGESTIONS)
    # 교체 안내는 사용자 notices에 싣지 않는다(2026-08-02 사용자 지시 — 요약 카드가
    # 유니버스를 이미 표시, 반환 문구는 적용 신호 전용).
    _log_llm("✓ 테마 교체", f"'{term}' → 지정 종목 {len(parsed.target_symbols)}곳")
    return None


def run_primary_modification(
    user_input: str, previous_parsed: dict, on_stage=None,
    previous_explicit_fields: Optional[List[str]] = None,
    pending_ask: Optional[Dict[str, Any]] = None,
    pending_question: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """수정 요청의 LLM Interpreter 기본 경로. 성공 시 결과 dict, 폴백 필요 시 None.

    안전 장치(전부 결정론):
    ① 라운드트립 가드 — 기존 전략을 decompile→재compile(+이월)했을 때 원본과 1비트라도
       다르면 StrategySpec이 표현 못 하는 전략(rsi rebound/macd zero 모드 등)이므로 이관을
       거부하고 기존 modify 경로로 폴백한다(목록형 필드 소실 사고 방지의 구조적 보장).
    ② patches 필수 — LLM이 전체 전략을 재출력하면(필드 소실 위험) 수락하지 않는다.
       예외: CLARIFY_STRATEGY(패치 없음)+질문이면 폴백해 질문을 버리는 대신 전략을
       그대로 유지한 채 질문을 clarification 채널로 전달한다(무변경 요약만 재렌더링되던
       2026-07-17 사고 방지).
       예외 2: 패치 없이 EXPLAIN_INDICATOR거나 unsupported_features만 보고된 경우도
       폴백하지 않고 전략을 유지한다(같은 사고의 2차 — 인터프리터가 질문 대신
       unsupported_features=["PBR 개념 설명 요청"]으로 보고). EXPLAIN_INDICATOR(LLM 라벨)면
       /query/general과 같은 LLM 설명을 notices로 실제 답변하고, 아니면 미반영을 알린다.
    ③ 패치 적용 후 검증 READY일 때만 컴파일. 아니면 폴백(임계값 없는 조건 추가 등은
       상류 clarification_for_add가 이미 가로챈다).
    description·execution_timing·entry_filters는 StrategySpec 밖이므로 원본에서 이월.
    """
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_compiler import StrategyCompileError
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.interpreter.models import StrategyIntent as _Intent
    from strategy_conversation.tools import call as call_tool

    try:
        prev = ParsedStrategy.model_validate(previous_parsed)
    except Exception:  # noqa: BLE001 — 비정상 previous는 기존 경로가 처리
        return None
    # None 파라미터를 엔진 실효값으로 명시 채운다(의미 불변) — 라운드트립이 Registry
    # 표준값(20/60 등)을 채워 '표현 불가'로 오폭하던 것을 막는다(2026-07-26 제주반도체
    # 추가 사고: 기간 없는 골든크로스 전략의 모든 수정이 레거시 레인으로 떨어짐).
    from strategy_conversation.compiler.engine_defaults import materialize_engine_defaults
    prev = materialize_engine_defaults(prev)

    # 해석 권한 순서(STRATEGY_MODIFY_INTERPRETER_MODE):
    #  · llm_first(기본) — LLM이 유일한 원문 해석자다. 이 경로는 결정론 fast-path
    #    (_modify_rule_based, 원문 정규식)를 상담하지 않는다(2026-07-26 계약 전환).
    #    인터프리터가 패치·질문·설명을 못 내면 None으로 폴백하고, 레거시 계층의 처리
    #    여부는 호출부 소관이다(§ 11 격차 1·3의 이관 대상).
    #  · fast_path_first(롤백) — 기존 동작. fast-path가 완전히 해석하는 수정("손절 10%로")은
    #    인터프리터를 건너뛴다(LLM 왕복 지연·수치/날짜 드리프트 회피).
    if config.modify_interpreter_mode() == "fast_path_first":
        if fast_path_can_handle(user_input, previous_parsed):
            _log_llm("↩ 폴백", "결정적 fast-path 처리 가능 — 인터프리터 생략")
            logger.info("modify primary skipped, deterministic fast-path handles input")
            return None

    def _carry_over(parsed):
        # execution_timing은 BacktestSpec이 표현할 수 있게 되어(2026-07-26) draft로 왕복하므로
        # 여기서 이월하지 않는다 — 이월하면 "당일 종가로 체결해줘" 같은 수정이 삼켜진다.
        return parsed.model_copy(update={
            "description": prev.description,
            "entry_filters": prev.entry_filters,
        })

    draft_spec = decompile_strategy(prev)
    ready_report = ValidationReport(is_valid=True, status="READY")
    try:
        roundtrip = _carry_over(call_tool(
            "compile_strategy",
            intent=_Intent(intent="CREATE_STRATEGY", strategy=draft_spec, confidence=1.0),
            report=ready_report, user_input=prev.description,
        ).parsed)
    except StrategyCompileError:
        return None
    prev_dump = prev.model_dump()
    roundtrip_dump = roundtrip.model_dump()
    if roundtrip_dump != prev_dump:
        diff = _diff_fields(prev_dump, roundtrip_dump)
        _log_llm("↩ 폴백", (
            "라운드트립 불일치(표현 불가 전략) — 기존 수정 경로로 | "
            f"불일치 필드(원본 → 복원본): {'; '.join(diff)}"
        ))
        logger.info("modify primary roundtrip mismatch, falling back to legacy modify")
        return None
    _log_llm("✓ 라운드트립", "기존 전략의 StrategySpec 무손실 변환 확인 — 인터프리터 호출")

    if on_stage is not None:
        on_stage("thinking")
    try:
        result = _get_interpreter(StrategyInterpreter).interpret(
            user_input, draft=draft_spec.model_dump(), pending_question=pending_question,
        )
    except InterpreterError as exc:
        logger.warning("modify primary interpreter failed, falling back | err=%s", str(exc)[:200])
        return None
    except Exception as exc:  # noqa: BLE001
        if config.modify_interpreter_mode() == "llm_first" and isinstance(exc, OSError):
            # llm_first는 레거시 수정 폴백이 없다(2026-07-26 제거) — LLM 서버 연결 장애를
            # None(→되묻기)으로 삼키면 인프라 장애가 "입력을 바꿔라"로 위장된다.
            # 503 경로(main._is_llm_connection_error)가 처리하도록 그대로 던진다.
            raise
        logger.warning("modify primary transport error, falling back | err=%r", exc)
        return None

    intent = result.intent
    # 2026-07-26 계약 전환: 인터프리터가 패치를 못 냈을 때 결정론 fast-path(_modify_rule_based,
    # 원문 정규식)에게 해석 가능 여부를 묻던 상담을 제거했다 — llm_first에서 원문 해석은
    # LLM만 한다. 인터프리터가 되묻기·설명도 내지 못한 미해석 발화는 아래 patches 미출력
    # 폴백(None)으로 기존 경로에 넘어간다(레거시 계층 자체는 § 11 격차 1·3의 이관 대상).
    if intent.intent == "CLARIFY_STRATEGY" and not intent.patches and intent.clarification_questions:
        # 되묻기 의도를 폴백으로 버리면 기존 수정 LLM이 무변경 전략을 정상 응답처럼
        # 반환해 질문이 사라진다(2026-07-17 "pbr이 뭐야?" 사고). LLM의 되묻기가 곧
        # 해석 결과다 — 전략을 유지한 채 질문을 채널로 전달한다.
        question, chips, ask = _modify_clarification(
            ValidationReport(clarification_questions=intent.clarification_questions),
            intent, prev,
        )
        _log_llm("✓ 되묻기", (
            f"질문={len(intent.clarification_questions)} — 전략 유지, clarification 채널로"
        ))
        return finalize_user_response({
            "parsed": prev,
            "clarification_question": question,
            "clarification_suggestions": chips,
            "pending_ask": ask,
            # 무변경 되묻기 공통 계약 — 프론트 설정 게이트가 삼키면 질문이 사라진다.
            "clarification_priority": "modify_unapplied",
            "notices": [],
            "interpreter": {
                "mode": "primary_modify_clarify",
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "repair_attempts": result.repair_attempts,
                "llm_latency_ms": result.latency_ms,
                "patch_count": 0,
                "confidence": intent.confidence,
            },
        })
    if not intent.patches and (
        intent.intent == "EXPLAIN_INDICATOR" or intent.unsupported_features
    ):
        # 개념 설명 질문·미지원 개념 요청을 폴백으로 버리면 기존 수정 LLM이 무변경 전략을
        # 정상 응답처럼 반환해 요청이 조용히 사라진다(2026-07-17 "pbr이 뭐야?" 사고 2차 —
        # 인터프리터가 질문을 내지 않고 unsupported_features로만 보고한 케이스). 전략은
        # 그대로 유지하되, 질문이면 /query/general과 같은 LLM 답변을 생성해 notices로
        # 실제 설명을 전달한다("변경하지 않았어요" 안내만 주던 2026-07-19 교정).
        # 질문 판정은 인터프리터 LLM의 라벨(EXPLAIN_INDICATOR)만 쓴다 — 원문 결정적
        # cue(is_definition_question 등)는 계약이 금지한 원문 의도 분류라 제거했다
        # (2026-07-26). 인터프리터가 질문을 unsupported_features로 오라벨하는 드리프트는
        # 프롬프트 규칙 10(설명 질문=EXPLAIN_INDICATOR)이 담당한다.
        from api.intent_routes import generate_general_answer

        is_question = intent.intent == "EXPLAIN_INDICATOR"
        answer = generate_general_answer(user_input) if is_question else None
        if answer:
            notices = [answer]
        elif is_question:
            notices = ["용어·지표 설명 질문으로 이해했지만 지금은 설명을 준비하지 못했어요. "
                       "전략은 변경하지 않았어요."]
        elif _reported_features_echo_input(intent.unsupported_features, user_input):
            # 인터프리터가 미지원 항목에 **발화 전체**를 그대로 담은 경우(오라벨). 그대로
            # 인용하면 "'어떻게 해야 할까?'은(는) 전략 조건으로 반영할 수 없어요"처럼
            # 뜻이 통하지 않는 안내가 나간다 — 조건 이름을 지목하지 않고 사실만 말한다.
            # 판정은 LLM 출력과 입력 문자열의 대조이지 원문 의미 해석이 아니다(§ 3-1).
            notices = ["요청을 전략 조건으로 해석하지 못했어요. 전략은 그대로 두었습니다."]
        else:
            # 사실 한 문장까지가 이 채널의 몫이다 — "그래서 지금 무엇을 하면 되는가"는
            # 진행 상태가 답한다(다음에 정할 조건 되묻기 / 실행 가능 안내, FR-SA-016·019).
            features = ", ".join(_humanize_features(intent.unsupported_features))
            notices = [
                f"'{features}' 조건은 지원하지 않아 전략에 넣지 못했어요. 나머지 조건은 그대로입니다."
            ]
        _log_llm("✓ 설명/미반영", (
            f"intent={intent.intent} 질문={is_question} 답변={'있음' if answer else '없음'} "
            f"미지원={intent.unsupported_features or '[]'} — 전략 유지, notices 채널로"
        ))
        return finalize_user_response({
            "parsed": prev,
            "clarification_question": None,
            "clarification_suggestions": None,
            "notices": notices,
            "interpreter": {
                "mode": "primary_modify_explain" if is_question else "primary_modify_unsupported",
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "repair_attempts": result.repair_attempts,
                "llm_latency_ms": result.latency_ms,
                "patch_count": 0,
                "confidence": intent.confidence,
            },
        })
    if intent.intent == "CONFIRM_RECOMMENDATION" and not intent.patches:
        # § 7 CONFIRM의 자유 서술 레인("응 그걸로", "그대로 좋아"). 확정이라는 판정은
        # 원문 해석이므로 LLM만 한다(intent 라벨). **무엇을** 확정했는지는 묻지 않는다 —
        # 확정은 언제나 우리가 방금 던진 질문에 대한 답이므로 pending_ask.topic으로
        # 결정론이 정한다(§ 20 정정이 되돌림 지점을 LLM에 묻지 않는 것과 같은 이유).
        # 물어본 적이 없거나 확정 가능 필드가 아니면 무엇을 확정했는지 알 수 없다 —
        # 임의로 고르지 말고 기존 경로로 넘긴다(말하지 않은 값 확정 금지).
        confirm_field = strategy_slots.confirmable_field_for_topic(
            (pending_ask or {}).get("topic"))
        if confirm_field is not None:
            from strategy_conversation.response.provenance import merge_explicit_fields

            explicit = merge_explicit_fields(previous_explicit_fields, [confirm_field])
            _log_llm("✓ 추천값 수락", f"{confirm_field} 현재값 확정(값 불변) — topic={pending_ask.get('topic')}")
            question, suggestions, priority, next_ask = _replan_next_question(
                user_input, prev, explicit)
            return finalize_user_response({
                "parsed": prev,
                "clarification_question": question,
                "clarification_suggestions": suggestions,
                "clarification_priority": priority,
                "pending_ask": next_ask,
                "explicit_fields": explicit,
                "notices": [],
                "interpreter": {
                    "mode": "primary_modify_confirm",
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "repair_attempts": result.repair_attempts,
                    "llm_latency_ms": result.latency_ms,
                    "patch_count": 0,
                    "confidence": intent.confidence,
                    "confirmed_fields": [confirm_field],
                },
            })
        _log_llm("↩ 폴백", "추천값 수락이지만 직전 질문이 없어 확정 대상 불명 — 기존 경로로")
    if intent.intent not in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") or not intent.patches:
        _log_llm("↩ 폴백", f"patches 미출력(intent={intent.intent}) — 기존 수정 경로로")
        logger.info("modify primary without patches (intent=%s), falling back", intent.intent)
        return None

    # 환각 게이트: 출처 인용도 수치 근거도 없는 패치는 지어낸 것이다 — 거부한다(대조, § 3-1).
    from engine.nl_parser import _compact
    compact_input = _compact(user_input)
    input_numbers = _input_number_candidates(user_input)
    verdicts = [
        _patch_provenance_supported(p, compact_input, input_numbers) for p in intent.patches
    ]
    # 같은 조건 객체를 겨냥한 형제 패치는 **한 덩어리의 수정**이다(factor·operator·value를
    # 함께 갈아끼우는 조건 교체). 개별 판정하면 일부만 통과해 LLM이 제안한 적 없는 상태가
    # 만들어진다 — "매수조건을 per 50이하로"에서 factor 패치만 인용 오기로 거부돼
    # `ma_crossover <= 50`이라는 불가능한 조건이 남고 검증이 오류로 폴백한 2026-07-31 사고.
    # 그룹 안에서 하나라도 출처가 확인되면 그 그룹은 실재하는 요청이므로 함께 수락한다
    # (§ 3-1 대조의 단위를 필드가 아니라 조건으로 잡는 것 — 근거 없는 그룹은 그대로 거부).
    groups: Dict[str, List[int]] = {}
    for i, p in enumerate(intent.patches):
        key = _patch_group_key(p.path)
        if key is not None:
            groups.setdefault(key, []).append(i)
    for key, idxs in groups.items():
        if len(idxs) < 2 or not any(verdicts[i] for i in idxs):
            continue
        carried = [intent.patches[i].path for i in idxs if not verdicts[i]]
        if carried:
            _log_llm("✓ 형제 패치 근거 전파", (
                f"{key} 그룹에 출처 확인된 패치가 있어 함께 수락: {'; '.join(carried)}"
            ))
        for i in idxs:
            verdicts[i] = True
    cued_patches: List[Any] = [p for i, p in enumerate(intent.patches) if verdicts[i]]
    rejected_patches: List[Any] = [p for i, p in enumerate(intent.patches) if not verdicts[i]]
    if rejected_patches:
        _log_llm("✗ 패치 거부", (
            "발화에 근거 없음(환각 게이트 — 인용 부재·불일치 또는 인용↔값 자릿수 어긋남): "
            + "; ".join(f"{p.op} {p.path}={_short(p.value)}" for p in rejected_patches)
        ))
    # 자기 의심 패치 게이트: 인터프리터가 패치 대상 필드에 스스로 질문을 낸 경우 —
    # 모델이 자기 해석을 불확실하다고 표시한 것이다("삼성전자 관련 etf"를 KOSPI200으로
    # 재해석하며 'KOSPI200인가요, 테마 ETF인가요?' 질문을 병행한 2026-07-27 사고).
    # 그 패치를 적용하는 대신 그 질문을 표면화한다(전략 무변경 — 조용한 오해석 차단).
    doubt_fields = _self_doubt_patch_fields(cued_patches, intent.clarification_questions)
    if doubt_fields:
        question, chips, ask = _modify_clarification(
            ValidationReport(clarification_questions=intent.clarification_questions),
            intent, prev,
        )
        if question:
            _log_llm("? 자기 의심 패치", (
                f"패치 필드={', '.join(doubt_fields)}에 모델 자신의 질문 병행 — "
                "적용 대신 되묻기(전략 유지)"
            ))
            return finalize_user_response({
                "parsed": prev,
                "clarification_question": question,
                "clarification_suggestions": chips,
                "pending_ask": ask,
                # 전략을 바꾸지 않았다는 사실은 이 질문으로만 드러난다 — 마커가 없으면
                # 프론트 explicit 설정 게이트가 자기 질문("어떤 조건에서 매수할지…")으로
                # 덮어써, 요청이 반영되지 않은 것을 사용자가 알 방법이 사라진다
                # (2026-07-30 사고: 쿠팡 요청이 화면에서 통째로 증발).
                "clarification_priority": "modify_unapplied",
                "notices": [],
                "interpreter": {
                    "mode": "primary_modify_self_doubt",
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "repair_attempts": result.repair_attempts,
                    "llm_latency_ms": result.latency_ms,
                    "patch_count": 0,
                    "confidence": intent.confidence,
                },
            })
    if not cued_patches:
        # 인터프리터가 유효 패치를 못 냈어도, 결정적 지정 종목/섹터 변경은 StrategySpec 밖이라
        # 여기서 구제한다 — 종목-only 수정("삼성전자 투자 하는 전략")은 _modify_rule_based
        # fast-path도 못 잡아(신호·수치 키워드 부재) 여기 도달하는데, 그대로 '해석 못 함'으로
        # 처리하면 지정 종목이 조용히 무시되고 유니버스 전략이 유지된다(FR-STR-068 회귀).
        # [[project_single_asset_backtest]]: 레거시 결정적 오버라이드는 primary에도 미러링.
        from engine.nl_parser import _apply_prompt_overrides
        det = (
            _apply_prompt_overrides(prev, user_input, preserve_universe=True)
            if config.prompt_overrides_enabled() else prev
        )
        if det.target_symbols != prev.target_symbols or det.sector != prev.sector:
            _log_llm("✓ 결정적 종목/섹터 수정", "인터프리터 무효 패치 — 결정적 오버라이드로 구제")
            return finalize_user_response({
                "parsed": det,
                "clarification_question": None,
                "clarification_suggestions": None,
                "notices": [],
                "interpreter": {
                    "mode": "primary_modify_deterministic_symbol",
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "repair_attempts": result.repair_attempts,
                    "llm_latency_ms": result.latency_ms,
                    "patch_count": 0,
                    "confidence": intent.confidence,
                },
            })
        # 전량 환각(예: 후속 질문 "다른 예는 없어?"에 임의 패치) — 전략을 그대로 유지하고
        # 미해석을 정직하게 안내한다(QA 20-3: 임의 변형 차단이 핵심). 과거의 질문 판정
        # 정규식(원문 의도 분류)과 fast-path 상담(원문 파서 상담)은 계약 위반이라 제거했다
        # (2026-07-26) — 후속 질문 라우팅은 상류 분류기(history 배선, FR-SA-002c-3) 소관.
        notices = [
            "요청을 전략 변경으로 해석하지 못해 전략은 그대로 유지했어요. "
            "바꾸고 싶은 조건(예: 손절 10%로, 종목 20개로)을 구체적으로 말씀해 주세요."
        ]
        return finalize_user_response({
            "parsed": prev,
            "clarification_question": None,
            "clarification_suggestions": None,
            "notices": notices,
            "interpreter": {
                "mode": "primary_modify_rejected_patches",
                "model_name": result.model_name,
                "prompt_version": result.prompt_version,
                "repair_attempts": result.repair_attempts,
                "llm_latency_ms": result.latency_ms,
                "patch_count": 0,
                "confidence": intent.confidence,
            },
        })
    _log_llm("✓ 패치 수락", "; ".join(
        f"{p.op} {p.path}={_short(p.value)}" for p in cued_patches
    ))
    try:
        patched_spec = apply_patches(draft_spec, cued_patches)
    except PatchError as exc:
        _log_llm("↩ 폴백", f"패치 거부: {str(exc)[:150]} — 기존 수정 경로로")
        logger.warning("modify primary patch rejected, falling back | err=%s", exc)
        return None

    # 이번 턴이 새로 넣은 유니버스 표현 중 정본 섹터로 풀리지 않는 것(= 테마 표현)은
    # **미지원이 아니라 지식 조회 대상**이다. 검증기(정본 사전만 안다)에 그대로 넘기면
    # 오류로 판정돼 이 레인 전체가 폴백하고, 요청은 무변경으로 끝난다(2026-07-30 사고).
    # 생성 경로에서 검증기가 sectors를 비우고 pre-validation 스냅샷으로 체인을 돌리는
    # 것과 같은 구조 — 여기서는 표현을 미리 떼어 두고 컴파일 뒤 체인에 넘긴다.
    theme_terms = (
        _sector_terms_for_chain(_changed_universe_terms(
            patched_spec.universe, draft_spec.universe))
        if "ETF" not in patched_spec.universe.markets else []
    )
    universe_changed = bool(
        _changed_universe_terms(patched_spec.universe, draft_spec.universe))
    if theme_terms:
        pending_theme = {t.replace(" ", "").lower() for t in theme_terms}
        patched_spec.universe.sectors = [
            s for s in patched_spec.universe.sectors
            if s.replace(" ", "").lower() not in pending_theme
        ]
        _log_llm("▶ 테마 표현 감지", f"{', '.join(theme_terms)} — 검증 대신 지식 조회로")

    modify_intent = _Intent(
        intent="MODIFY_STRATEGY", strategy=patched_spec,
        confidence=intent.confidence, unsupported_features=intent.unsupported_features,
    )
    _fill_deterministic_condition_params(modify_intent)
    validation = call_tool("validate_intent", intent=modify_intent)
    validated, report = validation.intent, validation.report
    _log_llm("✓ 검증", (
        f"status={report.status} patches={len(cued_patches)} "
        f"오류={len(report.errors)} 미지원={report.unsupported_features or '[]'}"
    ))
    modification_partial = False
    if not report.is_valid:
        # 오류 없이 질문만 남은 미완성은 두 경우를 구분한다(2026-07-27 재정의):
        #  · 질문이 이번 패치 필드 자체를 가리킴("데드크로스 청산 추가해줘" — 기간 미지정)
        #    → 전략 무변경+구체 질문·옵션 칩(2026-07-26 계약 유지). 칩은 조건 전체를 담아
        #    무상태 재전송으로 조건을 채운다.
        #  · 질문이 전부 다른 슬롯의 완결성(랭킹 추가 후 "리밸런싱 주기?") → 이번 수정은
        #    완결이므로 버리면 안 된다("최근 3개월 수익률 상위 매수" 답변이 폐기되고 매수
        #    조건을 재질문하던 사고). 부분 컴파일로 수정을 반영하고, 다음 질문은 아래 공통
        #    재계획 경로(DAG planner)가 갱신된 State 기준으로 담당한다.
        if not report.errors and report.clarification_questions:
            own_field_questions = _self_doubt_patch_fields(
                cued_patches, report.clarification_questions
            )
            if not own_field_questions:
                modification_partial = True
            else:
                question, chips, ask = _modify_clarification(report, validated, prev)
                if question:
                    _log_llm("✓ 되묻기", (
                        f"패치 필드 미확정 값 질문={len(report.clarification_questions)}"
                        " — 전략 유지, 옵션 칩과 함께 clarification 채널로"
                    ))
                    return finalize_user_response({
                        "parsed": prev,
                        "clarification_question": question,
                        "clarification_suggestions": chips,
                        "pending_ask": ask,
                        # 자기 의심 분기와 같은 이유 — 전략 무변경 되묻기는 프론트 게이트에
                        # 삼켜지면 "요청이 사라진" 것과 구분되지 않는다.
                        "clarification_priority": "modify_unapplied",
                        "notices": [],
                        "interpreter": {
                            "mode": "primary_modify_needs_value",
                            "model_name": result.model_name,
                            "prompt_version": result.prompt_version,
                            "repair_attempts": result.repair_attempts,
                            "llm_latency_ms": result.latency_ms,
                            "patch_count": len(cued_patches),
                            "confidence": intent.confidence,
                        },
                    })
        if not modification_partial:
            _log_llm("↩ 폴백", f"패치 적용 후 검증 미통과(status={report.status}) — 기존 수정 경로로")
            logger.info("modify primary not READY after patch (status=%s), falling back",
                        report.status)
            return None
    try:
        parsed = _carry_over(call_tool(
            "compile_strategy", intent=validated, report=report,
            user_input=prev.description, partial=modification_partial,
        ).parsed)
    except StrategyCompileError as exc:
        logger.warning("modify primary compile failed, falling back | err=%s", exc)
        return None
    # 레거시 수정 경로와 동일한 결정적 보정(신호 재검증 생략·universe 보존) — 명시된
    # 수치·날짜·리스크 값은 결정적 추출이 최종 진실이다.
    if config.prompt_overrides_enabled():
        from engine.nl_parser import _apply_prompt_overrides
        compiled_dump = parsed.model_dump()
        parsed = _apply_prompt_overrides(
            parsed, user_input, skip_signal_validation=True, preserve_universe=True
        )
        override_diff = _diff_fields(compiled_dump, parsed.model_dump())
        if override_diff:
            _log_llm("✓ 결정적 보정", "; ".join(override_diff))
    # 테마 유니버스 교체(§ 11-3 수정 레인) — 컴파일은 테마 **표기**를 옮길 뿐이고,
    # 그 테마의 상장사를 찾는 것은 지식 조회다. 이 체인이 없으면 인터프리터가 종목코드를
    # 스스로 알아내야 하는 처지가 되어, 모르는 테마의 교체 요청이 무변경으로 끝난다
    # (2026-07-30 "쿠팡 관련주로 수정해줘" 사고).
    notices = list(report.warnings)
    if (universe_changed and prev.theme_universe
            and set(parsed.target_symbols) <= set(prev.target_symbols)):
        # 유니버스를 바꾸는 턴인데 남은 종목이 전부 이전 테마의 목록이다 — 지정 종목이
        # 우선하므로 그대로 두면 새 업종/테마가 아무 효과 없이 삼켜진다(인터프리터가
        # symbols 일부만 remove하는 실측 드리프트도 여기서 함께 정리된다). 사용자가 이번
        # 턴에 새 종목을 지목했으면(이전 목록 밖 코드가 있으면) 건드리지 않는다.
        parsed.target_symbols = []
        parsed.theme_universe = None
        _log_llm("✓ 이전 테마 종목 해제", f"'{prev.theme_universe}' 유래 지정 종목 비움")
    if theme_terms:
        # 교체 체인의 입력 상태를 이전 테마로 되돌린다 — replace_theme_universe가
        # "무엇을 비워도 되는지"를 이 출처 표기로 판정한다.
        parsed.theme_universe = prev.theme_universe
        parsed.target_symbols = list(prev.target_symbols)
        theme_ask = _resolve_theme_change(parsed, theme_terms[0], notices, on_stage)
        if theme_ask is not None:
            # 해석 못 한 테마로 전략을 바꾸지 않는다 — 전략은 그대로 두고 범위를 묻는다.
            # 우선순위 마커: 유니버스 범위는 조건 질문보다 선행 결정 사항이라, 프론트
            # explicit 설정 게이트가 이 질문을 삼키면 요청이 조용히 사라진다.
            question, chips = theme_ask
            return finalize_user_response({
                "parsed": prev,
                "clarification_question": question,
                "clarification_suggestions": chips,
                "clarification_priority": "sector_unresolved",
                "pending_ask": _pending_ask_payload(question, chips, "유니버스"),
                "notices": [],
                "interpreter": {
                    "mode": "primary_modify_theme_ask",
                    "model_name": result.model_name,
                    "prompt_version": result.prompt_version,
                    "repair_attempts": result.repair_attempts,
                    "llm_latency_ms": result.latency_ms,
                    "patch_count": 0,
                    "confidence": intent.confidence,
                },
            })
    elif parsed.target_symbols == prev.target_symbols:
        # 종목 구성이 그대로면 출처 표기도 그대로 — 컴파일이 초안 표기를 옮겨 놓았을 뿐
        # 이므로 원본 값으로 확정한다(종목이 바뀐 턴이면 위에서 이미 None으로 비웠다).
        parsed.theme_universe = prev.theme_universe
    # 시장 제약 반영(지식 조회) — 지정 종목 모드는 universe 시장이 실행에 반영되지
    # 않아(변환기가 target_symbols 우선) 시장만 바꾸는 패치가 무변경으로 끝난다
    # (2026-08-02 "코스피에만 속한 종목으로 변경" 사고). 테마 유래 종목만 종목 마스터
    # 정본 조회로 필터링한다 — 직접 지목 종목은 불변(filter 내부 가드).
    from engine.nl_parser import filter_target_symbols_by_market, unapplied_market_constraint

    market_note = filter_target_symbols_by_market(parsed)
    if market_note:
        _log_llm("✓ 시장 필터", market_note)
    else:
        unmet = unapplied_market_constraint(parsed)
        if unmet is not None:
            # 이해는 했지만 반영할 수 없다(테마 전체에도 해당 시장 종목 없음) — 시장
            # 패치까지 되돌려 전략을 원상 유지하고 그 사실을 알린다. 침묵 금지:
            # 2026-08-02 "미안해 코피닥 종목만 선택 해줘" 사고 — universe만 KOSDAQ으로
            # 뒤집힌 채 종목은 그대로, 안내도 없어 오타 미해석으로 오인됐다.
            parsed.universe = list(prev.universe or [])
            market_label = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(unmet, unmet)
            notices.append(
                f"'{parsed.theme_universe}' 관련 종목에서 {market_label} 소속을 찾지 "
                "못해 요청을 반영하지 못했어요. 기존 전략을 그대로 유지했어요."
            )
            _log_llm("△ 시장 필터 미반영", f"{unmet} 소속 0곳 — 전략 유지+안내")
    final_diff = _diff_fields(prev_dump, parsed.model_dump())
    _log_llm("✓ 수정 완료", f"변경 필드(원본 대비): {'; '.join(final_diff) or '없음'}")

    # 미반영 수치는 로그로만 남긴다 — 안내 폐지(2026-08-01, 초기 파스 레인과 같은 판단).
    if result.unreflected_numbers:
        from strategy_conversation.validation.recall_validator import labels_absent_from

        # description은 사용자 원문 에코라 대조에서 뺀다(초기 파스 레인과 같은 이유).
        payload = parsed.model_dump()
        payload.pop("description", None)
        still_missing = labels_absent_from(result.unreflected_numbers, payload)
        if still_missing:
            _log_llm("△ 미반영(안내 없음)", f"{', '.join(still_missing)}")

    # Phase 4 primary — 수정 턴 재계획: 최신 입력이 State를 바꿨으니(위 패치 적용),
    # 다음 질문은 갱신된 State 기준으로 DAG planner가 다시 계획한다(유니버스가 바뀌면
    # 후속 질문·칩도 그에 맞게 재생성 — 사용자 계약 "입력은 답변 귀속이 아니라 State
    # 변경 판정이 먼저").
    dag_question, dag_suggestions, dag_priority, dag_pending_ask = _replan_next_question(
        user_input, parsed
    )

    # 수정 턴의 명시 필드는 **이번 턴이 바꾼 것**(패치)에서 판정하고 이전 턴 에코와
    # 합집합한다 — 이전 턴에 말한 값이 이번 턴 침묵으로 지워지지 않게.
    # 패치 적용 후 State에서 판정하면 안 된다: 그 State는 이전 전략을 디컴파일한 초안이라
    # 물질화 기본값이 이미 채워져 있고, 값의 존재로 판정하면 사용자가 말한 적 없는 값이
    # '명시'가 된다(2026-08-02: 기간만 답했는데 초기 자금을 묻지 않게 되던 사고).
    turn_explicit_fields = _modify_explicit_fields(cued_patches, previous_explicit_fields)
    return finalize_user_response({
        "parsed": parsed,
        "clarification_question": dag_question,
        "clarification_suggestions": dag_suggestions,
        "clarification_priority": dag_priority,
        "pending_ask": dag_pending_ask,
        "explicit_fields": turn_explicit_fields,
        "field_states": _field_states(
            parsed, validated.strategy, report, turn_explicit_fields,
        ),
        # 되돌리기(§ 19)의 근거 — 이 턴이 바꾼 필드 이름. 프론트가 변경 이력에 쌓고
        # 다음 턴에 에코한다(무상태 계약). _diff_fields는 사람이 읽는 로그 문장이라
        # 되돌리기 대상으로 쓸 수 없어 구조화 이름을 따로 낸다.
        "changed_fields": changed_field_names(prev_dump, parsed.model_dump()),
        "notices": notices,
        "interpreter": {
            "mode": "primary_modify",
            "model_name": result.model_name,
            "prompt_version": result.prompt_version,
            "repair_attempts": result.repair_attempts,
            "llm_latency_ms": result.latency_ms,
            "patch_count": len(cued_patches),
            "confidence": intent.confidence,
        },
    })


_interpreter_singleton = None


def _get_interpreter(cls):
    global _interpreter_singleton
    if _interpreter_singleton is None:
        _interpreter_singleton = cls()
    return _interpreter_singleton


def apply_primary_meta(result: dict, primary: Dict[str, Any]) -> None:
    """_build_parse_result 산출물에 primary 경로의 질문/안내/메타를 병합한다.

    인터프리터의 질문이 기존 detect_missing_entry_clarification 질문보다 구체적이므로
    있으면 우선한다. 단, 유니버스 범위 질문(clarification_priority — 테마 관련 상장사
    되묻기 FR-STR-071)은 조건 질문보다 선행 결정 사항이라 덮어쓰지 않는다.
    notices는 뒤에 덧붙인다(하한선 보정 안내가 앞).
    """
    if primary["clarification_question"] and not result.get("clarification_priority"):
        result["clarification_question"] = primary["clarification_question"]
        result["clarification_suggestions"] = primary["clarification_suggestions"]
        # term-in 체인의 미해결 업종 질문(§ 11-3)은 우선순위 마커까지 이월한다 —
        # 프론트 explicit 설정 게이트가 질문을 삼키지 않게(레거시 sector_reask와 동일 계약).
        if primary.get("clarification_priority"):
            result["clarification_priority"] = primary["clarification_priority"]
        # planner ask의 칩 답변 귀속 컨텍스트 — 질문이 채택된 경우에만 함께 이월한다
        # (채택되지 않은 질문의 pending_ask를 에코하면 다음 턴 칩 판정이 어긋난다).
        # **질문과 결속은 함께 움직인다** — primary 질문이 이겼는데 결속만 최소 조건
        # 게이트(main._build_parse_result)의 것이 남으면, 화면의 질문과 다음 턴 귀속
        # 근거가 서로 다른 질문을 가리킨다.
        result["pending_ask"] = primary.get("pending_ask")
    elif primary["interpreter"]["mode"] in ("primary_modify_explain", "primary_modify_unsupported", "primary_modify_rejected_patches"):
        # 전략 무변경 + 설명/미반영 안내 응답 — 프롬프트의 지표 언급("pbr이 뭐야?")에 반응한
        # 기존 되묻기("PBR은 몇 이하로 할까요?")는 설명·안내와 모순되므로 억제한다.
        result["clarification_question"] = None
        result["clarification_suggestions"] = None
    if primary["notices"]:
        result["notices"] = list(result.get("notices") or []) + primary["notices"]
    # provenance는 인터프리터가 판정한 경로에서만 갱신한다 — 폴백 경로(질문/설명/미반영)는
    # 이번 턴에 State를 바꾸지 않았으므로 호출부가 이전 턴 에코를 그대로 이월한다.
    if primary.get("explicit_fields") is not None:
        result["explicit_fields"] = primary["explicit_fields"]
    # 상태 축(§ 5)도 같은 계약 — 인터프리터가 State를 판정한 턴에서만 갱신한다.
    if primary.get("field_states"):
        result["field_states"] = primary["field_states"]
    # 변경 이력(§ 19)도 같은 계약. 빈 목록도 유효한 값이라 None만 걸러낸다 —
    # "이 턴은 아무것도 바꾸지 않았다"는 사실 자체가 이력에 남아야 한다.
    if primary.get("changed_fields") is not None:
        result["changed_fields"] = primary["changed_fields"]
    result["runtime"]["interpreter"] = primary["interpreter"]
