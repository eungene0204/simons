#!/usr/bin/env python3
"""MLX 9B vs Ollama 9B 파싱 **속도** 벤치마크.

같은 Qwen3.5-9B의 두 양자화본을 동일 프롬프트로 파싱하며 지연시간을 잰다.
  - cold: 첫 호출(모델 로드/슬롯 워밍 포함)
  - warm: 워밍 후 정상 상태 지연(여러 회 중앙값)

LLM 경로를 타는 프롬프트만 쓴다(규칙경로는 LLM을 호출하지 않아 ~즉시라 무의미).

사용:
  KMP_DUPLICATE_LIB_OK=1 OMP_NUM_THREADS=1 POLARS_MAX_THREADS=1 \
    python scripts/bench_mlx_ollama_parse.py
"""
from __future__ import annotations

import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from engine.nl_parser import NLStrategyParser, _parse_rule_based_strategy  # noqa: E402

MLX_MODEL = os.environ.get("CMP_MLX_MODEL", "mlx-community/Qwen3.5-9B-OptiQ-4bit")
OLLAMA_MODEL = os.environ.get("CMP_OLLAMA_MODEL", "hf.co/unsloth/Qwen3.5-9B-GGUF:Q4_K_M")
WARM_RUNS = int(os.environ.get("CMP_WARM_RUNS", "3"))

# LLM 경로를 타는(규칙기반에 안 잡히는) 프롬프트 후보. 규칙경로에 잡히는 건 런타임에 제외.
PROMPT_CANDIDATES = [
    "변동성이 큰 코스닥 종목 중에 거래량이 평소보다 폭증하고 20일선을 강하게 돌파하는 걸 잡아줘",
    "안정적인 대형주 위주로 배당 잘 주고 부채비율 낮은 회사를 분기마다 갈아타는 전략",
    "저평가된 가치주를 사서 6개월 들고 가되 15% 빠지면 손절하는 보수적인 전략 만들어줘",
]
# 규칙경로에 잡히는 프롬프트는 LLM을 호출하지 않으므로 속도 비교에서 제외
PROMPTS = [p for p in PROMPT_CANDIDATES if _parse_rule_based_strategy(p) is None]


def _timed_parse(parser: NLStrategyParser, prompt: str) -> float:
    t0 = time.perf_counter()
    parser.parse(prompt)
    return time.perf_counter() - t0


def bench(label: str, parser: NLStrategyParser) -> None:
    print(f"\n── {label} ──")
    cold_times = []
    warm_medians = []
    for prompt in PROMPTS:
        # cold: 첫 호출
        cold = _timed_parse(parser, prompt)
        cold_times.append(cold)
        # warm: 같은 프롬프트 반복(파서 내부 캐시 없음 — 매번 LLM 호출)
        warm = [_timed_parse(parser, prompt) for _ in range(WARM_RUNS)]
        med = statistics.median(warm)
        warm_medians.append(med)
        print(f"  {prompt[:34]:36s} cold {cold:6.2f}s | warm(med) {med:6.2f}s")
    print(f"  → cold 평균 {statistics.mean(cold_times):.2f}s | "
          f"warm 평균 {statistics.mean(warm_medians):.2f}s")
    return statistics.mean(warm_medians)


def main() -> None:
    if not PROMPTS:
        print("LLM 경로 프롬프트가 없습니다(모두 규칙경로에 잡힘).")
        return

    print(f"MLX    모델: {MLX_MODEL}")
    print(f"Ollama 모델: {OLLAMA_MODEL}")
    print(f"warm 반복: {WARM_RUNS}회/프롬프트")
    print("=" * 72)

    mlx = NLStrategyParser(backend="mlx", mlx_model=MLX_MODEL)
    ollama = NLStrategyParser(backend="ollama", ollama_model=OLLAMA_MODEL)

    mlx_warm = bench("MLX 9B (Apple Silicon 네이티브)", mlx)
    ollama_warm = bench("Ollama 9B (llama.cpp/Metal)", ollama)

    print("\n" + "=" * 72)
    if mlx_warm and ollama_warm:
        faster = "MLX" if mlx_warm < ollama_warm else "Ollama"
        ratio = max(mlx_warm, ollama_warm) / min(mlx_warm, ollama_warm)
        print(f"warm 평균: MLX {mlx_warm:.2f}s vs Ollama {ollama_warm:.2f}s "
              f"→ {faster}가 {ratio:.2f}배 빠름")


if __name__ == "__main__":
    main()
