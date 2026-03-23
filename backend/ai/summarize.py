"""
백테스트 결과 자연어 요약 스크립트.

사용 방법:
  python backend/ai/summarize.py <json_payload>

json_payload 구조:
  {
    "metrics": { totalReturn, cagr, buyAndHoldReturn, maxDrawdown, sharpe,
                 sortino, profitFactor, winRate, trades, volatility, kelly,
                 initialCapital, finalEquity },
    "strategySummary": { strategyName, universeName, entryBlocks, exitBlocks }
  }

출력 (stdout, JSON):
  { "summary": "..." }
"""

import sys
import json
import platform

MLX_MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"


def build_prompt(payload: dict) -> str:
    m = payload.get("metrics", {})
    s = payload.get("strategySummary") or {}

    strategy_desc = ""
    if s:
        name = s.get("strategyName") or "이름 없음"
        universe = s.get("universeName") or "-"
        entry = ", ".join(s.get("entryBlocks") or []) or "-"
        exit_ = ", ".join(s.get("exitBlocks") or []) or "-"
        strategy_desc = (
            f"전략명: {name}\n"
            f"유니버스: {universe}\n"
            f"진입 조건: {entry}\n"
            f"청산 조건: {exit_}\n\n"
        )

    def fmt(v):
        return f"{v:.2f}" if v is not None else "N/A"

    return (
        "당신은 주식 퀀트 투자 전략 분석가입니다. "
        "아래 백테스트 결과를 바탕으로 전략을 3~4문장으로 한국어로 요약해 주세요. "
        "수치를 언급하고, 강점과 약점을 간결하게 평가하세요.\n\n"
        f"{strategy_desc}"
        "백테스트 지표:\n"
        f"- 총 수익률: {fmt(m.get('totalReturn'))}%\n"
        f"- CAGR: {fmt(m.get('cagr'))}%\n"
        f"- 바이앤홀드 수익률: {fmt(m.get('buyAndHoldReturn'))}%\n"
        f"- 최대 낙폭(MDD): {fmt(m.get('maxDrawdown'))}%\n"
        f"- 샤프 지수: {fmt(m.get('sharpe'))}\n"
        f"- 소르티노 지수: {fmt(m.get('sortino'))}\n"
        f"- 손익비(Profit Factor): {fmt(m.get('profitFactor'))}\n"
        f"- 승률: {fmt(m.get('winRate'))}%\n"
        f"- 총 거래 횟수: {m.get('trades', 'N/A')}\n"
        f"- 연간 변동성: {fmt(m.get('volatility'))}%\n"
        f"- 켈리 기준: {fmt(m.get('kelly'))}%\n\n"
        "요약:"
    )


def summarize_mlx(prompt: str) -> str:
    import os
    from mlx_lm import load, generate  # type: ignore

    # HF 원격 확인 생략 → 캐시에서 바로 로드
    os.environ["HF_HUB_OFFLINE"] = "1"
    model, tokenizer = load(MLX_MODEL)

    # Apply chat template if available
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt}]
        formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        formatted = prompt

    result = generate(model, tokenizer, prompt=formatted, max_tokens=400, verbose=False)
    return result.strip()


def summarize_ollama(prompt: str) -> str:
    import urllib.request

    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 400},
        }
    ).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return data.get("response", "").strip()


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No payload provided"}))
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON parse error: {e}"}))
        sys.exit(1)

    prompt = build_prompt(payload)

    try:
        is_mac = platform.system() == "Darwin"
        if is_mac:
            summary = summarize_mlx(prompt)
        else:
            summary = summarize_ollama(prompt)

        print(json.dumps({"summary": summary}, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
