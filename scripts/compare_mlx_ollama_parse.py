#!/usr/bin/env python3
"""MLX 9B vs Ollama 9B 파싱 결과 동등성 비교 하니스.

같은 베이스 모델(Qwen3.5-9B)의 두 양자화본 —
  - MLX:    mlx-community/Qwen3.5-9B-OptiQ-4bit   (MLX/Metal + outlines, greedy)
  - Ollama: hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M  (llama.cpp/Metal + instructor, temp=0)
— 이 동일 프롬프트에 대해 **구조화 파싱 결과(ParsedStrategy)** 를 같게 내는지 검증한다.

앱이 실제로 쓰는 건 자유텍스트가 아니라 이 구조화 JSON이므로, 그것을 비교한다.

주의(중요):
  - 서로 다른 양자화 + 서로 다른 추론엔진은 temp=0(greedy)이라도 **logit이 비트단위로
    같지 않다**. 따라서 자유텍스트는 동일 보장이 없다. 단, JSON 스키마로 제약된 구조화
    출력은 많은 경우 최종 dict가 일치한다 — 이 스크립트가 그것을 실측한다.
  - parse()는 규칙기반(regex)을 먼저 타며, 거기서 처리되는 프롬프트는 두 백엔드가 같은
    Python 코드라 자명히 동일하다. 그래서 프롬프트를 (A)규칙경로 (B)LLM경로로 나눠 본다.

사용:
  KMP_DUPLICATE_LIB_OK=1 OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
    python scripts/compare_mlx_ollama_parse.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from engine.nl_parser import NLStrategyParser, _parse_rule_based_strategy  # noqa: E402

MLX_MODEL = os.environ.get("CMP_MLX_MODEL", "mlx-community/Qwen3.5-9B-OptiQ-4bit")
OLLAMA_MODEL = os.environ.get("CMP_OLLAMA_MODEL", "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")

# 규칙기반(regex)으로 잡히는 프롬프트(A) + LLM 경로를 타는 모호/복합 프롬프트(B)를 섞는다.
PROMPTS = [
    # (A) 규칙경로 — 두 백엔드 자명히 동일해야 함
    "PBR 1 이하 10개 1년 보유",
    "RSI 30 이하 매수 70 이상 매도",
    "트레일링 스탑 15%",
    # (B) LLM 경로 — 양자화/엔진 차이가 드러날 수 있는 복합/서술형
    "외국인이 3일 연속 순매수하고 ADX가 25를 넘는 종목을 RSI 30 이하에서 사고 손절은 7%",
    "변동성이 큰 코스닥 종목 중에 거래량이 평소보다 폭증하고 20일선을 강하게 돌파하는 걸 잡아줘",
    "안정적인 대형주 위주로 배당 잘 주고 부채비율 낮은 회사를 분기마다 갈아타는 전략",
    "골든크로스 나면서 MACD가 시그널선 위로 올라오는 순간 진입, 최대 5종목, 10% 익절",
    "저평가된 가치주를 사서 6개월 들고 가되 15% 빠지면 손절하는 보수적인 전략 만들어줘",
]


def parse_both(prompt: str) -> tuple[dict, dict, bool]:
    """두 백엔드로 파싱해 (mlx_dict, ollama_dict, rule_based여부) 반환."""
    is_rule = _parse_rule_based_strategy(prompt) is not None

    mlx = NLStrategyParser(backend="mlx", mlx_model=MLX_MODEL)
    ollama = NLStrategyParser(backend="ollama", ollama_model=OLLAMA_MODEL)

    mlx_out = mlx.parse(prompt).model_dump()
    ollama_out = ollama.parse(prompt).model_dump()
    return mlx_out, ollama_out, is_rule


def diff_fields(a: dict, b: dict) -> list[str]:
    """두 dict에서 값이 다른 필드 목록을 반환."""
    diffs = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            diffs.append(f"  · {key}: MLX={a.get(key)!r}  vs  OLLAMA={b.get(key)!r}")
    return diffs


def main() -> None:
    print(f"MLX    모델: {MLX_MODEL}")
    print(f"Ollama 모델: {OLLAMA_MODEL}")
    print("=" * 70)

    total = identical = 0
    llm_total = llm_identical = 0

    for i, prompt in enumerate(PROMPTS, 1):
        try:
            mlx_out, ollama_out, is_rule = parse_both(prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"[{i}] ❌ ERROR: {type(exc).__name__}: {exc}")
            print(f"     prompt={prompt!r}")
            continue

        total += 1
        match = mlx_out == ollama_out
        if match:
            identical += 1
        if not is_rule:
            llm_total += 1
            if match:
                llm_identical += 1

        tag = "규칙경로" if is_rule else "LLM경로"
        mark = "✅ 동일" if match else "⚠️ 차이"
        print(f"[{i}] {mark} ({tag}) — {prompt[:40]}...")
        if not match:
            for line in diff_fields(mlx_out, ollama_out):
                print(line)

    print("=" * 70)
    print(f"전체:    {identical}/{total} 동일")
    print(f"LLM경로: {llm_identical}/{llm_total} 동일  ← 양자화/엔진 차이가 드러나는 핵심 지표")
    if llm_total and llm_identical == llm_total:
        print("→ ✅ LLM 경로에서도 구조화 결과가 완전 일치")
    elif llm_total:
        print("→ ⚠️ LLM 경로에서 일부 구조화 결과가 다름 (아래 차이 참고)")


if __name__ == "__main__":
    main()
