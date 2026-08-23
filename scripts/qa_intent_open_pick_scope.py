# -*- coding: utf-8 -*-
"""의도 분류 QA — 열린 전략 추천(STRATEGY_PICK) 판정 범위 (라이브 LLM).

2026-08-11 사고: '소형주 투자 전략을 만들어줘'(설계 요청 + 시총 규모 기준)를 9B가
STRATEGY_PICK으로 오분류 → 추천 불가 안내문이 잘못 나감. 프롬프트에 "대상 범위를
좁히는 표현(시장·업종·테마·시총 규모)도 종목 선별 기준"임을 명시해 수정.

이 스크립트는 그 회귀 게이트다 — 프롬프트(intent/interpreter.SYSTEM_PROMPT)를 바꾸면
재실행한다. 라우트(/query/classify)와 동일 조건으로 로컬 Ollama 9B를 호출한다
(think:false, temperature 0.3, top_p 0.9, num_predict 220, num_ctx=_OLLAMA_NUM_CTX).
num_ctx는 하드코딩하지 않는다 — Ollama 러너는 적재 시점 num_ctx로 고정되므로 값이
다르면 keep_alive=-1로 고정된 러너 때문에 모든 호출이 무한 대기한다(2026-07-30 사고).

실행:
    python scripts/qa_intent_open_pick_scope.py [반복수=5]
종료 코드: 0=전 케이스 기대 라벨 일치, 1=불일치 존재.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
sys.path.insert(0, BACKEND)

from engine.nl_parser import _OLLAMA_NUM_CTX  # noqa: E402
from intent import interpreter  # noqa: E402

MODEL = os.environ.get("NL_OLLAMA_MODEL", "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")
BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def llm(system_prompt: str, user_msg: str) -> str:
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 220,
            "num_ctx": _OLLAMA_NUM_CTX,
        },
    }).encode()
    req = urllib.request.Request(
        f"{BASE}/api/chat", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return (json.load(resp).get("message") or {}).get("content", "").strip()


CASES = [
    # 범위를 좁히는 표현(시총 규모·시장)이 있는 설계 요청 — 열린 추천이 아니다.
    ("소형주 투자 전략을 만들어줘", "STRATEGY_ADVICE"),
    ("대형주 위주로 투자 전략 만들어줘", "STRATEGY_ADVICE"),
    ("중소형주 전략 하나 만들어줘", "STRATEGY_ADVICE"),
    # 통제군 — 진짜 열린 요청은 그대로 STRATEGY_PICK이어야 한다.
    ("어떤 전략이 제일 좋아?", "STRATEGY_PICK"),
    ("전략 추천해줘", "STRATEGY_PICK"),
    ("괜찮은 전략 좀 골라줘", "STRATEGY_PICK"),
    # 2026-08-23 사고: 성과 지표(CAGR·MDD·수익률·샤프)를 종목 선별 기준으로 읽어
    # STRATEGY_ADVICE로 분류 → 추천 불가 안내 없이 빌더로 직행했다. 성과 지표는
    # 백테스트 결과이지 조건이 아니므로 이것만 있으면 열린 요청이다.
    ("cagr를 최대화 하고 mdd를 최소화 하는 전략을 만들자", "STRATEGY_PICK"),
    ("수익률 극대화 전략 만들어줘", "STRATEGY_PICK"),
    ("손실 최소화 하는 전략 짜줘", "STRATEGY_PICK"),
    ("샤프지수 높은 전략 만들어줘", "STRATEGY_PICK"),
    # 성과 목표에 종목 선별 기준이 붙으면 다시 설계 요청이다.
    ("코스닥에서 수익률 높은 전략 만들어줘", "STRATEGY_ADVICE"),
    ("PER 10 이하 종목으로 MDD 낮은 전략 만들어줘", "STRATEGY_ADVICE"),
]

# 진행 중인 전략이 있을 때의 성과 개선 요청 — 새 전략을 골라 달라는 것이 아니라
# 지금 전략을 다듬는 것이므로 안내문이 대화를 끊으면 안 된다.
ACTIVE_CASES = [
    ("mdd를 좀 줄이고 싶어", "STRATEGY_ADVICE"),
    ("수익률을 더 높이고 싶어", "STRATEGY_ADVICE"),
]


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    fail = 0
    for text, expected, active in (
        [(t, e, False) for t, e in CASES] + [(t, e, True) for t, e in ACTIVE_CASES]
    ):
        labels: Counter = Counter()
        for _ in range(runs):
            interp = interpreter.interpret(text, llm, active_strategy=active)
            labels[interp.intent.value if interp else "PARSE_FAIL"] += 1
        ok = set(labels) == {expected}
        if not ok:
            fail += 1
        tag = "[전략중] " if active else ""
        print(f"{'OK ' if ok else 'BAD'} {tag}{text!r} 기대={expected} 실측={dict(labels)}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
