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

logger = logging.getLogger("strategy_interpreter.primary")

_STRATEGY_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def primary_enabled() -> bool:
    return config.interpreter_mode() == "primary"


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
    for q in report.clarification_questions:
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


# ── 수정 패치 환각 게이트(결정적) ──────────────────────────────────────────────
# 결정적 추출의 침묵은 요청 없음의 증거가 아니지만, '필드 cue조차 없는' 패치는 환각이다
# (FR-STR-019b와 동일 원칙). "다른 예는 없어?"라는 후속 질문에 인터프리터가 손절·리밸런싱·
# 백테스트 날짜 패치를 지어내 전략을 임의 변형한 실측 사고(레드팀 QA 20-3) 방지 —
# 패치가 만지는 필드의 cue가 발화에 없으면 그 패치를 거부한다.
_SIGNAL_TERM_CUES = [
    "per", "pbr", "psr", "roe", "roa", "rsi", "macd", "볼린저", "이동평균", "이평",
    "골든크로스", "데드크로스", "크로스", "스토캐스틱", "cci", "adx", "mfi", "거래량",
    "거래대금", "시총", "시가총액", "부채", "유동비율", "배당", "모멘텀", "돌파", "신고가",
    "과매도", "과매수", "ev", "ebitda",
]
_PATCH_FIELD_CUES: Dict[str, List[str]] = {
    "stop_loss": ["손절", "스탑로스", "stoploss", "손실"],
    "take_profit": ["익절", "목표수익", "수익실현", "수익확정", "수익"],
    "trailing_stop": ["트레일링", "최고가대비", "고점대비"],
    "max_mdd_limit": ["mdd", "낙폭", "드로우다운", "드로다운"],
    "max_position_weight": ["비중"],
    "selection_count": ["종목", "개수", "포지션", "개"],
    "weighting": ["비중", "동일비중", "가중"],
    "rebalance_frequency": ["리밸런", "재조정", "재선정", "매일", "매주", "매월", "격월",
                            "분기", "매년", "연간", "월간", "주간", "마다", "주기"],
    "hold_period_days": ["보유", "들고", "유지", "홀딩"],
    "markets": ["코스피", "코스닥", "kospi", "kosdaq", "etf", "시장", "유니버스", "전체", "대형주"],
    "sectors": ["업종", "섹터", "관련주", "테마"],
    "universe": ["코스피", "코스닥", "kospi", "kosdaq", "etf", "시장", "유니버스", "업종", "섹터"],
    "entry_conditions": ["진입", "매수", "사", "조건", "신호"] + _SIGNAL_TERM_CUES,
    "exit_conditions": ["청산", "매도", "팔", "정리", "조건", "신호"] + _SIGNAL_TERM_CUES,
    "ranking": ["상위", "수익률", "모멘텀", "랭킹", "순위"] + _SIGNAL_TERM_CUES,
    "backtest": ["백테스트", "기간", "년", "최근", "부터", "까지", "동안"],
    "period": ["백테스트", "기간", "년", "최근", "동안"],
    "name": ["이름", "명칭"],
}


def _patch_cue_supported(patch, compact: str) -> bool:
    tokens = [t for t in patch.path.split("/") if t]
    for token in reversed(tokens):  # 구체 필드(마지막 토큰)부터 상위 컨테이너 순으로
        cues = _PATCH_FIELD_CUES.get(token)
        if cues is not None:
            return any(cue in compact for cue in cues)
    # 매핑에 없는 경로는 판단 근거가 없다 — 보수적으로 거부하지 않고 기존 검증에 맡긴다.
    return True


