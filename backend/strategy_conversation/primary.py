"""Primary Mode (Phase 2) — LLM Interpreter를 초기 파스의 기본 경로로 승격.

STRATEGY_INTERPRETER_MODE=primary일 때 main.py 초기 파스가 이 모듈을 먼저 시도한다.
None을 반환하면 호출부가 기존 규칙 파서 경로(하이브리드)로 폴백한다:
  - LLM 호출/JSON 복구 실패
  - 전략 파이프라인 대상이 아닌 intent(비전략·설명·추천 요청 — 상류 분류기 소관)
  - strategy 본문 없음 / 컴파일 실패

READY면 전체 컴파일, NEEDS_CLARIFICATION이면 **미확정 조건을 제외한 부분 컴파일**
(조용한 기본값 확정 금지) + 되묻기 질문·추천값 칩을 기존 clarification 채널로 전달.
칩 텍스트("영업이익률 10% 이상")는 클릭 시 일반 수정 메시지로 재전송되어 기존
modify 경로(결정적 병합)가 조건을 채운다 — condition_builder와 동일한 무상태 패턴.

수정(modify) 경로는 Phase 2에서 기존 하이브리드를 유지한다(QA 실측 26/26 경로 보존,
대화 상태는 기존 아키텍처대로 프론트의 previous_parsed가 소유).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from strategy_conversation import config
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


def _build_clarification(
    report: ValidationReport, intent: StrategyIntent
) -> tuple[Optional[str], Optional[List[str]]]:
    """검증 리포트의 질문들을 기존 clarification 채널(질문 텍스트 + 칩)로 변환한다."""
    if not report.clarification_questions:
        return None, None
    lines: List[str] = []
    chips: List[str] = []
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
    for role in coalesced_cross_roles:
        role_label = "매수(진입)" if role == "entry" else "매도(청산)"
        lines.append(
            f"{role_label} 이동평균 크로스의 기간(단기/장기)은 몇 일로 할까요? "
            "(일반적으로 20일/60일을 많이 사용합니다)"
        )
        chips.extend(_cross_period_chip(role, s, l) for s, l in _CROSS_PERIOD_OPTIONS)
    return "\n".join(lines), (chips or None)


# 인터프리터가 unsupported_features에 내부 식별자(strategy_evaluation 등)를 그대로 담는
# 실측 드리프트 — 사용자 안내 문구에 내부명이 노출되지 않게 치환한다(레드팀 QA 20-5).
_INTERNAL_FEATURE_LABELS = {
    "strategy_evaluation": "전략 우열 평가",
    "strategy_recommendation": "전략 추천",
    "stock_recommendation": "종목 추천",
    "market_forecast": "시장 전망",
}
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
#      판단하지 않는다 — LLM의 출처 주장(인용)이 실재하는지만 본다.
#   ② 수치 대조 — 패치 값의 숫자가 입력의 숫자 표기(단위 환산 포함)와 일치하면
#      근거 있음(recall_validator와 같은 § 3-1 대조).
#   ③ 지정 종목 — 해석 가능성(§ 3-2 지식 조회): 마스터에 없는 이름은 환각.


def _patch_value_numbers(value: Any) -> set:
    from strategy_conversation.validation.recall_validator import _collect_numbers

    acc: set = set()
    _collect_numbers(value, acc)
    return acc


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
    quote = _compact(patch.source_text) if patch.source_text else ""
    if quote and quote in compact_input:
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


def run_primary_parse(user_input: str, on_stage=None) -> Optional[Dict[str, Any]]:
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
    try:
        interpreter = _get_interpreter(StrategyInterpreter)
        result = interpreter.interpret(user_input)
    except InterpreterError as exc:
        logger.warning("interpreter primary failed, reporting failure | err=%s",
                       str(exc)[:200])
        return None

    _fill_deterministic_condition_params(result.intent)
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
    # 보정이 섹터를 해석했으면(검색 그라운딩 학습분 포함) 같은 테마를 가리키는 미지원
    # 안내도 지운다 — "'마운자로 관련주'는 반영되지 않았어요"가 반영된 전략과 모순.
    if parsed.sector and report.unsupported_features:
        from engine.nl_parser import _extract_sector
        report.unsupported_features = [
            f for f in report.unsupported_features if _extract_sector(f) is None
        ]
    if parsed.target_symbols:
        # 지정 종목 전략의 청산 누락은 호출부 공유 보정(apply_single_asset_adjustments)이
        # 반대 신호 청산 추천/기간 종료 보유 안내(비차단 notices)로 처리한다(FR-STR-068) —
        # 정기 리밸런싱을 추천하는 유니버스형 되묻기 질문은 지정 종목에 맞지 않아 제거한다.
        report.clarification_questions = [
            q for q in report.clarification_questions
            if q.field != "strategy.exit_conditions"
        ]

    clarification_question, clarification_suggestions = _build_clarification(report, validated)
    if report.unsupported_features:
        features = ", ".join(_humanize_features(report.unsupported_features))
        notices.append(
            f"'{features}' 조건은 현재 지원되지 않아 전략에 반영되지 않았어요."
            + (" " + " ".join(report.suggested_fixes) if report.suggested_fixes else "")
        )
    # 제외됐지만 질문/미지원 안내가 다루지 않는 조건이 있으면 정직하게 알린다
    unexplained_drops = [d for d in dropped if d not in " ".join(
        [clarification_question or ""] + notices
    )]
    if unexplained_drops:
        notices.append(
            f"'{', '.join(unexplained_drops)}' 조건은 값 확인 전까지 전략에 반영되지 않았어요."
        )

    # Phase 3 shadow: 고정 체인이 해석하지 못한 업종/테마 표현이 있으면 mini-planner를
    # 관측 전용으로 병행 실행한다(기본 off, STRATEGY_PLANNER_MODE=shadow에서만 동작).
    try:
        if validated.strategy is not None and validated.strategy.universe.sectors:
            from strategy_conversation.planner.shadow import maybe_shadow_plan
            from strategy_conversation.registry.universe_resolver import resolve_sectors

            _, unresolved_sector_terms = resolve_sectors(validated.strategy.universe.sectors)
            maybe_shadow_plan(unresolved_sector_terms)
    except Exception:  # noqa: BLE001 — 관측 실행 실패가 파스를 깨면 안 된다
        logger.debug("planner shadow launch failed", exc_info=True)

    return finalize_user_response({
        "parsed": parsed,
        "clarification_question": clarification_question,
        "clarification_suggestions": clarification_suggestions,
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


def run_primary_modification(user_input: str, previous_parsed: dict, on_stage=None) -> Optional[Dict[str, Any]]:
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
            user_input, draft=draft_spec.model_dump()
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
        question, chips = _build_clarification(
            ValidationReport(clarification_questions=intent.clarification_questions),
            intent,
        )
        _log_llm("✓ 되묻기", (
            f"질문={len(intent.clarification_questions)} — 전략 유지, clarification 채널로"
        ))
        return finalize_user_response({
            "parsed": prev,
            "clarification_question": question,
            "clarification_suggestions": chips,
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
        else:
            features = ", ".join(_humanize_features(intent.unsupported_features))
            notices = [f"'{features}'은(는) 전략 조건으로 반영할 수 없어 전략을 변경하지 않았어요."]
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
    if intent.intent not in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") or not intent.patches:
        _log_llm("↩ 폴백", f"patches 미출력(intent={intent.intent}) — 기존 수정 경로로")
        logger.info("modify primary without patches (intent=%s), falling back", intent.intent)
        return None

    # 환각 게이트: 출처 인용도 수치 근거도 없는 패치는 지어낸 것이다 — 거부한다(대조, § 3-1).
    from engine.nl_parser import _compact
    compact_input = _compact(user_input)
    input_numbers = _input_number_candidates(user_input)
    cued_patches: List[Any] = []
    rejected_patches: List[Any] = []
    for p in intent.patches:
        (cued_patches if _patch_provenance_supported(p, compact_input, input_numbers)
         else rejected_patches).append(p)
    if rejected_patches:
        _log_llm("✗ 패치 거부", (
            "발화에 필드 cue 없음(환각 게이트): "
            + "; ".join(f"{p.op} {p.path}" for p in rejected_patches)
        ))
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
    if not report.is_valid:
        # 오류 없이 질문만 남은 미완성(예: "데드크로스 청산 추가해줘" — 기간 미지정)은
        # 폴백 대신 구체 질문+옵션 칩을 전달한다(2026-07-26 사용자 결정: 조용한 기본값
        # 확정 금지, 옵션 제시 되묻기). 칩은 조건 전체를 담아 재전송 가능(무상태) —
        # 전략은 무변경 유지하고 사용자의 칩/답변이 다음 수정 요청으로 조건을 채운다.
        if not report.errors and report.clarification_questions:
            question, chips = _build_clarification(report, validated)
            if question:
                _log_llm("✓ 되묻기", (
                    f"패치 적용 후 미확정 값 질문={len(report.clarification_questions)}"
                    " — 전략 유지, 옵션 칩과 함께 clarification 채널로"
                ))
                return finalize_user_response({
                    "parsed": prev,
                    "clarification_question": question,
                    "clarification_suggestions": chips,
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
        _log_llm("↩ 폴백", f"패치 적용 후 검증 미통과(status={report.status}) — 기존 수정 경로로")
        logger.info("modify primary not READY after patch (status=%s), falling back",
                    report.status)
        return None
    try:
        parsed = _carry_over(call_tool(
            "compile_strategy", intent=validated, report=report,
            user_input=prev.description,
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
    final_diff = _diff_fields(prev_dump, parsed.model_dump())
    _log_llm("✓ 수정 완료", f"변경 필드(원본 대비): {'; '.join(final_diff) or '없음'}")

    return finalize_user_response({
        "parsed": parsed,
        "clarification_question": None,
        "clarification_suggestions": None,
        "notices": list(report.warnings),
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
    elif primary["interpreter"]["mode"] in ("primary_modify_explain", "primary_modify_unsupported", "primary_modify_rejected_patches"):
        # 전략 무변경 + 설명/미반영 안내 응답 — 프롬프트의 지표 언급("pbr이 뭐야?")에 반응한
        # 기존 되묻기("PBR은 몇 이하로 할까요?")는 설명·안내와 모순되므로 억제한다.
        result["clarification_question"] = None
        result["clarification_suggestions"] = None
    if primary["notices"]:
        result["notices"] = list(result.get("notices") or []) + primary["notices"]
    result["runtime"]["interpreter"] = primary["interpreter"]
