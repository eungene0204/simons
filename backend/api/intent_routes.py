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
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import cancellation
from intent.classifier import classify, format_history_context
from intent.schemas import ChatTurn, IntentRequest, IntentResult
from intent import platform_defaults, strategy_builder
from observability import span
from stock_analysis import guardrails
from stock_analysis.schemas import DISCLAIMER

logger = logging.getLogger(__name__)
router = APIRouter(tags=["intent"])


# ─── 공유 MLX LLM 어댑터 ────────────────────────────────────────────────────────

# 서버가 이미 로드한 main 모듈만 사용한다(sys.modules). standalone/테스트에서 main을
# 새로 import해 전체 앱을 부트스트랩하는 부작용을 피한다 → 그 경우 LLM 미사용(템플릿 폴백).
def _main_module():
    return sys.modules.get("main")


def _chat(
    system_prompt: str,
    user_msg: str,
    *,
    max_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
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
            return parser.chat(
                system_prompt, user_msg,
                max_tokens=max_tokens, temperature=temperature, top_p=top_p,
            ) or ""
    except Exception:
        logger.debug("stock-analysis MLX 호출 실패 — 폴백", exc_info=True)
        return ""


# 어댑터를 둘로 나누는 이유: 이 모듈의 LLM 호출은 성격이 정반대인 두 갈래다.
#
#   구조화 출력(라벨·지표 키·ops JSON·용어 추출) — 정답을 고르는 일이다. 표현이
#   달라질 이유가 없고, 달라지면 같은 질문에 다른 답이 나간다.
#   산문 답변(/query/general) — 설명하는 일이다. 매번 같은 문장이면 오히려 어색하다.
#
# 종전에는 하나의 어댑터가 `temperature=0.3`으로 둘 다 처리했다. 0.3은 산문 쪽에
# 맞춘 값인데(nl_parser.chat: "temperature>0이면 표현이 매번 달라지도록 샘플링한다
# — 코치용") 분류가 같은 어댑터를 쓰면서 딸려온 것이지 분류를 위해 고른 값이 아니었다.
# 실측(2026-08-11): 같은 입력 '코스닥 상장사 수가 몇 개야?'가 5회 중
# GENERAL_INVESTMENT↔UNKNOWN으로 갈렸고, greedy로 바꾸자 5/5 고정됐다.
#
# 전략 해석기·파싱 검증기는 이미 temperature=0을 쓴다 — 구조화 출력엔 0이라는 기준이
# 코드베이스에 이미 서 있었고 이 모듈만 예외였다.

def _mlx_llm_structured(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
    """구조화 출력용 — greedy. 같은 입력에 같은 라벨이 나와야 한다."""
    return _chat(system_prompt, user_msg, max_tokens=max_tokens, temperature=0.0, top_p=1.0)


def _mlx_llm_prose(system_prompt: str, user_msg: str, *, max_tokens: int = 400) -> str:
    """자연어 설명용 — 표현이 매번 달라지도록 샘플링한다."""
    return _chat(system_prompt, user_msg, max_tokens=max_tokens, temperature=0.3, top_p=0.9)


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
    # 구조화 출력(intent + stock_name + refers_to_last_stock + workflow_effect +
    # clarify_target + fact_metric + list_scope + list_count_only)을 담을 만큼의 토큰을
    # 준다. 필드가 늘면 JSON이 절단돼 해석 실패(UNKNOWN)로 떨어지므로 여유를 둔다
    # (2026-07-31 clarify_target 추가로 180→220, 2026-08-11 축 3개 추가로 220→280).
    llm = (lambda s, u: _mlx_llm_structured(s, u, max_tokens=280)) if _llm_available() else None
    # 관찰 전용 span — 전략 파싱 레인(NullStock Strategy Agent)과 달리 이 레인은
    # Trace가 없어 "예상 못한 질문이 어느 라벨로 떨어졌나"를 사후 조회할 수 없었다.
    # 실행 경로는 건드리지 않는다(관찰 계층 계약: 읽기만).
    with span(
        "Classifier · 의도 분류",
        "chain",
        inputs={"query": req.query, "last_symbol": req.last_symbol},
        metadata={
            "history_turns": len(req.history or []),
            "active_strategy": req.active_strategy,
            "workflow_status": req.workflow_status,
            "has_pending_question": bool(req.pending_question),
            "llm_available": llm is not None,
        },
        root=True,
    ) as trace:
        result = await asyncio.to_thread(
            classify,
            req.query,
            last_symbol=req.last_symbol,
            llm=llm,
            history=req.history,
            active_strategy=req.active_strategy,
            workflow_status=req.workflow_status,
            pending_question=req.pending_question,
        )
        trace.output(
            intent=result.intent.value,
            deterministic=result.deterministic,
            reason=result.reason,
            confidence=result.confidence,
            workflow_effect=result.workflow_effect.value,
            workflow_status=result.workflow_status.value,
            clarify_target=result.clarify_target,
            # 규제 게이트를 통과해 사실 조회로 답한 턴인지 — 게이트 분리가 실제로
            # 어떤 발화를 열어줬는지가 커버리지 리포트의 판정 근거다.
            fact_metric=result.fact_metric,
            list_scope=result.list_scope,
            interpretation_failed=result.interpretation_failed,
            symbols=[s.name for s in (result.symbols or [])],
            has_suggested_reply=bool(result.suggested_reply),
        )
        return result


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


def _run_builder_step(state, input_text, risk_extractor, sector_resolver,
                      freetext_interpreter=None) -> strategy_builder.StepResult:
    """빌더 한 턴을 처리하고, 완성(confirmed)되면 DSL을 직접 구성해 붙인다.

    [전략별 특화 빌더] 한국어 재파싱 왕복 대신 build_parsed_strategy로 ParsedStrategy를
    직접 만들어(파라미터 유실 방지) 기존 to_backtest_request로 요청까지 생성한다. custom
    유형은 DSL을 만들 수 없어 parsed=None → 프론트가 prompt 재파싱 경로로 폴백한다."""
    result = strategy_builder.step(state, input_text, risk_extractor, sector_resolver,
                                   freetext_interpreter)
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
    seed_recognized = False
    if strategy_builder.is_empty(state):
        if req.seed:
            state = strategy_builder.seed_state(req.seed)
        state = strategy_builder.apply_parsed_seed(state, req.seed_parsed)
        # 시드 이해 판정은 step 실행 전(시드 적용 직후) 상태로 한다 — 프론트가 열린 추천
        # 안내문(STRATEGY_PICK) 표시 여부를 정하는 근거(둘 중 하나만, 2026-08-10).
        seed_recognized = strategy_builder.seed_recognized(state)
    risk_extractor, sector_resolver, freetext_interpreter = _builder_llm_helpers()
    result = await asyncio.to_thread(
        _run_builder_step, state, req.input, risk_extractor, sector_resolver, freetext_interpreter
    )
    result.seed_recognized = seed_recognized
    return result


def _builder_llm_helpers(on_search=None, on_kg_lookup=None):
    """빌더 스텝용 LLM 헬퍼 → (risk_extractor, sector_resolver, freetext_interpreter).
    LLM 없으면 (None, None, None).

    청산 조건 자유 입력·미해결 업종 언급은 공유 LLM 파서로 보강·해석한다.
    업종 해석은 어휘집 → 내부 지식 LLM → 인터넷 검색 그라운딩 체인(FR-STR-069) —
    LLM이 모르는 테마 용어(ESS 등)를 검색으로 학습해 정본 섹터로 매핑하고, 결과는
    어휘집에 영속 저장돼 같은 용어를 두 번 검색하지 않는다. on_search는 검색 그라운딩
    실제 진입 시 1회 호출된다(SSE 경로의 '검색 중...' 진행 표시). on_kg_lookup은 개념
    해석 체인 진입 시 1회 호출된다('개념 확인 중...' 표시 — 검색 진입 시 on_search가 대체)."""
    if not _llm_available():
        return None, None, None
    from engine.term_grounding import resolve_sector as _resolve_sector_grounded

    # 빌더 레인은 전부 구조화 추출이다(리스크 값·업종명·제한된 ops JSON).
    risk_extractor = lambda text: strategy_builder.llm_extract_risk(text, _mlx_llm_structured)
    sector_resolver = lambda text: _resolve_sector_grounded(
        text, _mlx_llm_structured,
        base_resolver=lambda t: strategy_builder.llm_extract_sector(t, _mlx_llm_structured),
        on_search=on_search,
        on_kg_lookup=on_kg_lookup,
    )
    # 자유 서술 LLM 레인(계약 단계 3 C안) — 결정적 레이어가 해석하지 못한 자유 텍스트를
    # 제한된 ops JSON으로 해석한다. 롤백=BUILDER_FREETEXT_MODE=deterministic.
    from intent.builder_interpreter import freetext_llm_enabled, interpret_utterance

    freetext_interpreter = (
        (lambda text, state: interpret_utterance(text, state, _mlx_llm_structured))
        if freetext_llm_enabled() else None
    )
    return risk_extractor, sector_resolver, freetext_interpreter


@router.post("/strategy/builder/step-stream")
async def strategy_builder_step_stream(req: BuilderStepRequest):
    """빌더 한 턴을 SSE로 처리한다 — 개념 해석 체인(지식그래프 조회 포함) 진입 시
    {"type":"stage","stage":"kg_lookup"}('개념 확인 중...'), 인터넷 검색 그라운딩
    (FR-STR-069) 진입 시 {"type":"stage","stage":"searching"}('검색 중...') 이벤트를
    먼저 흘려 프론트가 진행 표시할 수 있게 한다(parse-stream의 stage_holder 폴링 패턴 재사용).

    최종 결과는 {"type":"result","data":StepResult} 단일 이벤트. 결과 계약은 기존
    POST /strategy/builder/step과 동일하다(그 엔드포인트는 호환용으로 유지)."""
    import json as _json
    import threading

    from fastapi.responses import StreamingResponse

    state = req.state
    seed_recognized = False
    if strategy_builder.is_empty(state):
        if req.seed:
            state = strategy_builder.seed_state(req.seed)
        state = strategy_builder.apply_parsed_seed(state, req.seed_parsed)
        # JSON 라우트와 같은 계약 — 시드 적용 직후 상태로 이해 여부를 판정한다.
        seed_recognized = strategy_builder.seed_recognized(state)

    stage_holder: dict = {"stage": None}
    result_holder: dict = {}
    error_holder: dict = {}
    risk_extractor, sector_resolver, freetext_interpreter = _builder_llm_helpers(
        on_search=lambda: stage_holder.__setitem__("stage", "searching"),
        on_kg_lookup=lambda: stage_holder.__setitem__("stage", "kg_lookup"),
    )

    # 요청 취소 토큰 — 클라이언트가 스트림을 끊으면('대화 종료') 빌더 스텝 스레드의 LLM
    # 호출(리스크 추출·업종 해석·자유 서술 해석·검색 그라운딩)을 멈춘다(cancellation.py).
    cancel_token = cancellation.CancelToken()

    def run_step():
        with cancellation.bind(cancel_token):
            try:
                step_result = _run_builder_step(
                    state, req.input, risk_extractor, sector_resolver, freetext_interpreter
                )
                step_result.seed_recognized = seed_recognized
                result_holder["data"] = step_result.model_dump()
            except cancellation.OperationCancelled:
                print("[BUILDER-STEP] 취소됨(클라이언트 연결 종료)", flush=True)
            except Exception as exc:  # noqa: BLE001 — SSE로 에러 전달(스트림 중단 방지)
                error_holder["detail"] = str(exc)

    thread = threading.Thread(target=run_step, daemon=True)

    async def generate():
        completed = False
        try:
            thread.start()
            emitted = None
            while thread.is_alive():
                if stage_holder["stage"] != emitted:
                    emitted = stage_holder["stage"]
                    yield f"data: {_json.dumps({'type': 'stage', 'stage': emitted})}\n\n"
                await asyncio.sleep(0.1)
            thread.join()
            if "detail" in error_holder:
                yield f"data: {_json.dumps({'type': 'error', 'detail': error_holder['detail']}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {_json.dumps({'type': 'result', 'data': result_holder.get('data')}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            completed = True
        finally:
            # 정상 종료 전에 닫히면 클라이언트가 연결을 끊은 것이다(Starlette가 스트림 태스크를
            # 취소한다) — 스텝 스레드의 LLM 호출을 끊는다.
            if not completed:
                cancel_token.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    })


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
    # 호출부가 확정한 사실 블록(결과 수치 질문 RESULT_EXPLAIN에서 사용자의 실제 백테스트
    # 수치). 플랫폼 기본값·용어 사전과 같은 자리에 주입한다 — 주입이 없으면 LLM이 남의
    # 숫자를 지어낸다. **사실은 호출부가 만들고 LLM은 설명만 한다**(수치 생성 금지).
    facts: Optional[str] = None


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