def _explicit_breakout_lookback(text: Optional[str]) -> Optional[int]:
    """신고가/고점 돌파 원문에서 명시적 기준 기간(거래일)을 추출한다. 없으면 None.

    '52주'는 거래일로 환산(52주=252, N주=N×5), 'N일'은 그대로, 단위 없는 '52'만 1년(252).
    기간 언급이 아예 없으면(예: 그냥 '신고가 돌파') None — 조용한 기본값 확정 금지 원칙에
    따라 되묻기에 맡긴다. 레거시 nl_parser._extract_breakout_lookback과 동일 환산 규칙.
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


def _fill_deterministic_condition_params(intent: StrategyIntent, user_input: str) -> None:
    """LLM 인터프리터가 놓치거나 오분류한 조건을 원문에서 결정적으로 교정한다(되묻기 전에 적용).

    완결성 검증은 결정론 오버라이드 적용 전의 raw LLM intent에 대해 돌기 때문에, LLM의
    누락/오분류가 '이미 사용자가 말한 값'을 되묻는 사고로 이어진다. 여기서 결정론이 확실히
    아는 것을 미리 채워/고쳐 헛질문을 막는다.

    ① breakout(신고가 돌파) lookback_period: 프롬프트에 '52주=252' 환산 규칙이 없어 LLM이
       '52주 신고가'의 기간을 파라미터로 옮기지 못하고 비운다 → 원문(조건 source_text 우선,
       없으면 전체 입력)에 명시적 기간이 있을 때만 채운다(없으면 그대로 두어 되묻기에 맡김).
    ② trading_value 오분류: '거래량이 평균보다 늘어난' 같은 동적 급증 표현을 LLM이 종종
       거래대금 임계 신호(trading_value=절대 억원 값 필요)로 오분류 → 거래대금 임계값을 되묻는다.
       원문이 급증/평균대비 증가 표현이면 volume_spike(OBV, 임계값 불필요)로 결정적으로 고친다.
       (엔진 반영값도 이 재분류와 일치 — 오버라이드의 _extract_technical_signals가 같은 규칙.)
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
            if lookback is None:
                lookback = _explicit_breakout_lookback(user_input)
            if lookback is not None:
                cond.parameters["lookback_period"] = float(lookback)
        elif spec.id in ("technical.trading_value", "fundamental.trading_value"):
            surge_text = _compact(cond.source_text or user_input)
            if _mentions_volume_surge(surge_text):
                cond.factor = "technical.volume_spike"
                cond.operator = "crosses_above"
                cond.value = None


def run_primary_parse(user_input: str, on_stage=None) -> Optional[Dict[str, Any]]:
    """LLM Interpreter 기본 경로 실행. 성공 시 결과 dict, 폴백 필요 시 None.

    반환: {"parsed": ParsedStrategy, "clarification_question": str|None,
           "clarification_suggestions": [str]|None, "notices": [str],
           "interpreter": 관측 메타}
    """
    from strategy_conversation.compiler.strategy_compiler import (
        StrategyCompileError,
        compile_partial,
        compile_strategy,
    )
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.validation.pipeline import run_validation

    if on_stage is not None:
        on_stage("thinking")
    try:
        interpreter = _get_interpreter(StrategyInterpreter)
        result = interpreter.interpret(user_input)
    except InterpreterError as exc:
        logger.warning("interpreter primary failed, falling back to rule parser | err=%s",
                       str(exc)[:200])
        return None
    except Exception as exc:  # noqa: BLE001 — 연결 실패 등도 폴백(기존 경로가 503 처리)
        logger.warning("interpreter primary transport error, falling back | err=%r", exc)
        return None

    _fill_deterministic_condition_params(result.intent, user_input)
    validated, report = run_validation(result.intent)
    _log_llm("✓ 검증", (
        f"status={report.status} 오류={len(report.errors)} 누락={len(report.missing_fields)} "
        f"질문={len(report.clarification_questions)} 미지원={report.unsupported_features or '[]'}"
    ))
    if validated.intent not in _STRATEGY_INTENTS or validated.strategy is None:
        _log_llm("↩ 폴백", f"전략 파이프라인 대상이 아닌 intent={validated.intent} — 규칙 파서로")
        logger.info("interpreter primary non-strategy intent=%s, falling back",
                    validated.intent)
        return None

    notices: List[str] = list(report.warnings)
    try:
        if report.is_valid:
            parsed = compile_strategy(validated, report, user_input)
            dropped: List[str] = []
        else:
            parsed, dropped = compile_partial(validated, report, user_input)
    except StrategyCompileError as exc:
        logger.warning("interpreter primary compile failed, falling back | err=%s", exc)
        return None
    # 레거시 파서와 동일한 결정적 보정 전체를 적용한다 — 명시적 날짜·지정 종목만 부분
    # 적용하던 시절, '최근 3년'→MA 365일 오귀속(QA 11-1), 익절 0.0001% 드롭(14-5),
    # 시총 100조→100억 단위 오류(24-2), 슬리피지 드롭(24-10) 등 인터프리터 LLM의 수치
    # 드리프트가 그대로 노출됐다. 프롬프트에 명시된 값만 덮어쓰므로 인터프리터 해석과
    # 충돌하지 않는다(레거시 LLM 폴백과 같은 계약).
    from engine.nl_parser import _apply_prompt_overrides
    parsed = _apply_prompt_overrides(parsed, user_input)
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

    return {
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
    }


