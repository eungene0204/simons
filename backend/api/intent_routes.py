"""
FastAPI routes — Query Intent 분류 + 전략 빌더 + 일반 투자 지식.

POST /query/classify        — 사용자 입력을 QueryIntent로 분류
POST /strategy/builder/step — 전략 빌더 대화 한 턴
POST /query/general         — GENERAL_INVESTMENT 일반 투자 지식 답변(LLM)

[규제 안전] 개별 종목 분석(/stock/analyze)은 제거됐다 — 특정 종목 질문(STOCK_ANALYSIS)은
분류 단계에서 suggested_reply(추천 불가 안내 + 전략 설계 전환)로 응답한다.

LLM은 coach와 동일한 공유 Qwen MLX 모델을 inference lock 안에서 사용한다.
LLM이 없으면 결정적 템플릿/폴백으로 동작한다(기능 항상 보장).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from intent.classifier import classify, format_history_context
from intent.schemas import ChatTurn, IntentRequest, IntentResult
from intent import platform_defaults, strategy_builder
from stock_analysis import guardrails
from stock_analysis.schemas import DISCLAIMER

logger = logging.getLogger(__name__)
router = APIRouter(tags=["intent"])


# ─── 공유 MLX LLM 어댑터 ────────────────────────────────────────────────────────

# 서버가 이미 로드한 main 모듈만 사용한다(sys.modules). standalone/테스트에서 main을
# 새로 import해 전체 앱을 부트스트랩하는 부작용을 피한다 → 그 경우 LLM 미사용(템플릿 폴백).
def _main_module():
    return sys.modules.get("main")


def _mlx_llm(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
    """coach와 동일한 공유 parser를 inference lock 안에서 호출한다. 없으면 빈 문자열.
    백엔드(mlx/ollama)와 무관하게 등록된 공유 파서를 사용한다."""
    main_mod = _main_module()
    if main_mod is None:
        return ""
    try:
        active = getattr(main_mod, "_active_nl_parser", None)
        parser = active() if callable(active) else getattr(main_mod, "_nl_parsers", {}).get("mlx")
        lock = getattr(main_mod, "_mlx_inference_lock", None)
        if parser is None or lock is None:
            return ""
        with lock.priority(1):
            return parser.chat(system_prompt, user_msg, max_tokens=max_tokens, temperature=0.3, top_p=0.9) or ""
    except Exception:
        logger.debug("stock-analysis MLX 호출 실패 — 폴백", exc_info=True)
        return ""


def _llm_available() -> bool:
    main_mod = _main_module()
    if main_mod is None:
        return False
    active = getattr(main_mod, "_active_nl_parser", None)
    if callable(active):
        return active() is not None
    return getattr(main_mod, "_nl_parsers", {}).get("mlx") is not None


# ─── /query/classify ────────────────────────────────────────────────────────────

@router.post("/query/classify", response_model=IntentResult)
async def classify_query(req: IntentRequest) -> IntentResult:
    llm = (lambda s, u: _mlx_llm(s, u, max_tokens=40)) if _llm_available() else None
    return await asyncio.to_thread(
        classify, req.query, last_symbol=req.last_symbol, llm=llm, history=req.history
    )


# ─── /strategy/builder/step ──────────────────────────────────────────────────────
# [규제 안전] 열린 종목 추천(STOCK_PICK) 전환 직후 진입하는 전략 빌더 대화의 한 턴.
# 짧은 답변을 전략 필드로 누적하고, 완성되면 백테스트 프롬프트를 합성한다(결정적·LLM 불필요).


class BuilderStepRequest(BaseModel):
    state: strategy_builder.BuilderState = Field(default_factory=strategy_builder.BuilderState)
    input: str
    # 빌더 진입 시점의 사용자 원본 메시지. 상태가 비어 있을 때만 이 문장에서 인식 가능한
    # 전략 필드를 미리 채워(seed), 사용자가 이미 말한 조건은 다시 묻지 않는다.
    seed: Optional[str] = None
    # 빈 전략으로 빌더 전환 시 파싱 파이프라인(룰 파스→LLM 검증 교정→LLM 폴백)이 이미
    # 해석한 ParsedStrategy dump. 결정적 시드 regex가 놓친 필드(sector·청산)를 이어받아,
    # 긴 꼬리 표현마다 regex를 늘리지 않고 LLM 레이어의 해석이 빌더까지 흐르게 한다.
    seed_parsed: Optional[dict] = None


def _run_builder_step(state, input_text, risk_extractor, sector_resolver) -> strategy_builder.StepResult:
    """빌더 한 턴을 처리하고, 완성(confirmed)되면 DSL을 직접 구성해 붙인다.

    [전략별 특화 빌더] 한국어 재파싱 왕복 대신 build_parsed_strategy로 ParsedStrategy를
    직접 만들어(파라미터 유실 방지) 기존 to_backtest_request로 요청까지 생성한다. custom
    유형은 DSL을 만들 수 없어 parsed=None → 프론트가 prompt 재파싱 경로로 폴백한다."""
    result = strategy_builder.step(state, input_text, risk_extractor, sector_resolver)
    if result.status == "confirmed":
        parsed = strategy_builder.build_parsed_strategy(result.state)
        if parsed is not None:
            from engine.nl_parser import enforce_strategy_minimums
            from engine.strategy_converter import to_backtest_request

            # 하한선 방어 보정(공통) + 빌더가 이미 담은 안내(목록 밖 업종 등)를 보존한다.
            result.notices = enforce_strategy_minimums(parsed) + result.notices
            result.backtest_request = to_backtest_request(parsed)
            result.parsed = parsed.model_dump()
    return result


@router.post("/strategy/builder/step", response_model=strategy_builder.StepResult)
async def strategy_builder_step(req: BuilderStepRequest) -> strategy_builder.StepResult:
    state = req.state
    if strategy_builder.is_empty(state):
        if req.seed:
            state = strategy_builder.seed_state(req.seed)
        state = strategy_builder.apply_parsed_seed(state, req.seed_parsed)
    # 청산 조건 자유 입력·미해결 업종 언급은 공유 LLM 파서로 보강·해석한다.
    risk_extractor = None
    sector_resolver = None
    if _llm_available():
        risk_extractor = lambda text: strategy_builder.llm_extract_risk(text, _mlx_llm)
        sector_resolver = lambda text: strategy_builder.llm_extract_sector(text, _mlx_llm)
    return await asyncio.to_thread(_run_builder_step, state, req.input, risk_extractor, sector_resolver)


# ─── /strategy/compile ───────────────────────────────────────────────────────────


class StrategyCompileRequest(BaseModel):
    # 프론트가 누적해 온 ParsedStrategy dump. 재해석 없이 이 값이 진실이다.
    parsed: dict


class StrategyCompileResponse(BaseModel):
    parsed: dict
    backtest_request: dict
    notices: list[str] = Field(default_factory=list)


@router.post("/strategy/compile", response_model=StrategyCompileResponse)
async def strategy_compile(req: StrategyCompileRequest) -> StrategyCompileResponse:
    """확정된 ParsedStrategy를 재해석 없이 백테스트 요청으로 컴파일한다.

    결정적 조건 플로우의 '전략 확정'이 대화 전체를 LLM에 재파싱시키면, 규칙 파서가
    표현 못 하는 조건(예: '영업이익 흑자' 필터)을 LLM이 비결정적으로 떨어뜨려 완성
    전략의 매수 조건이 사라진 채 다시 되묻는 사고가 난다. 특화 빌더의 '한국어 재파싱
    왕복 없이 그대로 적용'(_run_builder_step confirmed)과 같은 계약으로, 누적 parsed를
    그대로 컴파일만 한다(하한선 방어 보정은 공통 적용)."""
    from engine.nl_parser import ParsedStrategy, enforce_strategy_minimums
    from engine.strategy_converter import to_backtest_request

    try:
        parsed = ParsedStrategy.model_validate(req.parsed)
    except Exception:
        raise HTTPException(status_code=422, detail="전략 데이터를 해석할 수 없습니다.")
    notices = enforce_strategy_minimums(parsed)
    backtest_request = await asyncio.to_thread(to_backtest_request, parsed)
    return StrategyCompileResponse(
        parsed=parsed.model_dump(), backtest_request=backtest_request, notices=notices,
    )


# ─── /query/general ──────────────────────────────────────────────────────────────

class GeneralQueryRequest(BaseModel):
    query: str
    # 최근 대화 턴(오래된 것부터). '다른 예는 없어?' 같은 후속 질문이 직전 답변에 이어
    # 답변되도록 LLM에 참고 맥락으로 넘긴다.
    history: list[ChatTurn] = Field(default_factory=list)


class GeneralQueryResponse(BaseModel):
    answer: str
    disclaimer: str = DISCLAIMER


_GENERAL_SYSTEM_PROMPT = (
    "당신은 투자 용어와 일반 투자 지식을 쉽게 설명하는 도우미입니다. "
    "사용자의 질문에 2~4문장으로 간결하고 정확하게 답하십시오. "
    "질문 앞에 [대화 맥락]이 주어지면 마지막 질문은 그 맥락에 이어지는 후속 질문일 수 있습니다 "
    "— 직전 답변과 겹치지 않게 이어서 답하십시오(예: 예시를 더 요청하면 앞서 말하지 않은 예시를 제시). "
    "특정 종목의 매수·매도를 권하지 말고, 확정적 수익 표현을 쓰지 마십시오. "
    "나이·자산·직업 등 개인 상황에 맞춘 전략·상품 추천(예: '40대에게는 채권이 적합')은 "
    "절대 하지 마십시오 — 그런 질문에는 맞춤 조언을 제공하지 않는다고 안내하십시오. "
    "질문에 잘못된 금융 상식이 전제되어 있으면 먼저 정확하게 바로잡으십시오. "
    "한국어로만 답하고, JSON 없이 평문으로만 답하십시오."
)


def _build_general_user_msg(req: GeneralQueryRequest) -> str:
    # 설정 용어(슬리피지·수수료 등)가 언급된 개념 질문에는 실제 플랫폼 기본값을 사실로
    # 주입한다 — LLM이 "기본값은 0%" 같은 값을 지어내는 것을 막는다.
    # 기초 용어(PER·RSI 등) 정의도 사실로 주입한다 — 소형 LLM의 정의 오류(레드팀 QA
    # 6-1/7-4: "PER=주가순자산비율", "RSI 90=과매도") 방지.
    from intent import glossary_facts
    facts_parts = [
        block for block in (
            platform_defaults.facts_block(req.query),
            glossary_facts.facts_block(req.query),
        ) if block
    ]
    facts = "\n".join(facts_parts)
    parts = [f"{facts}\n" if facts else ""]
    context = format_history_context(req.history)
    if context:
        parts.append(f"[대화 맥락]\n{context}\n[질문]\n{req.query}")
    else:
        parts.append(req.query)
    return "".join(parts)


def generate_general_answer(query: str, history: list[ChatTurn] | None = None) -> Optional[str]:
    """일반 투자 지식 질문의 답변을 동기 생성한다. LLM 미가용·빈 응답이면 None.

    /query/general 엔드포인트와, 정의형 질문이 전략 수정 경로로 오라우팅됐을 때의
    설명 백스톱(strategy_conversation.primary, FR-SA-002c-4)이 공유한다.
    백테스트 설정 기본값 질문은 LLM 대신 실제 코드 기본값으로 결정적으로 답한다.
    """
    deterministic = platform_defaults.reply(query)
    if deterministic:
        return deterministic
    if not _llm_available():
        return None
    req = GeneralQueryRequest(query=query, history=history or [])
    raw = _mlx_llm(_GENERAL_SYSTEM_PROMPT, _build_general_user_msg(req), max_tokens=300)
    return guardrails.sanitize(raw) or None


@router.post("/query/general", response_model=GeneralQueryResponse)
async def general_answer(req: GeneralQueryRequest) -> GeneralQueryResponse:
    answer = await asyncio.to_thread(generate_general_answer, req.query, req.history)
    if answer:
        return GeneralQueryResponse(answer=answer)
    return GeneralQueryResponse(
        answer="해당 주제에 대한 일반적인 설명을 준비하지 못했습니다. 질문을 좀 더 구체적으로 입력해 주세요."
    )
