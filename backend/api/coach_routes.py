"""
FastAPI routes for the Strategy Coach — conversational AI layer.

POST /strategy/coach   — generate a coaching response using advisor_result

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
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from advisor.agent import StrategyAdvisorAgent
from advisor.memory_repository import load_advisor_memory, load_vector_advisor_memory
from advisor.memory_retriever import retrieve_memory_context
from advisor.news_enrichment import build_coach_news_insight, build_news_context_from_strategy
from advisor.schemas import AdvisorRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["coach"])

# Injected by main.py after NLStrategyParser is preloaded
_parser = None
_CACHE_MAX = 200
_SESSION_MAX = 200
_COACH_CACHE_VERSION = "2026-06-01-exit-context-v2"
_coach_response_cache: OrderedDict[str, CoachResponse] = OrderedDict()
_coach_stream_cache: OrderedDict[str, str] = OrderedDict()
_coach_sessions: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def set_parser(parser: Any) -> None:
    global _parser
    _parser = parser


def _parser_debug_state() -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "injected_parser": _parser is not None,
        "injected_parser_type": type(_parser).__name__ if _parser is not None else None,
    }
    try:
        import main as _main
        parsers = getattr(_main, "_nl_parsers", {})
        status = getattr(_main, "_nl_parser_status", None)
        state.update({
            "main_parser_keys": sorted(parsers.keys()) if isinstance(parsers, dict) else None,
            "main_mlx_parser_loaded": isinstance(parsers, dict) and parsers.get("mlx") is not None,
            "main_parser_status": status,
            "main_has_inference_lock": hasattr(_main, "_mlx_inference_lock"),
        })
    except Exception as exc:
        state["main_lookup_error"] = repr(exc)
    return state


def _get_parser() -> Any:
    global _parser
    if _parser is not None:
        return _parser

    try:
        import main as _main
        parser = getattr(_main, "_nl_parsers", {}).get("mlx")
        if parser is not None:
            _parser = parser
            return parser
    except Exception:
        logger.debug("coach parser lookup from main failed", exc_info=True)
    return None


def _require_parser() -> Any:
    parser = _get_parser()
    if parser is None:
        logger.error("coach parser unavailable | state=%s", _parser_debug_state())
        raise HTTPException(status_code=503, detail="Coach model not loaded yet")
    return parser


COACH_SYSTEM_PROMPT = """당신은 퀀트 투자 전략 코칭 전문가입니다.

당신은 다음 내부 컨텍스트를 받습니다.
1. 원본 사용자 입력
2. parsed_strategy
3. advisor_result
4. conversation_context

