"""
백테스트 결과 자연어 요약 + 전략 점수 스크립트.

사용 방법:
  python backend/ai/summarize.py <json_payload>

출력 (stdout, JSON):
  { "score": 72, "summary": "..." }
"""

import os
import sys
import json
import re
import ast

MLX_MODEL = "mlx-community/Qwen3.5-4B-4bit"
# AI 리포트(백테스트 총평·강점·단점 서술) 전용 모델. NL 파서/인터프리터와 분리해
# 독립적으로 교체할 수 있다(예: 리포트만 더 큰 9B). 미설정 시 시스템 공용
# NL_OLLAMA_MODEL(없으면 qwen3:8b)로 폴백한다. prod에서 9B를 쓰려면 Modal이 해당
# 모델도 함께 서빙해야 한다(modal_ollama.py MODELS 참고).
OLLAMA_MODEL = os.environ.get(
    "SUMMARIZE_OLLAMA_MODEL",
    os.environ.get("NL_OLLAMA_MODEL", "qwen3:8b"),
)
# /api/generate가 아니라 /api/chat을 쓴다 — GGUF 임포트 모델(Qwen3.5)은 generate 경로에서
# think:false가 무시되어 <think> 추론이 응답에 섞인다. chat 경로는 nl_parser에서 검증됨.
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat"
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

_PROMPT_HEADER = (
    "당신은 주식 퀀트 투자 전략 분석가입니다. "
    "아래 백테스트 결과를 분석하여 반드시 아래 JSON 형식으로만 출력하세요. "
    "JSON 외 다른 텍스트는 절대 출력하지 마세요. "
    "Thinking Process, Reasoning, Analysis, <think> 같은 내부 추론 텍스트를 절대 출력하지 마세요. "
    "모든 텍스트는 한국어 격식체 존댓말(~습니다, ~입니다)을 사용하세요.\n\n"
)

_RULE_SUMMARY = (
    "1) total_summary는 5~7문장으로 작성하고, 전략의 성과, 위험도, 시장 대비 상대 성과 등 다각적으로 분석하세요. 최소 4개 이상의 지표 수치를 직접 인용하세요.\n"
)
_RULE_STRENGTHS = (
    "2) strengths는 정확히 3개로 작성하고, 각 항목은 2~3문장으로 상세히 설명하며 지표명 또는 수치를 포함하세요. 단순 나열이 아닌 분석적 설명을 제공하세요.\n"
)
_RULES_COMMON_TAIL = (
    "5) 과장된 단정 표현을 피하고 지표 기반으로 판단하세요.\n"
    "6) total_summary의 각 문장은 서로 다른 관점(수익성, 안정성, 효율성, 거래 신뢰도 등)에서 작성하세요.\n"
    "7) 지표 수치는 아래에 제시된 값만 그대로 인용하고, 제시되지 않은 수치나 기간을 추측해서 쓰지 마세요.\n"
    "8) 미래 성과 예측이나 단정(\"앞으로도 잘 작동할 것\", \"높은 수익이 기대됨\")은 금지합니다. 모든 서술은 과거 시뮬레이션 결과에 한정하세요.\n"
)


def _build_context_block(payload: dict) -> str:
    """전략 요약 + 백테스트 지표 + 해석 힌트 블록 (두 프롬프트 경로가 공유)."""
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

    # 백테스트 기간·자본 정보 — 제공되면 프롬프트에 명시해 LLM이 기간을 추측하지 않게 한다.
    period_start = m.get("periodStart")
    period_end = m.get("periodEnd")
    context_lines = ""
    if period_start and period_end:
        context_lines += f"- 백테스트 기간: {period_start} ~ {period_end}\n"

    def fmt_krw(v):
        # 억/만 단위로 미리 변환해 제공한다 — 원 단위 숫자만 주면 LLM이 단위 환산을
        # 시도하다 틀린다(실측: 10,000,000원을 "1억 원"으로 오환산).
        f = to_float(v)
        if not f or f <= 0:
            return None
        total_man = round(f / 10_000)
        if total_man == 0:
            return f"{f:,.0f}원"
        eok, man = divmod(total_man, 10_000)
        if eok and man:
            return f"{eok}억 {man:,}만원"
        if eok:
            return f"{eok}억원"
        return f"{man:,}만원"

    initial_krw = fmt_krw(m.get("initialCapital"))
    final_krw = fmt_krw(m.get("finalEquity"))
    if initial_krw and final_krw:
        context_lines += f"- 초기 자본: {initial_krw} → 최종 자산: {final_krw}\n"

    return (
        f"{strategy_desc}"
        "백테스트 지표:\n"
        f"{context_lines}"
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
    )


