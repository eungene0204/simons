"""출력 관문 — Responder 직전 결정론 규제 가드(Planner→Tool→Responder Phase 2).

strategy_conversation이 사용자에게 내보내는 자유 텍스트(notices·되묻기 질문·칩)는
전부 이 관문을 지난다. LLM이 생성한 텍스트(설명 답변 등)에 추천·전망·보장 표현이
섞여도 여기서 문장 단위로 제거된다 — 규제 안전 원칙(CLAUDE.md)의 최종 방어선이며,
이후 planner가 어떤 경로로 텍스트를 만들든 이 관문 통과가 계약이다.

판정은 전부 결정론(정규식)이다. '추천' 단어 자체는 금지가 아니다 — 시스템이 추천을
**하는** 문장(추천합니다·권장합니다)만 제거하고, 추천 기능을 **거절·안내**하는 문장
("'종목 추천' 조건은 지원되지 않아요")은 보존한다. 면책 문구("미래 수익을 보장하지
않습니다")의 '보장'도 부정형이므로 보존한다.

위반이 없는 텍스트는 원문 그대로 반환한다(개행·서식 불변) — 관문이 정상 응답을
변형하면 그 자체가 회귀다.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

# 종목 행동 지시·확정 수익 표현은 stock_analysis 가드와 같은 정본을 쓴다(중복 정의 금지).
from stock_analysis.guardrails import _FORBIDDEN as _STOCK_FORBIDDEN

logger = logging.getLogger("strategy_interpreter.output_guard")

# 전략 대화 고유 위반 — 전략 추천·우열 판단, 시장 전망, 성과 기대·보장.
_STRATEGY_FORBIDDEN = re.compile(
    r"추천\s*합니다|추천\s*해\s*드|추천\s*드립|권장\s*합니다|권해\s*드립|사용을\s*권장|"
    r"더\s*우수|더\s*좋은\s*전략|가장\s*좋은\s*전략|최고의\s*전략|"
    r"유망(?:한|합니다|해\s*보입니다)|유리\s*합니다|적합\s*합니다|"
    r"상승할\s*(?:것|가능성)|하락할\s*(?:것|가능성)|오를\s*(?:것|가능성)|"
    r"성과가\s*기대|잘\s*작동할\s*것|"
    r"수익[을이가\s]*보장(?!하지)|보장\s*됩니다"
)

# 라인 내부 문장 경계(개행은 라인 처리로 따로 보존한다)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。])\s+")


def _violates(text: str) -> bool:
    return bool(_STOCK_FORBIDDEN.search(text) or _STRATEGY_FORBIDDEN.search(text))


def guard_text(text: Optional[str]) -> Optional[str]:
    """위반 문장을 제거한 텍스트를 돌려준다. 위반이 없으면 원문 그대로(무변형)."""
    if not text or not _violates(text):
        return text
    kept_lines: List[str] = []
    dropped: List[str] = []
    for line in text.split("\n"):
        kept: List[str] = []
        for sentence in _SENTENCE_SPLIT.split(line):
            if not sentence.strip():
                continue
            (dropped if _violates(sentence) else kept).append(sentence.strip())
        if kept:
            kept_lines.append(" ".join(kept))
        elif not line.strip():
            kept_lines.append(line)  # 의도된 빈 줄(단락 구분)은 보존
    if dropped:
        logger.warning("[output-guard] 규제 표현 문장 제거: %s", "; ".join(dropped))
    return "\n".join(kept_lines).strip()


def finalize_user_response(result: Dict) -> Dict:
    """primary 경로 반환 직전 관문 — 사용자행 텍스트 필드에 가드를 적용한다(제자리)."""
    question = guard_text(result.get("clarification_question"))
    result["clarification_question"] = question or None
    if not question:
        # 질문이 통째로 제거되면 칩만 남기지 않는다(질문 없는 칩은 무의미한 UI)
        result["clarification_suggestions"] = None
    elif result.get("clarification_suggestions"):
        chips = [c for c in (guard_text(c) for c in result["clarification_suggestions"]) if c]
        result["clarification_suggestions"] = chips or None
    if result.get("pending_ask") is not None:
        # 칩 답변 귀속 컨텍스트는 사용자가 실제로 본 질문·칩과 일치해야 한다 — 가드가
        # 질문·칩을 바꿨으면 가드 통과본으로 재구성하고, 질문이 사라졌으면 함께 지운다.
        # 칩=값 결속(chip_bindings)도 살아남은 칩만 남긴다 — 가드가 문구를 바꾼 칩은
        # 결속 키가 어긋나므로 버린다(클릭 시 결정적 추출 안전망으로 강등).
        final_chips = list(result.get("clarification_suggestions") or [])
        bindings = result["pending_ask"].get("chip_bindings")
        result["pending_ask"] = (
            {**result["pending_ask"], "question": question, "chips": final_chips,
             **({"chip_bindings": {c: bindings[c] for c in final_chips if c in bindings}}
                if isinstance(bindings, dict) else {})}
            if question and final_chips else None
        )
    if result.get("notices"):
        result["notices"] = [n for n in (guard_text(n) for n in result["notices"]) if n]
    return result