def run_primary_modification(user_input: str, previous_parsed: dict, on_stage=None) -> Optional[Dict[str, Any]]:
    """수정 요청의 LLM Interpreter 기본 경로. 성공 시 결과 dict, 폴백 필요 시 None.

    안전 장치(전부 결정론):
    ① 라운드트립 가드 — 기존 전략을 decompile→재compile(+이월)했을 때 원본과 1비트라도
       다르면 StrategySpec이 표현 못 하는 전략(rsi rebound/macd zero 모드 등)이므로 이관을
       거부하고 기존 modify 경로로 폴백한다(목록형 필드 소실 사고 방지의 구조적 보장).
    ② patches 필수 — LLM이 전체 전략을 재출력하면(필드 소실 위험) 수락하지 않는다.
       예외: CLARIFY_STRATEGY(패치 없음)+질문이 있고 결정적 fast-path도 처리 못 하는
       입력이면, 폴백해 질문을 버리는 대신 전략을 그대로 유지한 채 질문을 clarification
       채널로 전달한다(무변경 요약만 재렌더링되던 2026-07-17 사고 방지).
       예외 2: 패치 없이 EXPLAIN_INDICATOR거나 unsupported_features만 보고된 경우도
       폴백하지 않고 전략을 유지한다(같은 사고의 2차 — 인터프리터가 질문 대신
       unsupported_features=["PBR 개념 설명 요청"]으로 보고). 정의형 질문(결정적 cue)이면
       /query/general과 같은 LLM 설명을 notices로 실제 답변하고, 아니면 미반영을 알린다.
    ③ 패치 적용 후 검증 READY일 때만 컴파일. 아니면 폴백(임계값 없는 조건 추가 등은
       상류 clarification_for_add가 이미 가로챈다).
    description·execution_timing·entry_filters는 StrategySpec 밖이므로 원본에서 이월.
    """
    from engine.nl_parser import ParsedStrategy
    from strategy_conversation.compiler.strategy_compiler import (
        StrategyCompileError,
        compile_strategy,
    )
    from strategy_conversation.compiler.strategy_decompiler import decompile_strategy
    from strategy_conversation.conversation.patch_applier import PatchError, apply_patches
    from strategy_conversation.interpreter.llm_strategy_interpreter import (
        InterpreterError,
        StrategyInterpreter,
    )
    from strategy_conversation.interpreter.models import StrategyIntent as _Intent
    from strategy_conversation.validation.pipeline import run_validation

    try:
        prev = ParsedStrategy.model_validate(previous_parsed)
    except Exception:  # noqa: BLE001 — 비정상 previous는 기존 경로가 처리
        return None

    # 결정적 fast-path가 완전히 해석하는 수정("손절 10%로", 명시적 백테스트 기간 등)은
    # 인터프리터를 건너뛴다 — 폴백 경로(parse_modification)의 첫 단계가 같은 fast-path라
    # 즉시 확정된다. LLM 왕복 지연과 수치·날짜 드리프트(오늘 날짜를 모르는 모델이
    # 과거 연도를 미래로 오판해 종료일을 누락하는 사고 등)를 원천 회피한다
    # (핵심은 결정적, 긴 꼬리는 LLM).
    from engine.nl_parser import _modify_rule_based
    if _modify_rule_based(user_input, previous_parsed) is not None:
        _log_llm("↩ 폴백", "결정적 fast-path 처리 가능 — 인터프리터 생략")
        logger.info("modify primary skipped, deterministic fast-path handles input")
        return None

    def _carry_over(parsed):
        return parsed.model_copy(update={
            "description": prev.description,
            "execution_timing": prev.execution_timing,
            "entry_filters": prev.entry_filters,
        })

    draft_spec = decompile_strategy(prev)
    ready_report = ValidationReport(is_valid=True, status="READY")
    try:
        roundtrip = _carry_over(compile_strategy(
            _Intent(intent="CREATE_STRATEGY", strategy=draft_spec, confidence=1.0),
            ready_report, prev.description,
        ))
    except StrategyCompileError:
        return None
    if roundtrip.model_dump() != prev.model_dump():
        _log_llm("↩ 폴백", "라운드트립 불일치(표현 불가 전략) — 기존 수정 경로로")
        logger.info("modify primary roundtrip mismatch, falling back to legacy modify")
        return None

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
        logger.warning("modify primary transport error, falling back | err=%r", exc)
        return None

    intent = result.intent
    if intent.intent == "CLARIFY_STRATEGY" and not intent.patches and intent.clarification_questions:
        # 되묻기 의도를 폴백으로 버리면 기존 수정 LLM이 무변경 전략을 정상 응답처럼
        # 반환해 질문이 사라진다(2026-07-17 "pbr이 뭐야?" 사고). 결정적 fast-path가
        # 처리할 수 있는 입력은 상단 게이트가 이미 폴백시켰으므로, 여기 도달한 되묻기는
        # 단순 수정을 가로막을 수 없다 — 전략을 유지한 채 질문을 채널로 전달한다.
        question, chips = _build_clarification(
            ValidationReport(clarification_questions=intent.clarification_questions),
            intent,
        )
        _log_llm("✓ 되묻기", (
            f"질문={len(intent.clarification_questions)} — 전략 유지, clarification 채널로"
        ))
        return {
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
        }
    if not intent.patches and (
        intent.intent == "EXPLAIN_INDICATOR" or intent.unsupported_features
    ):
        # 개념 설명 질문·미지원 개념 요청을 폴백으로 버리면 기존 수정 LLM이 무변경 전략을
        # 정상 응답처럼 반환해 요청이 조용히 사라진다(2026-07-17 "pbr이 뭐야?" 사고 2차 —
        # 인터프리터가 질문을 내지 않고 unsupported_features로만 보고한 케이스). 전략은
        # 그대로 유지하되, 정의형 질문이면 /query/general과 같은 LLM 답변을 생성해 notices로
        # 실제 설명을 전달한다("변경하지 않았어요" 안내만 주던 2026-07-19 교정). 질문 판정은
        # 4B 라벨이 아니라 결정적 cue(is_definition_question)가 기준 — 같은 발화를 4B가
        # EXPLAIN_INDICATOR로도 unsupported_features로도 내는 실측 대응.
        from api.intent_routes import generate_general_answer
        from intent import platform_defaults
        from intent.classifier import is_definition_question

        is_question = (
            intent.intent == "EXPLAIN_INDICATOR"
            or is_definition_question(user_input)
            # 설정 기본값 질문("슬리피지 몇 %가 기본이지?")도 수정이 아닌 질문이다 —
            # generate_general_answer가 실제 코드 기본값으로 결정적으로 답한다.
            or platform_defaults.is_default_question(user_input)
        )
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
        return {
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
        }
    if intent.intent not in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") or not intent.patches:
        _log_llm("↩ 폴백", f"patches 미출력(intent={intent.intent}) — 기존 수정 경로로")
        logger.info("modify primary without patches (intent=%s), falling back", intent.intent)
        return None

    # 환각 게이트: 발화에 해당 필드의 cue조차 없는 패치는 지어낸 것이다 — 거부한다.
    from engine.nl_parser import _compact
    compact_input = _compact(user_input)
    cued_patches = [p for p in intent.patches if _patch_cue_supported(p, compact_input)]
    rejected = len(intent.patches) - len(cued_patches)
    if rejected:
        _log_llm("✗ 패치 거부", f"{rejected}건 — 발화에 필드 cue 없음(환각 게이트)")
    if not cued_patches:
        # 전량 환각(예: 후속 질문 "다른 예는 없어?"에 임의 패치) — 전략을 그대로 유지하고,
        # 질문성 입력이면 지식 답변을, 아니면 미해석 안내를 전달한다(QA 20-3).
        from api.intent_routes import generate_general_answer
        looks_like_question = bool(re.search(r"[?？]\s*$|없어\s*\??$|알려줘$", user_input.strip()))
        answer = generate_general_answer(user_input) if looks_like_question else None
        notices = [answer] if answer else [
            "요청을 전략 변경으로 해석하지 못해 전략은 그대로 유지했어요. "
            "바꾸고 싶은 조건(예: 손절 10%로, 종목 20개로)을 구체적으로 말씀해 주세요."
        ]
        return {
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
        }
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
    _fill_deterministic_condition_params(modify_intent, user_input)
    validated, report = run_validation(modify_intent)
    _log_llm("✓ 검증", (
        f"status={report.status} patches={len(cued_patches)} "
        f"오류={len(report.errors)} 미지원={report.unsupported_features or '[]'}"
    ))
    if not report.is_valid:
        _log_llm("↩ 폴백", f"패치 적용 후 검증 미통과(status={report.status}) — 기존 수정 경로로")
        logger.info("modify primary not READY after patch (status=%s), falling back",
                    report.status)
        return None
    try:
        parsed = _carry_over(compile_strategy(validated, report, prev.description))
    except StrategyCompileError as exc:
        logger.warning("modify primary compile failed, falling back | err=%s", exc)
        return None
    # 레거시 수정 경로와 동일한 결정적 보정(신호 재검증 생략·universe 보존) — 명시된
    # 수치·날짜·리스크 값은 결정적 추출이 최종 진실이다.
    from engine.nl_parser import _apply_prompt_overrides
    parsed = _apply_prompt_overrides(
        parsed, user_input, skip_signal_validation=True, preserve_universe=True
    )

    return {
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
    }


_interpreter_singleton = None


def _get_interpreter(cls):
    global _interpreter_singleton
    if _interpreter_singleton is None:
        _interpreter_singleton = cls()
    return _interpreter_singleton


def apply_primary_meta(result: dict, primary: Dict[str, Any]) -> None:
    """_build_parse_result 산출물에 primary 경로의 질문/안내/메타를 병합한다.

    인터프리터의 질문이 기존 detect_missing_entry_clarification 질문보다 구체적이므로
    있으면 우선한다. notices는 뒤에 덧붙인다(하한선 보정 안내가 앞).
    """
    if primary["clarification_question"]:
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