def _build_corpus_comparison_block(corpus_comparison: dict | None) -> str:
    """코퍼스 비교(결정론 계산) 블록 — 총평이 '결과 읽기'를 넘어 상대적 위치를 서술하게 한다."""
    if not corpus_comparison:
        return ""
    cmp = corpus_comparison
    lines = list(cmp.get("lines") or [])
    contrast = list(cmp.get("contrast_lines") or [])
    if not lines and not contrast:
        return ""
    block = f"코퍼스 비교 (기준: {cmp.get('cohort_label', '과거 전략 시뮬레이션')}):\n"
    block += "".join(f"- {line}\n" for line in lines)
    if contrast:
        block += "구조 장치 유무별 과거 통계:\n"
        block += "".join(f"- {line}\n" for line in contrast)
    return block + "\n"


def _corpus_rule(corpus_comparison: dict | None) -> str:
    if not corpus_comparison:
        return ""
    return (
        "9) 아래 '코퍼스 비교'는 동일 백테스트 엔진으로 실행된 다른 전략 시뮬레이션들과의 객관적 비교입니다. "
        "total_summary에 상대적 위치(상위/하위 %)와 그 시사점을 2문장 이상 반영하고, 제시된 비교 문장의 수치와 우열 판단(높음/낮음)을 그대로 옮기세요. "
        "'하위 X%'는 비교군 다수보다 나쁜 성과를 뜻하므로 긍정적으로 서술하지 마세요. "
        "'구조 장치 유무별 과거 통계'가 있으면 weaknesses 또는 total_summary에 과거 통계 서술로만 반영하세요(추천 표현 금지).\n"
    )


