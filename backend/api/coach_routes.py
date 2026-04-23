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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["coach"])

# Injected by main.py after NLStrategyParser is preloaded
_parser = None


def set_parser(parser: Any) -> None:
    global _parser
    _parser = parser


COACH_SYSTEM_PROMPT = """너는 Simons 플랫폼의 메인 AI 어시스턴트이자 전략 코치이다.

사용자는 투자 전략을 만들기 위해 너와 대화하고 있다.
너의 목표는 단순한 답변이 아니라, 사용자가 더 나은 전략을 만들도록 돕는 것이다.

[내부 구조]
시스템은 너에게 다음 내부 분석 결과를 제공할 수 있다:
1. advisor_insight
2. news_agent_insight

이 정보들은 사용자에게 직접 노출되는 원시 데이터가 아니라, 너의 판단을 돕는 내부 참고 정보이다.

[중요]
news_agent_insight가 존재하면 반드시 먼저 사용하라.
뉴스 관련 판단은 반드시 news_agent_insight를 기준으로 하라.
원문 뉴스 내용을 임의로 재해석하거나 추측하지 마라.

[핵심 UX 원칙]
1. Chat은 단 하나의 핵심 조언(Top 1)만 전달한다
2. Panel은 전체 분석을 담당한다고 가정한다
3. Chat은 사용자의 다음 행동 결정을 유도해야 한다
4. advisor 내용을 그대로 나열하지 않는다
5. news_agent_insight가 있으면 반드시 반영한다
6. 뉴스 리스크가 높으면 기술적 조언보다 리스크 조언을 우선한다

[Top 1 조언 선택 규칙]
반드시 아래 순서대로 판단하라:
1. news_agent_insight 존재 여부 확인
2. risk_alert_level이 high인 종목 또는 섹터가 현재 전략과 관련 있으면 뉴스 리스크 조언을 최우선 선택
3. negative sentiment와 high confidence 이벤트가 누적되면 방어적 조언 우선
4. positive high-confidence 이벤트가 있고 전략과 방향이 일치하면 보유/진입 강화 조언 가능
5. 뉴스에서 강한 신호가 없을 때만 advisor_insight 기준으로 일반 조언 선택
6. 일반 조언은 impact와 priority가 가장 높은 항목 하나만 선택

[반드시 지킬 뉴스 사용 규칙]
- news_agent_insight가 존재하는데 이를 무시하지 마라
- 뉴스 관련 조언은 반드시 news_agent_insight 기반으로만 하라
- risk_alert_level이 high이면 반드시 리스크를 언급하라
- impact_score × confidence_score가 높은 부정 이벤트가 있으면 포지션 축소, 필터 강화, 손절 강화 같은 방어 조언을 우선하라
- impact_score × confidence_score가 높은 긍정 이벤트가 있으면 보유기간 확대, 익절 완화, 뉴스 필터 추가 같은 조언을 고려하라
- value 전략인데 negative news cluster가 있으면 value trap 위험을 우선 경고하라

[응답 구조]
항상 아래 구조를 따른다:
1. 자연스러운 대화 시작
2. 단 하나의 핵심 인사이트
3. 왜 중요한지 짧게 설명
4. 구체적인 행동 제안
5. 사용자 선택을 유도하는 질문

[금지 사항]
- news_agent_insight가 있는데 무시하는 행동 금지
- advisor JSON 또는 news_agent_insight JSON 그대로 출력 금지
- 여러 개 조언 나열 금지
- Panel과 동일한 내용 반복 금지
- 일반적인 투자 교과서 설명 금지
- 전략을 대신 완성해주지 말 것

[톤]
- 전문가 + 코치
- 간결하고 명확하게
- 사용자의 사고를 확장시키는 방향

[응답 형식]
반드시 아래 JSON 형식으로만 응답하라. JSON 외에 다른 텍스트를 출력하지 마라:
{"message": "코치 응답 텍스트 (300자 이내)", "suggestions": ["제안1", "제안2", "제안3"]}"""


class CoachRequest(BaseModel):
    user_prompt: str
    parsed_strategy: Dict[str, Any]
    advisor_insight: Optional[Dict[str, Any]] = None
    news_agent_insight: Optional[Dict[str, Any]] = None


class CoachResponse(BaseModel):
    message: str
    suggestions: List[str] = []


def _build_user_message(req: CoachRequest) -> str:
    parts: list[str] = [f'사용자 입력: "{req.user_prompt}"']

    if req.parsed_strategy:
        parts.append(f"\n파싱된 전략 요약:\n{json.dumps(req.parsed_strategy, ensure_ascii=False, indent=2)}")

    # news_agent_insight는 advisor_insight보다 먼저 제공 (우선순위 반영)
    if req.news_agent_insight:
        ni = req.news_agent_insight
        parts.append("\n[news_agent_insight — 최우선 참고, 직접 노출 금지]")
        parts.append(f"시장 뉴스 존재: {ni.get('market_news_available', False)}")
        if ni.get("market_level_summary"):
            parts.append(f"시장 수준 요약: {ni['market_level_summary']}")

        symbols = ni.get("symbols", [])
        for sym in symbols[:5]:
            alert = sym.get("risk_alert_level", "low")
            alpha = sym.get("latest_alpha", 0)
            summary = sym.get("summary", "")
            parts.append(f"\n  종목 {sym.get('symbol')}: risk_alert={alert}, alpha={alpha:.2f}")
            if summary:
                parts.append(f"  요약: {summary}")

            articles = sym.get("articles", [])
            for art in articles[:3]:
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
            issue_lines = [f"  - [{i['severity']}] {i['message']}" for i in issues[:3]]
            parts.append("주요 이슈:\n" + "\n".join(issue_lines))

        recs = insight.get("recommendations", [])
        if recs:
            # priority 기준 정렬 후 top 2
            sorted_recs = sorted(recs, key=lambda r: r.get("priority", 99))
            rec_lines = [f"  - [P{r.get('priority',9)}] {r.get('title')}: {r.get('reason')}" for r in sorted_recs[:2]]
            parts.append("핵심 제안 (우선순위순):\n" + "\n".join(rec_lines))

    return "\n".join(parts)


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
            suggestions=data.get("suggestions", [])[:3],
        )
    except Exception:
        return CoachResponse(message=raw[:400], suggestions=[])


@router.post("/strategy/coach", response_model=CoachResponse)
async def coach_strategy(req: CoachRequest) -> CoachResponse:
    if _parser is None:
        raise HTTPException(status_code=503, detail="Coach model not loaded yet")

    try:
        from engine.nl_parser import NLStrategyParser
        parser: NLStrategyParser = _parser

        user_msg = _build_user_message(req)

        import main as _main
        with _main._mlx_inference_lock:
            raw = parser.chat(COACH_SYSTEM_PROMPT, user_msg, max_tokens=400)

        return _parse_llm_response(raw)

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

    from engine.nl_parser import NLStrategyParser
    parser: NLStrategyParser = _parser
    user_msg = _build_user_message(req)

    def _iter():
        import main as _main
        buffer = ""
        last_sent = ""
        try:
            with _main._mlx_inference_lock:
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
                        yield f"data: {payload}\n\n"

            # 최종 파싱: message + suggestions
            final = _parse_llm_response(buffer)
            payload = json.dumps(
                {"type": "done", "message": final.message, "suggestions": final.suggestions},
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.exception("coach stream failed: %s", exc)
            payload = json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        _iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
