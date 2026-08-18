"""리밸런싱 기간별 결과 비교 분석 (FR-BT-064).

같은 전략을 매일·매주·매월·분기·반기·연간 6가지 리밸런싱 주기로 다시 백테스트해 성과를
비교하고, 그 수치 위에서 LLM이 민감도·거래비용·과최적화·전략 성격을 서술한다.

역할 분담(AI 리포트와 같은 하이브리드):
- 백테스트 실행·지표 추출·순위·인접 주기 차이·기간 길이 같은 **근거는 전부 결정론**으로 만든다.
- LLM은 전달받은 근거만으로 서술 JSON(summary/comparison_table/analysis/recommendation)을 쓴다.
  비교표의 숫자는 LLM 출력을 쓰지 않고 엔진 값을 그대로 싣는다(LLM은 주기별 `evaluation`
  한 줄만 채운다) — 소형 모델의 숫자 옮겨 적기 오류를 구조적으로 배제한다.
- LLM 출력은 형식만 검증·정규화한다(주기 별칭 통일, 등급 A~D, 신뢰도 0~100 clamp).
  추천 주기가 실제 실행된 주기 밖이면 파싱 실패로 보고 degraded로 보고한다(임의 보정 금지).
"""

from __future__ import annotations

import copy
import json
import math
import time
from typing import Any, Callable, Dict, List, Optional

# 비교 대상 6주기 — 짧은 주기 → 긴 주기 순(인접 주기 비교의 기준 순서).
REBALANCE_PERIODS: tuple[str, ...] = ("daily", "weekly", "monthly", "quarterly", "semiannual", "yearly")

PERIOD_LABELS_KO: Dict[str, str] = {
    "daily": "매일",
    "weekly": "매주",
    "monthly": "매월",
    "quarterly": "분기",
    "semiannual": "반기",
    "yearly": "연간",
    "bimonthly": "격월",
    "none": "리밸런싱 없음",
}

# LLM이 낼 수 있는 표기 별칭 → 엔진 정본 키 (형식 정규화 — 의미 판정이 아님).
_PERIOD_ALIASES: Dict[str, str] = {
    "daily": "daily", "day": "daily", "매일": "daily",
    "weekly": "weekly", "week": "weekly", "매주": "weekly",
    "monthly": "monthly", "month": "monthly", "매월": "monthly", "월간": "monthly",
    "quarterly": "quarterly", "quarter": "quarterly", "분기": "quarterly",
    "semiannual": "semiannual", "semi-annual": "semiannual", "semi_annual": "semiannual",
    "semiannually": "semiannual", "semi-annually": "semiannual", "half-yearly": "semiannual",
    "halfyearly": "semiannual", "biannual": "semiannual", "반기": "semiannual",
    "yearly": "yearly", "annual": "yearly", "annually": "yearly", "year": "yearly", "연간": "yearly",
    "none": "none",
}

# 결과 지표 정밀도(응답 크기·프롬프트 길이 절약).
_ROUND = 4


def normalize_period(value: Any) -> Optional[str]:
    """LLM/외부 표기를 엔진 정본 주기 키로 통일한다. 모르면 None."""
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "")
    return _PERIOD_ALIASES.get(key)


def _finite(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, _ROUND)


def compute_turnover(signals: List[Dict[str, Any]], equity: List[Any]) -> float:
    """회전율(%) = (총 매수·매도 체결금액 / 2) / 기간 평균 자산 × 100.

    프론트 결과 화면(BacktestDashboard.calculateTurnoverRate)과 같은 산식이라 메인 결과의
    회전율과 비교표의 회전율이 같은 잣대다.
    """
    valid_equity = [float(v) for v in (equity or []) if _finite(v) is not None and float(v) > 0]
    if not valid_equity:
        return 0.0
    total = 0.0
    for sig in signals or []:
        amount = _finite(sig.get("amount"))
        if amount is None or abs(amount) <= 0:
            price = _finite(sig.get("price")) or 0.0
            qty = _finite(sig.get("quantity")) or 0.0
            amount = price * qty
        total += abs(amount)
    average_assets = sum(valid_equity) / len(valid_equity)
    return (total / 2.0 / average_assets) * 100.0 if average_assets > 0 else 0.0