def build_prompt(payload: dict, corpus_comparison: dict | None = None) -> str:
    """LLM 단독 경로 프롬프트 — 총평/강점/단점/개선 방안 전부를 LLM이 작성한다."""
    return (
        _PROMPT_HEADER
        + "작성 규칙:\n"
        + _RULE_SUMMARY
        + _RULE_STRENGTHS
        + "3) weaknesses는 정확히 3개로 작성하고, 각 항목은 단점이나 개선 필요 영역만 설명합니다(개선안 없음). 각 항목 1~2문장으로 간결히 작성하세요.\n"
        + "4) improvements는 정확히 3개로 작성하고, 각 항목은 구체적인 개선 방안과 기대 효과를 2~3문장으로 작성하세요. \"~하면 좋습니다\", \"~을 고려해보세요\" 같은 제안형으로 작성하세요.\n"
        + _RULES_COMMON_TAIL
        + _corpus_rule(corpus_comparison)
        + "\n"
        + _build_context_block(payload)
        + _build_corpus_comparison_block(corpus_comparison)
        + "출력 형식 (JSON만 출력):\n"
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


def build_advisor_grounded_prompt(payload: dict, advisor_report: dict, corpus_comparison: dict | None = None) -> str:
    """하이브리드 프롬프트 — advisor 진단을 근거로 total_summary/strengths/weaknesses만 서술하게 한다.

    improvements 는 advisor 가 결정론적으로 채우므로 LLM 에 요청하지 않는다.
    base 프롬프트에 덧붙이는 방식(규칙 두 벌 충돌)은 모델이 지시문을 복창하거나
    내부 추론을 노출하게 만들었으므로, 처음부터 모순 없는 단일 규칙 세트로 구성한다.
    """
    grounding = _build_advisor_grounding(advisor_report)

    return (
        _PROMPT_HEADER
        + "작성 규칙:\n"
        + _RULE_SUMMARY
        + _RULE_STRENGTHS
        + "3) weaknesses는 아래 'advisor 진단 근거'에 진단된 문제와 위 지표·코퍼스 비교에서 직접 확인되는 약점에서만 도출하세요. "
        "진단이나 지표에 근거가 없는 문제를 지어내지 마세요. 근거가 있는 만큼만 최대 3개까지 작성하고, 해당 사항이 없으면 빈 배열 []로 출력하세요. 각 항목은 1~2문장으로 간결히 작성하세요.\n"
        + "4) improvements는 별도 시스템이 채우므로 절대 출력하지 마세요. JSON에 improvements 키를 포함하지 마세요.\n"
        + _RULES_COMMON_TAIL
        + _corpus_rule(corpus_comparison)
        + "\n"
        + _build_context_block(payload)
        + _build_corpus_comparison_block(corpus_comparison)
        + "advisor 진단 근거:\n"
        f"{grounding}\n\n"
        + "출력 형식 (JSON만 출력, improvements 키 없음):\n"
        "{\n"
        '  "total_summary": "전략 전체 총평 5~7문장. 수익성/안정성/효율성/거래 신뢰도 다각도 분석",\n'
        '  "strengths": ["강점1 - 2~3문장, 지표 수치 포함", "강점2 - 2~3문장", "강점3 - 2~3문장"],\n'
        '  "weaknesses": ["단점1 - 진단 근거 기반 1~2문장 (진단된 문제 수만큼만, 없으면 빈 배열)"]\n'
        "}"
    )


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


def _find_json_value_start(source: str, key: str) -> int | None:
    match = re.search(rf"['\"]{re.escape(key)}['\"]\s*:\s*", source)
    return match.end() if match else None


def _read_quoted_fragment(source: str, start: int) -> tuple[str, int] | None:
    if start >= len(source) or source[start] not in ("'", '"'):
        return None

    quote = source[start]
    idx = start + 1
    escape = False
    raw_chars: list[str] = []

    while idx < len(source):
        ch = source[idx]
        if escape:
            raw_chars.append("\\" + ch)
            escape = False
            idx += 1
            continue
        if ch == "\\":
            escape = True
            idx += 1
            continue
        if ch == quote:
            raw = "".join(raw_chars)
            try:
                decoded = json.loads(f'"{raw}"') if quote == '"' else ast.literal_eval(f"'{raw}'")
            except (json.JSONDecodeError, ValueError, SyntaxError):
                decoded = raw.replace('\\"', '"').replace("\\'", "'")
            return str(decoded).strip(), idx + 1
        raw_chars.append(ch)
        idx += 1

    return None


def _extract_string_field(source: str, keys: list[str]) -> str | None:
    for key in keys:
        start = _find_json_value_start(source, key)
        if start is None:
            continue
        while start < len(source) and source[start].isspace():
            start += 1
        value = _read_quoted_fragment(source, start)
        if value and value[0]:
            return value[0]
    return None


def _extract_array_field(source: str, keys: list[str]) -> list[str]:
    for key in keys:
        start = _find_json_value_start(source, key)
        if start is None:
            continue
        while start < len(source) and source[start].isspace():
            start += 1
        if start >= len(source):
            continue
        if source[start] in ("'", '"'):
            value = _read_quoted_fragment(source, start)
            return [value[0]] if value and value[0] else []
        if source[start] != "[":
            continue

        values: list[str] = []
        idx = start + 1
        while idx < len(source):
            ch = source[idx]
            if ch == "]":
                break
            if ch in ("'", '"'):
                value = _read_quoted_fragment(source, idx)
                if value is None:
                    break
                if value[0]:
                    values.append(value[0])
                idx = value[1]
                continue
            idx += 1
        return values
    return []


def _extract_partial_json_report(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None

    source = text[start:]
    if not re.search(r"['\"](?:total_summary|totalSummary|summary|strengths|weaknesses|improvements)['\"]\s*:", source):
        return None

    summary = _extract_string_field(
        source,
        ["total_summary", "totalSummary", "summary", "overall_summary", "overallSummary"],
    )
    if not summary:
        return None

    return {
        "total_summary": summary,
        "strengths": _extract_array_field(source, ["strengths", "pros", "advantages", "장점"]),
        "weaknesses": _extract_array_field(source, ["weaknesses", "단점", "cons"]),
        "improvements": _extract_array_field(source, ["improvements", "개선점", "recommendations", "suggestions"]),
    }


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


# 프롬프트 지시문·출력 템플릿이 응답에 복창(에코)됐음을 나타내는 시그니처.
# 이런 텍스트가 총평으로 노출되면 안 되므로 감지 시 해당 후보를 버린다.
_PROMPT_ECHO_SIGNATURES = (
    "[중요]",
    "작성 규칙",
    "출력 형식",
    "advisor 진단 근거",
    "JSON만 출력",
    "improvements 키",
    "5~7문장",
    "진단 근거 기반 1~2문장",
    "<think>",
)


def _looks_like_prompt_echo(text: str) -> bool:
    if not text:
        return False
    return any(sig in text for sig in _PROMPT_ECHO_SIGNATURES)


def _fallback_report() -> dict:
    return {"total_summary": FALLBACK_SUMMARY, "strengths": [], "weaknesses": [], "improvements": []}


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
        if normalized and not _looks_like_prompt_echo(normalized["total_summary"]):
            return normalized

    # 닫히지 않은 <think>(추론이 토큰 한도까지 이어진 경우) 이후는 전부 내부 추론이다.
    # JSON 추출에 실패한 뒤의 텍스트 기반 폴백 경로에는 절대 흘려보내지 않는다.
    unclosed_think = re.search(r"<think>", text, flags=re.IGNORECASE)
    if unclosed_think:
        text = text[: unclosed_think.start()].strip()

    # 프롬프트 지시문을 복창한 출력이면 텍스트 폴백 자체를 포기한다 — 지시문이
    # 총평으로 노출되는 것보다 "다시 시도" 안내가 낫다.
    if _looks_like_prompt_echo(text):
        return _fallback_report()

    partial_json = _extract_partial_json_report(text)
    if partial_json and not _looks_like_prompt_echo(partial_json["total_summary"]):
        return partial_json

    section_based = _extract_report_from_sections(text)
    if section_based and not _looks_like_prompt_echo(section_based["total_summary"]):
        return section_based

    plain = _extract_plain_summary(text)
    if _looks_like_prompt_echo(plain):
        return _fallback_report()
    return {"total_summary": plain, "strengths": [], "weaknesses": [], "improvements": []}


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

    result = generate(model, tokenizer, prompt=formatted, max_tokens=1200, verbose=False)
    return result.strip()


def summarize_ollama(prompt: str) -> str:
    import urllib.request

    from llm_backend import ollama_auth_headers  # Modal proxy-auth (배포 시)
    from engine.nl_parser import _OLLAMA_NUM_CTX, _ollama_ensure_warm, _ollama_open_with_retry

    body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            # Qwen3 계열 thinking 우회 — 이게 없으면 <think> 내부 추론이 응답에 섞여
            # 파싱 실패 시 프롬프트 지시문·추론 텍스트가 총평으로 노출된다(nl_parser와 동일 정책).
            "think": False,
            # MLX(summarize_mlx) 경로와 동일하게 greedy/결정론적으로 생성한다.
            # num_ctx: grounded 프롬프트가 기본 컨텍스트(4096)를 넘을 수 있어 nl_parser와 동일값 사용.
            "options": {"temperature": 0, "num_predict": 1200, "num_ctx": _OLLAMA_NUM_CTX},
        }
    ).encode()

    # Modal scale-to-zero 콜드스타트 내성 — 코치/NL파서와 동일하게
    # ① 본문 없는 GET으로 컨테이너를 먼저 깨우고(콜드 첫 POST body 유실 방지)
    # ② POST는 재시도 예산 안에서 연다. (기존 단발 60s urlopen은 콜드에서 항상 실패했다)
    _ollama_ensure_warm()
    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json", **ollama_auth_headers()},
        method="POST",
    )
    with _ollama_open_with_retry(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return (data.get("message") or {}).get("content", "").strip()


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
        from llm_backend import resolve_llm_backend
        use_mlx = resolve_llm_backend() == "mlx"
        raw = summarize_mlx(prompt) if use_mlx else summarize_ollama(prompt)
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
