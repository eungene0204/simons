"""LLM Strategy Interpreter — 사용자 자연어를 StrategyIntent JSON으로 변환.

자연어 이해의 주체는 인터프리터 LLM이다(STRATEGY_INTERPRETER_MODEL 전용 슬롯 —
2026-07-26부터 Qwen 3.5 9B, 미설정 시 NL_OLLAMA_MODEL 폴백). 이 모듈은:
  ① Ollama /api/chat(format=json, think=false)로 구조화 출력을 요청하고
  ② JSON 추출 → Pydantic 검증 → 실패 시 오류와 함께 1회 자동 수정 요청
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
    build_recall_repair_prompt,
    find_unreflected_numbers,
)

logger = logging.getLogger("strategy_interpreter")

# 대조 대상은 전략 본문을 만들어내는 intent뿐이다 — 설명 질문·비전략 요청은
# 수치가 출력에 없는 것이 정상이다.
_RECALL_CHECKED_INTENTS = ("CREATE_STRATEGY", "MODIFY_STRATEGY", "CLARIFY_STRATEGY")


def _recall_gap(user_input: str, intent) -> list[str]:
    if intent.intent not in _RECALL_CHECKED_INTENTS:
        return []
    return find_unreflected_numbers(user_input, intent)

ChatFn = Callable[[str, str], str]  # (system_prompt, user_message) -> raw text


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
        # 재요청 후에도 출력에 나타나지 않은 입력 수치 표현 — 하류가 사용자에게 알린다.
        self.unreflected_numbers = unreflected_numbers or []


def _default_ollama_chat(model: str) -> ChatFn:
    """기존 파서와 동일한 콜드스타트 내성 Ollama 호출(warm-up + 재시도 재사용)."""

    # 공유 chat 계약은 (system_prompt, user_msg, *, max_tokens) -> str — term_grounding
    # 등 소비자가 max_tokens를 넘긴다(미수용 시 TypeError로 검색 그라운딩 전체가 침묵 실패).
    def chat(system_prompt: str, user_message: str, *, max_tokens: int | None = None) -> str:
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
            "stream": False,
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
        with _ollama_open_with_retry(req, timeout=120) as resp:
            data = json.loads(resp.read())
        return (data.get("message") or {}).get("content", "")

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
        self._system_prompt = build_system_prompt()

    def interpret(self, user_input: str, draft: Optional[dict] = None) -> InterpreterResult:
        started = time.perf_counter()
        user_prompt = build_user_prompt(user_input, draft)
        _log_llm("▶ 요청", f"{user_input!r}" + (" (수정 모드 — 전략 초안 포함)" if draft else ""))
        raw = self._chat(self._system_prompt, user_prompt)
        _log_llm("◀ 원본 응답", raw.strip())

        attempts = 0
        last_error: Exception | None = None
        current_raw = raw
        recall_retried = False
        # 수치 재요청 직전의 유효 해석 — 재요청 결과가 더 나쁘면 되돌린다.
        pre_recall: tuple[StrategyIntent, str] | None = None
        while True:
            try:
                intent = StrategyIntent.model_validate_json(extract_json_object(current_raw))
                # 문맥 보정(결정론): 기존 초안이 없으면 MODIFY/CLARIFY는 성립 불가 —
                # 4B가 단문 전략 서술을 MODIFY_STRATEGY로 오분류하는 드리프트 실측(2026-07-16).
                if draft is None and intent.intent in ("MODIFY_STRATEGY", "CLARIFY_STRATEGY") \
                        and intent.strategy is not None:
                    intent = intent.model_copy(update={"intent": "CREATE_STRATEGY"})
                # 수치 재요청이 전략을 잃어버렸으면 재요청 출력을 폐기하고 직전 해석을 쓴다.
                # 실측 사고(2026-07-27, '반도체 업종 ROE·부채비율+모멘텀' 예시): 1차 출력은
                # 유니버스·재무 조건·랭킹·포트폴리오까지 정상이었는데 거래대금 '50억'만 빠져
                # 재요청 → 9B가 수정 턴처럼 patches만(strategy=null) 돌려주면서 정상 해석이
                # 통째로 교체 → 초기 파스에는 적용할 초안이 없어 해석 실패로 종결됐다.
                # 수치 누락은 요청을 실패시킬 사유가 아니다(§ 3-1) — 유효한 해석을 버리지 않는다.
                # 수정 턴은 patches가 내용이므로 strategy·patches가 모두 비면 잃은 것이다.
                repair_lost_content = (
                    intent.strategy is None if draft is None
                    else (intent.strategy is None and not intent.patches)
                )
                if pre_recall is not None and repair_lost_content:
                    intent, current_raw = pre_recall
                    _log_llm("△ 수치 재요청 폐기", "재요청 출력이 비어 직전 해석 유지")
                # 수치 반영 대조(§ 3-1). 스키마는 통과했지만 사용자가 말한 수치가 통째로
                # 빠진 경우 — 값을 채우지 않고 모델에게 한 번 다시 시킨다. 재요청 예산은
                # 스키마 복구와 공유하며, 재생성 후에도 남으면 그대로 진행한다(누락은
                # 스키마 오류가 아니므로 요청을 실패시키지 않는다).
                if not recall_retried and config.recall_check_enabled():
                    missing = _recall_gap(user_input, intent)
                    if missing and attempts < config.MAX_REPAIR_ATTEMPTS:
                        recall_retried = True
                        attempts += 1
                        pre_recall = (intent, current_raw)
                        _log_llm("⟳ 수치 누락 재요청", f"미반영: {', '.join(missing)}")
                        current_raw = self._chat(
                            self._system_prompt,
                            build_recall_repair_prompt(user_input, missing, current_raw, draft),
                        )
                        _log_llm("◀ 재요청 응답", current_raw.strip())
                        continue
                # 재요청 후에도(또는 재요청 예산이 없어) 남은 누락은 요청을 실패시키지 않되
                # 결과에 실어 하류가 사용자에게 정직하게 알린다 — 조용한 누락 금지.
                residual = (
                    _recall_gap(user_input, intent) if config.recall_check_enabled() else []
                )
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