당신의 역할은 advisor_result를 사용자가 이해하기 쉬운 자연어 코칭으로 변환하는 것입니다.
사용자를 주식 초보자라고 생각하고 설명하십시오.
사용자는 전략 입력 초보자라고 가정하고, 전문 용어는 쉬운 말로 풀어 설명하십시오.
트레일링 스탑 같은 전문 용어를 사용할 때는 그 표현만 단독으로 쓰지 말고, 바로 뒤에 뜻을 쉬운 말로 덧붙이십시오.
트레일링 스탑처럼 수치가 필요한 조건을 사용자가 숫자 없이 요청하면 임의의 수치를 제안하거나 추정하지 말고, 몇 %로 설정할지 먼저 물어보십시오.
advisor_result에 포함된 리뷰와 추천 내용을 우선적으로 반영하십시오.
parsed_strategy는 전략 구조를 이해하기 위한 보조 정보로 사용하십시오.
원본 사용자 입력은 사용자의 의도와 표현을 이해하기 위한 참고 정보로 사용하십시오.
advisor_result에 없는 백테스트 결과, 수익률, 위험 수치, 뉴스 분석, 시장 레짐 판단을 새로 만들어내지 마십시오.
strategy_memory_context가 있으면 유사 전략 사례와 과거 조언 성공/실패 교훈을 근거로 삼되, data_sufficiency가 insufficient이면 확정적 표현을 피하십시오.
retrieved_cases가 비어 있으면 과거 사례가 충분한 것처럼 꾸며내지 마라.
백테스트 결과가 없으면 수익성이 좋거나 개선되었다고 단정하지 마십시오.
제공되지 않은 백테스트 사례, 성과 수치, 개선 효과를 새로 만들지 마십시오.
당신은 검색/계산/판정 엔진이 아니라, 이미 계산된 근거를 사용자에게 설명하는 코치입니다.
사용자에게 내부 필드명인 parsed_strategy, advisor_result, rule_context, internal_analysis 같은 용어를 노출하지 마십시오.
사용자는 최종 코칭 문장만 봐야 합니다.
응답은 짧고 실용적이며, 다음 행동을 제안하는 방식으로 작성하십시오.
사용자에게 과거 데이터 검색, 유사 전략 탐색, 외부 자료 확인을 숙제로 주지 마십시오.
사용자가 지금 바로 할 수 없는 행동(외부 조사, 수동 계산, 별도 데이터 확인)을 다음 행동으로 제안하지 마십시오.
다음 행동을 물을 때는 "비교 테스트를 진행해 보시겠어요?"처럼 추상적으로 묻지 말고, "트레일링 스탑을 추가해 보시겠어요?"처럼 추가할 조건을 직접 물어보십시오.
사용자가 "트레일링 스탑 15%"처럼 정확한 수치를 말한 경우에만 해당 조건으로 비교 백테스트를 안내하십시오.
사용자가 "트레일링 스탑을 추가해줘"처럼 수치를 말하지 않았으면 "트레일링 스탑은 최고가에서 몇 % 내려오면 팔지 정하는 조건입니다. 몇 %로 설정할까요?"처럼 먼저 물어보십시오.
보유 기간을 개선안으로 제안할 때는 "몇 일로 설정할까요?"처럼 정확한 일수를 요구하지 말고, "보유 기간을 설정할까요?"처럼 사용자가 추가 여부를 선택하게 물어보십시오.
익절 비율을 개선안으로 제안할 때는 "몇 %로 설정할까요?"처럼 정확한 비율을 요구하지 말고, "익절 비율을 설정할까요?"처럼 사용자가 추가 여부를 선택하게 물어보십시오.

