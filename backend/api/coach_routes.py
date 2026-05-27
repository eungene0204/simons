"""
FastAPI routes for the Strategy Coach — conversational AI layer.

POST /strategy/coach   — generate a coaching response using advisor_insight

Uses the same Qwen MLX model already loaded by NLStrategyParser (no extra memory cost).
main.py calls set_parser() after preloading to wire the shared model reference.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import OrderedDict
from hashlib import sha256
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from advisor.memory_repository import load_advisor_memory, load_vector_advisor_memory
from advisor.memory_retriever import retrieve_memory_context
from advisor.news_enrichment import build_coach_news_insight, build_news_context_from_strategy

logger = logging.getLogger(__name__)
router = APIRouter(tags=["coach"])

# Injected by main.py after NLStrategyParser is preloaded
_parser = None
_CACHE_MAX = 200
_coach_response_cache: OrderedDict[str, CoachResponse] = OrderedDict()
_coach_stream_cache: OrderedDict[str, str] = OrderedDict()


def set_parser(parser: Any) -> None:
    global _parser
    _parser = parser


COACH_SYSTEM_PROMPT = """당신은 퀀트 트레이딩 전략의 문제점을 짚어주는 전문 코치입니다.

당신의 역할은 전략에서 가장 중요한 문제 하나를 발견하고,
사용자가 왜 그것이 문제인지 직관적으로 이해하도록 설명하는 것입니다.

해결 방법은 별도 패널에서 안내되므로, 당신은 문제 설명에만 집중하세요.

[입력 컨텍스트]
시스템은 다음 내부 정보를 제공합니다 (사용자에게 직접 노출 금지):
1. parsed_strategy — 파싱된 전략 JSON (불완전할 수 있음)
2. advisor_insight — 사전 계산된 메트릭
3. news_agent_insight — 뉴스 신호 (선택)
4. strategy_memory_context — RAG/Experience Memory 검색 결과 (선택)

[핵심 목표]
가장 중요한 단 하나의 문제를 선택하여, 사용자가 그 심각성을 체감하게 설명하라.
우선순위:
1. 실행 불가능한 구조
2. 전략의 불완전성 (missing parameters)
3. 자본 대비 비현실적인 설정
4. 리스크 정의 부족
5. 성과상의 문제

[Missing 정보 탐지]
다음 항목이 parsed_strategy에 없으면 반드시 우선 지적하라:
- 최대 보유 종목 수 (max_positions)
- 손절 기준 (stop_loss_pct)
- 익절 기준 (take_profit_pct)
- 보유 기간 (hold_period_days)

[자본 기반 판단]
- initial_capital 기준으로 실행 가능성을 판단하라
- max_positions가 없으면 "자금 배분 기준이 불명확하다"는 문제로 접근

[뉴스 신호 우선 규칙]
news_agent_insight에 risk_alert_level이 high인 종목이 있으면 뉴스 리스크 문제를 최우선으로 지적

[RAG / Experience Memory 규칙]
- strategy_memory_context가 있으면 유사 전략 사례와 과거 조언 성공/실패 교훈을 근거로 판단하라
- data_sufficiency가 insufficient이면 유사 사례가 부족하다고 보고, 확정적 표현을 피하라
- retrieved_cases가 비어 있으면 과거 사례가 충분한 것처럼 꾸며내지 마라
- 백테스트 결과가 없으면 수익성이 좋거나 개선되었다고 단정하지 마라
- 과거 사례가 있어도 현재 전략의 자본, 거래비용, 슬리피지, OOS 검증 필요성을 무시하지 마라
- 유사 전략 수, 성과 수치, 성공/실패 분류는 제공된 컨텍스트만 사용하라
- 너는 검색/계산/판정 엔진이 아니라, 이미 계산된 근거를 설명하는 코치다

[금지 사항]
- 해결 방법, 구체적 수치 제안, 행동 지시 금지 — 문제 설명만 할 것
- 여러 문제 나열 금지 — 가장 중요한 하나만
- 제공되지 않은 백테스트 사례, 성과 수치, 개선 효과를 새로 만들지 말 것
- 내부 필드명(snake_case 변수명) 절대 출력 금지
  → take_profit_pct → "익절 기준", stop_loss_pct → "손절 기준", max_positions → "최대 보유 종목 수", hold_period_days → "보유 기간"
- advisor JSON 또는 뉴스 JSON 그대로 출력 금지
- 이미 전략에 포함된 내용 문제로 지적 금지

