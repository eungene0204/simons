"""LLM Strategy Interpreter — 사용자 자연어를 StrategyIntent JSON으로 변환.

자연어 이해의 주체는 인터프리터 LLM이다(STRATEGY_INTERPRETER_MODEL 전용 슬롯 —
2026-07-26부터 Qwen 3.5 9B, 미설정 시 NL_OLLAMA_MODEL 폴백). 이 모듈은:
  ① Ollama /api/chat(format=json, think=false)로 구조화 출력을 요청하고
  ② JSON 추출 → Pydantic 검증 → 스키마 실패 시 오류와 함께 1회 자동 수정 요청
     (수치 누락으로 인한 재생성 요청은 2026-08-07 폐지 — recall_validator 상단 참조)
  ③ 다시 실패하면 InterpreterError를 던진다(호출부가 안전한 사용자 응답 담당).

transport(chat_fn)는 주입 가능해 테스트가 LLM 없이 스텁으로 검증할 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Callable, Optional

from pydantic import ValidationError

from llm_backend import OLLAMA_MODEL_9B
from strategy_conversation import config
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.output_repair import (
    build_repair_prompt,
    extract_json_object,
)
from strategy_conversation.interpreter.prompts import (
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
)
from strategy_conversation.validation.recall_validator import (
    drop_ungrounded_condition_periods,
    find_unreflected_numbers,
)

logger = logging.getLogger("strategy_interpreter")

# 대조 대상은 전략 본문을 만들어내는 intent뿐이다 — 설명 질문·비전략 요청은
# 수치가 출력에 없는 것이 정상이다.
_RECALL_CHECKED_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")

# 이 슬롯(9B)을 쓰는 모든 호출의 per-call 상한. 인터프리터와 planner가 같은 chat을
# 공유하므로 한 곳에서 정한다. 예산 사슬: 프록시 240초 ⊃ per-call 180초 + 후행 검증 90초.
_LLM_CALL_TIMEOUT_S = 180


def _recall_gap(user_input: str, intent) -> list[str]:
    if intent.intent not in _RECALL_CHECKED_INTENTS:
        return []
    return find_unreflected_numbers(user_input, intent)

ChatFn = Callable[[str, str], str]  # (system_prompt, user_message) -> raw text

# 스트리밍 출력에서 '지금 생성 중인 섹션'을 진행 단계로 매핑한다. 입력은 사용자 원문이
# 아니라 LLM이 생성 중인 StrategyIntent JSON이며, 따옴표 포함 키 문자열의 위치만 본다
# — 형식 관찰이지 의미 해석이 아니다(자연어 해석 구조 원칙의 정규화 레인).
# portfolio·backtest는 별도 문구를 만들 만큼 길지 않아 'settings' 하나로 묶는다.
_SECTION_STAGE_MARKERS: list[tuple[str, str]] = [
    ('"universe"', "universe"),
    ('"entry_conditions"', "entry"),
    ('"exit_conditions"', "exit"),
    ('"risk_management"', "risk"),
    ('"portfolio"', "settings"),
    ('"backtest"', "settings"),
]


def _stage_from_partial(partial_output: str) -> Optional[str]:
    """누적 출력에서 가장 마지막에 등장한 섹션 키의 단계를 돌려준다(없으면 None)."""
    best_stage: Optional[str] = None
    best_idx = -1
    for marker, stage in _SECTION_STAGE_MARKERS:
        idx = partial_output.rfind(marker)
        if idx > best_idx:
            best_idx = idx
            best_stage = stage
    return best_stage


def _flatten_json_columns(text: str) -> Optional[str]:
    """JSON 객체 텍스트를 'key = value' 컬럼 목록으로 펼친다. JSON 객체가 아니면 None."""
    try:
        obj = json.loads(extract_json_object(text))
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict) or not obj:
        return None

    lines: list[tuple[str, str]] = []

    def walk(value, path: str) -> None:
        if isinstance(value, dict) and value:
            for key, child in value.items():
                walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")
        else:
            rendered = json.dumps(value, ensure_ascii=False)
            if len(rendered) > 200:
                rendered = rendered[:200] + "…"
            lines.append((path, rendered))

    walk(obj, "")
    width = max(len(path) for path, _ in lines)
    return "\n".join(f"  {path.ljust(width)} = {value}" for path, value in lines)


def _log_llm(tag: str, text: str) -> None:
    """LLM 왕복을 dev 콘솔에서 눈으로 확인할 수 있게 출력한다([NL-PARSE]와 동일한 print 관례).

    uvicorn 로깅 설정과 무관하게 항상 보이도록 print를 쓴다. JSON 응답은 한 줄 raw로는
    읽을 수 없어 key = value 컬럼으로 펼쳐 찍는다(사용자 요청 2026-07-29) — 정보는 그대로,
    JSON으로 파싱되지 않는 텍스트만 원문 그대로 찍는다(깨진 출력 디버깅용).
    """
    columns = _flatten_json_columns(text)
    if columns is None:
        print(f"[LLM-INTERPRETER] {tag} {text}", flush=True)
    else:
        print(f"[LLM-INTERPRETER] {tag}\n{columns}", flush=True)


class InterpreterError(RuntimeError):
    """복구 재시도 후에도 유효한 StrategyIntent를 얻지 못한 경우."""


class InterpreterResult:
    def __init__(
        self,
        intent: StrategyIntent,
        raw_output: str,
        repair_attempts: int,
        latency_ms: float,
        model_name: str,
        unreflected_numbers: Optional[list[str]] = None,
    ):
        self.intent = intent
        self.raw_output = raw_output
        self.repair_attempts = repair_attempts
        self.latency_ms = latency_ms
        self.model_name = model_name
        self.prompt_version = PROMPT_VERSION
        # 출력에 나타나지 않은 입력 수치 표현(진단용) — 사용자 안내는 하지 않는다.
        self.unreflected_numbers = unreflected_numbers or []


def _default_ollama_chat(model: str) -> ChatFn:
    """기존 파서와 동일한 콜드스타트 내성 Ollama 호출(warm-up + 재시도 재사용)."""

    # 공유 chat 계약은 (system_prompt, user_msg, *, max_tokens) -> str — term_grounding
    # 등 소비자가 max_tokens를 넘긴다(미수용 시 TypeError로 검색 그라운딩 전체가 침묵 실패).
    # on_chunk: 진행 단계 표시용 스트리밍 콜백(누적 텍스트 수신). 미전달 시 기존 비스트리밍
    # 경로 그대로 — 반환 계약(완성 텍스트)은 두 경로 모두 동일하다.
    def chat(system_prompt: str, user_message: str, *, max_tokens: int | None = None,
             on_chunk: Callable[[str], None] | None = None) -> str:
        import urllib.request

        from engine.nl_parser import (
            _OLLAMA_NUM_CTX,
            _ollama_ensure_warm,
            _ollama_open_with_retry,
        )
        from llm_backend import OLLAMA_BASE_URL, is_local_ollama, ollama_auth_headers

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": on_chunk is not None,
            "think": False,
            "format": "json",
            "options": {"temperature": 0, "num_ctx": _OLLAMA_NUM_CTX,
                        "num_predict": max_tokens or 2048},
        }
        if is_local_ollama():
            # 로컬 dev 상주 유지 — Ollama는 마지막 요청의 keep_alive로 언로드 타이머를
            # 갱신하므로(기본 5분), startup preload(-1)만으론 첫 요청 후 다시 풀린다.
            # 원격(Modal)은 컨테이너 수명이 별도 관리라 기본값을 유지한다.
            payload["keep_alive"] = -1
        body = json.dumps(payload).encode()
        _ollama_ensure_warm()
        req = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json", **ollama_auth_headers()},
            method="POST",
        )
        # 관찰 span(비활성 시 no-op) — 호출 자체는 그대로다. 토큰 수는 Ollama 응답에
        # 이미 들어 있는 값을 읽기만 한다(prompt_eval_count/eval_count).
        from observability import span
        from observability.agent_trace import ollama_usage

        with span(
            f"LLM · {model}", "llm",
            inputs={"system_prompt": system_prompt, "user_prompt": user_message},
            metadata={"model": model, "temperature": 0,
                      "num_ctx": _OLLAMA_NUM_CTX, "max_tokens": max_tokens or 2048},
        ) as trace:
            # per-call 상한. 비용은 프롬프트 길이가 아니라 **생성 토큰 수 ÷ 그 시각의
            # 처리량**이다 — 인터프리터 한 호출이 400~500토큰을 생성하므로 처리량이
            # 4 tok/s까지 떨어지면 125초가 되어 120초 상한에 걸렸다(실측 2026-08-07).
            # 프록시 예산(240초)에서 후행 검증 몫(90초)을 남긴 값이다.
            with _ollama_open_with_retry(req, timeout=_LLM_CALL_TIMEOUT_S) as resp:
                if on_chunk is None:
                    data = json.loads(resp.read())
                    content = (data.get("message") or {}).get("content", "")
                else:
                    # 스트리밍(NDJSON) — 조각을 누적해 콜백에 넘기고, done 라인의
                    # 사용량 통계를 비스트리밍과 동일하게 trace에 기록한다.
                    parts: list[str] = []
                    data = {}
                    for line in resp:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        piece = (obj.get("message") or {}).get("content", "")
                        if piece:
                            parts.append(piece)
                            try:
                                on_chunk("".join(parts))
                            except Exception:  # noqa: BLE001 — 진행 표시 실패가 해석을 깨면 안 된다
                                logger.debug("interpreter on_chunk failed", exc_info=True)
                        if obj.get("done"):
                            data = obj
                    content = "".join(parts)
            trace.meta(**ollama_usage(data))
            trace.output(response=content)
            return content

    return chat


class StrategyInterpreter:
    def __init__(self, chat_fn: Optional[ChatFn] = None, model: Optional[str] = None):
        # 인터프리터 전용 모델 슬롯(SUMMARIZE_OLLAMA_MODEL 선례) — 파서·코치가 공유하는
        # NL_OLLAMA_MODEL과 분리해, 해석 품질을 위해 더 큰 모델을 쓰되 다른 경로의 지연에
        # 영향을 주지 않는다.
        #
        # 미설정 시 NL_OLLAMA_MODEL 폴백은 유지한다(기존 계약) — 다만 **아무 슬롯도
        # 설정되지 않았으면 코드에 박힌 모델명으로 떨어지지 않고 즉시 실패한다**
        # (2026-07-30). load_dotenv()는 main.py 임포트에만 걸려 있어 서버를 거치지 않는
        # 스크립트(QA 하니스·진단)는 두 env가 모두 비는데, 종전엔 잘못된 기본값
        # `qwen3:8b`로 조용히 떨어져 **운영과 다른 모델로 검증하고도 통과한 것처럼
        # 보였다**(실제 회귀를 놓칠 뻔한 사고, FR-STR-019p ⑤).
        #
        # 실패 조건을 '둘 다 미설정'으로 좁힌 이유: 배포는 env_file로 .env를 주입하므로
        # 둘 중 하나는 항상 설정돼 있다 — 인터프리터 슬롯만 비운 환경(레거시 폴백 운용)을
        # 이 가드로 깨뜨리지 않으면서, 위 사고 경로(둘 다 빈 스크립트)는 그대로 막는다.
        self.model_name = (
            model
            or os.environ.get("STRATEGY_INTERPRETER_MODEL")
            or os.environ.get("NL_OLLAMA_MODEL")
            or ""
        )
        if not self.model_name.strip():
            raise InterpreterError(
                "해석 모델 슬롯이 설정되지 않았습니다 "
                "(STRATEGY_INTERPRETER_MODEL 또는 NL_OLLAMA_MODEL). "
                f"코드 기본값으로 대체하지 않습니다 — 운영 인터프리터 모델은 {OLLAMA_MODEL_9B}입니다. "
                "서버 밖에서 실행 중이면 .env를 로드하거나 이 환경변수를 명시하세요."
            )
        self._chat = chat_fn or _default_ollama_chat(self.model_name)
        # 진행 단계 스트리밍은 on_chunk를 받는 chat만 가능하다 — 주입 스텁(테스트·QA
        # 하니스)은 (system, user) 2-인자 계약이므로 서명을 보고 조용히 비활성화한다.
        import inspect

        try:
            self._chat_accepts_chunks = any(
                p.name == "on_chunk" or p.kind is inspect.Parameter.VAR_KEYWORD
                for p in inspect.signature(self._chat).parameters.values()
            )
        except (TypeError, ValueError):
            self._chat_accepts_chunks = False
        self._system_prompt = build_system_prompt()

    def interpret(
        self, user_input: str, draft: Optional[dict] = None,
        pending_question: Optional[str] = None,
        on_stage: Optional[Callable[[str], None]] = None,
    ) -> InterpreterResult:
        """본체는 _interpret다 — 이 래퍼는 관찰 span만 연다(비활성 시 no-op).

        on_stage: 생성 중인 섹션 전환 콜백(진행 표시용) — 초기 생성에서만 쓰고,
        수정 모드(draft)는 patches 출력이라 섹션 순서가 없어 적용하지 않는다.
        """
        from observability import span
        from observability.agent_trace import state_diff

        with span(
            "Interpreter · 전략 해석", "chain",
            inputs={"user_input": user_input, "draft": draft,
                    "pending_question": pending_question},
            metadata={"model": self.model_name, "prompt_version": PROMPT_VERSION,
                      "mode": "modify" if draft else "create"},
        ) as trace:
            result = self._interpret(user_input, draft, pending_question, on_stage)
            # 복구 재시도 = LLM 출력이 스키마를 못 맞춰 다시 부른 횟수(스펙 § Retry Count).
            trace.meta(retry_count=result.repair_attempts,
                       interpreter_latency_ms=result.latency_ms,
                       unreflected_numbers=result.unreflected_numbers)
            from observability.tracing import bump

            bump("retry_count", result.repair_attempts)
            trace.output(
                intent=result.intent.intent,
                strategy=result.intent.strategy,
                # 수정 모드에서 초안이 무엇으로 바뀌었나(스펙 § 6 State 변화).
                state_diff=state_diff(draft, result.intent.strategy) if draft else None,
            )
            return result

    def _interpret(
        self, user_input: str, draft: Optional[dict] = None,
        pending_question: Optional[str] = None,
        on_stage: Optional[Callable[[str], None]] = None,
    ) -> InterpreterResult:
        started = time.perf_counter()
        user_prompt = build_user_prompt(user_input, draft, pending_question)
        _log_llm("▶ 요청", f"{user_input!r}" + (" (수정 모드 — 전략 초안 포함)" if draft else ""))
        on_chunk: Optional[Callable[[str], None]] = None
        if on_stage is not None and draft is None and self._chat_accepts_chunks:
            last_stage: dict = {"stage": None}

            def on_chunk(accumulated: str) -> None:
                stage = _stage_from_partial(accumulated)
                if stage is not None and stage != last_stage["stage"]:
                    last_stage["stage"] = stage
                    on_stage(stage)

        if on_chunk is not None:
            raw = self._chat(self._system_prompt, user_prompt, on_chunk=on_chunk)
        else:
            raw = self._chat(self._system_prompt, user_prompt)
        _log_llm("◀ 원본 응답", raw.strip())

        attempts = 0
        last_error: Exception | None = None
        current_raw = raw
        while True:
            try:
                intent = StrategyIntent.model_validate_json(extract_json_object(current_raw))
                # 문맥 보정(결정론): 기존 초안이 없으면 MODIFY/CLARIFY는 성립 불가 —
                # 4B가 단문 전략 서술을 MODIFY_STRATEGY로 오분류하는 드리프트 실측(2026-07-16).
                if draft is None and intent.intent in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") \
                        and intent.strategy is not None:
                    intent = intent.model_copy(update={"intent": "CREATE_STRATEGY"})
                # 수치 반영 대조(§ 3-1). 탐지는 유지하되 **재생성 요청은 하지 않는다**
                # (2026-08-07 전수 실측으로 폐지). 재요청 62건 중 45건은 아무것도 고치지
                # 못했고(47%는 1차와 바이트 동일 — temperature=0), 고친 17건도 진짜 구제 3건
                # 대 훼손 3건이었다(정성 표현 '낮은 편'의 의도적 되묻기를 "월 1회"의 유령
                # 숫자 1로 덮어 PER≤1·PBR≤1을 만든 실측). 값은 본전인데 누적 2,445초를 썼다.
                #
                # 재요청이 1차보다 더 알던 것은 '어느 수치가 빠졌나' 목록 하나뿐인데, 그
                # 목록은 입력만으로 계산된다 — 그래서 1차 프롬프트로 옮겼다(build_user_prompt).
                # 게다가 1차는 그 수치를 **문맥 안에서** 본다("월 1회 리밸런싱"), 재요청은
                # 맥락 없는 '1'만 받아 채워 넣을 곳을 지어냈다. 탐지 결과는 아래 두 곳이
                # 계속 쓴다: 근거 없는 기간 비우기, 미반영 진단 로그.
                residual = (
                    _recall_gap(user_input, intent) if config.recall_check_enabled() else []
                )
                # 근거 없는 기간 파라미터는 확정하지 않는다 — 비워서 되묻기로 보낸다.
                # ('60일 신고가'에 252가 들어가고 검증이 READY로 통과하던 2026-08-07 사고)
                if residual:
                    cleared = drop_ungrounded_condition_periods(user_input, intent, residual)
                    if cleared:
                        _log_llm("△ 근거 없는 기간 제거",
                                 f"{', '.join(cleared)} — 확정 대신 되묻기")
                if residual:
                    _log_llm("△ 수치 누락 잔존", f"미반영: {', '.join(residual)}")
                _log_llm("✓ 해석", (
                    f"intent={intent.intent} "
                    f"patches={len(intent.patches)} repairs={attempts} "
                    f"({round((time.perf_counter() - started) * 1000)}ms)"
                ))
                return InterpreterResult(
                    intent=intent,
                    raw_output=current_raw,
                    repair_attempts=attempts,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    model_name=self.model_name,
                    unreflected_numbers=residual,
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempts >= config.MAX_REPAIR_ATTEMPTS:
                    break
                attempts += 1
                logger.warning(
                    "interpreter output invalid, requesting repair | attempt=%d err=%s",
                    attempts, str(exc)[:300],
                )
                _log_llm(f"⟳ 복구 요청({attempts}회차)", f"검증 오류: {str(exc)[:300]}")
                repair_prompt = build_repair_prompt(user_input, current_raw, str(exc), draft)
                current_raw = self._chat(self._system_prompt, repair_prompt)
                _log_llm(f"◀ 복구 응답({attempts}회차)", current_raw.strip())

        _log_llm("✗ 해석 실패", f"{attempts}회 복구 후에도 스키마 불만족: {str(last_error)[:200]}")
        raise InterpreterError(
            f"LLM 출력이 {attempts}회 복구 후에도 StrategyIntent 스키마를 만족하지 않습니다: "
            f"{str(last_error)[:500]}"
        )
