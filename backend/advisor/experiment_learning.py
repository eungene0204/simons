"""
Experiment-learning retrieval for the strategy advisor.

This module reads the offline prompt experiment artifacts and returns compact
evidence that can be injected into advisor responses without model fine-tuning.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Set


DEFAULT_LEARNING_DIR = Path(__file__).resolve().parents[2] / "data" / "advisor-learning"


_FUNDAMENTAL_BLOCKS = {
    "per",
    "pbr",
    "roe",
    "roe_or_gpa",
    "debt_ratio",
    "market_cap",
    "trading_value",
    "dividend_yield",
    "revenue_growth",
    "operating_margin",
}

_INDICATOR_ALIASES = {
    "ai_model": "ai_prediction",
    "ai_prediction": "ai_prediction",
    "adx": "adx",
    "bollinger": "bollinger_band",
    "bollinger_band": "bollinger_band",
    "breakout": "breakout",
    "breakout_52w": "breakout_52w",
    "cci": "cci",
    "ema": "ema",
    "golden_cross": "ma_crossover",
    "ma": "ma_crossover",
    "ma_cross": "ma_crossover",
    "ma_crossover": "ma_crossover",
    "macd": "macd",
    "moving_average": "ma_crossover",
    "roe_or_gpa": "roe",
    "rsi": "rsi",
    "stochastic": "stochastic",
    "volume": "volume_spike",
    "volume_spike": "volume_spike",
}

_DISPLAY_LABELS = {
    "adx": "ADX",
    "bollinger_band": "볼린저밴드",
    "bollinger_bands": "볼린저밴드",
    "breakout": "돌파",
    "cci": "CCI",
    "ema": "EMA",
    "ma_crossover": "이동평균 교차",
    "macd": "MACD",
    "market_cap": "시가총액",
    "max_holding_days": "최대 보유기간",
    "max_positions": "보유 종목 수",
    "pbr": "PBR",
    "per": "PER",
    "roe": "ROE",
    "roe_or_gpa": "ROE",
    "rsi": "RSI",
    "stochastic": "스토캐스틱",
    "stop_loss": "손절",
    "take_profit": "익절",
    "trading_value": "거래대금",
    "trailing_stop": "트레일링 스탑",
    "volume_spike": "거래량 급증",
}


def _read_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    rows.append(json.loads(text))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def _normalize_block(value: Any) -> Optional[str]:
    key = str(value or "").strip().lower()
    if not key:
        return None
    return _INDICATOR_ALIASES.get(key, key if key in _FUNDAMENTAL_BLOCKS else None)


def extract_strategy_blocks(parsed_strategy: Dict[str, Any]) -> List[str]:
    blocks: Set[str] = set()
    for item in parsed_strategy.get("fundamental_filters") or []:
        block = _normalize_block(item.get("metric"))
        if block:
            blocks.add(block)
    for item in (parsed_strategy.get("entry_signals") or []) + (parsed_strategy.get("exit_signals") or []):
        block = _normalize_block(item.get("indicator") or item.get("type"))
        if block:
            blocks.add(block)
    if parsed_strategy.get("stop_loss_pct") is not None:
        blocks.add("stop_loss")
    if parsed_strategy.get("take_profit_pct") is not None:
        blocks.add("take_profit")
    if parsed_strategy.get("trailing_stop_pct") is not None:
        blocks.add("trailing_stop")
    if parsed_strategy.get("hold_period_days") is not None:
        blocks.add("max_holding_days")
    if parsed_strategy.get("max_positions") is not None:
        blocks.add("max_positions")
    return sorted(blocks)


def _extract_parameters(parsed_strategy: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    for key in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "hold_period_days", "max_positions"):
        if parsed_strategy.get(key) is not None:
            params[key] = parsed_strategy[key]
    for signal in parsed_strategy.get("entry_signals") or []:
        indicator = _normalize_block(signal.get("indicator"))
        if indicator == "rsi":
            value = signal.get("threshold") or signal.get("value")
            if value is not None:
                params["rsi_threshold"] = value
    return params


def _block_set(value: str) -> Set[str]:
    return {item for item in value.split("+") if item}


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _safe_median(values: Sequence[Any]) -> Optional[float]:
    numeric = [float(value) for value in values if isinstance(value, (int, float))]
    return median(numeric) if numeric else None


def _confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def _format_combo_description(combo: str) -> str:
    return " + ".join(_DISPLAY_LABELS.get(item, item) for item in combo.split("+") if item)


def _humanize_advice_text(text: str) -> str:
    output = text
    for key in sorted(_DISPLAY_LABELS, key=len, reverse=True):
        output = output.replace(key, _DISPLAY_LABELS[key])
    return output.replace("_", " ")


class ExperimentLearningProvider:
    def __init__(self, learning_dir: Optional[Path] = None) -> None:
        self.learning_dir = learning_dir or DEFAULT_LEARNING_DIR

    def build_insight(self, parsed_strategy: Dict[str, Any], user_prompt: str = "") -> Dict[str, Any]:
        summary_doc = _read_json(self.learning_dir / "strategy_prompt_experiment_summary.json", {})
        rules_doc = _read_json(self.learning_dir / "strategy_advisor_rules.json", {})
        dataset = _read_jsonl(self.learning_dir / "strategy_advisor_learning_dataset.jsonl")

        blocks = extract_strategy_blocks(parsed_strategy)
        block_set = set(blocks)
        summary = summary_doc.get("summary") or {}
        matched_combinations = self._match_combinations(summary.get("best_indicator_combinations") or {}, block_set)
        matched_indicators = self._match_indicators(summary.get("best_single_indicators") or {}, block_set)
        matched_samples = self._match_samples(dataset, block_set)
        matched_rules = self._match_rules(rules_doc.get("rules") or [], parsed_strategy)

        evidence = self._build_evidence(matched_combinations, matched_indicators, matched_samples)
        confidence = self._resolve_confidence(evidence, matched_combinations)
        recommended = self._build_recommended_advice(matched_combinations, matched_rules, evidence, confidence)

        return {
            "source_file": str(self.learning_dir / "strategy_prompt_experiment_summary.json"),
            "matched_blocks": blocks,
            "extracted_parameters": _extract_parameters(parsed_strategy),
            "matched_rules": matched_rules,
            "matched_patterns": matched_combinations[:3],
            "matched_single_indicators": matched_indicators[:5],
            "similar_samples": matched_samples[:5],
            "recommended_advice": recommended,
            "recommended_adjustments": self._suggest_adjustments(parsed_strategy, matched_rules),
            "warnings": self._build_warnings(confidence, matched_combinations),
            "confidence": confidence,
            "historical_pattern_quality": evidence.get("quality_score"),
            "similar_strategy_count": evidence.get("similar_strategy_count", 0),
            "median_cagr": evidence.get("median_cagr"),
            "median_sharpe": evidence.get("median_sharpe"),
            "median_mdd": evidence.get("median_mdd"),
        }

    def _match_combinations(self, combinations: Dict[str, Any], block_set: Set[str]) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for key, payload in combinations.items():
            combo_blocks = _block_set(key)
            overlap = len(block_set & combo_blocks)
            if overlap < 2 and combo_blocks != block_set:
                continue
            sample_count = int(payload.get("combination_count") or payload.get("count") or 0)
            similarity = _jaccard(block_set, combo_blocks)
            matches.append({
                "pattern_key": key,
                "blocks": sorted(combo_blocks),
                "overlap": overlap,
                "similarity": round(similarity, 3),
                "extra_blocks": sorted(combo_blocks - block_set),
                "sample_count": sample_count,
                "median_cagr": payload.get("median_cagr"),
                "median_sharpe": payload.get("median_sharpe"),
                "median_mdd": payload.get("median_mdd"),
                "median_profit_factor": payload.get("median_profit_factor"),
                "median_trades": payload.get("median_trades"),
                "quality_score": payload.get("median_quality_score"),
                "confidence": payload.get("confidence", "low"),
                "coach_guidance": payload.get("recommended_guidance"),
                "warnings": payload.get("warnings") or [],
            })
        return sorted(
            matches,
            key=lambda item: (
                item["similarity"],
                item["overlap"],
                _confidence_rank(item["confidence"]),
                item["sample_count"],
            ),
            reverse=True,
        )

    def _match_indicators(self, indicators: Dict[str, Any], block_set: Set[str]) -> List[Dict[str, Any]]:
        matches = []
        for key in sorted(block_set):
            payload = indicators.get(key)
            if payload:
                matches.append({"indicator": key, **payload})
        return sorted(matches, key=lambda item: item.get("median_quality_score") or -999, reverse=True)

    def _match_samples(self, dataset: List[Dict[str, Any]], block_set: Set[str]) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for row in dataset:
            input_data = row.get("input") or {}
            sample_blocks = set(input_data.get("parsed_blocks") or [])
            score = _jaccard(block_set, sample_blocks)
            if score < 0.34:
                continue
            evidence = (row.get("output") or {}).get("evidence") or {}
            matches.append({
                "user_prompt": input_data.get("user_prompt", ""),
                "parsed_blocks": sorted(sample_blocks),
                "similarity": round(score, 3),
                "evidence": evidence,
            })
        return sorted(matches, key=lambda item: item["similarity"], reverse=True)

    def _match_rules(self, rules: List[Dict[str, Any]], parsed_strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        has_exit = bool(parsed_strategy.get("exit_signals"))
        has_risk_exit = any(parsed_strategy.get(key) is not None for key in (
            "stop_loss_pct",
            "take_profit_pct",
            "trailing_stop_pct",
            "hold_period_days",
        ))
        matches = []
        for rule in rules:
            condition = str(rule.get("condition") or "")
            if "missing stop_loss_pct" in condition and not has_exit and not has_risk_exit:
                matches.append(rule)
        return matches

    def _build_evidence(
        self,
        combinations: List[Dict[str, Any]],
        indicators: List[Dict[str, Any]],
        samples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        primary = combinations[0] if combinations else (indicators[0] if indicators else {})
        sample_evidence = [sample.get("evidence") or {} for sample in samples]
        return {
            "similar_strategy_count": int(primary.get("sample_count") or primary.get("count") or len(samples)),
            "similarity": primary.get("similarity"),
            "median_cagr": primary.get("median_cagr") if primary else _safe_median([e.get("median_cagr") for e in sample_evidence]),
            "median_sharpe": primary.get("median_sharpe") if primary else _safe_median([e.get("median_sharpe") for e in sample_evidence]),
            "median_mdd": primary.get("median_mdd") if primary else _safe_median([e.get("median_mdd") for e in sample_evidence]),
            "quality_score": primary.get("quality_score") or primary.get("median_quality_score"),
        }

    def _resolve_confidence(self, evidence: Dict[str, Any], combinations: List[Dict[str, Any]]) -> str:
        if combinations:
            confidence = combinations[0].get("confidence", "low")
            similarity = evidence.get("similarity")
            if isinstance(similarity, (int, float)):
                if similarity < 0.5:
                    return "low"
                if similarity < 0.75 and confidence == "high":
                    return "medium"
            return confidence
        sample_count = int(evidence.get("similar_strategy_count") or 0)
        if sample_count >= 20:
            return "high"
        if sample_count >= 10:
            return "medium"
        return "low"

    def _build_recommended_advice(
        self,
        combinations: List[Dict[str, Any]],
        rules: List[Dict[str, Any]],
        evidence: Dict[str, Any],
        confidence: str,
    ) -> List[str]:
        if rules:
            return [str(rules[0].get("advice") or "청산 조건과 리스크 설정을 먼저 보완하세요.")]
        if not combinations:
            return ["비슷한 실험 데이터가 부족합니다. 현재 전략은 추가 백테스트로 먼저 검증하세요."]
        extra_blocks = combinations[0].get("extra_blocks") or []
        if extra_blocks:
            extra_text = _format_combo_description("+".join(extra_blocks))
            return [
                f"가장 가까운 실험군은 {extra_text} 조건을 함께 포함합니다. "
                "현재 전략과 완전히 같지는 않으므로, 해당 조건을 한 번에 묶지 말고 개별 후보로 분리해 비교하세요."
            ]
        guidance = combinations[0].get("coach_guidance") or "유사 실험의 중앙값 성과를 기준으로 리스크 설정을 비교하세요."
        if confidence == "low":
            return [f"실험 샘플이 부족해 확신하기 어렵습니다. {guidance}"]
        return [guidance]

    def _suggest_adjustments(self, parsed_strategy: Dict[str, Any], rules: List[Dict[str, Any]]) -> List[str]:
        if rules:
            actions = rules[0].get("suggested_actions") or []
            return [str(action) for action in actions[:3]]
        suggestions = []
        if parsed_strategy.get("stop_loss_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            suggestions.append("손절 8% 또는 트레일링 스탑 10% 추가")
        if parsed_strategy.get("take_profit_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            suggestions.append("익절 15% 또는 트레일링 스탑 추가")
        if parsed_strategy.get("hold_period_days") is None:
            suggestions.append("최대 보유기간 20일 비교")
        return suggestions[:3]

    def _build_warnings(self, confidence: str, combinations: List[Dict[str, Any]]) -> List[str]:
        warnings: List[str] = []
        if confidence == "low":
            warnings.append("실험 샘플이 부족해 단정적으로 해석하면 안 됩니다.")
        if combinations:
            warnings.extend(str(item) for item in combinations[0].get("warnings") or [])
        return list(dict.fromkeys(warnings))


def build_experiment_learning_advice(insight: Dict[str, Any]) -> Optional[str]:
    sample_count = int(insight.get("similar_strategy_count") or 0)
    if sample_count <= 0:
        return None

    metrics = []
    for label, key in (("CAGR", "median_cagr"), ("Sharpe", "median_sharpe"), ("MDD", "median_mdd")):
        value = insight.get(key)
        if isinstance(value, (int, float)):
            suffix = "%" if label != "Sharpe" else ""
            metrics.append(f"{label} 중앙값 {value:.2f}{suffix}")
    evidence = ", ".join(metrics) if metrics else "성과 중앙값은 제한적으로만 확인됨"
    advice = _humanize_advice_text(
        (insight.get("recommended_advice") or ["조건별 비교 백테스트를 먼저 진행하세요."])[0]
    )
    adjustments = [
        _humanize_advice_text(str(item))
        for item in insight.get("recommended_adjustments") or []
        if str(item).strip()
    ]
    adjustment_text = ""
    if adjustments:
        adjustment_text = f" 우선 비교할 후보는 {', '.join(adjustments[:3])}입니다."
    confidence = str(insight.get("confidence") or "low")
    confidence_label = {"high": "높음", "medium": "중간", "low": "낮음"}.get(confidence, confidence)
    if confidence == "low":
        confidence_note = "근거 수준이 낮아 이 결과만으로 결론을 내리면 안 됩니다."
    else:
        confidence_note = f"근거 수준은 {confidence_label}입니다."

    return (
        f"현재 조건과 가까운 실험군의 결과는 {evidence}입니다. "
        f"{confidence_note}{adjustment_text} 다음 백테스트에서는 현재안과 각 후보를 하나씩만 바꿔 비교하고, "
        f"MDD와 Sharpe가 동시에 나아지는 쪽만 후보로 남기세요. {advice}"
    )