# 결과 수치 질문 전용 시스템 프롬프트.
# [규제 안전] CLAUDE.md 안전한 표현 원칙 — 과거 데이터 사실 서술은 허용, 우열·전망 판단은
# 금지다. "좋다/나쁘다/유망하다"를 말하는 순간 투자 자문이 되므로, 수치의 **의미**와
# 사용자의 **실제 값**을 잇는 데까지만 답한다.
_RESULT_SYSTEM_PROMPT = (
    "당신은 사용자가 방금 실행한 백테스트 결과의 지표를 설명하는 도우미입니다. "
    "질문 앞에 주어진 [사실]은 그 사용자의 실제 결과입니다 — 이 수치만 인용하고 "
    "다른 숫자를 지어내지 마십시오. [사실]에 없는 값을 물으면 그 값은 결과에 없다고 "
    "밝히십시오.\n"
    "지표가 무엇을 뜻하는지, 주어진 수치들이 서로 어떤 관계인지를 2~4문장으로 "
    "설명하십시오(예: 승률이 높아도 손실 거래의 평균 손실이 크면 총손익은 마이너스일 수 "
    "있습니다).\n"
    "절대 하지 마십시오: 이 전략이 좋다·나쁘다·우수하다·위험하다는 평가, 계속 쓰라거나 "
    "바꾸라는 권유, 앞으로의 성과 전망, 다른 전략·종목과의 우열 비교. "
    "개별 지표에 등급을 매기는 표현도 평가입니다 — '양호하다·우수하다·훌륭하다·나쁘다·"
    "안정적이다·효율적이다' 같은 말을 수치에 붙이지 마십시오. 지표 사이의 관계는 "
    "설명해도 되지만('승률이 높아도 평균 손실이 크면 총손익은 마이너스가 됩니다'), "
    "수치 하나를 두고 잘하고 못했다고 말하지는 마십시오. "
    "'이 결과를 믿어도 되냐'처럼 판단을 요구하는 질문에는 평가 대신, 과거 데이터 기반 "
    "시뮬레이션 결과라는 점과 워크포워드·몬테카를로 검증으로 견고성을 더 확인할 수 "
    "있다는 사실을 안내하십시오.\n"
    "한국어로만, JSON 없이 평문으로 답하십시오."
)


