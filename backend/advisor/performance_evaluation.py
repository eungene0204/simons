"""
Performance evaluation for experiment-learned advisor responses.

The pipeline compares a baseline advisor without experiment-learning retrieval
against the learned advisor using the same JSONL learning cases.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .agent import StrategyAdvisorAgent
from .experiment_learning import DEFAULT_LEARNING_DIR, ExperimentLearningProvider
from .schemas import AdvisorRequest, AdvisorResponse


PROHIBITED_PHRASES = (
    "매수 추천",
    "투자 추천",
    "수익 보장",
    "반드시 오른",
    "확실한 수익",
    "미래 수익을 보장",
)


class NullLearningProvider:
    def build_insight(self, parsed_strategy: Dict[str, Any], user_prompt: str = "") -> Dict[str, Any]:
        return {
            "source_file": None,
            "matched_blocks": [],
            "matched_rules": [],
            "matched_patterns": [],
            "similar_samples": [],
            "recommended_advice": [],
            "recommended_adjustments": [],
            "warnings": [],
            "confidence": "low",
            "similar_strategy_count": 0,
            "median_cagr": None,
            "median_sharpe": None,
            "median_mdd": None,
        }


@dataclass
class AdvisorCase:
    user_prompt: str
    category: str
    risk_profile: str
    parsed_blocks: List[str]
    extracted_parameters: Dict[str, Any]


@dataclass
class ResponseScore:
    total: float
    evidence_coverage: float
    grounded_advice: float
    confidence_disclosure: float
    risk_action_specificity: float
    safety: float


@dataclass
class CaseComparison:
    user_prompt: str
    category: str
    risk_profile: str
    baseline_score: ResponseScore
    learned_score: ResponseScore
    improvement: float
    learned_confidence: str
    similar_strategy_count: int


@dataclass
class AdvisorEvaluationReport:
    total_cases: int
    baseline_average_score: float
    learned_average_score: float
    absolute_improvement: float
    relative_improvement_pct: float
    evidence_coverage_rate: float
    grounded_advice_rate: float
    confidence_disclosure_rate: float
    safety_pass_rate: float
    cases: List[CaseComparison]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def load_advisor_cases(
    learning_dir: Path = DEFAULT_LEARNING_DIR,
    limit: Optional[int] = None,
) -> List[AdvisorCase]:
    rows = _read_jsonl(learning_dir / "strategy_advisor_learning_dataset.jsonl")
    cases: List[AdvisorCase] = []
    for row in rows:
        input_data = row.get("input") or {}
        cases.append(AdvisorCase(
            user_prompt=str(input_data.get("user_prompt") or ""),
            category=str(input_data.get("category") or "unknown"),
            risk_profile=str(input_data.get("risk_profile") or "unknown"),
            parsed_blocks=[str(block) for block in input_data.get("parsed_blocks") or []],
            extracted_parameters=dict(input_data.get("extracted_parameters") or {}),
        ))
        if limit is not None and len(cases) >= limit:
            break
    return cases


def _filter(metric: str, operator: str, value: Any) -> Dict[str, Any]:
    return {"metric": metric, "operator": operator, "value": value}


def case_to_parsed_strategy(case: AdvisorCase) -> Dict[str, Any]:
    blocks = set(case.parsed_blocks)
    params = case.extracted_parameters
    filters = []
    entry_signals = []
    if "pbr" in blocks:
        filters.append(_filter("pbr", "<=", params.get("pbr_threshold", 1.0)))
    if "per" in blocks:
        filters.append(_filter("per", "<=", params.get("per_threshold", 12)))
    if "roe" in blocks:
        filters.append(_filter("roe", ">=", params.get("roe_threshold", 10)))
    if "trading_value" in blocks:
        filters.append(_filter("trading_value", ">=", params.get("trading_value", 10)))
    if "rsi" in blocks:
        entry_signals.append({"indicator": "rsi", "threshold": params.get("rsi_threshold", 30)})
    if "macd" in blocks:
        entry_signals.append({"indicator": "macd"})
    if "ma_crossover" in blocks:
        entry_signals.append({"indicator": "ma_cross"})
    if "bollinger_band" in blocks:
        entry_signals.append({"indicator": "bollinger"})
    if "volume_spike" in blocks:
        entry_signals.append({"indicator": "volume_spike"})
    if "ai_prediction" in blocks:
        entry_signals.append({"indicator": "ai_model"})

    return {
        "universe": ["KOSPI200"],
        "entry_signals": entry_signals,
        "exit_signals": [],
        "fundamental_filters": filters,
        "stop_loss_pct": params.get("stop_loss_pct") if "stop_loss" in blocks else None,
        "take_profit_pct": params.get("take_profit_pct") if "take_profit" in blocks else None,
        "trailing_stop_pct": params.get("trailing_stop_pct") if "trailing_stop" in blocks else None,
        "hold_period_days": params.get("max_holding_days") if "max_holding_days" in blocks else None,
        "max_positions": params.get("max_positions", 10),
        "initial_capital": 10_000_000,
    }


def _advice_text(response: AdvisorResponse) -> str:
    return " ".join(f"{item.title} {item.body}" for item in response.advice)


def _has_prohibited_claim(text: str) -> bool:
    safe_text = text.replace("투자 추천이 아니라", "").replace("투자 추천이 아닌", "")
    return any(phrase in safe_text for phrase in PROHIBITED_PHRASES)


def score_response(response: AdvisorResponse) -> ResponseScore:
    learning = response.strategy_experiment_learning or {}
    text = _advice_text(response)
    similar_count = int(learning.get("similar_strategy_count") or 0)
    has_metrics = any(learning.get(key) is not None for key in ("median_cagr", "median_sharpe", "median_mdd"))
    evidence_coverage = 1.0 if similar_count > 0 and has_metrics else 0.0
    grounded_advice = 1.0 if "전략 실험 근거" in text or "실험군의 결과" in text or "비슷한 전략의 결과" in text else 0.0
    confidence_disclosure = 1.0 if "비슷한 실험 샘플 수" in text or "성과 신호가 거의 없었습니다" in text else 0.0
    risk_action_specificity = 1.0 if learning.get("recommended_adjustments") or any(item.proposed_change for item in response.advice) else 0.0
    safety = 0.0 if _has_prohibited_claim(text) else 1.0
    total = (
        evidence_coverage * 0.30
        + grounded_advice * 0.25
        + confidence_disclosure * 0.15
        + risk_action_specificity * 0.15
        + safety * 0.15
    )
    return ResponseScore(
        total=round(total, 4),
        evidence_coverage=evidence_coverage,
        grounded_advice=grounded_advice,
        confidence_disclosure=confidence_disclosure,
        risk_action_specificity=risk_action_specificity,
        safety=safety,
    )


def _average(values: Iterable[float]) -> float:
    values = list(values)
    return round(sum(values) / len(values), 4) if values else 0.0


class AdvisorPerformanceEvaluator:
    def __init__(self, learning_dir: Path = DEFAULT_LEARNING_DIR) -> None:
        self.learning_dir = learning_dir

    def evaluate(self, limit: Optional[int] = None) -> AdvisorEvaluationReport:
        cases = load_advisor_cases(self.learning_dir, limit)
        baseline_agent = StrategyAdvisorAgent(learning_provider=NullLearningProvider())
        learned_agent = StrategyAdvisorAgent(learning_provider=ExperimentLearningProvider(self.learning_dir))
        comparisons: List[CaseComparison] = []

        for case in cases:
            parsed_strategy = case_to_parsed_strategy(case)
            request = AdvisorRequest(user_prompt=case.user_prompt, parsed_strategy=parsed_strategy)
            baseline = baseline_agent.review(request)
            learned = learned_agent.review(request)
            baseline_score = score_response(baseline)
            learned_score = score_response(learned)
            insight = learned.strategy_experiment_learning or {}
            comparisons.append(CaseComparison(
                user_prompt=case.user_prompt,
                category=case.category,
                risk_profile=case.risk_profile,
                baseline_score=baseline_score,
                learned_score=learned_score,
                improvement=round(learned_score.total - baseline_score.total, 4),
                learned_confidence=str(insight.get("confidence") or "low"),
                similar_strategy_count=int(insight.get("similar_strategy_count") or 0),
            ))

        baseline_avg = _average(item.baseline_score.total for item in comparisons)
        learned_avg = _average(item.learned_score.total for item in comparisons)
        absolute = round(learned_avg - baseline_avg, 4)
        relative = round((absolute / baseline_avg) * 100, 2) if baseline_avg > 0 else 0.0
        return AdvisorEvaluationReport(
            total_cases=len(comparisons),
            baseline_average_score=baseline_avg,
            learned_average_score=learned_avg,
            absolute_improvement=absolute,
            relative_improvement_pct=relative,
            evidence_coverage_rate=_average(item.learned_score.evidence_coverage for item in comparisons),
            grounded_advice_rate=_average(item.learned_score.grounded_advice for item in comparisons),
            confidence_disclosure_rate=_average(item.learned_score.confidence_disclosure for item in comparisons),
            safety_pass_rate=_average(item.learned_score.safety for item in comparisons),
            cases=comparisons,
        )


def report_to_dict(report: AdvisorEvaluationReport, include_cases: bool = False) -> Dict[str, Any]:
    payload = asdict(report)
    if not include_cases:
        payload.pop("cases", None)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate advisor experiment-learning uplift.")
    parser.add_argument("--learning-dir", default=str(DEFAULT_LEARNING_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-cases", action="store_true")
    args = parser.parse_args()
    report = AdvisorPerformanceEvaluator(Path(args.learning_dir)).evaluate(limit=args.limit)
    print(json.dumps(report_to_dict(report, include_cases=args.include_cases), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
