# -*- coding: utf-8 -*-
"""의도 분류 QA — 열린 전략 추천(STRATEGY_PICK) 판정 범위 (라이브 LLM).

2026-08-11 사고: '소형주 투자 전략을 만들어줘'(설계 요청 + 시총 규모 기준)를 9B가
STRATEGY_PICK으로 오분류 → 추천 불가 안내문이 잘못 나감. 프롬프트에 "대상 범위를
좁히는 표현(시장·업종·테마·시총 규모)도 종목 선별 기준"임을 명시해 수정.

이 스크립트는 그 회귀 게이트다 — 프롬프트(intent/interpreter.SYSTEM_PROMPT)를 바꾸면
재실행한다. 라우트(/query/classify)와 동일 조건으로 로컬 Ollama 9B를 호출한다
(think:false, temperature 0.3, top_p 0.9, num_predict 220, num_ctx 16384).

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
            "num_ctx": 16384,
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
]


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    fail = 0
    for text, expected in CASES:
        labels: Counter = Counter()
        for _ in range(runs):
            interp = interpreter.interpret(text, llm)
            labels[interp.intent.value if interp else "PARSE_FAIL"] += 1
        ok = set(labels) == {expected}
        if not ok:
            fail += 1
        print(f"{'OK ' if ok else 'BAD'} {text!r} 기대={expected} 실측={dict(labels)}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