[응답 형식]
반드시 아래 JSON 형식으로만 응답하라. JSON 외에 다른 텍스트를 출력하지 마라:
{"message": "문제 설명 텍스트 (200자 이내, 왜 이것이 문제인지 사용자가 체감하도록)"}"""


class CoachRequest(BaseModel):
    user_prompt: str
    parsed_strategy: Dict[str, Any]
    advisor_insight: Optional[Dict[str, Any]] = None
    news_agent_insight: Optional[Dict[str, Any]] = None
    memory_strategy_cases: Optional[List[Dict[str, Any]]] = None
    memory_experiences: Optional[List[Dict[str, Any]]] = None


class CoachResponse(BaseModel):
    message: str
    suggestions: List[str] = []
    runtime: Optional[Dict[str, Any]] = None


_MISSING_FIELDS = {
    "max_positions": "최대 보유 종목 수",
    "stop_loss_pct": "손절 비율",
    "take_profit_pct": "익절 비율",
    "hold_period_days": "보유 기간",
}

_LARGE_CAP_UNIVERSES = {"KOSPI200", "SP500", "NASDAQ100"}
_COACH_STRATEGY_FIELDS = (
    "universe",
    "fundamental_filters",
    "entry_signals",
    "exit_signals",
    "max_positions",
    "hold_period_days",
    "rebalancing_period",
    "stop_loss_pct",
    "take_profit_pct",
    "trailing_stop_pct",
    "max_mdd_limit_pct",
    "initial_capital",
)


def _detect_missing(ps: dict) -> list[str]:
    return [label for field, label in _MISSING_FIELDS.items() if ps.get(field) is None]


def _remember(cache: OrderedDict[str, Any], key: str, value: Any) -> None:
    if key in cache:
        del cache[key]
    cache[key] = value
    while len(cache) > _CACHE_MAX:
        cache.popitem(last=False)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _coach_cache_key(req: CoachRequest) -> str:
    return sha256(_stable_json(req.model_dump()).encode("utf-8")).hexdigest()


def _compact_strategy_context(ps: dict) -> dict:
    return {
        field: ps.get(field)
        for field in _COACH_STRATEGY_FIELDS
        if field in ps and ps.get(field) not in (None, [], {})
    }


def _reset_coach_cache_for_tests() -> None:
    _coach_response_cache.clear()
    _coach_stream_cache.clear()


def _record_runtime(stage: str, runtime: Dict[str, Any] | None) -> None:
    try:
        import main as _main
        recorder = getattr(_main, "_record_ai_runtime", None)
        if callable(recorder):
            recorder(stage, runtime)
    except Exception:
        logger.debug("coach runtime metric recording skipped", exc_info=True)


def _build_user_message(req: CoachRequest) -> str:
    parts: list[str] = [f'사용자 입력: "{req.user_prompt}"']

    ps = req.parsed_strategy or {}

    if ps:
        parts.append(f"\n[parsed_strategy — 직접 노출 금지. 필드명을 응답에 포함하지 말 것]")
        parts.append(_stable_json(_compact_strategy_context(ps)))

        # Missing field analysis
        missing = _detect_missing(ps)
        if missing:
            parts.append(f"\n[누락 필드 분석]")
            parts.append(f"미정의 항목: {', '.join(missing)}")

        # Capital-based feasibility
        capital = ps.get("initial_capital")
        max_pos = ps.get("max_positions")
        if capital:
            parts.append(f"\n[자본 기반 판단]")
            parts.append(f"initial_capital: {capital:,}원")
            if max_pos:
                budget = capital / max_pos
                parts.append(f"max_positions: {max_pos}개 → 종목당 예산: {budget:,.0f}원")
            else:
                parts.append("max_positions 미정의 → 자금 배분 기준 불명확")

        # Universe type for liquidity filter rule
        universe = ps.get("universe") or []
        is_large_cap = any(u in _LARGE_CAP_UNIVERSES for u in universe)
        if capital and capital <= 20_000_000 and is_large_cap:
            parts.append("※ 소액 + 대형주 유니버스 → 유동성 필터 불필요")

    # news_agent_insight — 뉴스 우선 처리
    if req.news_agent_insight:
        ni = req.news_agent_insight
        parts.append("\n[news_agent_insight — 최우선 참고, 직접 노출 금지]")
        parts.append(f"시장 뉴스 존재: {ni.get('market_news_available', False)}")
        if ni.get("market_level_summary"):
            parts.append(f"시장 수준 요약: {ni['market_level_summary']}")

        symbols = ni.get("symbols", [])
        for sym in symbols[:3]:
            alert = sym.get("risk_alert_level", "low")
            alpha = sym.get("latest_alpha", 0)
            summary = sym.get("summary", "")
            parts.append(f"\n  종목 {sym.get('symbol')}: risk_alert={alert}, alpha={alpha:.2f}")
            if summary:
                parts.append(f"  요약: {summary}")

            articles = sym.get("articles", [])
            for art in articles[:1]:
                score = art.get("impact_score", 0) * art.get("confidence_score", 0)
                parts.append(
                    f"  이벤트: {art.get('event_type')} | {art.get('sentiment')} | "
                    f"impact×conf={score:.2f} | alpha_1d={art.get('expected_alpha_1d', 0):.3f}"
                )

    if req.advisor_insight:
        insight = req.advisor_insight
        parts.append("\n[advisor_insight — 참고용, 직접 노출 금지]")
        parts.append(f"전략 점수: {insight.get('strategy_score', 'N/A')} / 100")
        parts.append(f"리스크 점수: {insight.get('risk_score', 'N/A')} / 100")
        parts.append(f"과최적화 위험: {insight.get('overfit_risk', 'N/A')}")

        issues = insight.get("issues", [])
        if issues:
            issue_lines = [f"  - [{i['severity']}] {i['message']}" for i in issues[:2]]
            parts.append("주요 이슈:\n" + "\n".join(issue_lines))

        recs = insight.get("recommendations", [])
        if recs:
            sorted_recs = sorted(recs, key=lambda r: r.get("priority", 99))
            rec_lines = [f"  - [P{r.get('priority',9)}] {r.get('title')}: {r.get('reason')}" for r in sorted_recs[:1]]
            parts.append("핵심 제안 (우선순위순):\n" + "\n".join(rec_lines))

    if req.memory_strategy_cases or req.memory_experiences:
        memory_context = retrieve_memory_context(
            req.user_prompt,
            req.parsed_strategy,
            req.memory_strategy_cases or [],
            req.memory_experiences or [],
        )
        parts.append("\n[strategy_memory_context — RAG/Experience Memory, 직접 노출 금지]")
        parts.append(f"strategy_id: {memory_context['strategy_id']}")
        parts.append(f"confidence: {memory_context['confidence']}")
        parts.append(f"data_sufficiency: {memory_context['data_sufficiency']}")
        similar_ids = memory_context.get("similar_strategy_ids") or []
        if similar_ids:
            parts.append(f"similar_strategy_ids: {', '.join(similar_ids[:5])}")
        for similar in memory_context.get("similar_strategies", [])[:3]:
            parts.append(
                "  - similar="
                f"{similar.get('strategy_id')} "
                f"score={similar.get('combined_score')} "
                f"reason={similar.get('similarity_reason')}"
            )
        if memory_context["data_sufficiency"] == "insufficient":
            parts.append("유사 사례 부족: 조언은 낮은 신뢰도로 제한하고 재백테스트 필요성을 명시")
        for case in memory_context.get("retrieved_cases", [])[:3]:
            lesson = case.get("lesson") or "lesson 없음"
            before = _stable_json(case.get("before_metrics") or {})
            after = _stable_json(case.get("after_metrics") or {})
            parts.append(
                "  - case="
                f"{case.get('case_strategy_id')} "
                f"success={case.get('advice_success')} "
                f"before={before} after={after} lesson={lesson}"
            )

    return "\n".join(parts)


async def _with_auto_context(req: CoachRequest) -> CoachRequest:
    effective_req = req
    if not effective_req.news_agent_insight:
        news_context = build_news_context_from_strategy(effective_req.parsed_strategy)
        news_insight = build_coach_news_insight(news_context)
        if news_insight:
            effective_req = effective_req.model_copy(update={"news_agent_insight": news_insight})

    if (
        effective_req.memory_strategy_cases is None
        and effective_req.memory_experiences is None
    ):
        strategy_cases, experiences = await load_vector_advisor_memory(
            effective_req.user_prompt,
            effective_req.parsed_strategy,
        )
        if not strategy_cases and not experiences:
            strategy_cases, experiences = load_advisor_memory()
        if strategy_cases or experiences:
            effective_req = effective_req.model_copy(
                update={
                    "memory_strategy_cases": strategy_cases,
                    "memory_experiences": experiences,
                }
            )
    return effective_req


def _parse_llm_response(raw: str) -> CoachResponse:
    """LLM 응답에서 JSON 추출. 실패 시 전체 텍스트를 message로 사용."""
    raw = raw.strip()
    # strip <think>...</think> blocks (Qwen3 thinking mode artifact)
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw).strip()
    # extract JSON from markdown code block if present
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    # extract first {...} block
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    try:
        data = json.loads(raw)
        return CoachResponse(
            message=data.get("message", "")[:400],
            suggestions=data.get("suggestions", [])[:1],
        )
    except Exception:
        return CoachResponse(message=raw[:400], suggestions=[])


@router.post("/strategy/coach", response_model=CoachResponse)
async def coach_strategy(req: CoachRequest) -> CoachResponse:
    if _parser is None:
        raise HTTPException(status_code=503, detail="Coach model not loaded yet")

    try:
        request_started = time.perf_counter()
        cache_key = _coach_cache_key(req)
        effective_req = await _with_auto_context(req)

        cached = _coach_response_cache.get(cache_key)
        if cached is not None:
            _coach_response_cache.move_to_end(cache_key)
            response = cached.model_copy(deep=True)
            response.runtime = {
                "cache_hit": True,
                "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
            }
            _record_runtime("coach", response.runtime)
            return response

        from engine.nl_parser import NLStrategyParser
        parser: NLStrategyParser = _parser

        user_msg = _build_user_message(effective_req)

        inference_started = time.perf_counter()
        import main as _main
        with _main._mlx_inference_lock.priority(1):
            raw = parser.chat(COACH_SYSTEM_PROMPT, user_msg, max_tokens=400)
        inference_ms = round((time.perf_counter() - inference_started) * 1000, 2)

        response = _parse_llm_response(raw)
        response.runtime = {
            "cache_hit": False,
            "inference_ms": inference_ms,
            "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
        }
        _record_runtime("coach", response.runtime)
        _remember(_coach_response_cache, cache_key, response.model_copy(deep=True))
        return response

    except Exception as exc:
        logger.exception("coach failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _extract_message_so_far(buffer: str) -> str:
    """누적 버퍼에서 '"message": "..."' 값을 최대한 추출한다 (스트리밍 중)."""
    # strip <think>...</think>
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", buffer)
    cleaned = re.sub(r"<think>[\s\S]*$", "", cleaned)  # unclosed <think>
    # match "message": "..." — 끝따옴표 없어도 부분 추출
    m = re.search(r'"message"\s*:\s*"((?:\\.|[^"\\])*)"?', cleaned)
    if not m:
        return ""
    raw = m.group(1)
    # JSON escape 해제: \n, \", \\ 등
    try:
        return json.loads(f'"{raw}"')
    except Exception:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


@router.post("/strategy/coach/stream")
async def coach_strategy_stream(req: CoachRequest):
    if _parser is None:
        raise HTTPException(status_code=503, detail="Coach model not loaded yet")

    request_started = time.perf_counter()
    effective_req = await _with_auto_context(req)

    from engine.nl_parser import NLStrategyParser
    parser: NLStrategyParser = _parser
    user_msg = _build_user_message(effective_req)
    cache_key = _coach_cache_key(effective_req)
    cached_stream = _coach_stream_cache.get(cache_key)

    if cached_stream is not None:
        _coach_stream_cache.move_to_end(cache_key)
        _record_runtime(
            "coach_stream",
            {
                "cache_hit": True,
                "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
            },
        )

        def _cached_iter():
            yield cached_stream

        return StreamingResponse(
            _cached_iter(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def _iter():
        import main as _main
        buffer = ""
        last_sent = ""
        emitted: list[str] = []
        try:
            with _main._mlx_inference_lock.priority(1):
                for delta in parser.stream_chat(COACH_SYSTEM_PROMPT, user_msg, max_tokens=400):
                    if not delta:
                        continue
                    buffer += delta
                    # 스트리밍 중: "message" 값 부분만 추출해 전달
                    current = _extract_message_so_far(buffer)
                    if current and current != last_sent:
                        added = current[len(last_sent):] if current.startswith(last_sent) else current
                        last_sent = current
                        payload = json.dumps({"type": "delta", "text": added, "message": current}, ensure_ascii=False)
                        event = f"data: {payload}\n\n"
                        emitted.append(event)
                        yield event

            # 최종 파싱: message + suggestions
            final = _parse_llm_response(buffer)
            payload = json.dumps(
                {
                    "type": "done",
                    "message": final.message,
                    "suggestions": final.suggestions,
                    "runtime": {
                        "cache_hit": False,
                        "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
                    },
                },
                ensure_ascii=False,
            )
            event = f"data: {payload}\n\n"
            emitted.append(event)
            _record_runtime(
                "coach_stream",
                {
                    "cache_hit": False,
                    "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
                },
            )
            _remember(_coach_stream_cache, cache_key, "".join(emitted))
            yield event
        except Exception as exc:
            logger.exception("coach stream failed: %s", exc)
            payload = json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        _iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
