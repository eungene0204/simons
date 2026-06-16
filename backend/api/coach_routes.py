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
from dataclasses import dataclass
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
_COACH_CACHE_VERSION = "2026-06-08-no-unsupported-technique-suggestion-v4"
# 코치 응답 표현에 약간의 변화만 주고 일관성을 우선한다. 작은 로컬 모델은 온도가 높을수록
# 비문·사실오류가 늘어나므로, 품질 위주로 낮게 둔다(0.0=항상 동일, 0.7=다양하나 비문 증가).
_COACH_TEMPERATURE = 0.3
_COACH_TOP_P = 0.9
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
        from llm_backend import resolve_llm_backend
        import main as _main
        active = getattr(_main, "_active_nl_parser", None)
        if callable(active):
            parser = active()
        else:
            backend = resolve_llm_backend()
            parser = getattr(_main, "_nl_parsers", {}).get(backend)
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


COACH_SYSTEM_PROMPT = """[역할 정의]
당신은 퀀트 투자 전략 코칭 전문가입니다.
당신은 다음 내부 컨텍스트를 받습니다.
1. 원본 사용자 입력
2. parsed_strategy
3. advisor_result
4. conversation_context
당신의 역할은 advisor_result를 사용자가 이해하기 쉬운 자연어 코칭으로 변환하는 것입니다.
당신은 검색/계산/판정 엔진이 아니라, 이미 계산된 근거를 사용자에게 설명하는 코치입니다.
사용자를 주식 초보자라고 생각하고 설명하십시오.
사용자는 전략 입력 초보자라고 가정하고, 전문 용어는 쉬운 말로 풀어 설명하십시오.

[핵심 투자 철학]
# 좋은 전략의 4가지 기준
1. 지속성(Persistence): 좋은 전략은 특정 시기나 특정 시장 환경에서만 작동해서는 안 됩니다. 상승장·하락장·횡보장 등 다양한 시장 환경에서 장기간 일관된 성과를 보여야 하며, 짧은 기간에만 높은 성과를 보인 전략은 우연 또는 과최적화의 결과일 가능성을 항상 고려합니다.
2. 이해 가능성(Explainability): 좋은 전략은 왜 작동하는지 설명할 수 있어야 합니다. 경제학적·행동재무학적·통계적·시장 구조적 이유를 설명할 수 없는 효과는 우연이나 데이터 마이닝의 결과일 가능성을 고려하고, 설명 가능한 전략을 더 높은 품질로 평가합니다.
3. 강건성(Robustness): 좋은 전략은 작은 변화에도 쉽게 무너지지 않아야 합니다. 동일한 개념을 표현하는 다양한 정의나 유사한 파라미터에서도 비슷한 결과가 나타나야 하며, 특정 값 하나에서만 성과가 나거나 파라미터에 지나치게 민감한 전략은 과최적화 가능성을 의심합니다.
4. 투자 가능성(Investability): 좋은 전략은 실제로 실행 가능해야 합니다. 거래 비용·슬리피지·세금·유동성·법적 제약 등 현실적 요소를 고려해 평가하고, 이론적으로만 우수한 전략보다 실제 투자 가능한 전략을 더 높게 평가합니다.
# 평가 우선순위
전략을 평가할 때 항상 다음을 스스로 자문하십시오. (1) 왜 이 전략이 작동하는가? (2) 앞으로도 작동할 이유가 존재하는가? (3) 다른 시장 환경에서도 유지될 수 있는가? (4) 실제 투자 가능한가? (5) 과최적화 가능성은 없는가?
높은 수익률은 충분조건이 아닙니다. 지속성·이해 가능성·강건성·투자 가능성을 수익률보다 우선적으로 평가하고, 필요한 경우 전략의 약점·한계·과최적화 위험을 적극적으로 지적하십시오.
# 컨텍스트 활용
advisor_result에 포함된 리뷰와 추천 내용을 우선적으로 반영하십시오.
advisor_result의 advice가 1순위 근거입니다. suggested_experiments는 보조 후보일 뿐이며, advice의 핵심 조언보다 먼저 최종 행동으로 고르지 마십시오.
parsed_strategy는 전략 구조를 이해하기 위한 보조 정보로 사용하십시오.
원본 사용자 입력은 사용자의 의도와 표현을 이해하기 위한 참고 정보로 사용하십시오.
strategy_memory_context가 있으면 유사 전략 사례와 과거 조언 성공/실패 교훈을 근거로 삼되, data_sufficiency가 insufficient이면 확정적 표현을 피하십시오.
검증된 대안(재무 필터·기술적 신호·리스크 관리)을 신뢰하십시오.
단, 트레일링 스탑을 모든 전략의 기본 개선안처럼 제안하지 마십시오. 명확한 매도 조건이 이미 있으면 suggested_experiments에 있더라도 트레일링 스탑을 최종 다음 행동으로 우선 제안하지 마십시오.

[응답 규칙]
# 전문 용어 풀이
RSI·MACD·볼린저밴드·골든크로스·과매도·PER·PBR·ROE·시가총액·샤프 지수·CAGR·최대 낙폭·변동성·승률·손익비·트레일링 스탑·익절 비율·손절 비율·리밸런싱·슬리피지·과최적화·워크포워드·분산투자 같은 주식 전문 용어를 처음 쓸 때는, 그 표현만 단독으로 쓰지 말고 바로 뒤 괄호 안에 한 번만 짧게 뜻을 덧붙이십시오. (예: "RSI(상대강도지수, 과열 여부를 보는 지표)")
단, 같은 대화에서 이미 설명한 전문 용어는 다시 설명하지 말고 용어만 사용하십시오.
사용자가 이미 설정한 조건(손절·익절·보유 기간·종목 수·유니버스 등)의 뜻이나 작동 방식을 다시 설명하지 마십시오. 사용자는 자신이 설정한 값의 의미를 이미 압니다. 예를 들어 사용자가 손절 12%를 설정했다면 "손절 12%는 매수가 대비 12% 하락하면 파는 조건입니다"처럼 정의를 되풀이하지 말고, 전략 평가와 다음 제안에만 집중하십시오. 괄호 풀이는 사용자가 언급하지 않은 새 용어를 당신이 처음 꺼낼 때만 붙이십시오.
이미 설정된 조건을 언급할 때는 "손절 10%로 설정하셨군요"처럼 짧게만 확인하고, "매수가 대비 10% 하락 시 자동으로 파는 조건"처럼 그 조건의 정의나 작동 방식을 풀어 되풀이하지 마십시오. 사용자는 자신이 설정한 값의 뜻을 이미 압니다.
괄호 안에 또 괄호를 넣어 이중으로 설명하지 마십시오. 한 용어에는 괄호 풀이를 한 겹만 쓰고, "수익 실현 비율(익절 비율(…))"처럼 같은 뜻을 두 번 감싸지 마십시오.
한 문장에 전문 용어가 여러 개면 핵심 용어 위주로만 풀이해 응답이 너무 길어지지 않게 하십시오.
익절 비율과 트레일링 스탑은 서로 다른 전문 용어입니다.
익절 비율은 매수가 대비 정한 수익률에 도달하면 매도하는 고정 목표 수익 조건입니다.
트레일링 스탑은 보유 중 최고가에서 정한 비율만큼 내려오면 매도해 이미 난 수익을 보호하는 조건입니다.
트레일링 스탑을 뜻하면서 익절 비율이라고 부르지 말고, 반드시 "트레일링 스탑"이라는 정확한 용어와 쉬운 설명을 함께 쓰십시오.
손절 비율은 매수가(산 가격) 대비 정한 비율만큼 하락하면 자동으로 파는 손실 제한 조건입니다. 기준은 매수가이지 최고가가 아닙니다.
손절을 설명할 때 "최고가에서 내려오면" "고점 대비 하락하면"처럼 말하지 마십시오. 그것은 트레일링 스탑의 설명이며, 손절과 혼동하면 틀린 설명이 됩니다. 예: "손절 12%"는 매수가 대비 12% 하락 시 매도라는 뜻입니다.
# 질문 대응과 맥락 유지
사용자의 현재 질문에 먼저 직접 답하는 것이 최우선입니다. conversation_context의 직전 대화 흐름을 반드시 이어가십시오.
사용자가 특정 조건(예: 보유 기간, 익절 비율, 손절, 종목 수)에 대해 물으면 그 조건을 중심으로 답하고, 사용자가 묻지 않은 다른 개선안으로 주제를 돌리지 마십시오. advisor_result의 조언이 다른 주제라도, 사용자가 방금 물은 주제에 먼저 답한 뒤에만 보조적으로 덧붙이십시오.
parsed_strategy에 실제로 존재하는 조건만 전략에 반영된 것으로 보고 평가하십시오. 사용자가 원본 입력에서 어떤 지표(RSI·MACD·ADX·볼린저밴드 등)나 재무 조건을 말했더라도, parsed_strategy에 그 조건이 없으면 '설정되어 있다', '잡혀 있다', '반영되어 있다'고 말하지 마십시오. 원본 입력에 있는 표현을 전략에 들어간 것처럼 단정하면 사용자가 잘못된 백테스트를 신뢰하게 됩니다. 누락된 조건은 아직 반영되지 않았다고 사실대로 알리고 추가를 제안하십시오.
# 문장 작성
응답은 짧고 실용적이며, 다음 행동을 제안하는 방식으로 작성하십시오.
모든 문장은 자연스럽고 문법에 맞는 완결된 한국어여야 합니다. 비문이나 뜻이 통하지 않는 문장을 만들지 마십시오.
전략을 긍정할 때는 맨 "좋습니다."처럼 단독 감탄으로 시작하지 말고 "좋아 보이는 전략입니다"처럼 무엇이 좋은지 분명한 문장으로 시작하십시오.
사용자에게 내부 필드명인 parsed_strategy, advisor_result, rule_context, internal_analysis 같은 용어를 노출하지 마십시오. 사용자는 최종 코칭 문장만 봐야 합니다.
조언의 내용과 근거는 정확히 유지하되, 매번 똑같은 문장 구조와 도입부로 시작하지 마십시오. 같은 의미라도 첫 문장, 어휘, 문장 흐름을 그때그때 다르게 써서 기계적으로 찍어낸 듯한 반복적인 답변이 되지 않게 하십시오. 사용자 입력의 표현과 맥락에 맞춰 자연스럽게 운을 떼고, 정형화된 템플릿처럼 들리지 않게 작성하십시오.
# 다음 행동 제안
다음 행동으로는 지금 전략에 바로 추가할 수 있는 조건(손절·익절·트레일링 스탑·보유 기간·종목 수·재무 필터·기술적 신호·AI 예측 신호)이나 백테스트 실행만 제안하십시오.
다음 행동을 물을 때는 "비교 테스트를 진행해 보시겠어요?"처럼 추상적으로 묻지 말고, "익절 비율 설정을 추천드립니다"처럼 추가할 조건을 직접 제안하십시오.
사용자가 "트레일링 스탑 15%"처럼 정확한 수치를 말한 경우에만 해당 조건으로 비교 백테스트를 안내하십시오.
사용자가 "트레일링 스탑을 추가해줘"처럼 수치를 말하지 않았으면 "트레일링 스탑은 최고가에서 몇 % 내려오면 팔지 정하는 조건입니다. 몇 %로 설정할까요?"처럼 먼저 물어보십시오.
보유 기간을 개선안으로 제안할 때는 "몇 일로 설정할까요?"처럼 정확한 일수를 요구하지 말고, "보유 기간을 설정할까요?"처럼 사용자가 추가 여부를 선택하게 물어보십시오.
익절 비율을 개선안으로 제안할 때는 "몇 %로 설정할까요?"처럼 정확한 비율을 요구하지 말고, "익절 비율 설정을 추천드립니다" 또는 "익절 비율 설정을 조언드립니다"처럼 추천/조언 표현을 사용하십시오.
익절 비율 같은 개선안을 제안할 때는 "몇 %로 세팅할까요?"처럼 망설이며 되묻지 말고, "수익 실현 비율 설정을 추천드립니다"처럼 확실한 추천/조언 문장으로 끝맺으십시오.
추가 조건을 제안할 때는 반드시 "아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."라고 덧붙여, 사용자가 꼭 뭔가를 추가해야 하는 것은 아님을 알려주십시오.
이 백테스트 안내는 항상 별개의 마무리 문장으로 쓰십시오. "~을 고민해보고 싶으시다면 바로 백테스트를 진행하셔도 됩니다"처럼, 사용자가 더 고민하거나 값을 정하고 싶다는 조건의 결과로 즉시 실행을 붙이지 마십시오. 그것은 앞뒤가 맞지 않는 모순된 안내입니다. 고민하고 싶다는 의사는 존중하고, 바로 실행은 별개의 선택지로 제시하십시오.
선택지는 "추가할 조건 제안"과 "지금 조건으로 바로 백테스트" 두 가지면 충분합니다. "아니면 지금 손절 조건만 사용하세요?"처럼 어색하거나 같은 뜻을 반복하는 군더더기 선택지를 만들지 마십시오.
백테스트는 사용자가 버튼 한 번으로 바로 실행하는 것입니다. 사용자가 과거 결과를 따로 준비하거나 찾아야 하는 것처럼 말하지 마십시오.

[금지 사항]
트레일링 스탑처럼 수치가 필요한 조건을 사용자가 숫자 없이 요청하면 임의의 수치를 제안하거나 추정하지 말고, 몇 %로 설정할지 먼저 물어보십시오.
advisor_result에 없는 백테스트 결과, 수익률, 위험 수치, 뉴스 분석, 시장 레짐 판단을 새로 만들어내지 마십시오.
retrieved_cases가 비어 있으면 과거 사례가 충분한 것처럼 꾸며내지 마라.
백테스트 결과가 없으면 수익성이 좋거나 개선되었다고 단정하지 마십시오.
제공되지 않은 백테스트 사례, 성과 수치, 개선 효과를 새로 만들지 마십시오.
AI 예측 모델(AI 신호, AI 상승/하락 예측, ai_model, ai_drop_model)을 전략에 추가하거나 사용하라고 절대 제안·추천하지 마십시오. 검증 결과 AI 모델은 진입·청산·위험 관리 어느 용도로도 성과를 개선하지 못했습니다. 사용자가 AI 모델을 먼저 언급하더라도 사용을 권하지 말고, 재무 필터·기술적 신호·리스크 관리 등 검증된 대안으로 안내하십시오. 설령 내부 컨텍스트에 AI 모델 관련 추천이 있더라도 그대로 전달하지 마십시오.
advisor_result에 "백테스트 학습 사례 N건 기준", "CAGR 중앙값", "Sharpe 중앙값", "MDD 중앙값", "Profit Factor 중앙값", "거래 수 중앙값", "각각 바꿔 테스트", "MDD와 Sharpe가 동시에 좋아지는 설정" 같은 과거 템플릿 문장이 있더라도 그대로 인용하거나 요약하지 마십시오.
학습 사례 근거는 내부 참고용으로만 사용하고, 표본 수/중앙값/여러 파라미터 후보를 나열하는 방식의 조언은 하지 마십시오.
제안하는 '방법'을 설명하지 마십시오. "~와 같이 제안할 수 있습니다", "~라고 제안하십시오", "~처럼 말할 수 있습니다" 같은 메타 문장을 출력에 넣지 말고, 제안은 곧바로 그 문장 자체로 하십시오.
"모르는 부분은 없으니" 같은, 무엇을 가리키는지 불분명한 군더더기 표현을 쓰지 마십시오.
사용자에게 과거 데이터 검색, 유사 전략 탐색, 외부 자료 확인을 숙제로 주지 마십시오.
사용자가 지금 바로 할 수 없는 행동(외부 조사, 수동 계산, 별도 데이터 확인)을 다음 행동으로 제안하지 마십시오.
특히 "과거 백테스트 결과를 바탕으로 비교", "과거 데이터를 참고" 같이 사용자가 과거 데이터를 이미 가지고 있거나 다룰 줄 안다고 가정하는 제안을 하지 마십시오. 사용자는 과거 데이터가 없거나 다루는 방법을 모를 수 있습니다.
몬테카를로 시뮬레이션·부트스트랩·민감도 분석·시나리오 분석처럼 전략 조건이 아니거나 사용자가 직접 수행할 수 없는 분석 기법은 다음 행동으로 제안하지 마십시오.

[출력 형식]
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
    # 전략 수정으로 세션을 새로 만들 때, 직전까지의 코치 대화를 넘겨 받아
    # 이미 설명한 전문용어를 다시 설명하지 않도록 한다.
    conversation_context: Optional[List[Dict[str, Any]]] = None


class CoachSessionFollowUpRequest(BaseModel):
    session_id: str
    user_prompt: str


_MISSING_FIELDS = {
    "max_positions": "최대 보유 종목 수",
    "stop_loss_pct": "손절 비율",
    "take_profit_pct": "익절 비율",
    "hold_period_days": "보유 기간",
}

# 사용자의 현재 질문이 어떤 조건을 묻는지 감지해, 코치가 그 주제로 직접 답하도록 한다.
_QUESTION_TOPIC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("보유 기간", r"보유\s*기간|며칠|몇\s*일|얼마나\s*보유|보유[^.?!。]*얼마|holding"),
    ("익절 비율", r"익절|목표\s*수익|수익\s*실현|수익\s*확정|take\s*profit"),
    ("손절 비율", r"손절|stop\s*loss"),
    ("트레일링 스탑", r"트레일링|trailing|최고가\s*대비"),
    ("종목 수", r"종목\s*수|몇\s*종목|분산"),
    ("리밸런싱", r"리밸런"),
)


def _detect_question_topics(prompt: str) -> list[str]:
    """현재 사용자 입력에서 묻고 있는 조건 주제를 감지한다(순서 유지)."""
    text = prompt or ""
    topics: list[str] = []
    for label, pattern in _QUESTION_TOPIC_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            topics.append(label)
    return topics


# 질문 주제 → parsed_strategy 필드. 이미 값이 있으면 코치가 '재설정 권유' 대신 '확인'하도록 한다.
_TOPIC_SET_FIELD: dict[str, str] = {
    "보유 기간": "hold_period_days",
    "익절 비율": "take_profit_pct",
    "손절 비율": "stop_loss_pct",
    "트레일링 스탑": "trailing_stop_pct",
}


def _already_set_topics(topics: list[str], ps: dict) -> list[str]:
    """질문 주제 중 전략에 이미 설정된 것(값 존재)을 반환한다."""
    return [
        topic
        for topic in topics
        if topic in _TOPIC_SET_FIELD and ps.get(_TOPIC_SET_FIELD[topic]) is not None
    ]


_LARGE_CAP_UNIVERSES = {"KOSPI200", "SP500", "NASDAQ100"}
_COACH_STRATEGY_FIELDS = (
    "universe",
    "fundamental_filters",
    "entry_signals",
    "ranking_metric",
    "ranking_lookback_days",
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


# 사용자가 프롬프트에서 명시한 지표/재무 조건이 parsed_strategy에 반영됐는지 검사하기 위한 표.
# (표시 라벨, 프롬프트 정규식, parsed_strategy에서 존재 여부를 판정하는 술어)
def _has_signal_indicator(ps: dict, indicator: str) -> bool:
    signals = (ps.get("entry_signals") or []) + (ps.get("exit_signals") or [])
    return any(isinstance(s, dict) and s.get("indicator") == indicator for s in signals)


def _has_fundamental(ps: dict, metric: str) -> bool:
    return any(
        isinstance(f, dict) and f.get("metric") == metric
        for f in (ps.get("fundamental_filters") or [])
    )


_UNPARSED_MENTION_SPECS: tuple[tuple[str, str, Any], ...] = (
    ("RSI", r"rsi", lambda ps: _has_signal_indicator(ps, "rsi")),
    ("MACD", r"macd", lambda ps: _has_signal_indicator(ps, "macd")),
    ("ADX", r"adx", lambda ps: _has_signal_indicator(ps, "adx")),
    ("볼린저밴드", r"볼린저", lambda ps: _has_signal_indicator(ps, "bollinger_bands")),
    ("스토캐스틱", r"스토캐스틱|stochastic", lambda ps: _has_signal_indicator(ps, "stochastic")),
    ("CCI", r"\bcci\b", lambda ps: _has_signal_indicator(ps, "cci")),
    ("PER", r"per", lambda ps: _has_fundamental(ps, "per")),
    ("PBR", r"pbr", lambda ps: _has_fundamental(ps, "pbr")),
    ("ROE", r"roe", lambda ps: _has_fundamental(ps, "roe_or_gpa")),
    ("부채비율", r"부채비율", lambda ps: _has_fundamental(ps, "debt_ratio")),
)


def _unparsed_mentions(user_prompt: str, parsed_strategy: dict) -> list[str]:
    """사용자가 말했지만 parsed_strategy에 반영되지 않은 지표/재무 조건의 라벨을 반환한다.

    코치가 누락된 조건을 '설정되어 있다/잘 잡혀 있다'고 거짓 확언(confabulation)하는 것을 막기 위해,
    프롬프트에 등장했으나 전략 구조에 없는 항목을 명시적으로 경고 컨텍스트로 넘긴다.
    """
    text = (user_prompt or "").lower()
    ps = parsed_strategy or {}
    dropped: list[str] = []
    for label, pattern, present in _UNPARSED_MENTION_SPECS:
        if re.search(pattern, text, re.IGNORECASE) and not present(ps):
            dropped.append(label)
    return dropped


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


def _is_legacy_experiment_learning_copy(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return False
    return (
        ("백테스트 학습 사례" in normalized and "중앙값" in normalized)
        or ("CAGR 중앙값" in normalized and "Sharpe 중앙값" in normalized and "MDD 중앙값" in normalized)
        or ("Profit Factor 중앙값" in normalized and "거래 수 중앙값" in normalized)
        or ("각각 바꿔 테스트" in normalized and "MDD와 Sharpe" in normalized)
    )


def _compact_learning_evidence(learning: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(learning, dict):
        return {}
    compact = {
        "available": bool(int(learning.get("similar_strategy_count") or 0) > 0),
        "confidence": learning.get("confidence"),
        "has_negative_samples": bool(int(learning.get("negative_sample_count") or 0) > 0),
    }
    warnings = [
        str(item)
        for item in (learning.get("warnings") or [])
        if str(item).strip() and not _is_legacy_experiment_learning_copy(str(item))
    ][:2]
    if warnings:
        compact["warnings"] = warnings
    return {key: value for key, value in compact.items() if value not in (None, [], {})}


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
            and not _is_legacy_experiment_learning_copy(str(section.get("body") or ""))
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
            and not _is_legacy_experiment_learning_copy(str(item.get("body") or ""))
        ]

    learning = _compact_learning_evidence(advisor_result.get("strategy_experiment_learning"))
    if learning:
        compact["strategy_experiment_learning"] = learning

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

    # 정책: AI 예측 모델은 추천하지 않으므로 ai_model_recommendation을 코치 LLM에
    # 전달하지 않는다. (검증 결과 알파 없음 — project_ai_auxiliary_usage 참고)
    # 컨텍스트에 넣지 않아 코치가 AI 모델 사용을 제안할 근거 자체를 갖지 못하게 한다.

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


@dataclass(frozen=True)
class _GlossaryTerm:
    """코치가 쓰는 전문용어 1개 — 대화당 최초 1회만 뜻을 풀이하고 이후에는 용어만 쓴다."""

    key: str
    label: str
    explanation: str  # 괄호 안에 들어갈 쉬운 풀이
    keywords: str  # 풀이가 이미 있는지 감지하는 핵심어(정규식 alternation). 단순 언급에는 안 걸리도록 풀이에만 나오는 표현을 쓴다.
    force_explain: bool = False  # True면 풀이가 빠졌을 때 괄호 풀이를 강제로 주입한다.
    special_injection: bool = False  # 트레일링 스탑처럼 개별 주입 로직을 쓰는 항목(일반 루프에서 제외).

    @property
    def context_pattern(self) -> str:
        """이전 대화(assistant 메시지)에서 '이미 설명함'을 감지하는 정규식."""
        lab = re.escape(self.label)
        return rf"{lab}\(|{lab}(?:은|는|이|가)?[^.?!。]*?(?:{self.keywords})"

    @property
    def inline_pattern(self) -> str:
        """현재 메시지에 이미 풀이가 들어 있는지 감지하는 정규식."""
        lab = re.escape(self.label)
        return rf"{lab}[^.?!。]*?(?:{self.keywords})"


# 코치가 쓰는 주식 전문용어 사전.
# - 모든 항목: 대화당 최초 1회만 설명하고 이후에는 용어만 쓰도록 감지/프롬프트/반복 풀이 제거가 적용된다.
# - force_explain=True 항목만 풀이가 빠졌을 때 괄호 풀이를 강제 주입한다(코치가 직접 추가를 권하는 청산 조건들).
#   나머지 지표/재무/성과 용어는 LLM이 최초 1회 자연스럽게 풀이하도록 두어 응답이 길어지는 것을 막는다.
# 흔한 일상어(매수/매도/주식/종목/수익/거래량/백테스트)는 초보자도 아는 표현이라 일부러 제외한다.
_COACH_GLOSSARY: tuple[_GlossaryTerm, ...] = (
    # ── 청산/리스크 조건 (코치가 직접 추가를 권하므로 풀이 강제) ──
    _GlossaryTerm(
        key="take_profit",
        label="익절 비율",
        explanation="매수가 대비 정한 수익률에 도달하면 자동으로 파는 고정 목표 수익 조건",
        keywords=r"매수가|목표 수익|정한 수익률|도달하면|고정",
        force_explain=True,
    ),
    _GlossaryTerm(
        key="trailing_stop",
        label="트레일링 스탑",
        explanation="주가가 오른 뒤 최고가에서 정한 비율만큼 내려오면 자동으로 파는 조건",
        keywords=r"최고가|고점|일정 비율|하락|내려오면|팔아",
        force_explain=True,
        special_injection=True,
    ),
    _GlossaryTerm(
        key="stop_loss",
        label="손절 비율",
        explanation="매수가 대비 정한 비율만큼 손실이 나면 자동으로 파는 손실 제한 조건",
        keywords=r"매수가|손실|내려가면|떨어지면|손실 제한",
        force_explain=True,
    ),
    # ── 성과/위험 지표 ──
    _GlossaryTerm(
        key="max_drawdown",
        label="최대 낙폭",
        explanation="운용 중 자산이 고점 대비 가장 크게 하락한 비율",
        keywords=r"고점 대비|가장 크게 하락|최대 하락폭",
    ),
    _GlossaryTerm(
        key="sharpe",
        label="샤프 지수",
        explanation="감수한 가격 출렁임(위험) 대비 얼마나 효율적으로 수익을 냈는지 보여주는 지표",
        keywords=r"위험 대비|효율적으로|출렁임",
    ),
    _GlossaryTerm(
        key="cagr",
        label="CAGR",
        explanation="연평균 복리 수익률, 매년 일정하게 복리로 불었다고 가정한 평균 수익률",
        keywords=r"연평균 복리|복리로 불",
    ),
    _GlossaryTerm(
        key="volatility",
        label="변동성",
        explanation="가격이 위아래로 출렁이는 정도로, 클수록 위험이 큼",
        keywords=r"위아래로 출렁|출렁이는 정도",
    ),
    _GlossaryTerm(
        key="win_rate",
        label="승률",
        explanation="전체 매매 중 이익으로 끝난 매매의 비율",
        keywords=r"이익으로 끝난|이긴 매매의 비율",
    ),
    _GlossaryTerm(
        key="profit_factor",
        label="손익비",
        explanation="이긴 매매의 평균 수익을 진 매매의 평균 손실로 나눈 값",
        keywords=r"평균 손실로 나눈|이긴 매매의 평균",
    ),
    # ── 기술적 지표 ──
    _GlossaryTerm(
        key="rsi",
        label="RSI",
        explanation="상대강도지수, 최근 상승·하락 폭을 비교해 0~100으로 과열 여부를 보는 지표",
        keywords=r"상대강도",
    ),
    _GlossaryTerm(
        key="macd",
        label="MACD",
        explanation="단기·장기 이동평균의 차이로 추세 전환을 포착하는 지표",
        keywords=r"이동평균의 차이|추세 전환",
    ),
    _GlossaryTerm(
        key="bollinger",
        label="볼린저밴드",
        explanation="평균선 위아래로 표준편차 띠를 둘러 가격이 비싼지 싼지 보는 지표",
        keywords=r"표준편차",
    ),
    _GlossaryTerm(
        key="golden_cross",
        label="골든크로스",
        explanation="단기 이동평균선이 장기 이동평균선을 아래에서 위로 뚫는 매수 신호",
        keywords=r"아래에서 위로",
    ),
    _GlossaryTerm(
        key="dead_cross",
        label="데드크로스",
        explanation="단기 이동평균선이 장기 이동평균선을 위에서 아래로 뚫는 매도 신호",
        keywords=r"위에서 아래로",
    ),
    _GlossaryTerm(
        key="stochastic",
        label="스토캐스틱",
        explanation="최근 가격 범위에서 현재가가 어디쯤인지 0~100으로 나타내는 지표",
        keywords=r"가격 범위에서 현재가",
    ),
    _GlossaryTerm(
        key="overbought",
        label="과매수",
        explanation="단기간 너무 많이 올라 가격이 비싸졌다고 보는 상태",
        keywords=r"너무 많이 올라",
    ),
    _GlossaryTerm(
        key="oversold",
        label="과매도",
        explanation="단기간 너무 많이 내려 가격이 싸졌다고 보는 상태",
        keywords=r"너무 많이 내려",
    ),
    _GlossaryTerm(
        key="trading_value",
        label="거래대금",
        explanation="일정 기간 거래된 금액의 합으로, 클수록 사고팔기 쉬움",
        keywords=r"거래된 금액",
    ),
    # ── 재무 지표 ──
    _GlossaryTerm(
        key="per",
        label="PER",
        explanation="주가수익비율, 주가가 한 해 순이익의 몇 배인지 나타내는 값",
        keywords=r"주가수익비율",
    ),
    _GlossaryTerm(
        key="pbr",
        label="PBR",
        explanation="주가순자산비율, 주가가 회사 순자산의 몇 배인지 나타내는 값",
        keywords=r"주가순자산비율",
    ),
    _GlossaryTerm(
        key="roe",
        label="ROE",
        explanation="자기자본이익률, 자기 돈으로 한 해 얼마나 이익을 냈는지 비율",
        keywords=r"자기자본이익률",
    ),
    _GlossaryTerm(
        key="debt_ratio",
        label="부채비율",
        explanation="자기자본 대비 빚이 얼마나 많은지 나타내는 비율",
        keywords=r"자기자본 대비 빚",
    ),
    _GlossaryTerm(
        key="market_cap",
        label="시가총액",
        explanation="주가에 발행 주식 수를 곱한 회사 전체의 시장 가치",
        keywords=r"발행 주식 수|시장 가치",
    ),
    _GlossaryTerm(
        key="dividend_yield",
        label="배당수익률",
        explanation="주가 대비 한 해 받는 배당금의 비율",
        keywords=r"받는 배당금|배당금의 비율",
    ),
    # ── 전략/백테스트 개념 ──
    _GlossaryTerm(
        key="rebalancing",
        label="리밸런싱",
        explanation="정해진 주기마다 보유 종목과 비중을 다시 조정하는 것",
        keywords=r"주기마다|비중을 다시",
    ),
    _GlossaryTerm(
        key="slippage",
        label="슬리피지",
        explanation="주문 가격과 실제 체결 가격의 차이",
        keywords=r"체결 가격",
    ),
    _GlossaryTerm(
        key="overfitting",
        label="과최적화",
        explanation="과거 데이터에만 지나치게 맞춰 실전에서는 잘 안 통하게 되는 것",
        keywords=r"지나치게 맞춰|안 통하게",
    ),
    _GlossaryTerm(
        key="walk_forward",
        label="워크포워드",
        explanation="기간을 나눠 앞 구간으로 만들고 뒤 구간으로 검증하기를 반복하는 검증 방법",
        keywords=r"기간을 나눠|뒤 구간으로 검증",
    ),
    _GlossaryTerm(
        key="diversification",
        label="분산투자",
        explanation="한 종목에 몰지 않고 여러 종목에 나눠 담아 위험을 줄이는 것",
        keywords=r"나눠 담아|여러 종목에",
    ),
)


def _explained_terms_from_context(context: List[Dict[str, Any]] | None) -> set[str]:
    explained: set[str] = set()
    for item in context or []:
        if not isinstance(item, dict) or item.get("role") != "assistant":
            continue
        content = str(item.get("content") or item.get("message") or "")
        for term in _COACH_GLOSSARY:
            if re.search(term.context_pattern, content):
                explained.add(term.key)
    return explained


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


# 기술적 지표(진입 신호) 후보. RSI·MACD·이동평균처럼 사용자가 "몇으로 설정할지" 물을 때는
# 손절·트레일링 스탑과 달리 임의 수치를 피하지 말고, 바로 쓸 수 있는 구체적 예시를 제시해야 한다.
_INDICATOR_SETUP_TERMS = re.compile(
    r"rsi|macd|이동\s*평균|이평|골든\s*크로스|데드\s*크로스|크로스오버|ma\s*크로스|"
    r"볼린저|스토캐스틱|stochastic|cci|adx|돌파|breakout|모멘텀",
    re.IGNORECASE,
)
_INDICATOR_SETUP_INTENT = re.compile(
    r"몇|어떻게|얼마|어떤|어느|추천|뭐로|뭐가|좋을까|정할까|설정\s*할까|어떤\s*값",
    re.IGNORECASE,
)


def _asks_indicator_setup(prompt: str) -> bool:
    """사용자가 기술적 지표 진입 조건을 어떻게/몇으로 설정할지 묻는지 감지한다."""
    text = prompt or ""
    if not _INDICATOR_SETUP_TERMS.search(text):
        return False
    return bool(_INDICATOR_SETUP_INTENT.search(text))


def _build_user_message(req: CoachRequest) -> str:
    parts: list[str] = [f'원본 사용자 입력(출력 금지): "{req.user_prompt}"']
    explained_terms = _explained_terms_from_context(req.conversation_context)
    question_topics = _detect_question_topics(req.user_prompt)
    if question_topics:
        parts.append("\n[현재 질문 우선 — 최우선 반영]")
        parts.append(
            f"사용자는 지금 '{', '.join(question_topics)}'을(를) 다루고 있습니다. "
            "이 주제를 중심으로 사용자의 현재 입력에 먼저 직접 답하십시오. "
            "사용자가 다루지 않은 다른 조건으로 주제를 바꾸지 마십시오. "
            "직전 대화(conversation_context)의 흐름을 이어서 답하십시오."
        )
        already_set = _already_set_topics(question_topics, req.parsed_strategy or {})
        if already_set:
            parts.append(
                f"단, '{', '.join(already_set)}'은(는) 사용자가 방금 전략에 설정해 이미 반영되어 있습니다. "
                "다시 설정/추가하라고 권하거나 '설정할까요?'라고 되묻지 말고, 설정된 값을 짧게 확인한 뒤"
                "(예: '한 달(30일) 보유로 설정하셨군요') 전략 평가와 다음 단계로 넘어가십시오."
            )
    parts.append("\n[코칭 행동 제약]")
    parts.append(
        "사용자에게 과거 데이터 검색, 유사 전략 탐색, 외부 자료 확인을 숙제로 주지 마십시오. "
        "다음 행동은 '비교 테스트를 진행해 보시겠어요?'처럼 추상적으로 묻지 말고, "
        "'익절 비율 설정을 추천드립니다'처럼 추가할 조건을 직접 제안하십시오. "
        "트레일링 스탑은 모든 전략의 기본 개선안이 아니므로 advisor_result의 핵심 조언이 아닌 경우 우선 제안하지 마십시오."
    )
    if explained_terms:
        labels = [term.label for term in _COACH_GLOSSARY if term.key in explained_terms]
        parts.append("\n[전문용어 설명 반복 금지]")
        parts.append(f"이미 설명한 용어: {', '.join(labels)}. 이 용어는 다시 뜻을 풀이하지 말고 용어만 사용하십시오.")
    if _needs_trailing_stop_percentage(req.user_prompt):
        parts.append("\n[필수 확인 질문]")
        parts.append(
            "사용자가 트레일링 스탑 수치를 말하지 않았습니다. "
            "advisor_result에 15% 같은 후보가 있어도 임의 수치를 제안하지 말고, 몇 %로 설정할지 먼저 물어보십시오."
        )

    if _asks_indicator_setup(req.user_prompt):
        parts.append("\n[지표 조건 설정 — 구체적 예시 필수]")
        parts.append(
            "사용자가 RSI·MACD·이동평균 같은 기술적 지표 진입 조건을 어떻게/몇으로 설정할지 묻고 있습니다. "
            "'조건을 먼저 확정해 주세요'처럼 결정을 사용자에게 떠넘기지 말고, "
            "바로 전략에 추가할 수 있는 구체적인 예시를 1~2개 제시하십시오. "
            "각 예시에는 정확한 기준값과 매수/매도 방향, 그리고 한 줄짜리 이유를 함께 쓰십시오. "
            "(예: 'RSI가 30 이하로 떨어졌을 때 매수 — 과매도 구간에서 반등을 노리는 진입입니다', "
            "'단기 이동평균이 장기 이동평균을 위로 뚫는 골든크로스에서 매수'). "
            "수치는 일반적으로 많이 쓰는 값을 기본 예시로 제안하되, 사용자가 원하면 조정할 수 있다고 알려주십시오. "
            "이는 임의 수치를 피해야 하는 손절·트레일링 스탑 같은 리스크 조건과 다릅니다."
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
            if has_exit_signal:
                parts.append(
                    "명확한 매도 신호가 이미 있습니다. suggested_experiments에 트레일링 스탑이 있더라도 "
                    "advisor_result의 1순위 advice가 아니라면 트레일링 스탑을 최종 다음 행동으로 고르지 마십시오."
                )

        # 사용자가 말했지만 전략에 반영되지 않은 지표 — '설정돼 있다'고 거짓 확언하지 않도록 경고.
        dropped = _unparsed_mentions(req.user_prompt, ps)
        if dropped:
            parts.append("\n[미반영 조건 — 경고]")
            parts.append(
                f"사용자는 '{', '.join(dropped)}'을(를) 언급했지만 현재 전략에는 반영되지 않았습니다. "
                "이 조건들이 '설정되어 있다', '잘 잡혀 있다', '반영되어 있다', '명확하게 잡혀 있다'고 절대 말하지 마십시오. "
                "아직 전략에 들어가지 않았다고 사실대로 알리고, 추가할 수 있는 구체적 설정 예시를 제시하거나 추가할지 물어보십시오. "
                "전략을 평가할 때는 실제로 반영된 조건만 근거로 삼으십시오."
            )

        # Missing field analysis
        missing = _detect_missing(ps)
        if missing:
            parts.append(f"\n[누락 필드 분석]")
            parts.append(f"미정의 항목: {', '.join(missing)}")
            if "익절 비율" in missing:
                parts.append(
                    "익절 비율은 개선안으로만 제안하십시오. "
                    "단, 트레일링 스탑과 혼동하지 마십시오. "
                    "익절 비율은 매수가 대비 정한 수익률에 도달하면 매도하는 고정 목표 수익 조건이고, "
                    "트레일링 스탑은 보유 중 최고가에서 정한 비율만큼 내려오면 매도하는 조건입니다. "
                    "'몇 %로 설정할까요?'처럼 정확한 비율을 요구하지 말고, "
                    "'익절 비율 설정을 추천드립니다'처럼 추천/조언 표현을 사용하십시오."
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
    try:
        news_context = build_news_context_from_strategy(req.parsed_strategy)
    except Exception:
        logger.exception("coach advisor news context skipped | request_id=%s", request_id)
        news_context = []
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
        try:
            news_context = build_news_context_from_strategy(effective_req.parsed_strategy)
            news_insight = build_coach_news_insight(news_context)
        except Exception:
            logger.exception(
                "coach news context skipped | request_id=%s elapsed_ms=%.2f",
                request_id,
                (time.perf_counter() - news_started) * 1000,
            )
            news_context = []
            news_insight = None
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


def _strip_repeated_term_explanations(message: str, explained_terms: set[str]) -> str:
    for term in _COACH_GLOSSARY:
        if term.key in explained_terms:
            message = re.sub(rf"{re.escape(term.label)}\([^)]*\)", term.label, message)
    if "trailing_stop" in explained_terms:
        message = re.sub(
            r"\s*예를 들면\s*'트레일링 스탑[^']*'[^.?!。]*(?:[.?!。]|$)",
            "",
            message,
        )
    return message.strip()


def _ensure_explained_terms(
    message: str,
    *,
    include_trailing_example: bool = True,
    explained_terms: set[str] | None = None,
) -> str:
    explained_terms = explained_terms or set()
    message = _strip_repeated_term_explanations(message, explained_terms)
    # force_explain 용어만 풀이가 빠졌을 때 괄호로 한 번 덧붙인다 (트레일링 스탑은 예시 문장이 있어 개별 처리).
    # 나머지 용어는 LLM이 자연스럽게 풀이하도록 두어 응답 길이(300자)를 아낀다.
    for term in _COACH_GLOSSARY:
        if not term.force_explain or term.special_injection or term.key in explained_terms:
            continue
        if term.label in message and not re.search(term.inline_pattern, message):
            message = message.replace(term.label, f"{term.label}({term.explanation})", 1)
    if "트레일링 스탑" not in message:
        return message
    if "trailing_stop" in explained_terms:
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


# 익절 비율과 동의어(수익 실현 비율/기준, 목표 수익) — 망설이는 질문을 확신형 추천으로 바꿀 때 함께 인식한다.
_TAKE_PROFIT_TERM = r"(?:익절 비율|수익\s*실현\s*비율|수익\s*실현\s*기준|목표\s*수익률|목표\s*수익)"


def _prefer_take_profit_recommendation_wording(message: str) -> str:
    def replace(match: re.Match[str]) -> str:
        target = re.sub(r"\s+", " ", match.group("target")).strip()
        target = re.sub(r"(?:을|를)?\s*몇\s*%\s*로?$", "", target).strip()  # 막연한 '몇 %' 제거
        target = re.sub(r"(?:을|를)\s*(?=\d)", " ", target).strip()         # '비율을 30%' → '비율 30%'
        target = re.sub(r"\s*로$", "", target).strip()
        target = re.sub(r"(?:을|를)$", "", target).strip()
        return f"{target} 설정을 추천드립니다."

    message = re.sub(
        rf"(?P<target>{_TAKE_PROFIT_TERM}(?:\([^)]*\))?(?:을|를)?"
        r"(?:\s*(?:\d+(?:\.\d+)?|몇)\s*%로)?)\s*(?:설정|세팅)"
        r"(?:해 볼까요|할까요|하시겠어요|해 보시겠어요|할지요)\s*[?？]",
        replace,
        message,
    )
    # '… 설정하는 것이 좋을까요?'처럼 망설이는 질문형 → 확실한 조언형('… 좋습니다.')으로.
    message = re.sub(
        rf"({_TAKE_PROFIT_TERM}(?:\([^)]*\))?[^.?!。]*?(?:설정|세팅)[^.?!。]*?것이\s*)"
        r"(?:좋을까요|좋겠습니까|좋겠죠|좋을지요|좋겠어요|어떨까요)\s*[?？]",
        r"\1좋습니다.",
        message,
    )
    return message


def _collapse_nested_term_explanation(message: str) -> str:
    """'수익 실현 비율(익절 비율(설명))'처럼 용어 풀이를 주입하다 생긴 이중 괄호를
    '수익 실현 비율(설명)'으로 평탄화한다."""
    labels = "|".join(re.escape(term.label) for term in _COACH_GLOSSARY)
    pattern = re.compile(rf"\(\s*(?:{labels})\s*\(([^()]+)\)\s*\)")
    prev = None
    while prev != message:
        prev = message
        message = pattern.sub(r"(\1)", message)
    return message


def _fix_awkward_affirmation_opening(message: str) -> str:
    """첫 문장이 맨 '좋습니다.'로 시작하면 어색하므로 자연스러운 전략 평가 문장으로 바꾼다."""
    return re.sub(r"^\s*좋습니다\s*[.!]\s*", "좋아 보이는 전략입니다. ", message)


def _remove_meaningless_filler(message: str) -> str:
    """'모르는 부분은 없으니 그대로 사용하셔도 됩니다.'처럼 뜻이 통하지 않는 군더더기 문장을 제거한다."""
    message = re.sub(r"\s*모르는\s*부분[은이]?\s*없[^.?!。]*?[.?!。]", "", message)
    return re.sub(r"\s{2,}", " ", message).strip()


# 이미 설정된 조건을 정의까지 풀어 되풀이하는 확인 문장을 '손절 10%로 설정하셨군요.'로 줄인다.
# 다음 형태를 모두 포괄한다:
#   - "손절 10%는 매수가 대비 10% 하락 시 자동으로 파는 조건으로 설정해 계신군요."
#   - "손절 비율(매수가 대비 …) 10%로 설정하셨군요."  ← 괄호 풀이까지 흡수
# 끝의 확인 동사(설정하셨/설정해 계신/설정하신 + 군요/습니다…)로만 발동하고,
# 사이 구간은 다른 필드(손절/익절/트레일링)를 넘지 않게 막아 다중 절 문장을 오삭제하지 않는다.
_SET_CONDITION_RESTATE = re.compile(
    r"(?P<field>손절|익절|트레일링\s*스탑)(?:\s*비율)?\s*"
    r"(?:\([^)]*\))?\s*"                                  # 선택적 괄호 풀이
    r"(?P<num>\d+(?:\.\d+)?)\s*%\s*"
    r"(?:[은는이가을를로]\s*)?"                            # 조사
    r"(?:(?!손절|익절|트레일링)[^.?!。]){0,80}?"           # 정의 등 짧은 연결구(다른 필드 미포함)
    r"설정(?:하셨|해\s*두셨|해\s*계[시신]|하신)[^.?!。]{0,4}?(?:군요|습니다|네요|어요)\s*[.。]"
)


def _simplify_set_condition_restatement(message: str) -> str:
    """이미 설정된 조건을 정의까지 풀어 되풀이하는 문장을 '손절 10%로 설정하셨군요.'처럼 짧게 줄인다.
    괄호 풀이가 붙어 있어도 함께 떼어낸다. 사용자는 자신이 설정한 값의 뜻을 이미 안다."""
    def repl(match: re.Match[str]) -> str:
        field = re.sub(r"\s+", " ", match.group("field")).strip()
        return f"{field} {match.group('num')}%로 설정하셨군요."

    return _SET_CONDITION_RESTATE.sub(repl, message)


# "이는 매수가 대비 10% 하락 시 자동으로 매도하는 손실 제한 조건입니다."처럼,
# 앞 문장에서 이미 확인/언급한 조건의 '정의'를 지시어로 다시 풀어 쓰는 군더더기 문장을 제거한다.
# '이는 좋은 조건입니다'처럼 정의 단서가 없는 평가 문장은 건드리지 않는다.
_REDUNDANT_DEFINITION_FOLLOWUP = re.compile(
    r"(?:(?<=[.?!。])|^)\s*"
    r"(?:이는|이것은|이 설정은|이 조건은|이 값은|즉,?)\s*"
    r"[^.?!。]*?(?:매수가|최고가|하락\s*시|상승\s*시|도달하면|손실\s*제한|목표\s*수익|자동으로\s*(?:매도|파))"
    r"[^.?!。]*?(?:조건입니다|조건이에요|뜻입니다|의미입니다|말합니다)\s*[.。]"
)


def _remove_redundant_definition_followup(message: str) -> str:
    """앞 문장과 같은 조건의 정의를 지시어로 다시 풀어 쓰는 중복 문장을 제거한다."""
    message = _REDUNDANT_DEFINITION_FOLLOWUP.sub("", message)
    message = re.sub(r"\s{2,}", " ", message)
    message = re.sub(r"\s+([.?!。])", r"\1", message)
    return message.strip()


def _remove_meta_suggestion_sentence(message: str) -> str:
    """'…와 같이/처럼/라고 제안할 수 있습니다.'처럼 제안하는 '방법'을 설명하는 메타 문장
    (프롬프트의 예시 문구를 그대로 복창한 비문)을 통째로 제거한다. 제안은 곧바로 본문으로 해야 한다."""
    message = re.sub(
        r"(?:(?<=[.?!。])|^)\s*[^.?!。]*?(?:와\s*같이|처럼|라고)\s*제안(?:할\s*수\s*있습니다|하실\s*수\s*있습니다|드릴\s*수\s*있습니다)[.。]?",
        "",
        message,
    )
    message = re.sub(r"\s{2,}", " ", message)
    message = re.sub(r"\s+([.?!。])", r"\1", message)
    return message.strip()


# 전략 빌더에 바로 추가할 수 있는 조건이 아니라, 사용자가 직접 수행할 수 없는 분석 기법.
# 코치가 '다음 행동'으로 제안하면 실질적 도움이 안 되므로 해당 제안 문장을 통째로 제거한다.
_UNSUPPORTED_TECHNIQUE = (
    r"몬테\s*카를로|몬떼\s*카를로|monte\s*carlo|부트\s*스트랩|bootstrap|민감도\s*분석|시나리오\s*분석"
)


def _remove_unsupported_technique_suggestion(message: str) -> str:
    """몬테카를로 시뮬레이션 등 전략 조건이 아닌 분석 기법을 권하는 문장을 제거한다.
    그 문장이 유일한 다음 행동이었다면 백테스트 안내로 대체해 응답이 비지 않게 한다."""
    cleaned = re.sub(
        rf"(?:(?<=[.?!。])|^)\s*[^.?!。]*?(?:{_UNSUPPORTED_TECHNIQUE})[^.?!。]*?[.?!。？]",
        "",
        message,
    )
    if cleaned == message:
        return message
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.?!。])", r"\1", cleaned).strip()
    if cleaned and not _already_offers_run_as_is(cleaned):
        cleaned = f"{cleaned.rstrip()} 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    return cleaned


def _remove_redundant_keep_condition_question(message: str) -> str:
    """'아니면 지금 손절 조건만 사용하세요?'처럼 어색하고 불필요한 중복 선택지를 제거한다.
    '바로 백테스트를 진행하셔도 됩니다' 안내가 이미 '지금 조건 유지'와 같은 의미를 담는다."""
    message = re.sub(
        r"\s*아니면\s*지금[^.?!。]*?(?:만|그대로)[^.?!。]*?(?:사용|유지)"
        r"(?:하세요|하시겠어요|하실래요|할까요|해\s*주세요)\s*[?？]",
        "",
        message,
    )
    return re.sub(r"\s{2,}", " ", message).strip()


# 프롬프트의 내부 라벨/지시문(직접 노출 금지로 표시된 컨텍스트, 필드명, '내부 참고용으로만
# 사용하라'는 식의 메타 지시)을 모델이 그대로 따라 써서 사용자에게 새어 나온 문장을 제거한다.
# 이런 문장은 어떤 경우에도 사용자 응답에 등장해서는 안 된다.
_INTERNAL_LEAK_MARKERS = (
    r"내부\s*참고용|참고용으로만|직접\s*노출|노출\s*금지|출력\s*금지|내부\s*컨텍스트|내부\s*지시문?|"
    r"parsed_strategy|advisor_result|news_agent_insight|legacy_advisor_insight|"
    r"conversation_context|strategy_memory_context"
)


def _strip_internal_context_leak(message: str) -> str:
    """내부 컨텍스트 라벨/지시문이 새어 나온 문장을 통째로 제거한다.
    제거 후 남은 본문이 비면 원본을 유지해 응답이 통째로 비는 것을 막는다."""
    # 1) 마커를 포함하는 완결 문장(종결부호까지) 제거
    cleaned = re.sub(
        rf"(?:(?<=[.?!。])|^)\s*[^.?!。]*?(?:{_INTERNAL_LEAK_MARKERS})[^.?!。]*?[.?!。]",
        "",
        message,
    )
    # 2) 종결부호 없이 끝에 붙은 누출 조각 제거
    cleaned = re.sub(
        rf"(?:(?<=[.?!。])|^)\s*[^.?!。]*?(?:{_INTERNAL_LEAK_MARKERS})[^.?!。]*$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.?!。])", r"\1", cleaned).strip()
    # 3) 누출 문장 제거 후 앞에 남는 매달린 접속어 정리(예: "판단하면 …")
    cleaned = re.sub(r"^(?:판단하면|보면|라고\s*보면|그러면|따라서)\s*,?\s*", "", cleaned).strip()
    return cleaned or message.strip()


def _block_legacy_experiment_learning_copy(message: str) -> str:
    if not _is_legacy_experiment_learning_copy(message):
        return message
    return (
        "유사 사례 지표를 그대로 나열하는 조언은 생략하겠습니다. "
        "현재 전략은 먼저 같은 기간과 비용 조건으로 백테스트하고, 이후 변경은 한 번에 하나씩만 비교하세요."
    )


_PAST_BACKTEST_REF = r"과거\s*(?:백테스트(?:\s*결과)?|데이터)[^.?!。]*?(?:바탕|기반|참고|비교)"


def _strip_past_backtest_comparison(message: str) -> str:
    """'과거 백테스트 결과/데이터를 바탕으로 비교'하라는 식의 조언을 제거한다.
    사용자가 과거 데이터를 갖고 있지 않거나 다루는 방법을 모를 수 있으므로 숙제로 주지 않는다.
    앱 안에서 바로 실행하는 '백테스트 진행/실행'(과거 언급 없음) 안내는 건드리지 않는다."""
    # 1) 'A하거나, 과거 …비교해 보는 것이 좋겠습니다' → 'A하는 것이 좋겠습니다'
    message = re.sub(
        rf"하거나,?\s*{_PAST_BACKTEST_REF}[^.?!。]*?(?=(?:는|은)\s*(?:것|게|편))",
        "하",
        message,
    )
    # 2) ', 과거 …비교' / '또는 과거 …참고' 같은 보조절을 문장 끝까지 제거
    message = re.sub(rf"(?:,|\s또는|\s혹은)\s*{_PAST_BACKTEST_REF}[^.?!。]*?(?=[.?!。]|$)", "", message)
    # 3) 과거 데이터 비교만 권하는 독립 문장 통째 제거
    message = re.sub(rf"(?:(?<=[.?!。])|^)\s*{_PAST_BACKTEST_REF}[^.?!。]*?[.?!。]", "", message)
    # 정리: 중복 공백과 구두점 앞 공백 제거
    message = re.sub(r"\s{2,}", " ", message)
    message = re.sub(r"\s+([.?!。])", r"\1", message)
    return message.strip()


def _already_offers_run_as_is(message: str) -> bool:
    """'지금/현재/기존 조건 그대로 바로 (백테스트/실험/돌려/진행/실행)' 류 제안이
    이미 있는지 — 있으면 같은 뜻의 안내를 중복으로 덧붙이지 않는다."""
    if "백테스트" in message and re.search(r"바로|진행|실행|할 수", message):
        return True
    as_is_cue = re.search(r"(지금|현재|기존)\s*조건|그대로", message)
    run_cue = re.search(r"바로[^.!?。]*?(백테스트|실험|돌려|진행|실행)", message)
    return bool(as_is_cue and run_cue)


def _fix_contradictory_backtest_option(message: str) -> str:
    """'~고민/결정하고 싶으시다면, 지금 조건으로 바로 백테스트' 처럼 숙고하고 싶다는
    조건의 결과로 즉시 실행을 붙인 모순된 문장을 바로잡는다.
    숙고는 그대로 존중하고, 백테스트는 별개의 선택지('아니면 …')로 분리한다."""
    backtest_clause = r"지금 조건으로 바로 백테스트를 진행하셔도 됩니다"
    ending = r"(?:으시다면|으시면|다면|으면)"
    message = re.sub(
        rf"보고\s*싶{ending}\s*,?\s*(?={backtest_clause})",
        "보셔도 됩니다. 아니면 ",
        message,
    )
    message = re.sub(
        rf"하고\s*싶{ending}\s*,?\s*(?={backtest_clause})",
        "하셔도 됩니다. 아니면 ",
        message,
    )
    return message


def _ensure_backtest_option(message: str) -> str:
    if _already_offers_run_as_is(message):
        return message
    if not re.search(r"(설정|추가|반영|변경|조정|보유 기간|익절 비율|트레일링 스탑)[^.!?。]*[?？]", message):
        return message
    return f"{message.rstrip()} 아니면 지금 조건으로 바로 백테스트를 진행하셔도 됩니다."


# '바로 백테스트를 진행하셔도 됩니다' 안내 문장(선택적 '아니면/지금 조건으로' 접두 포함).
_BACKTEST_CTA_RE = re.compile(
    r"(?:아니면\s*)?(?:지금\s*조건으로\s*)?바로\s*백테스트를\s*진행하셔도\s*됩니다\s*[.]?"
)


def _move_backtest_cta_to_end(message: str) -> str:
    """'바로 백테스트를 진행하셔도 됩니다' 안내는 항상 마지막 마무리 문장이어야 한다.
    이 문장 뒤에 또 조건 추가를 권하면 '백테스트하셔도 됩니다 → 그런데 이걸 추가하세요'가 되어
    앞뒤가 안 맞는다. LLM이나 다른 후처리가 본문 중간에 넣었더라도 맨 끝으로 옮긴다.
    안내가 없으면 그대로 둔다."""
    if not _BACKTEST_CTA_RE.search(message):
        return message
    body = _BACKTEST_CTA_RE.sub("", message)
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([.?!。])", r"\1", body).strip()
    cta = "지금 조건으로 바로 백테스트를 진행하셔도 됩니다."
    if not body:
        return cta
    return f"{body} 아니면 {cta}"


def _format_pct(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(num)) if num == int(num) else str(num)


def _strategy_field_pct(strategy: Dict[str, Any] | None, field: str) -> Any:
    if not isinstance(strategy, dict):
        return None
    if strategy.get(field) is not None:
        return strategy.get(field)
    risk = strategy.get("risk")
    if isinstance(risk, dict):
        return risk.get(field)
    return None


def _strategy_trailing_stop_pct(strategy: Dict[str, Any] | None) -> Any:
    return _strategy_field_pct(strategy, "trailing_stop_pct")


def _align_response_with_strategy(response: CoachResponse, strategy: Dict[str, Any]) -> CoachResponse:
    message = response.message or ""

    trailing_stop_pct = _strategy_trailing_stop_pct(strategy)
    if (
        trailing_stop_pct is not None
        and "트레일링 스탑" in message
        and re.search(r"추가|설정.*말씀|바로 추가", message)
    ):
        return CoachResponse(
            message=(
                f"트레일링 스탑 {trailing_stop_pct}% 조건을 전략에 반영했습니다. "
                "이 조건으로 백테스트를 실행할 수 있습니다."
            )[:300]
        )

    # 익절 비율이 이미 설정돼 있는데도 '설정/추가/추천'하라는 응답이면, 이미 반영됐음을 알린다.
    take_profit_pct = _strategy_field_pct(strategy, "take_profit_pct")
    if (
        take_profit_pct is not None
        and "익절 비율" in message
        and re.search(r"추천|추가|설정", message)
    ):
        return CoachResponse(
            message=(
                f"익절 비율 {_format_pct(take_profit_pct)}% 조건을 전략에 반영했습니다. "
                "이 조건으로 백테스트를 실행할 수 있습니다."
            )[:300]
        )

    # 보유 기간이 이미 설정돼 있는데도 '설정/추가'를 권하는 응답이면, 이미 반영됐음을 알린다.
    hold_period_days = _strategy_field_pct(strategy, "hold_period_days")
    if (
        hold_period_days is not None
        and "보유 기간" in message
        and re.search(r"추천|추가|설정", message)
    ):
        return CoachResponse(
            message=(
                f"보유 기간 {_format_pct(hold_period_days)}일 조건을 전략에 반영했습니다. "
                "이 조건으로 백테스트를 실행할 수 있습니다."
            )[:300]
        )

    return response


def _strategy_has_explicit_sell_rule(strategy: Dict[str, Any] | None) -> bool:
    if not isinstance(strategy, dict):
        return False
    return bool(strategy.get("exit_signals")) or any(
        strategy.get(field) is not None
        for field in ("take_profit_pct", "trailing_stop_pct", "hold_period_days")
    )


def _advisor_primary_recommends_trailing_stop(advisor_result: Dict[str, Any] | None) -> bool:
    if not isinstance(advisor_result, dict):
        return False
    advice = advisor_result.get("advice") or []
    if not advice:
        return False
    primary = advice[0]
    if not isinstance(primary, dict):
        return False
    proposed_change = primary.get("proposed_change")
    proposed_text = _stable_json(proposed_change) if isinstance(proposed_change, dict) else str(proposed_change or "")
    primary_text = " ".join([
        str(primary.get("title") or ""),
        str(primary.get("body") or ""),
        proposed_text,
    ])
    return "트레일링" in primary_text or "trailing" in primary_text.lower()


def _first_non_trailing_advice_message(advisor_result: Dict[str, Any] | None) -> str:
    if not isinstance(advisor_result, dict):
        return ""
    for item in advisor_result.get("advice") or []:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if body and "트레일링" not in body and "trailing" not in body.lower():
            return body[:300]
    return ""


def _align_response_with_advisor_priority(
    response: CoachResponse,
    strategy: Dict[str, Any],
    advisor_result: Dict[str, Any] | None,
) -> CoachResponse:
    message = response.message or ""
    if "트레일링 스탑" not in message and "trailing" not in message.lower():
        return response
    if not _strategy_has_explicit_sell_rule(strategy):
        return response
    if _advisor_primary_recommends_trailing_stop(advisor_result):
        return response

    fallback = _first_non_trailing_advice_message(advisor_result)
    if fallback:
        return CoachResponse(message=fallback)
    return CoachResponse(
        message=(
            "현재 전략에는 이미 매도 기준이 있습니다. 트레일링 스탑을 기본으로 추가하기보다 "
            "우선 개선 후보를 하나씩만 바꿔 같은 기간과 비용 조건으로 백테스트하세요."
        )
    )


def _news_source_url(news_agent_insight: Optional[Dict[str, Any]]) -> Optional[str]:
    """news_agent_insight에 실제 출처 기사 URL이 있으면 첫 번째 URL을 반환한다.
    URL이 없으면(또는 인사이트가 없으면) None — 링크를 달지 않는다."""
    if not isinstance(news_agent_insight, dict):
        return None
    for sym in news_agent_insight.get("symbols") or []:
        for art in sym.get("articles") or []:
            url = str(art.get("url") or "").strip()
            if url.startswith("http"):
                return url
    return None


def _attach_news_source_link(message: str, news_agent_insight: Optional[Dict[str, Any]]) -> str:
    """코치 메시지가 '뉴스'를 언급하고 실제 출처 URL이 존재하면, 첫 '뉴스'를 마크다운
    링크([뉴스](url))로 만든다. 실제 링크가 없으면 메시지를 그대로 둔다."""
    if not message or "뉴스" not in message:
        return message
    if "](http" in message:  # 이미 링크가 달려 있으면 중복 처리하지 않는다
        return message
    url = _news_source_url(news_agent_insight)
    if not url:
        return message
    return message.replace("뉴스", f"[뉴스]({url})", 1)


def _apply_coach_postprocessing(text: str, explained_terms: set[str] | None) -> str:
    """코치 메시지 후처리 파이프라인 (순서 중요). 두 추출 경로가 공유한다."""
    text = _strip_internal_context_leak(text)               # 내부 라벨/지시문 누출 문장 제거
    text = _ensure_explained_terms(text, explained_terms=explained_terms)
    text = _collapse_nested_term_explanation(text)          # 이중 괄호 평탄화
    text = _simplify_set_condition_restatement(text)        # 설정 조건 정의 복창 → 짧은 확인
    text = _remove_redundant_definition_followup(text)      # '이는 …조건입니다' 중복 정의 문장 제거
    text = _fix_awkward_affirmation_opening(text)           # 어색한 '좋습니다' 시작 교정
    text = _remove_meaningless_filler(text)                 # 무의미한 군더더기 문장 제거
    text = _remove_meta_suggestion_sentence(text)           # '…와 같이 제안할 수 있습니다' 메타 비문 제거
    text = _remove_unsupported_technique_suggestion(text)   # 몬테카를로 등 비실용 분석 기법 제안 제거
    text = _strip_past_backtest_comparison(text)
    text = _remove_redundant_keep_condition_question(text)  # 어색한 중복 선택지 제거
    text = _ensure_backtest_option(text)
    text = _prefer_take_profit_recommendation_wording(text)  # 망설이는 질문 → 확신형 추천
    text = _fix_contradictory_backtest_option(text)
    text = _block_legacy_experiment_learning_copy(text)
    text = _move_backtest_cta_to_end(text)              # 백테스트 안내는 항상 마지막 마무리 문장
    return text[:300]


def _parse_llm_response(raw: str, explained_terms: set[str] | None = None) -> CoachResponse:
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
            return CoachResponse(
                message=_apply_coach_postprocessing((nested or message).strip(), explained_terms)
            )
        return CoachResponse(message="")
    except Exception:
        message = _extract_message_value(raw)
        return CoachResponse(
            message=_apply_coach_postprocessing((message or raw).strip(), explained_terms)
        )


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
            raw = parser.chat(
                COACH_SYSTEM_PROMPT,
                user_msg,
                max_tokens=400,
                temperature=_COACH_TEMPERATURE,
                top_p=_COACH_TOP_P,
            )
        except Exception:
            logger.exception(
                "coach parser.chat failed | request_id=%s chat_elapsed_ms=%.2f parser_state=%s",
                request_id,
                (time.perf_counter() - chat_started) * 1000,
                _parser_debug_state(),
            )
            raise
    inference_ms = round((time.perf_counter() - inference_started) * 1000, 2)

    explained_terms = _explained_terms_from_context(effective_req.conversation_context)
    response = _align_response_with_strategy(
        _parse_llm_response(raw, explained_terms=explained_terms),
        effective_req.parsed_strategy,
    )
    response = _align_response_with_advisor_priority(
        response,
        effective_req.parsed_strategy,
        effective_req.advisor_result or effective_req.advisor_insight,
    )
    response = CoachResponse(
        message=_attach_news_source_link(response.message, effective_req.news_agent_insight)
    )
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
        prior_context = req.conversation_context or []
        coach_req = CoachRequest(
            user_prompt=req.user_prompt,
            parsed_strategy=req.parsed_strategy,
            memory_strategy_cases=req.memory_strategy_cases,
            memory_experiences=req.memory_experiences,
            conversation_context=prior_context or None,
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
                    *prior_context,
                    {"role": "user", "content": req.user_prompt},
                    {"role": "assistant", "content": coach_response.message},
                ][-8:],
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
                for delta in parser.stream_chat(
                    COACH_SYSTEM_PROMPT,
                    user_msg,
                    max_tokens=400,
                    temperature=_COACH_TEMPERATURE,
                    top_p=_COACH_TOP_P,
                ):
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
            final = _parse_llm_response(
                buffer,
                explained_terms=_explained_terms_from_context(effective_req.conversation_context),
            )
            final_message = _attach_news_source_link(final.message, effective_req.news_agent_insight)
            payload = json.dumps(
                {
                    "type": "done",
                    "message": final_message,
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
