"""
백테스트 결과 자연어 요약 + 전략 점수 스크립트.

사용 방법:
  python backend/ai/summarize.py <json_payload>

출력 (stdout, JSON):
  { "score": 72, "summary": "..." }
"""

import sys
import json
import platform

MLX_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"
OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://localhost:11434/api/generate"


# ── 지표 기반 점수 계산 ──────────────────────────────────────────────────────

def calculate_score(m: dict) -> int:
    """
    CAGR, MDD, Sharpe, ProfitFactor, WinRate 5개 지표를 가중 평균해 0~100점 반환.
    기준은 BacktestDashboard의 METRIC_DESCRIPTIONS 가이드라인과 동일.
    """
    def score_cagr(v):
        if v is None: return 50
        if v >= 20: return 100
        if v >= 10: return 70
        return max(0, int(v / 10 * 70))

    def score_mdd(v):
        # MDD는 음수로 오거나 양수(절댓값)로 올 수 있음
        if v is None: return 50
        v = abs(v)
        if v <= 10: return 100
        if v <= 20: return 70
        if v <= 30: return 40
        return max(0, int(100 - v * 2))

    def score_sharpe(v):
        if v is None: return 50
        if v >= 1.5: return 100
        if v >= 1.0: return 70
        if v >= 0.5: return 40
        return max(0, int(v / 1.5 * 100))

    def score_pf(v):
        if v is None: return 50
        if v >= 2.0: return 100
        if v >= 1.5: return 70
        if v >= 1.0: return 40
        return max(0, int(v / 2.0 * 100))

    def score_winrate(v):
        if v is None: return 50
        if v >= 55: return 100
        if v >= 50: return 70
        if v >= 45: return 40
        return max(0, int(v / 55 * 100))

    weights = [
        (score_cagr(m.get("cagr")), 0.30),
        (score_mdd(m.get("maxDrawdown")), 0.25),
        (score_sharpe(m.get("sharpe")), 0.20),
        (score_pf(m.get("profitFactor")), 0.15),
        (score_winrate(m.get("winRate")), 0.10),
    ]
    return round(sum(s * w for s, w in weights))


# ── 프롬프트 빌드 ────────────────────────────────────────────────────────────

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
        "아래 백테스트 결과를 분석하여 반드시 아래 JSON 형식으로만 출력하세요. "
        "JSON 외 다른 텍스트는 절대 출력하지 마세요. "
        "모든 텍스트는 한국어 격식체 존댓말(~습니다, ~입니다)을 사용하세요.\n\n"
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
        "출력 형식 (JSON만 출력):\n"
        "{\n"
        '  "total_summary": "전략 전체 총평 2~3문장",\n'
        '  "strengths": ["강점1", "강점2", "강점3"],\n'
        '  "risks": ["리스크 또는 개선안1", "리스크 또는 개선안2", "리스크 또는 개선안3"]\n'
        "}"
    )


def parse_llm_output(text: str) -> dict:
    """LLM 출력에서 JSON을 추출한다. 실패 시 전체 텍스트를 total_summary로 사용."""
    import re
    # JSON 블록 추출 시도
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            data = json.loads(match.group())
            if "total_summary" in data:
                return data
        except json.JSONDecodeError:
            pass
    # 폴백: 텍스트 전체를 총평으로
    return {"total_summary": text.strip(), "strengths": [], "risks": []}


# ── LLM 호출 ────────────────────────────────────────────────────────────────

def summarize_mlx(prompt: str) -> str:
    import os
    from mlx_lm import load, generate  # type: ignore

    os.environ["HF_HUB_OFFLINE"] = "1"
    model, tokenizer = load(MLX_MODEL)

    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt}]
        formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        formatted = prompt

    result = generate(model, tokenizer, prompt=formatted, max_tokens=600, verbose=False)
    return result.strip()


def summarize_ollama(prompt: str) -> str:
    import urllib.request

    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 600},
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


# ── 진입점 ───────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No payload provided"}))
        sys.exit(1)

    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"JSON parse error: {e}"}))
        sys.exit(1)

    metrics = payload.get("metrics", {})
    score = calculate_score(metrics)
    prompt = build_prompt(payload)

    try:
        is_mac = platform.system() == "Darwin"
        raw = summarize_mlx(prompt) if is_mac else summarize_ollama(prompt)
        parsed = parse_llm_output(raw)
        print(json.dumps({
            "score": score,
            "summary": parsed.get("total_summary", ""),
            "strengths": parsed.get("strengths", []),
            "risks": parsed.get("risks", []),
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
