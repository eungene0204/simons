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
import re
import ast

MLX_MODEL = "mlx-community/Qwen3.5-4B-4bit"
OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_URL = "http://localhost:11434/api/generate"
FALLBACK_SUMMARY = "모델 출력 형식이 올바르지 않아 요약을 생성하지 못했습니다. 다시 시도해 주세요."


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

    def to_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def build_metric_hints() -> str:
        hints = []

        total_return = to_float(m.get("totalReturn"))
        buy_hold = to_float(m.get("buyAndHoldReturn"))
        if total_return is not None and buy_hold is not None:
            diff = total_return - buy_hold
            if diff >= 0:
                hints.append(f"전략 수익률이 바이앤홀드 대비 {diff:.2f}%p 높습니다.")
            else:
                hints.append(f"전략 수익률이 바이앤홀드 대비 {abs(diff):.2f}%p 낮습니다.")

        cagr = to_float(m.get("cagr"))
        if cagr is not None:
            if cagr >= 15:
                hints.append(f"CAGR {cagr:.2f}%로 연복리 성장성이 우수합니다.")
            elif cagr >= 5:
                hints.append(f"CAGR {cagr:.2f}%로 완만한 성장 구간입니다.")
            else:
                hints.append(f"CAGR {cagr:.2f}%로 성장성이 제한적입니다.")

        mdd = to_float(m.get("maxDrawdown"))
        if mdd is not None:
            mdd_abs = abs(mdd)
            if mdd_abs <= 12:
                hints.append(f"최대 낙폭 {mdd_abs:.2f}%로 손실 방어력이 양호합니다.")
            elif mdd_abs <= 20:
                hints.append(f"최대 낙폭 {mdd_abs:.2f}%로 보통 수준의 리스크를 보입니다.")
            else:
                hints.append(f"최대 낙폭 {mdd_abs:.2f}%로 리스크 관리 보강이 필요합니다.")

        sharpe = to_float(m.get("sharpe"))
        if sharpe is not None:
            if sharpe >= 1.0:
                hints.append(f"샤프 {sharpe:.2f}로 위험 대비 성과가 안정적인 편입니다.")
            else:
                hints.append(f"샤프 {sharpe:.2f}로 위험 대비 성과 개선 여지가 큽니다.")

        profit_factor = to_float(m.get("profitFactor"))
        if profit_factor is not None:
            if profit_factor >= 1.5:
                hints.append(f"손익비 {profit_factor:.2f}로 거래 효율이 우수합니다.")
            elif profit_factor >= 1.0:
                hints.append(f"손익비 {profit_factor:.2f}로 손익 균형은 확보했지만 개선 여지가 있습니다.")
            else:
                hints.append(f"손익비 {profit_factor:.2f}로 손실 거래 비중이 높을 수 있습니다.")

        win_rate = to_float(m.get("winRate"))
        if win_rate is not None:
            if win_rate >= 55:
                hints.append(f"승률 {win_rate:.2f}%로 신호 적중률이 높은 편입니다.")
            elif win_rate >= 45:
                hints.append(f"승률 {win_rate:.2f}%로 평균 범위의 적중률입니다.")
            else:
                hints.append(f"승률 {win_rate:.2f}%로 진입 신호 정제가 필요합니다.")

        trades = to_float(m.get("trades"))
        if trades is not None:
            trades_int = int(trades)
            if trades_int < 15:
                hints.append(f"총 거래 {trades_int}회로 표본 수가 적어 성과 신뢰도 점검이 필요합니다.")
            elif trades_int > 250:
                hints.append(f"총 거래 {trades_int}회로 과매매 가능성을 점검해야 합니다.")

        if not hints:
            return "- 해석 가능한 추가 힌트가 부족합니다."
        return "\n".join(f"- {line}" for line in hints[:6])

    metric_hints = build_metric_hints()

    return (
        "당신은 주식 퀀트 투자 전략 분석가입니다. "
        "아래 백테스트 결과를 분석하여 반드시 아래 JSON 형식으로만 출력하세요. "
        "JSON 외 다른 텍스트는 절대 출력하지 마세요. "
        "Thinking Process, Reasoning, Analysis, <think> 같은 내부 추론 텍스트를 절대 출력하지 마세요. "
        "모든 텍스트는 한국어 격식체 존댓말(~습니다, ~입니다)을 사용하세요.\n\n"
        "작성 규칙:\n"
        "1) total_summary는 5~7문장으로 작성하고, 전략의 성과, 위험도, 시장 대비 상대 성과 등 다각적으로 분석하세요. 최소 4개 이상의 지표 수치를 직접 인용하세요.\n"
        "2) strengths는 정확히 3개로 작성하고, 각 항목은 2~3문장으로 상세히 설명하며 지표명 또는 수치를 포함하세요. 단순 나열이 아닌 분석적 설명을 제공하세요.\n"
        "3) weaknesses는 정확히 3개로 작성하고, 각 항목은 단점이나 개선 필요 영역만 설명합니다(개선안 없음). 각 항목 1~2문장으로 간결히 작성하세요.\n"
        "4) improvements는 정확히 3개로 작성하고, 각 항목은 구체적인 개선 방안과 기대 효과를 2~3문장으로 작성하세요. \"~하면 좋습니다\", \"~을 고려해보세요\" 같은 제안형으로 작성하세요.\n"
        "5) 과장된 단정 표현을 피하고 지표 기반으로 판단하세요.\n"
        "6) total_summary의 각 문장은 서로 다른 관점(수익성, 안정성, 효율성, 거래 신뢰도 등)에서 작성하세요.\n\n"
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
        "지표 해석 힌트(참고용):\n"
        f"{metric_hints}\n\n"
        "출력 형식 (JSON만 출력):\n"
        "{\n"
        '  "total_summary": "전략 전체 총평 5~7문장으로 상세히 작성. 수익성, 안정성, 효율성, 거래 신뢰도 등 다각도 분석",\n'
        '  "strengths": ["강점1 - 2~3문장으로 상세 설명, 지표 수치 포함", "강점2 - 2~3문장", "강점3 - 2~3문장"],\n'
        '  "weaknesses": ["단점1 - 1~2문장으로 간결히", "단점2 - 1~2문장", "단점3 - 1~2문장"],\n'
        '  "improvements": ["개선 방안1 - 2~3문장으로 구체적 조치와 기대효과", "개선 방안2 - 2~3문장", "개선 방안3 - 2~3문장"]\n'
        "}"
    )