def extract_period_metrics(period: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """엔진 결과 dict → 비교표 한 행(결정론)."""
    cagr = _finite(result.get("cagr"))
    mdd = _finite(result.get("maxDrawdown"))
    calmar = _finite(result.get("calmar"))
    if calmar is None and cagr is not None and mdd not in (None, 0.0):
        calmar = cagr / abs(mdd)
    equity = result.get("equity") or []
    return {
        "period": period,
        "cagr": _round(cagr),
        "mdd": _round(mdd),
        "sharpe_ratio": _round(_finite(result.get("sharpe"))),
        # None = 손실 거래 0건(∞). 0.0(이익 없음)과 다르다 — 엔진 계약 그대로 전달.
        "profit_factor": _round(_finite(result.get("profitFactor"))),
        "trade_count": int(result.get("trades") or 0),
        "turnover": _round(compute_turnover(result.get("signals") or [], equity)),
        "total_return": _round(_finite(result.get("totalReturn"))),
        "win_rate": _round(_finite(result.get("winRate"))),
        "calmar": _round(calmar),
        "final_equity": _round(_finite(equity[-1]) if equity else None),
        "error": None,
    }


def rebalance_applies(base_request: Dict[str, Any]) -> bool:
    """리밸런싱 주기가 결과에 영향을 주는 전략인가(시뮬레이터의 rebalance_mode 조건과 동일).

    보유 상한(max_positions)·비율 선정(max_positions_pct)·분위 그룹이 없거나 포지션 설정을
    건너뛰는 전략은 주기를 바꿔도 6번 모두 같은 결과가 나온다 — 헛된 실행 전에 알린다.
    """
    risk = base_request.get("risk") or base_request.get("risk_params") or {}
    if risk.get("skip_position_setting"):
        return False
    return bool(
        risk.get("max_positions") or risk.get("max_positions_pct") or risk.get("ranking_quantile_groups")
    )


def build_request_for_period(base_request: Dict[str, Any], period: str) -> Dict[str, Any]:
    req = copy.deepcopy(base_request)
    risk = req.get("risk")
    if not isinstance(risk, dict):
        risk = dict(req.get("risk_params") or {})
        req["risk"] = risk
    risk["rebalancing_period"] = period
    return req


def run_rebalance_backtests(
    engine,
    base_request: Dict[str, Any],
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    periods: tuple[str, ...] = REBALANCE_PERIODS,
) -> Dict[str, Any]:
    """6주기 백테스트를 순차 실행해 행 목록과 백테스트 기간을 돌려준다(결정론)."""
    rows: List[Dict[str, Any]] = []
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    total = len(periods)
    for index, period in enumerate(periods, start=1):
        if should_cancel and should_cancel():
            return {"status": "cancelled", "rebalance_results": rows, "backtest_period": None}
        if progress_callback:
            progress_callback({"stage": "backtest", "period": period, "index": index, "total": total})
        started = time.perf_counter()
        try:
            result = engine.run_backtest(build_request_for_period(base_request, period))
            row = extract_period_metrics(period, result)
            dates = result.get("dates") or []
            if dates and period_start is None:
                period_start, period_end = str(dates[0]), str(dates[-1])
        except Exception as exc:  # noqa: BLE001 — 한 주기 실패가 전체 비교를 죽이지 않게 행 단위로 기록
            row = {"period": period, "error": str(exc)}
        row["elapsed_s"] = round(time.perf_counter() - started, 2)
        rows.append(row)
    return {
        "status": "ok",
        "rebalance_results": rows,
        "backtest_period": {"start": period_start, "end": period_end} if period_start else None,
    }


# ── 결정론 근거 ───────────────────────────────────────────────────────────────

def _years_between(start: Optional[str], end: Optional[str]) -> Optional[float]:
    if not start or not end:
        return None
    try:
        from datetime import date
        s = date.fromisoformat(str(start)[:10])
        e = date.fromisoformat(str(end)[:10])
    except ValueError:
        return None
    return round(max((e - s).days, 0) / 365.25, 2)


def _rank(rows: List[Dict[str, Any]], key: str, reverse: bool, transform=lambda v: v) -> Dict[str, int]:
    scored = [(r["period"], transform(r[key])) for r in rows if r.get(key) is not None]
    scored.sort(key=lambda item: item[1], reverse=reverse)
    return {period: rank for rank, (period, _) in enumerate(scored, start=1)}


def build_evidence(rows: List[Dict[str, Any]], backtest_period: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """LLM이 인용할 결정론 근거 — 순위·인접 주기 차이·CAGR 분산·거래 빈도 배수·기간 길이."""
    valid = [r for r in rows if not r.get("error")]
    years = _years_between((backtest_period or {}).get("start"), (backtest_period or {}).get("end"))
    evidence: Dict[str, Any] = {
        "valid_periods": [r["period"] for r in valid],
        "failed_periods": [r["period"] for r in rows if r.get("error")],
        "backtest_years": years,
        "short_backtest": bool(years is not None and years < 3),
    }
    if not valid:
        return evidence

    ranks = {
        "sharpe_ratio": _rank(valid, "sharpe_ratio", reverse=True),
        "cagr": _rank(valid, "cagr", reverse=True),
        "mdd": _rank(valid, "mdd", reverse=False, transform=abs),  # 낮은 낙폭이 1위
        "calmar": _rank(valid, "calmar", reverse=True),
        "profit_factor": _rank(valid, "profit_factor", reverse=True),
    }
    evidence["ranks"] = ranks
    evidence["best_by"] = {
        metric: next((p for p, r in table.items() if r == 1), None) for metric, table in ranks.items()
    }

    cagrs = [r["cagr"] for r in valid if r.get("cagr") is not None]
    if cagrs:
        spread = max(cagrs) - min(cagrs)
        evidence["cagr_spread"] = _round(spread)
        evidence["cagr_max"] = _round(max(cagrs))
        evidence["cagr_min"] = _round(min(cagrs))
        peak = max(abs(v) for v in cagrs)
        evidence["cagr_spread_ratio"] = _round(spread / peak) if peak > 0 else None

    ordered = sorted(valid, key=lambda r: REBALANCE_PERIODS.index(r["period"]))
    adjacent = []
    for prev, nxt in zip(ordered, ordered[1:]):
        adjacent.append({
            "from": prev["period"],
            "to": nxt["period"],
            "cagr_diff": _round((nxt["cagr"] or 0) - (prev["cagr"] or 0)) if prev.get("cagr") is not None and nxt.get("cagr") is not None else None,
            "sharpe_diff": _round((nxt["sharpe_ratio"] or 0) - (prev["sharpe_ratio"] or 0)) if prev.get("sharpe_ratio") is not None and nxt.get("sharpe_ratio") is not None else None,
        })
    evidence["adjacent"] = adjacent

    counts = {r["period"]: r.get("trade_count") or 0 for r in valid}
    longest = ordered[-1]["period"]
    shortest = ordered[0]["period"]
    if counts.get(longest):
        evidence["trade_count_ratio_shortest_to_longest"] = _round(counts[shortest] / counts[longest])
    evidence["shortest_period"] = shortest
    evidence["longest_period"] = longest
    return evidence


# ── LLM 프롬프트 ─────────────────────────────────────────────────────────────

_ROLE_AND_RULES = """# Role
당신은 퀀트 투자 분석 전문가입니다.
백테스트 결과를 기반으로 리밸런싱 주기별 성과 차이를 분석하고,
사용자가 전략의 적절한 운용 주기를 이해할 수 있도록 설명하는 역할을 수행합니다.

# Objective
사용자가 생성한 투자 전략에 대해 다양한 리밸런싱 기간별 백테스트 결과를 비교 분석합니다.
분석 대상 주기: daily(매일) / weekly(매주) / monthly(매월) / quarterly(분기) / semiannual(반기) / yearly(연간)

# Analysis Requirements
## 1. 성과 비교 분석
각 리밸런싱 기간별로 CAGR, MDD, Sharpe Ratio, Profit Factor, 거래 횟수, 포트폴리오 회전율(Turnover)을 비교합니다.
단순히 가장 높은 수익률만 평가하지 않고 위험 대비 수익성, 안정성, 거래 비용 가능성, 과최적화 가능성을 함께 고려합니다.

## 2. 최적 리밸런싱 기간 선정
선정 기준: (1) Sharpe Ratio가 높은 기간 (2) CAGR 대비 MDD가 낮은 기간 (3) 거래 빈도가 과도하지 않은 기간
(4) 인접한 리밸런싱 기간에서도 성능이 유지되는 기간 (5) 특정 기간에만 성과가 집중되지 않는 기간.
단순히 CAGR이 가장 높은 기간을 선정하지 않습니다.

## 3. 리밸런싱 민감도 분석
인접 주기 간 CAGR·Sharpe가 완만하게 이어지면 주기에 크게 의존하지 않는 안정적인 전략,
특정 주기에서만 성과가 튀면 그 주기에 과적합 가능성이 있다고 평가합니다.

## 4. 거래 비용 영향 분석
리밸런싱 빈도가 늘 때의 거래 횟수·수수료·슬리피지·시장 충격 비용 증가를 분석하고,
단기 리밸런싱의 성과가 거래 비용 반영 후 줄어들 가능성을 평가합니다.

## 5. 전략 특성 추론
짧은 주기에서 우수하면 단기 모멘텀·시장 타이밍 성격, 긴 주기에서도 유지되면 가치·장기 팩터 성격,
특정 주기에서만 우수하면 과최적화 가능성으로 추론합니다.

# Rules
- CAGR이 가장 높은 기간을 자동으로 고르지 않는다.
- 백테스트 기간이 짧으면(3년 미만) 높은 신뢰도(confidence_score)를 부여하지 않는다.
- 리밸런싱 기간 하나만 보고 결론 내리지 않는다.
- 인접 기간 간 성능 안정성을 반드시 평가한다.
- 투자 조언처럼 표현하지 않고 데이터 기반 분석으로 표현한다("~하세요/~해야 합니다" 금지, "과거 데이터 기준 ~였다" 형식).
- 숫자는 아래 [입력 데이터]와 [결정론 근거]에 있는 값만 인용한다. 새로 계산하거나 지어내지 않는다.
- period 값은 반드시 daily/weekly/monthly/quarterly/semiannual/yearly 중 하나를 그대로 쓴다(번역·별칭 금지).
- 실행에 실패한 주기(failed_periods)는 선정 대상에서 제외한다.
"""

_OUTPUT_FORMAT = """# Output Format
반드시 아래 JSON 형식 **하나만** 출력한다(설명·코드펜스·머리말 금지). 서술 값은 한국어 문장으로 쓴다.
{
  "summary": {
    "recommended_rebalance_period": "monthly",
    "confidence_score": 0,
    "strategy_character": "",
    "stability_rating": "A/B/C/D"
  },
  "comparison_table": [
    { "period": "daily", "evaluation": "" },
    { "period": "weekly", "evaluation": "" },
    { "period": "monthly", "evaluation": "" },
    { "period": "quarterly", "evaluation": "" },
    { "period": "semiannual", "evaluation": "" },
    { "period": "yearly", "evaluation": "" }
  ],
  "analysis": {
    "performance_analysis": "",
    "risk_analysis": "",
    "transaction_cost_analysis": "",
    "overfitting_analysis": ""
  },
  "recommendation": {
    "recommended_period": "",
    "reason": "",
    "warning": ""
  }
}
- confidence_score: 0~100 정수. stability_rating: A(주기 무관 안정)/B/C/D(특정 주기 과적합 의심) 중 한 글자.
- comparison_table의 evaluation은 해당 주기 한 줄 평가(숫자는 입력값 인용). 다른 필드는 넣지 않는다.
"""


def build_rebalance_prompt(payload: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    input_block = json.dumps(payload, ensure_ascii=False, indent=2)
    evidence_block = json.dumps(evidence, ensure_ascii=False, indent=2)
    return (
        f"{_ROLE_AND_RULES}\n"
        f"# Input Data\n[입력 데이터]\n{input_block}\n\n"
        f"[결정론 근거] (순위 1=가장 좋음. mdd 순위는 낙폭이 작을수록 1위)\n{evidence_block}\n\n"
        f"{_OUTPUT_FORMAT}"
    )


# ── LLM 출력 파싱(형식 검증·정규화만) ─────────────────────────────────────────

_RATINGS = ("A", "B", "C", "D")


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _coerce_confidence(value: Any) -> Optional[int]:
    score = _finite(value)
    if score is None:
        return None
    if 0 < score <= 1:
        score *= 100  # 0.7 같은 비율 표기 허용
    return int(max(0, min(100, round(score))))


def _coerce_rating(value: Any) -> Optional[str]:
    text = _clean_text(value).upper()
    if not text:
        return None
    first = text[0]
    return first if first in _RATINGS else None


def parse_rebalance_analysis(text: str, valid_periods: List[str]) -> Optional[Dict[str, Any]]:
    """LLM 출력 → 분석 dict. 형식 위반(필수 섹션 없음·추천 주기가 실행 주기 밖)이면 None."""
    from ai.summarize import _extract_json_objects, _parse_json_candidate  # 코드펜스·<think> 제거 후 JSON 경계 추출
    import re

    cleaned = re.sub(r"<think>[\s\S]*?</think>\s*", "", text or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```", "", cleaned).strip()

    for candidate in _extract_json_objects(cleaned):
        data = _parse_json_candidate(candidate)
        if not data:
            continue
        normalized = _coerce_analysis_shape(data, valid_periods)
        if normalized:
            return normalized
    return None


def _coerce_analysis_shape(data: Dict[str, Any], valid_periods: List[str]) -> Optional[Dict[str, Any]]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    recommendation = data.get("recommendation") if isinstance(data.get("recommendation"), dict) else {}
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}

    recommended = normalize_period(
        summary.get("recommended_rebalance_period") or recommendation.get("recommended_period")
    )
    if recommended is None or recommended not in valid_periods:
        return None
    if not analysis:
        return None

    evaluations: Dict[str, str] = {}
    table = data.get("comparison_table")
    if isinstance(table, list):
        for item in table:
            if not isinstance(item, dict):
                continue
            period = normalize_period(item.get("period"))
            evaluation = _clean_text(item.get("evaluation"))
            if period and evaluation:
                evaluations[period] = evaluation

    return {
        "summary": {
            "recommended_rebalance_period": recommended,
            "confidence_score": _coerce_confidence(summary.get("confidence_score")),
            "strategy_character": _clean_text(summary.get("strategy_character")),
            "stability_rating": _coerce_rating(summary.get("stability_rating")),
        },
        "evaluations": evaluations,
        "analysis": {
            "performance_analysis": _clean_text(analysis.get("performance_analysis")),
            "risk_analysis": _clean_text(analysis.get("risk_analysis")),
            "transaction_cost_analysis": _clean_text(analysis.get("transaction_cost_analysis")),
            "overfitting_analysis": _clean_text(analysis.get("overfitting_analysis")),
        },
        "recommendation": {
            "recommended_period": normalize_period(recommendation.get("recommended_period")) or recommended,
            "reason": _clean_text(recommendation.get("reason")),
            "warning": _clean_text(recommendation.get("warning")),
        },
    }


# ── 진입점 ────────────────────────────────────────────────────────────────────

def _default_llm(prompt: str) -> str:
    """AI 리포트와 같은 9B Ollama 경로(think:false, UI 언어 지시 부착)."""
    from ai.summarize import summarize_ollama
    import ui_language

    return summarize_ollama(ui_language.append_directive(prompt), num_predict=1800)


NO_POSITION_CAP_NOTICE = (
    "이 전략은 최대 보유 종목 수·비율 선정이 없어 리밸런싱 주기가 결과에 영향을 주지 않습니다 — "
    "6주기 결과가 모두 같게 나올 수 있어요. 리밸런싱은 보유 종목 집합을 주기마다 다시 고르는 설정이라, "
    "보유 상한이 있는 전략에서 차이가 납니다."
)


def analyze_rebalance_comparison(
    engine,
    base_request: Dict[str, Any],
    *,
    strategy_name: Optional[str] = None,
    investment_universe: Optional[str] = None,
    current: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    llm: Optional[Callable[[str], str]] = None,
    llm_attempts: int = 2,
) -> Dict[str, Any]:
    """6주기 백테스트 + 결정론 근거 + LLM 서술. LLM 실패 시 표(수치)는 그대로 두고 degraded 표기.

    보유 상한이 없는 전략도 막지 않고 6주기를 그대로 계산한다(2026-08-18 사용자 지시 — 리밸런싱
    설정이 없어도 그냥 계산해 보여줄 것). 이 경우 결과가 모두 같을 수 있음을 notices로 알린다.
    """
    notices: List[str] = []
    if not rebalance_applies(base_request):
        notices.append(NO_POSITION_CAP_NOTICE)

    run = run_rebalance_backtests(engine, base_request, progress_callback, should_cancel)
    if run["status"] == "cancelled":
        return {"status": "cancelled", "message": "리밸런싱 비교 분석이 취소되었습니다."}

    rows = run["rebalance_results"]
    backtest_period = run["backtest_period"]
    valid_rows = [r for r in rows if not r.get("error")]
    if not valid_rows:
        first_error = next((r.get("error") for r in rows if r.get("error")), "백테스트 실행 실패")
        return {"status": "error", "message": f"리밸런싱 주기별 백테스트가 모두 실패했습니다: {first_error}"}

    evidence = build_evidence(rows, backtest_period)
    if notices:
        # LLM이 동일한 6행을 '주기 무관 안정'으로 오독하지 않게 근거에 사실을 적는다.
        evidence["position_cap_absent"] = True
        evidence["note"] = "보유 상한이 없어 리밸런싱 주기가 결과에 영향을 주지 않는 전략 — 6주기 결과가 같으면 주기 효과가 없는 것이지 안정성의 증거가 아니다."
    risk = base_request.get("risk") or base_request.get("risk_params") or {}
    current_period = normalize_period(risk.get("rebalancing_period")) or str(risk.get("rebalancing_period") or "none")

    # LLM 입력은 소수 2자리로 줄인다(서술이 4자리 숫자를 그대로 옮겨 적는 것을 막는다) — 표는 원값.
    def _prompt_row(row: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for key in ("period", "cagr", "mdd", "sharpe_ratio", "profit_factor", "trade_count", "turnover"):
            value = row.get(key)
            out[key] = round(value, 2) if isinstance(value, float) else value
        return out

    payload: Dict[str, Any] = {
        "strategy_name": strategy_name or "",
        "investment_universe": investment_universe or "",
        "backtest_period": backtest_period,
        "current_setting": {**_prompt_row(dict(current or {})), "period": current_period},
        "rebalance_results": [_prompt_row(r) for r in valid_rows],
    }

    result: Dict[str, Any] = {
        "status": "ok",
        "current_period": current_period,
        "backtest_period": backtest_period,
        "rebalance_results": rows,
        "evidence": evidence,
        "notices": notices,
        "analysis": None,
        "analysis_degraded": False,
    }

    if progress_callback:
        progress_callback({"stage": "analysis"})
    if should_cancel and should_cancel():
        return {"status": "cancelled", "message": "리밸런싱 비교 분석이 취소되었습니다."}

    call_llm = llm or _default_llm
    prompt = build_rebalance_prompt(payload, evidence)
    valid_periods = [r["period"] for r in valid_rows]
    started = time.perf_counter()
    parsed = None
    last_error: Optional[str] = None
    for _ in range(max(1, llm_attempts)):
        try:
            raw = call_llm(prompt)
        except Exception as exc:  # noqa: BLE001 — LLM 장애는 표를 살린 채 degraded로 보고
            last_error = repr(exc)
            continue
        parsed = parse_rebalance_analysis(raw, valid_periods)
        if parsed:
            break
        last_error = "LLM 출력 형식 불일치"
    result["runtime"] = {"backend": "ollama", "llm_ms": round((time.perf_counter() - started) * 1000, 2)}
    if parsed:
        result["analysis"] = parsed
    else:
        result["analysis_degraded"] = True
        result["analysis_error"] = last_error
    return result