def _build_general_user_msg(req: GeneralQueryRequest, extra_facts: Optional[str] = None) -> str:
    # 설정 용어(슬리피지·수수료 등)가 언급된 개념 질문에는 실제 플랫폼 기본값을 사실로
    # 주입한다 — LLM이 "기본값은 0%" 같은 값을 지어내는 것을 막는다.
    # 기초 용어(PER·RSI 등) 정의도 사실로 주입한다 — 소형 LLM의 정의 오류(레드팀 QA
    # 6-1/7-4: "PER=주가순자산비율", "RSI 90=과매도") 방지.
    # extra_facts: 테마 용어 검증 정의 블록(term_grounding.general_facts_block — 지식그래프/
    # 어휘집/검색 그라운딩. ESS를 '에너지 효율성'으로 환각하던 사고 방지).
    from intent import glossary_facts
    facts_parts = [
        block for block in (
            # 호출부가 확정한 사실(사용자의 실제 결과 수치)이 가장 먼저 온다 — LLM이
            # 일반 지식보다 이 값을 근거로 삼아야 한다.
            f"[사실]\n{req.facts}" if req.facts else None,
            platform_defaults.facts_block(req.query),
            glossary_facts.facts_block(req.query),
            extra_facts,
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


def generate_general_answer(
    query: str,
    history: list[ChatTurn] | None = None,
    caller_facts: Optional[str] = None,
) -> Optional[str]:
    """일반 투자 지식 질문의 답변을 동기 생성한다. LLM 미가용·빈 응답이면 None.

    /query/general 엔드포인트와, 정의형 질문이 전략 수정 경로로 오라우팅됐을 때의
    설명 백스톱(strategy_conversation.primary, FR-SA-002c-4)이 공유한다.
    백테스트 설정 기본값 질문은 LLM 대신 실제 코드 기본값으로 결정적으로 답한다.
    """
    # 관찰 전용 span — 라벨 밖 질문(UNKNOWN)이 이 레인으로 흘러오므로, 답이 결정론
    # 기본값이었는지·LLM이었는지·어떤 사실이 주입됐는지가 "무엇을 못 알아듣나"의 근거다.
    # root=False: 전략 레인 백스톱에서 불리면 그 Trace에 붙고, /query/general에서
    # 불리면 부모가 없어 자기 레코드로 방출된다.
    with span(
        "General · 일반 지식 답변",
        "chain",
        inputs={"query": query},
        metadata={
            "history_turns": len(history or []),
            "caller_facts": bool(caller_facts),
        },
    ) as trace:
        # 호출부가 사실을 들고 왔으면(결과 수치 질문) 설정 기본값 결정론 답변으로 새지
        # 않는다 — 묻는 대상이 플랫폼 설정이 아니라 사용자의 결과다.
        if not caller_facts:
            deterministic = platform_defaults.reply(query)
            if deterministic:
                trace.output(source="platform_defaults", answered=True)
                return deterministic
        if not _llm_available():
            trace.output(source="none", answered=False, reason="llm_unavailable")
            return None
        req = GeneralQueryRequest(query=query, history=history or [], facts=caller_facts)
        # 테마 용어 검증 정의 주입(FR-STR-069) — 기초 용어(glossary/기본값)가 이미 잡힌
        # 질문은 검색 폴백을 건너뛴다(불필요한 용어 추출 LLM 호출·검색 방지).
        # 호출부 사실이 있으면 그것이 이미 권위 있는 근거라 검색까지 갈 이유가 없다.
        extra_facts = None
        if not caller_facts:
            try:
                from intent import glossary_facts
                from engine.term_grounding import general_facts_block

                known_vocab = bool(
                    platform_defaults.facts_block(query) or glossary_facts.facts_block(query)
                )
                # 용어 **추출**은 구조화(짧은 문자열 하나), 아래 **답변 생성**만 산문이다.
                extra_facts = general_facts_block(
                    query, _mlx_llm_structured, allow_search=not known_vocab
                )
            except Exception:  # noqa: BLE001 — 사실 주입 실패가 답변 자체를 막으면 안 된다
                logger.debug("용어 정의 사실 주입 실패 — 주입 없이 답변", exc_info=True)
        system_prompt = _RESULT_SYSTEM_PROMPT if caller_facts else _GENERAL_SYSTEM_PROMPT
        raw = _mlx_llm_prose(
            system_prompt, _build_general_user_msg(req, extra_facts), max_tokens=300
        )
        answer = guardrails.sanitize(raw)
        if caller_facts:
            # 결과 수치 설명에서만 등급 표현을 걷어낸다 — 프롬프트 지시를 9B가 완전히
            # 지키지 못해서 남는 '양호한 수준' 류를 마지막에 거른다.
            answer = guardrails.strip_metric_grading(answer)
        answer = answer or None
        trace.output(
            source="llm",
            answered=bool(answer),
            grounded=bool(extra_facts or caller_facts),
            sanitized=bool(raw) and not answer,
            answer=answer,
        )
        return answer


@router.post("/query/general", response_model=GeneralQueryResponse)
async def general_answer(req: GeneralQueryRequest) -> GeneralQueryResponse:
    answer = await asyncio.to_thread(
        generate_general_answer, req.query, req.history, req.facts
    )
    if answer:
        return GeneralQueryResponse(answer=answer)
    return GeneralQueryResponse(
        answer="해당 주제에 대한 일반적인 설명을 준비하지 못했습니다. 질문을 좀 더 구체적으로 입력해 주세요."
    )


# ─── /strategy/rollback/resolve ─────────────────────────────────────────────────
# [설계 스펙 § 19] 되돌리기 대상 판정. 대화는 무상태이므로 변경 이력은 프론트가 보관하고
# 요청에 실어 보낸다(pending_ask·explicit_fields와 같은 에코 계약). 여기서는 "어디로
# 되돌릴지"만 정하고, 실제 복원은 스냅샷을 들고 있는 프론트가 결정론으로 수행한다.


def _rollback_llm():
    """되돌리기 판정용 9B chat. 준비 안 됐으면 None(되묻기로 강등된다)."""
    try:
        from strategy_conversation.planner.shadow import _default_chat

        return _default_chat()
    except Exception:  # noqa: BLE001 — LLM 준비 실패가 500이 되면 안 된다
        logger.warning("되돌리기 판정 LLM 준비 실패 — 되묻기로 강등", exc_info=True)
        return None


class RollbackChangeEvent(BaseModel):
    """변경 이력 한 항목. 값은 싣지 않는다 — 판정에 필요한 것은 무엇이 바뀌었나뿐이다."""

    index: int
    user_text: str = ""
    changed_fields: List[str] = Field(default_factory=list)


class RollbackResolveRequest(BaseModel):
    query: str
    events: List[RollbackChangeEvent] = Field(default_factory=list)


class RollbackResolveResponse(BaseModel):
    action: str
    turn_index: Optional[int] = None
    fields: List[str] = Field(default_factory=list)
    question: Optional[str] = None
    reason: str = ""


@router.post("/strategy/rollback/resolve", response_model=RollbackResolveResponse)
async def resolve_rollback(req: RollbackResolveRequest) -> RollbackResolveResponse:
    from strategy_conversation.conversation.rollback import resolve

    # [모델 슬롯] 인터프리터와 같은 9B를 쓴다. 이 판정은 분류가 아니라 이력 목록 위의
    # 추론이라 4B(레거시 파서·코치 슬롯)로는 성립하지 않는다 — 실측 2026-07-30:
    # 4B 1/7 vs 9B 5/7(같은 프롬프트·같은 이력). 잘못 고른 턴은 사용자가 쌓아온 전략을
    # 지우므로, 여기서 슬롯을 아끼면 안 된다.
    llm = _rollback_llm()
    decision = await asyncio.to_thread(
        resolve, req.query, [e.model_dump() for e in req.events], llm
    )
    return RollbackResolveResponse(**decision.model_dump())


# ─── /knowledge/graph ───────────────────────────────────────────────────────────

@router.get("/knowledge/graph")
async def knowledge_graph_dump() -> dict:
    """합성 지식그래프 전체 덤프 — 관리자 콘솔 KG 시각화(FR-STR-070c)용 읽기 전용 뷰.

    시드+정본(섹터·기업·ETF)+학습 오버레이가 합성된 그래프를 그대로 내보낸다.
    객관적 관계 데이터 표시이며 추천·전망이 아니다.
    """
    from engine.knowledge_graph import get_graph

    graph = await asyncio.to_thread(get_graph)
    return {
        "nodes": list(graph.nodes.values()),
        "edges": graph.edges,
        "issues": graph.issues,
    }


@router.get("/ontology/graph")
async def indicator_ontology_dump() -> dict:
    """지표 온톨로지 덤프 — 관리자 콘솔 시각화·검색용 읽기 전용 뷰.

    분류 계층(is_a)·잎(Registry 전체)·합성 개념(expands_to/requires)을 그대로
    내보낸다. 시스템 계약 데이터 표시이며 추천·전망이 아니다.
    """
    from strategy_conversation.registry.concept_ontology import ontology_graph

    return await asyncio.to_thread(ontology_graph)


@router.get("/knowledge/concept-universe")
async def knowledge_concept_universe(q: str) -> dict:
    """Concept 중심 유니버스 결정론 생성(FR-STR-072) — 읽기 전용 뷰.

    KG 근거(원장 점수·출처 수·관계 거리)에서 관련도를 결정론 산출한 종목 집합.
    객관적 관계 데이터 표시이며 추천·전망이 아니다. 모르는 개념은 found=false.
    """
    from engine.concept_universe import build_concept_universe

    result = await asyncio.to_thread(build_concept_universe, q)
    if result is None:
        return {"found": False, "query": q}
    return {"found": True, "query": q, **result}