# ── Advisor 연동 (하이브리드 리포트) ──────────────────────────────────────────
#
# advisor 에이전트가 결정론적으로 진단/조언을 만들고, LLM 은 그 위에서 총평·강점·
# 단점만 서술한다. improvements(구체적 개선 조치)는 advisor 결과를 그대로 쓴다.


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_advisor_backtest_summary(metrics: dict) -> dict:
    """프론트 퍼센트 지표(cagr=18.0)를 advisor BacktestSummary(분수, cagr=0.18)로 변환한다."""
    metrics = metrics or {}

    def pct(key):
        f = _to_float(metrics.get(key))
        return f / 100.0 if f is not None else None

    mdd = pct("maxDrawdown")
    if mdd is not None and mdd > 0:
        mdd = -mdd  # advisor 는 MDD 를 음수로 받는다

    trades = metrics.get("trades")
    try:
        trade_count = int(trades) if trades is not None else None
    except (TypeError, ValueError):
        trade_count = None

    return {
        "cagr": pct("cagr"),
        "mdd": mdd,
        "sharpe": _to_float(metrics.get("sharpe")),
        "sortino": _to_float(metrics.get("sortino")),
        "profit_factor": _to_float(metrics.get("profitFactor")),
        "trade_count": trade_count,
        "win_rate": pct("winRate"),
    }


def build_report_from_advisor(advisor: dict) -> dict:
    """AdvisorResponse(dict) → 리포트의 결정론적 부분(improvements + 점수 + 근거)으로 매핑한다."""
    advisor = advisor or {}
    advice = advisor.get("advice") or []
    severity_order = {"high": 0, "medium": 1, "low": 2}
    advice_sorted = sorted(
        advice, key=lambda a: severity_order.get((a or {}).get("severity"), 9)
    )

    improvements: list[str] = []
    for item in advice_sorted:
        item = item or {}
        change = item.get("proposed_change") or {}
        text = (
            str(change.get("description") or "").strip()
            or str(item.get("title") or "").strip()
            or str(item.get("body") or "").strip()
        )
        if text:
            improvements.append(text)
    for exp in advisor.get("suggested_experiments") or []:
        exp = str(exp or "").strip()
        if exp:
            improvements.append(exp)

    # weaknesses 서술의 환각을 막기 위한 근거 — LLM 프롬프트에 주입한다.
    advice_titles = [
        str((item or {}).get("title") or "").strip()
        for item in advice_sorted
        if str((item or {}).get("title") or "").strip()
    ]
    sections = [
        {
            "title": str((s or {}).get("title") or "").strip(),
            "body": str((s or {}).get("body") or "").strip(),
        }
        for s in advisor.get("response_sections") or []
    ]

    return {
        "improvements": normalize_report_items(improvements[:3]),
        "advisorScore": advisor.get("strategy_score"),
        "riskScore": advisor.get("risk_score"),
        "overfitRisk": advisor.get("overfit_risk"),
        "advice_titles": advice_titles,
        "response_sections": sections,
    }