[응답 형식]
반드시 아래 JSON 형식으로만 응답하라. JSON 외에 다른 텍스트를 출력하지 마라:
{"message": "짧고 실용적인 코칭 문장"}"""


class CoachRequest(BaseModel):
    user_prompt: str
    parsed_strategy: Dict[str, Any]
    advisor_result: Optional[Dict[str, Any]] = None
    conversation_context: Optional[List[Dict[str, Any]]] = None
    # Backward compatibility for existing callers that pass a compact advisor payload.
    advisor_insight: Optional[Dict[str, Any]] = None
    news_agent_insight: Optional[Dict[str, Any]] = None
    memory_strategy_cases: Optional[List[Dict[str, Any]]] = None
    memory_experiences: Optional[List[Dict[str, Any]]] = None


class CoachResponse(BaseModel):
    message: str


class CoachSessionRequest(BaseModel):
    user_prompt: str
    parsed_strategy: Dict[str, Any]
    memory_strategy_cases: Optional[List[Dict[str, Any]]] = None
    memory_experiences: Optional[List[Dict[str, Any]]] = None


class CoachSessionFollowUpRequest(BaseModel):
    session_id: str
    user_prompt: str


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
    has_exit_signal = bool(ps.get("exit_signals"))
    has_trailing_stop = ps.get("trailing_stop_pct") is not None
    missing: list[str] = []
    for field, label in _MISSING_FIELDS.items():
        if ps.get(field) is not None:
            continue
        if field == "take_profit_pct" and (has_exit_signal or has_trailing_stop):
            continue
        missing.append(label)
    return missing


def _remember(cache: OrderedDict[str, Any], key: str, value: Any) -> None:
    if key in cache:
        del cache[key]
    cache[key] = value
    while len(cache) > _CACHE_MAX:
        cache.popitem(last=False)


def _remember_session(session_id: str, value: Dict[str, Any]) -> None:
    if session_id in _coach_sessions:
        del _coach_sessions[session_id]
    _coach_sessions[session_id] = value
    while len(_coach_sessions) > _SESSION_MAX:
        _coach_sessions.popitem(last=False)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _coach_cache_key(req: CoachRequest) -> str:
    payload = {
        "version": _COACH_CACHE_VERSION,
        "request": req.model_dump(),
    }
    return sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _compact_strategy_context(ps: dict) -> dict:
    return {
        field: ps.get(field)
        for field in _COACH_STRATEGY_FIELDS
        if field in ps and ps.get(field) not in (None, [], {})
    }


def _compact_advisor_result(advisor_result: Dict[str, Any] | None) -> Dict[str, Any]:
    if not advisor_result:
        return {}

    compact: Dict[str, Any] = {
        "strategy_score": advisor_result.get("strategy_score"),
        "risk_score": advisor_result.get("risk_score"),
        "overfit_risk": advisor_result.get("overfit_risk"),
    }

    sections = advisor_result.get("response_sections") or []
    if sections:
        compact["response_sections"] = [
            {
                "title": section.get("title"),
                "body": section.get("body"),
            }
            for section in sections[:4]
            if isinstance(section, dict)
        ]

    advice = advisor_result.get("advice") or []
    if advice:
        compact["advice"] = [
            {
                "severity": item.get("severity"),
                "title": item.get("title"),
                "body": item.get("body"),
            }
            for item in advice[:3]
            if isinstance(item, dict)
        ]

    news = advisor_result.get("news_analysis")
    if isinstance(news, dict):
        compact["news_analysis"] = {
            "summary": news.get("summary"),
            "risk_level": news.get("risk_level"),
            "key_events": (news.get("key_events") or [])[:3],
        }

    memory = advisor_result.get("strategy_memory_context")
    if isinstance(memory, dict):
        compact["strategy_memory_context"] = {
            "confidence": memory.get("confidence"),
            "data_sufficiency": memory.get("data_sufficiency"),
            "similar_strategy_ids": (memory.get("similar_strategy_ids") or [])[:5],
            "retrieved_cases": (memory.get("retrieved_cases") or [])[:3],
        }

    experiments = advisor_result.get("suggested_experiments") or []
    if experiments:
        compact["suggested_experiments"] = experiments[:3]

    ai_rec = advisor_result.get("ai_model_recommendation")
    if isinstance(ai_rec, dict):
        compact["ai_model_recommendation"] = ai_rec

    return {key: value for key, value in compact.items() if value not in (None, [], {})}


def _compact_conversation_context(context: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    if not context:
        return []
    compact: list[dict[str, Any]] = []
    for item in context[-6:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content") or item.get("message") or "").strip()
        if role and content:
            compact.append({"role": role, "content": content[:500]})
    return compact


def _reset_coach_cache_for_tests() -> None:
    _coach_response_cache.clear()
    _coach_stream_cache.clear()
    _coach_sessions.clear()


def _record_runtime(stage: str, runtime: Dict[str, Any] | None) -> None:
    try:
        import main as _main
        recorder = getattr(_main, "_record_ai_runtime", None)
        if callable(recorder):
            recorder(stage, runtime)
    except Exception:
        logger.debug("coach runtime metric recording skipped", exc_info=True)


def _needs_trailing_stop_percentage(prompt: str) -> bool:
    compact = re.sub(r"\s+", "", prompt.lower())
    if "트레일링" not in compact and "trailing" not in compact:
        return False
    return re.search(r"\d+(?:\.\d+)?%?", compact) is None


def _build_user_message(req: CoachRequest) -> str:
    parts: list[str] = [f'원본 사용자 입력(출력 금지): "{req.user_prompt}"']
    parts.append("\n[코칭 행동 제약]")
    parts.append(
        "사용자에게 과거 데이터 검색, 유사 전략 탐색, 외부 자료 확인을 숙제로 주지 마십시오. "
        "다음 행동은 '비교 테스트를 진행해 보시겠어요?'처럼 추상적으로 묻지 말고, "
        "'트레일링 스탑을 추가해 보시겠어요?'처럼 추가할 조건을 직접 물어보십시오."
    )
    if _needs_trailing_stop_percentage(req.user_prompt):
        parts.append("\n[필수 확인 질문]")
        parts.append(
            "사용자가 트레일링 스탑 수치를 말하지 않았습니다. "
            "advisor_result에 15% 같은 후보가 있어도 임의 수치를 제안하지 말고, 몇 %로 설정할지 먼저 물어보십시오."
        )

    ps = req.parsed_strategy or {}

    if ps:
        parts.append("\n[parsed_strategy — 내부 컨텍스트, 직접 노출 금지]")
        parts.append(_stable_json(_compact_strategy_context(ps)))

        has_exit_signal = bool(ps.get("exit_signals"))
        has_risk_exit = any(
            ps.get(field) is not None
            for field in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "hold_period_days")
        )
        if has_exit_signal or has_risk_exit:
            parts.append("\n[청산 규칙 판단]")
            parts.append("청산 기준이 존재합니다. '언제 팔아야 할지 기준이 없다'고 말하지 마십시오.")

        # Missing field analysis
        missing = _detect_missing(ps)
        if missing:
            parts.append(f"\n[누락 필드 분석]")
            parts.append(f"미정의 항목: {', '.join(missing)}")
            if "익절 비율" in missing:
                parts.append(
                    "익절 비율은 개선안으로만 제안하십시오. "
                    "'몇 %로 설정할까요?'처럼 정확한 비율을 요구하지 말고, "
                    "'익절 비율을 설정할까요?'처럼 추가 여부를 묻는 표현을 사용하십시오."
                )
            if "보유 기간" in missing:
                parts.append(
                    "보유 기간은 개선안으로만 제안하십시오. "
                    "'몇 일로 설정할까요?'처럼 정확한 일수를 요구하지 말고, "
                    "'보유 기간을 설정할까요?'처럼 추가 여부를 묻는 표현을 사용하십시오."
                )

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

    advisor_result = req.advisor_result or req.advisor_insight
    if advisor_result:
        parts.append("\n[advisor_result — 최우선 내부 컨텍스트, 직접 노출 금지]")
        parts.append(_stable_json(_compact_advisor_result(advisor_result)))

    if req.advisor_insight and not req.advisor_result:
        insight = req.advisor_insight
        parts.append("\n[legacy_advisor_insight — 참고용, 직접 노출 금지]")
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

    conversation_context = _compact_conversation_context(req.conversation_context)
    if conversation_context:
        parts.append("\n[conversation_context — 이전 대화, 직접 노출 금지]")
        parts.append(_stable_json(conversation_context))

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
            parts.append(
                "유사 사례 부족: 조언은 낮은 신뢰도로 제한하고, "
                "사용자에게 외부 데이터를 찾게 하지 말고 조건 추가 후 비교 백테스트만 제안"
            )
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


def _build_advisor_result(req: CoachRequest, request_id: str | None = None) -> Dict[str, Any]:
    started = time.perf_counter()
    logger.info(
        "coach advisor build start | request_id=%s prompt_len=%d universe=%s",
        request_id,
        len(req.user_prompt or ""),
        req.parsed_strategy.get("universe"),
    )
    advisor = StrategyAdvisorAgent()
    news_context = build_news_context_from_strategy(req.parsed_strategy)
    advisor_req = AdvisorRequest(
        user_prompt=req.user_prompt,
        parsed_strategy=req.parsed_strategy,
        news_context=news_context or None,
        memory_strategy_cases=req.memory_strategy_cases,
        memory_experiences=req.memory_experiences,
    )
    result = advisor.review(advisor_req).model_dump(mode="json")
    logger.info(
        "coach advisor build done | request_id=%s elapsed_ms=%.2f advice_count=%d",
        request_id,
        (time.perf_counter() - started) * 1000,
        len(result.get("advice") or []),
    )
    return result


async def _with_auto_context(req: CoachRequest, request_id: str | None = None) -> CoachRequest:
    started = time.perf_counter()
    logger.info(
        "coach context build start | request_id=%s has_advisor=%s has_memory=%s has_news=%s",
        request_id,
        bool(req.advisor_result or req.advisor_insight),
        req.memory_strategy_cases is not None or req.memory_experiences is not None,
        bool(req.news_agent_insight),
    )
    effective_req = req
    if not effective_req.news_agent_insight:
        news_started = time.perf_counter()
        news_context = build_news_context_from_strategy(effective_req.parsed_strategy)
        news_insight = build_coach_news_insight(news_context)
        logger.info(
            "coach news context done | request_id=%s elapsed_ms=%.2f context_count=%d has_insight=%s",
            request_id,
            (time.perf_counter() - news_started) * 1000,
            len(news_context or []),
            bool(news_insight),
        )
        if news_insight:
            effective_req = effective_req.model_copy(update={"news_agent_insight": news_insight})

    if (
        effective_req.memory_strategy_cases is None
        and effective_req.memory_experiences is None
    ):
        memory_started = time.perf_counter()
        strategy_cases, experiences = await load_vector_advisor_memory(
            effective_req.user_prompt,
            effective_req.parsed_strategy,
        )
        source = "vector"
        if not strategy_cases and not experiences:
            strategy_cases, experiences = load_advisor_memory()
            source = "file"
        logger.info(
            "coach memory load done | request_id=%s elapsed_ms=%.2f source=%s strategy_cases=%d experiences=%d",
            request_id,
            (time.perf_counter() - memory_started) * 1000,
            source,
            len(strategy_cases or []),
            len(experiences or []),
        )
        if strategy_cases or experiences:
            effective_req = effective_req.model_copy(
                update={
                    "memory_strategy_cases": strategy_cases,
                    "memory_experiences": experiences,
                }
            )
    if not effective_req.advisor_result and not effective_req.advisor_insight:
        effective_req = effective_req.model_copy(
            update={"advisor_result": _build_advisor_result(effective_req, request_id)}
        )
    logger.info(
        "coach context build done | request_id=%s elapsed_ms=%.2f has_advisor=%s",
        request_id,
        (time.perf_counter() - started) * 1000,
        bool(effective_req.advisor_result or effective_req.advisor_insight),
    )
    return effective_req


def _extract_message_value(raw: str) -> str | None:
    match = re.search(r'"message"\s*:\s*"((?:\\.|[^"\\])*)', raw)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"').strip()
    except Exception:
        return match.group(1).strip()


def _ensure_explained_terms(message: str, *, include_trailing_example: bool = True) -> str:
    if "트레일링 스탑" not in message:
        return message
    original = message
    if re.search(r"트레일링 스탑[^.?!。]*?(최고가|고점|일정 비율|하락|내려오면|팔아)", message):
        explained = message
    else:
        explained = message.replace(
            "트레일링 스탑",
            "트레일링 스탑(주가가 오른 뒤 최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건)",
            1,
        )
    if "예를 들면 트레일링 스탑" in original:
        return explained
    if not include_trailing_example:
        return explained
    return f"{explained} 예를 들면 '트레일링 스탑 15% 설정'이라고 말씀해주시면 바로 추가하겠습니다."


def _strategy_trailing_stop_pct(strategy: Dict[str, Any] | None) -> Any:
    if not isinstance(strategy, dict):
        return None
    if strategy.get("trailing_stop_pct") is not None:
        return strategy.get("trailing_stop_pct")
    risk = strategy.get("risk")
    if isinstance(risk, dict):
        return risk.get("trailing_stop_pct")
    return None


def _align_response_with_strategy(response: CoachResponse, strategy: Dict[str, Any]) -> CoachResponse:
    trailing_stop_pct = _strategy_trailing_stop_pct(strategy)
    message = response.message or ""
    if trailing_stop_pct is None or "트레일링 스탑" not in message:
        return response
    if not re.search(r"추가|설정.*말씀|바로 추가", message):
        return response

    return CoachResponse(
        message=(
            f"트레일링 스탑 {trailing_stop_pct}% 조건을 전략에 반영했습니다. "
            "이 조건으로 백테스트를 실행할 수 있습니다."
        )[:300]
    )


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
        message = data.get("message", "")
        if isinstance(message, str):
            nested = _extract_message_value(message)
            return CoachResponse(message=_ensure_explained_terms((nested or message).strip())[:300])
        return CoachResponse(message="")
    except Exception:
        message = _extract_message_value(raw)
        return CoachResponse(message=_ensure_explained_terms((message or raw).strip())[:300])


def _generate_coach_response(
    effective_req: CoachRequest,
    request_started: float,
    request_id: str | None = None,
) -> CoachResponse:
    from engine.nl_parser import NLStrategyParser

    parser: NLStrategyParser = _require_parser()
    user_msg = _build_user_message(effective_req)

    inference_started = time.perf_counter()
    import main as _main
    lock = getattr(_main, "_mlx_inference_lock", None)
    if lock is None:
        logger.error(
            "coach inference lock missing | request_id=%s state=%s",
            request_id,
            _parser_debug_state(),
        )
        raise RuntimeError("MLX inference lock is not available")

    logger.info(
        "coach inference waiting | request_id=%s parser_type=%s user_msg_len=%d state=%s",
        request_id,
        type(parser).__name__,
        len(user_msg),
        _parser_debug_state(),
    )
    with _main._mlx_inference_lock.priority(1):
        lock_wait_ms = round((time.perf_counter() - inference_started) * 1000, 2)
        logger.info("coach inference lock acquired | request_id=%s wait_ms=%.2f", request_id, lock_wait_ms)
        chat_started = time.perf_counter()
        try:
            raw = parser.chat(COACH_SYSTEM_PROMPT, user_msg, max_tokens=400)
        except Exception:
            logger.exception(
                "coach parser.chat failed | request_id=%s chat_elapsed_ms=%.2f parser_state=%s",
                request_id,
                (time.perf_counter() - chat_started) * 1000,
                _parser_debug_state(),
            )
            raise
    inference_ms = round((time.perf_counter() - inference_started) * 1000, 2)

    response = _align_response_with_strategy(_parse_llm_response(raw), effective_req.parsed_strategy)
    logger.info(
        "coach inference done | request_id=%s inference_ms=%.2f raw_len=%d message_len=%d",
        request_id,
        inference_ms,
        len(raw or ""),
        len(response.message or ""),
    )
    runtime = {
        "cache_hit": False,
        "inference_ms": inference_ms,
        "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
    }
    _record_runtime("coach", runtime)
    return response


@router.post("/strategy/coach", response_model=CoachResponse)
async def coach_strategy(req: CoachRequest) -> CoachResponse:
    _require_parser()
    request_id = uuid4().hex[:12]

    try:
        request_started = time.perf_counter()
        logger.info("coach request start | request_id=%s mode=legacy", request_id)
        cache_key = _coach_cache_key(req)
        cached = _coach_response_cache.get(cache_key)
        if cached is not None:
            _coach_response_cache.move_to_end(cache_key)
            response = cached.model_copy(deep=True)
            runtime = {
                "cache_hit": True,
                "total_ms": round((time.perf_counter() - request_started) * 1000, 2),
            }
            _record_runtime("coach", runtime)
            logger.info("coach request cache hit | request_id=%s total_ms=%.2f", request_id, runtime["total_ms"])
            return response

        effective_req = await _with_auto_context(req, request_id)
        response = _generate_coach_response(effective_req, request_started, request_id)
        _remember(_coach_response_cache, cache_key, response.model_copy(deep=True))
        logger.info(
            "coach request done | request_id=%s total_ms=%.2f",
            request_id,
            (time.perf_counter() - request_started) * 1000,
        )
        return response

    except Exception as exc:
        logger.exception("coach failed | request_id=%s error=%s state=%s", request_id, exc, _parser_debug_state())
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/strategy/coach/sessions", response_model=CoachResponse)
async def create_coach_session(req: CoachSessionRequest, response: Response) -> CoachResponse:
    _require_parser()
    request_id = uuid4().hex[:12]

    try:
        request_started = time.perf_counter()
        session_id = uuid4().hex
        logger.info("coach request start | request_id=%s mode=create_session session_id=%s", request_id, session_id)
        coach_req = CoachRequest(
            user_prompt=req.user_prompt,
            parsed_strategy=req.parsed_strategy,
            memory_strategy_cases=req.memory_strategy_cases,
            memory_experiences=req.memory_experiences,
        )
        effective_req = await _with_auto_context(coach_req, request_id)
        coach_response = _generate_coach_response(effective_req, request_started, request_id)

        _remember_session(
            session_id,
            {
                "parsed_strategy": effective_req.parsed_strategy,
                "advisor_result": effective_req.advisor_result or effective_req.advisor_insight,
                "memory_strategy_cases": effective_req.memory_strategy_cases,
                "memory_experiences": effective_req.memory_experiences,
                "news_agent_insight": effective_req.news_agent_insight,
                "conversation_context": [
                    {"role": "user", "content": req.user_prompt},
                    {"role": "assistant", "content": coach_response.message},
                ],
            },
        )
        response.headers["X-Coach-Session-Id"] = session_id
        logger.info(
            "coach request done | request_id=%s mode=create_session session_id=%s total_ms=%.2f",
            request_id,
            session_id,
            (time.perf_counter() - request_started) * 1000,
        )
        return coach_response
    except Exception as exc:
        logger.exception(
            "coach session create failed | request_id=%s error=%s state=%s",
            request_id,
            exc,
            _parser_debug_state(),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/strategy/coach/sessions/follow-up", response_model=CoachResponse)
async def continue_coach_session(req: CoachSessionFollowUpRequest) -> CoachResponse:
    _require_parser()
    request_id = uuid4().hex[:12]

    session = _coach_sessions.get(req.session_id)
    if session is None:
        logger.warning("coach follow-up session missing | request_id=%s session_id=%s", request_id, req.session_id)
        raise HTTPException(status_code=404, detail="Coach session not found")
    _coach_sessions.move_to_end(req.session_id)

    try:
        request_started = time.perf_counter()
        logger.info("coach request start | request_id=%s mode=follow_up session_id=%s", request_id, req.session_id)
        coach_req = CoachRequest(
            user_prompt=req.user_prompt,
            parsed_strategy=session["parsed_strategy"],
            advisor_result=session.get("advisor_result"),
            news_agent_insight=session.get("news_agent_insight"),
            memory_strategy_cases=session.get("memory_strategy_cases"),
            memory_experiences=session.get("memory_experiences"),
            conversation_context=session.get("conversation_context") or [],
        )
        coach_response = _generate_coach_response(coach_req, request_started, request_id)
        session["conversation_context"] = [
            *(session.get("conversation_context") or []),
            {"role": "user", "content": req.user_prompt},
            {"role": "assistant", "content": coach_response.message},
        ][-8:]
        _remember_session(req.session_id, session)
        logger.info(
            "coach request done | request_id=%s mode=follow_up session_id=%s total_ms=%.2f",
            request_id,
            req.session_id,
            (time.perf_counter() - request_started) * 1000,
        )
        return coach_response
    except Exception as exc:
        logger.exception(
            "coach session follow-up failed | request_id=%s session_id=%s error=%s state=%s",
            request_id,
            req.session_id,
            exc,
            _parser_debug_state(),
        )
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
    _require_parser()

    request_started = time.perf_counter()
    cache_key = _coach_cache_key(req)
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

    effective_req = await _with_auto_context(req)

    from engine.nl_parser import NLStrategyParser
    parser: NLStrategyParser = _require_parser()
    user_msg = _build_user_message(effective_req)

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