def _build_advisor_grounding(report: dict) -> str:
    """advisor 진단을 LLM 프롬프트용 텍스트 블록으로 직렬화한다."""
    report = report or {}
    lines: list[str] = []

    score = report.get("advisorScore")
    risk = report.get("riskScore")
    overfit = report.get("overfitRisk")
    if score is not None:
        lines.append(f"- 전략 종합 점수: {float(score):.0f}/100")
    if risk is not None:
        lines.append(f"- 리스크 점수: {float(risk):.0f}/100 (높을수록 위험)")
    if overfit:
        lines.append(f"- 과적합 위험: {overfit}")

    titles = report.get("advice_titles") or []
    if titles:
        lines.append("진단된 문제/조언:")
        lines.extend(f"  - {t}" for t in titles[:6])

    sections = report.get("response_sections") or []
    if sections:
        lines.append("추가 분석:")
        for section in sections[:4]:
            title = section.get("title") or ""
            body = (section.get("body") or "").strip()
            if not body:
                continue
            if len(body) > 160:
                body = body[:160].rstrip() + "…"
            lines.append(f"  - {title}: {body}" if title else f"  - {body}")

    if not lines:
        return "- 진단된 추가 근거가 없습니다."
    return "\n".join(lines)


def build_advisor_grounded_prompt(payload: dict, advisor_report: dict) -> str:
    """하이브리드 프롬프트 — advisor 진단을 근거로 total_summary/strengths/weaknesses만 서술하게 한다.

    improvements 는 advisor 가 결정론적으로 채우므로 LLM 에 요청하지 않는다.
    """
    base = build_prompt(payload)
    grounding = _build_advisor_grounding(advisor_report)

    instructions = (
        "\n\n[중요] 위 지표에 더해 아래 'advisor 진단 근거'가 제공됩니다. "
        "weaknesses(단점)는 반드시 아래 진단된 문제에서만 도출하고, 진단에 없는 새로운 문제를 "
        "지어내지 마세요. improvements 는 별도 시스템이 채우므로 출력하지 마세요.\n\n"
        "advisor 진단 근거:\n"
        f"{grounding}\n\n"
        "출력 형식 (JSON만 출력, improvements 키 없음):\n"
        "{\n"
        '  "total_summary": "전략 전체 총평 5~7문장. 수익성/안정성/효율성/거래 신뢰도 다각도 분석",\n'
        '  "strengths": ["강점1 - 2~3문장, 지표 수치 포함", "강점2 - 2~3문장", "강점3 - 2~3문장"],\n'
        '  "weaknesses": ["단점1 - 진단 근거 기반 1~2문장", "단점2 - 1~2문장", "단점3 - 1~2문장"]\n'
        "}"
    )
    return base + instructions


def _extract_json_objects(text: str) -> list[str]:
    objects: list[str] = []
    stack = 0
    start = -1
    in_string = False
    escape = False

    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            if stack == 0:
                start = idx
            stack += 1
            continue

        if ch == "}":
            if stack == 0:
                continue
            stack -= 1
            if stack == 0 and start != -1:
                objects.append(text[start:idx + 1])
                start = -1

    return objects


def _to_string_list(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]

    if isinstance(value, tuple) or isinstance(value, set):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]

    if isinstance(value, str):
        lines = []
        for raw in value.splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+\.)\s*", "", raw).strip()
            if line:
                lines.append(line)
        if lines:
            return lines
        return [value.strip()] if value.strip() else []

    normalized = str(value).strip()
    return [normalized] if normalized else []


def _coerce_report_shape(data: dict) -> dict | None:
    summary = (
        data.get("total_summary")
        or data.get("totalSummary")
        or data.get("summary")
        or data.get("overall_summary")
        or data.get("overallSummary")
    )
    if summary is None:
        return None

    strengths = (
        data.get("strengths")
        or data.get("pros")
        or data.get("advantages")
        or data.get("장점")
    )
    weaknesses = (
        data.get("weaknesses")
        or data.get("단점")
        or data.get("cons")
    )
    improvements = (
        data.get("improvements")
        or data.get("개선점")
        or data.get("recommendations")
        or data.get("suggestions")
    )

    return {
        "total_summary": str(summary).strip(),
        "strengths": _to_string_list(strengths),
        "weaknesses": _to_string_list(weaknesses),
        "improvements": _to_string_list(improvements),
    }


def _parse_json_candidate(candidate: str) -> dict | None:
    for prepared in (
        candidate,
        re.sub(r",\s*([}\]])", r"\1", candidate),
    ):
        try:
            parsed = json.loads(prepared)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    try:
        parsed = ast.literal_eval(candidate)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError):
        pass

    return None


def _extract_report_from_sections(text: str) -> dict | None:
    section_key_map = {
        "총평": "summary",
        "요약": "summary",
        "summary": "summary",
        "강점": "strengths",
        "장점": "strengths",
        "strengths": "strengths",
        "단점": "weaknesses",
        "약점": "weaknesses",
        "weaknesses": "weaknesses",
        "리스크": "weaknesses",
        "위험": "weaknesses",
        "개선": "improvements",
        "개선점": "improvements",
        "improvements": "improvements",
    }

    sections = {"summary": [], "strengths": [], "weaknesses": [], "improvements": []}

    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^(Thinking Process|Reasoning|Analysis)\s*:?\s*$", line, flags=re.IGNORECASE):
            continue
        match = re.match(r"^([A-Za-z가-힣 ]{1,20})\s*[:：]\s*(.*)$", line)
        if match:
            label = match.group(1).strip().lower()
            tail = match.group(2).strip()
            current = None
            for key, target in section_key_map.items():
                if key.lower() in label:
                    current = target
                    if tail:
                        sections[target].append(tail)
                    break
            if current is not None:
                continue

        normalized = re.sub(r"^\s*(?:[-*•]|\d+\.)\s*", "", line).strip()
        if not normalized:
            continue
        if current is None:
            sections["summary"].append(normalized)
            continue
        sections[current].append(normalized)

    summary = " ".join(sections["summary"]).strip()
    if not summary and not sections["strengths"] and not sections["weaknesses"] and not sections["improvements"]:
        return None

    if not summary:
        summary = FALLBACK_SUMMARY

    return {
        "total_summary": summary,
        "strengths": sections["strengths"],
        "weaknesses": sections["weaknesses"],
        "improvements": sections["improvements"],
    }


def _extract_plain_summary(text: str) -> str:
    cleaned_lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^(Thinking Process|Reasoning|Analysis)\s*:?\s*$", line, flags=re.IGNORECASE):
            continue
        line = re.sub(r"^\s*\d+\.\s*", "", line).strip()
        line = re.sub(r"^\s*(?:[-*•])\s*", "", line).strip()
        if line:
            cleaned_lines.append(line)

    if not cleaned_lines:
        return FALLBACK_SUMMARY

    summary = " ".join(cleaned_lines).strip()
    return summary if summary else FALLBACK_SUMMARY


def parse_llm_output(text: str) -> dict:
    """LLM 출력에서 JSON을 추출한다. 실패 시 안전한 폴백 요약을 반환한다."""
    text = text.strip()
    text = re.sub(r"<think>[\s\S]*?</think>\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```", "", text).strip()

    candidates = _extract_json_objects(text)
    for candidate in candidates:
        parsed = _parse_json_candidate(candidate)
        if not parsed:
            continue
        normalized = _coerce_report_shape(parsed)
        if normalized:
            return normalized

    section_based = _extract_report_from_sections(text)
    if section_based:
        return section_based

    return {"total_summary": _extract_plain_summary(text), "strengths": [], "weaknesses": [], "improvements": []}


def normalize_report_items(items) -> list[str]:
    """빈 강점/리스크 목록은 ['없음']으로 통일한다."""
    if not items:
        return ["없음"]

    normalized = [
        str(item).strip()
        for item in items
        if item is not None and str(item).strip()
    ]
    return normalized if normalized else ["없음"]


# ── LLM 호출 ────────────────────────────────────────────────────────────────

def summarize_mlx(prompt: str) -> str:
    import os
    from mlx_lm import load, generate  # type: ignore

    os.environ["HF_HUB_OFFLINE"] = "1"
    model, tokenizer = load(MLX_MODEL)

    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template:
        messages = [{"role": "user", "content": prompt}]
        formatted = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
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
            "strengths": normalize_report_items(parsed.get("strengths", [])),
            "risks": normalize_report_items(parsed.get("risks", [])),
        }, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
