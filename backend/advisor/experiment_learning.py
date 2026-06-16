"""
Experiment-learning retrieval for the strategy advisor.

This module reads the offline prompt experiment artifacts and returns compact
evidence that can be injected into advisor responses without model fine-tuning.
"""

from __future__ import annotations

import json
import heapq
import re
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


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def _format_combo_description(combo: str) -> str:
    return " + ".join(_DISPLAY_LABELS.get(item, item) for item in combo.split("+") if item)


_PARAM_DISTANCE_SCALE = {
    "stop_loss_pct": 15.0,
    "take_profit_pct": 30.0,
    "trailing_stop_pct": 20.0,
    "hold_period_days": 60.0,
    "max_positions": 20.0,
    "rsi_threshold": 50.0,
}

_NEGATIVE_MDD_THRESHOLD = -30.0
_NEGATIVE_SHARPE_THRESHOLD = 0.0
_LOW_TRADE_THRESHOLD = 5.0
_RISK_CONTROL_BLOCKS = {
    "max_holding_days",
    "max_positions",
    "stop_loss",
    "take_profit",
    "trailing_stop",
}
_MAX_MATCHED_SAMPLES = 50


def _bounded_quality(value: Any) -> float:
    numeric = _safe_float(value)
    if numeric is None:
        return 0.0
    return max(-1.0, min(1.0, numeric))


def _sample_risk_flags(evidence: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    sharpe = _safe_float(evidence.get("median_sharpe"))
    mdd = _safe_float(evidence.get("median_mdd"))
    trades = _safe_float(evidence.get("median_trades"))
    if sharpe is not None and sharpe < _NEGATIVE_SHARPE_THRESHOLD:
        flags.append("Sharpe가 0보다 낮음")
    if mdd is not None and mdd <= _NEGATIVE_MDD_THRESHOLD:
        flags.append("MDD가 -30% 이하")
    if trades is not None and trades < _LOW_TRADE_THRESHOLD:
        flags.append("거래 수 부족")
    return flags


def _is_positive_sample(sample: Dict[str, Any]) -> bool:
    evidence = sample.get("evidence") or {}
    cagr = _safe_float(evidence.get("median_cagr"))
    sharpe = _safe_float(evidence.get("median_sharpe"))
    mdd = _safe_float(evidence.get("median_mdd"))
    quality = _safe_float(sample.get("quality_score"))
    return (
        (cagr is None or cagr > 0)
        and (sharpe is None or sharpe >= 0.35)
        and (mdd is None or mdd > _NEGATIVE_MDD_THRESHOLD)
        and (quality is None or quality >= 0)
    )


def _is_negative_sample(sample: Dict[str, Any]) -> bool:
    evidence = sample.get("evidence") or {}
    if _sample_risk_flags(evidence):
        return True
    quality = _safe_float(sample.get("quality_score"))
    return bool(quality is not None and quality < -0.05)


def _parameter_similarity(left: Dict[str, Any], right: Dict[str, Any]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 1.0

    scores = []
    for key in keys:
        left_value = _safe_float(left.get(key))
        right_value = _safe_float(right.get(key))
        if left_value is None and right_value is None:
            scores.append(1.0)
            continue
        if left_value is None or right_value is None:
            scores.append(0.35)
            continue
        scale = _PARAM_DISTANCE_SCALE.get(key, max(abs(left_value), abs(right_value), 1.0))
        scores.append(max(0.0, 1.0 - abs(left_value - right_value) / scale))
    return sum(scores) / len(scores)


def _metric_quality(evidence: Dict[str, Any]) -> float:
    cagr = _safe_float(evidence.get("median_cagr")) or 0.0
    sharpe = _safe_float(evidence.get("median_sharpe")) or 0.0
    mdd = _safe_float(evidence.get("median_mdd")) or 0.0
    profit_factor = _safe_float(evidence.get("median_profit_factor"))
    trades = _safe_float(evidence.get("median_trades"))

    score = cagr / 100.0 + sharpe * 0.25 + mdd / 100.0
    if profit_factor is not None:
        score += min(max(profit_factor - 1.0, -1.0), 2.0) * 0.08
    if trades is not None:
        score += min(trades, 100.0) / 1000.0
    return round(score, 4)


def _format_display_value(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _format_param_candidate(key: str, value: Any, current_value: Any = None) -> Optional[str]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    display = _format_display_value(numeric)
    current = _safe_float(current_value)

    def compare_or_add(label: str, suffix: str = "") -> str:
        target = f"{label} {display}{suffix}"
        if current is None:
            return f"{target} 추가 버전 비교"
        current_display = _format_display_value(current)
        return f"기준안({label} {current_display}{suffix})과 {target} 버전 비교"

    if key == "stop_loss_pct":
        return compare_or_add("손절", "%")
    if key == "take_profit_pct":
        return compare_or_add("익절", "%")
    if key == "trailing_stop_pct":
        return compare_or_add("트레일링 스탑", "%")
    if key == "hold_period_days":
        return compare_or_add("최대 보유기간", "일")
    if key == "max_positions":
        return compare_or_add("보유 종목 수", "개")
    return None


def _format_paired_delta(delta: Dict[str, Any], request_params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    changed = delta.get("changed_parameter")
    if not isinstance(changed, dict):
        return None
    candidate = None
    for key, value in changed.items():
        current = (request_params or {}).get(key)
        candidate = _format_param_candidate(key, value, current)
        if candidate:
            break
    if not candidate:
        return None

    parts = []
    for label, key, suffix in (
        ("CAGR", "cagr_delta", "%p"),
        ("Sharpe", "sharpe_delta", ""),
        ("MDD", "mdd_delta", "%p"),
        ("PF", "profit_factor_delta", ""),
    ):
        value = _safe_float(delta.get(key))
        if value is not None:
            parts.append(f"{label} {value:+.2f}{suffix}")
    if not parts:
        return candidate
    return f"{candidate}({', '.join(parts)})"


def _first_fundamental_value(parsed_strategy: Dict[str, Any], metric: str) -> Optional[float]:
    for item in parsed_strategy.get("fundamental_filters") or []:
        if str(item.get("metric") or "").lower() != metric:
            continue
        value = _safe_float(item.get("value"))
        if value is not None:
            return value
    return None


def _strategy_specific_candidates(parsed_strategy: Dict[str, Any], block_set: Set[str]) -> List[str]:
    candidates: List[str] = []

    if "rsi" in block_set:
        threshold = _safe_float(_extract_parameters(parsed_strategy).get("rsi_threshold"))
        if threshold is not None:
            low = _format_display_value(max(5.0, threshold - 5.0))
            high = _format_display_value(min(95.0, threshold + 5.0))
            candidates.append(f"RSI 진입 기준 {low}/{_format_display_value(threshold)}/{high} 비교")
        else:
            candidates.append("RSI 진입 기준 25/30/35 비교")

    if "breakout" in block_set or "breakout_52w" in block_set:
        candidates.append("신고가 기간 120일/252일 비교")

    if "macd" in block_set:
        candidates.append("MACD 확인 조건 신호선 교차/0선 돌파 비교")

    if "volume_spike" in block_set:
        candidates.append("거래량 급증 기준 1.5배/2배 비교")

    if "ma_crossover" in block_set:
        candidates.append("이동평균 기간 10/40일과 20/60일 비교")

    if "pbr" in block_set:
        value = _first_fundamental_value(parsed_strategy, "pbr")
        if value is not None and value <= 1:
            candidates.append("PBR 기준 0.8배/1.0배 비교")
        else:
            candidates.append("PBR 기준 1.0배 이하 비교")

    return candidates[:2]


def _evidence_judgment(insight: Dict[str, Any]) -> str:
    sharpe = _safe_float(insight.get("median_sharpe"))
    mdd = _safe_float(insight.get("median_mdd"))
    trades = _safe_float(insight.get("median_trades"))
    negative_count = int(insight.get("negative_sample_count") or 0)

    judgments: List[str] = []
    if sharpe is not None:
        if sharpe >= 0.7:
            judgments.append("위험 대비 수익성은 비교적 양호했습니다")
        elif sharpe <= 0:
            judgments.append("위험 대비 수익성은 약했습니다")
        else:
            judgments.append("위험 대비 수익성은 아직 확신하기 어렵습니다")
    if mdd is not None:
        if mdd <= _NEGATIVE_MDD_THRESHOLD:
            judgments.append("손실 구간이 깊어 리스크 조건을 먼저 분해해야 합니다")
        elif mdd > -20:
            judgments.append("손실 제어는 상대적으로 안정적이었습니다")
    if trades is not None and trades < _LOW_TRADE_THRESHOLD:
        judgments.append("거래 수가 적어 통계 신뢰도가 낮습니다")
    if negative_count > 0:
        judgments.append("유사 실패 패턴도 함께 확인됐습니다")

    if not judgments:
        return "성과보다 조건별 민감도 검증이 더 중요합니다"
    return ", ".join(dict.fromkeys(judgments))


class ExperimentLearningProvider:
    def __init__(self, learning_dir: Optional[Path] = None) -> None:
        self.learning_dir = learning_dir or DEFAULT_LEARNING_DIR
        self._summary_doc = _read_json(self.learning_dir / "strategy_prompt_experiment_summary.json", {})
        self._rules_doc = _read_json(self.learning_dir / "strategy_advisor_rules.json", {})
        self._dataset = _read_jsonl(self.learning_dir / "strategy_advisor_learning_dataset.jsonl")
        self._dataset_by_block = self._build_dataset_index(self._dataset)

    def build_insight(self, parsed_strategy: Dict[str, Any], user_prompt: str = "") -> Dict[str, Any]:
        blocks = extract_strategy_blocks(parsed_strategy)
        block_set = set(blocks)
        summary = self._summary_doc.get("summary") or {}
        matched_combinations = self._match_combinations(summary.get("best_indicator_combinations") or {}, block_set)
        matched_indicators = self._match_indicators(summary.get("best_single_indicators") or {}, block_set)
        request_params = _extract_parameters(parsed_strategy)
        matched_samples = self._match_samples(self._candidate_rows(block_set), block_set, request_params)
        positive_samples = [sample for sample in matched_samples if _is_positive_sample(sample)]
        negative_samples = [sample for sample in matched_samples if _is_negative_sample(sample)]
        matched_rules = self._match_rules(self._rules_doc.get("rules") or [], parsed_strategy)

        evidence = self._build_evidence(matched_combinations, matched_indicators, matched_samples, negative_samples)
        confidence = self._resolve_confidence(evidence, matched_combinations)
        recommended = self._build_recommended_advice(matched_combinations, matched_rules, evidence, confidence)

        return {
            "source_file": str(self.learning_dir / "strategy_prompt_experiment_summary.json"),
            "matched_blocks": blocks,
            "extracted_parameters": request_params,
            "matched_rules": matched_rules,
            "matched_patterns": matched_combinations[:3],
            "matched_single_indicators": matched_indicators[:5],
            "similar_samples": matched_samples[:5],
            "positive_samples": positive_samples[:3],
            "negative_samples": negative_samples[:3],
            "recommended_advice": recommended,
            "recommended_adjustments": self._suggest_adjustments(
                parsed_strategy,
                matched_rules,
                positive_samples or matched_samples,
            ),
            "warnings": self._build_warnings(confidence, matched_combinations, negative_samples),
            "confidence": confidence,
            "historical_pattern_quality": evidence.get("quality_score"),
            "similar_strategy_count": evidence.get("similar_strategy_count", 0),
            "positive_sample_count": evidence.get("positive_sample_count", 0),
            "negative_sample_count": evidence.get("negative_sample_count", 0),
            "median_cagr": evidence.get("median_cagr"),
            "median_sharpe": evidence.get("median_sharpe"),
            "median_mdd": evidence.get("median_mdd"),
            "median_profit_factor": evidence.get("median_profit_factor"),
            "median_trades": evidence.get("median_trades"),
        }

    @staticmethod
    def _build_dataset_index(dataset: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        index: Dict[str, List[Dict[str, Any]]] = {}
        for row in dataset:
            input_data = row.get("input") or {}
            for block in input_data.get("parsed_blocks") or []:
                index.setdefault(str(block), []).append(row)
        return index

    def _candidate_rows(self, block_set: Set[str]) -> List[Dict[str, Any]]:
        selective_blocks = block_set - _RISK_CONTROL_BLOCKS
        candidate_blocks = selective_blocks or block_set
        if not candidate_blocks:
            return self._dataset

        rows: Dict[int, Dict[str, Any]] = {}
        for block in candidate_blocks:
            for row in self._dataset_by_block.get(block, []):
                rows[id(row)] = row
        return list(rows.values()) or self._dataset

    def _match_combinations(self, combinations: Dict[str, Any], block_set: Set[str]) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for key, payload in combinations.items():
            combo_blocks = _block_set(key)
            overlap = len(block_set & combo_blocks)
            if overlap < 2 and combo_blocks != block_set:
                continue
            sample_count = int(payload.get("combination_count") or payload.get("count") or 0)
            similarity = _jaccard(block_set, combo_blocks)
            extra_blocks = combo_blocks - block_set
            if extra_blocks and sample_count < 5:
                similarity *= overlap / max(len(combo_blocks), 1)
            matches.append({
                "pattern_key": key,
                "blocks": sorted(combo_blocks),
                "overlap": overlap,
                "similarity": round(similarity, 3),
                "extra_blocks": sorted(extra_blocks),
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

    def _match_samples(
        self,
        dataset: List[Dict[str, Any]],
        block_set: Set[str],
        request_params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        for row in dataset:
            input_data = row.get("input") or {}
            sample_blocks = set(input_data.get("parsed_blocks") or [])
            block_score = _jaccard(block_set, sample_blocks)
            sample_params = input_data.get("extracted_parameters") or {}
            param_score = _parameter_similarity(request_params, sample_params)
            score = block_score * 0.7 + param_score * 0.3
            if score < 0.28 and block_score < 0.2:
                continue
            evidence = (row.get("output") or {}).get("evidence") or {}
            actions = (row.get("output") or {}).get("suggested_actions") or []
            paired_delta = (row.get("output") or {}).get("paired_delta")
            quality_score = _metric_quality(evidence)
            rank_score = round(score * 0.75 + _bounded_quality(quality_score) * 0.25, 4)
            matches.append({
                "sample_id": input_data.get("sample_id"),
                "user_prompt": input_data.get("user_prompt", ""),
                "parsed_blocks": sorted(sample_blocks),
                "extracted_parameters": sample_params,
                "similarity": round(score, 3),
                "block_similarity": round(block_score, 3),
                "parameter_similarity": round(param_score, 3),
                "quality_score": quality_score,
                "rank_score": rank_score,
                "risk_flags": _sample_risk_flags(evidence),
                "evidence": evidence,
                "paired_delta": paired_delta if isinstance(paired_delta, dict) else None,
                "suggested_actions": [str(action) for action in actions],
            })
        return heapq.nlargest(
            _MAX_MATCHED_SAMPLES,
            matches,
            key=lambda item: (item["rank_score"], item["similarity"]),
        )

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
        negative_samples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        primary = combinations[0] if combinations else (indicators[0] if indicators else {})
        sample_evidence = [sample.get("evidence") or {} for sample in samples]
        sample_quality = _safe_median([sample.get("quality_score") for sample in samples[:10]])
        positive_count = len([sample for sample in samples if _is_positive_sample(sample)])
        return {
            "similar_strategy_count": int(primary.get("sample_count") or primary.get("count") or len(samples)),
            "positive_sample_count": positive_count,
            "negative_sample_count": len(negative_samples),
            "similarity": primary.get("similarity"),
            "sample_similarity": samples[0].get("similarity") if samples else None,
            "parameter_similarity": samples[0].get("parameter_similarity") if samples else None,
            "median_cagr": primary.get("median_cagr") if primary else _safe_median([e.get("median_cagr") for e in sample_evidence]),
            "median_sharpe": primary.get("median_sharpe") if primary else _safe_median([e.get("median_sharpe") for e in sample_evidence]),
            "median_mdd": primary.get("median_mdd") if primary else _safe_median([e.get("median_mdd") for e in sample_evidence]),
            "median_profit_factor": primary.get("median_profit_factor") if primary else _safe_median([e.get("median_profit_factor") for e in sample_evidence]),
            "median_trades": primary.get("median_trades") if primary else _safe_median([e.get("median_trades") for e in sample_evidence]),
            "quality_score": primary.get("quality_score") or primary.get("median_quality_score") or sample_quality,
        }

    def _resolve_confidence(self, evidence: Dict[str, Any], combinations: List[Dict[str, Any]]) -> str:
        if self._is_flat_evidence(evidence):
            return "low"
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
            return [f"비슷한 실험 샘플 수가 적습니다. {guidance}"]
        return [guidance]

    def _suggest_adjustments(
        self,
        parsed_strategy: Dict[str, Any],
        rules: List[Dict[str, Any]],
        samples: List[Dict[str, Any]],
    ) -> List[str]:
        request_params = _extract_parameters(parsed_strategy)
        block_set = set(extract_strategy_blocks(parsed_strategy))
        candidates: Dict[str, tuple[float, str]] = {
            f"strategy:{idx}": (1.3 - idx * 0.01, text)
            for idx, text in enumerate(_strategy_specific_candidates(parsed_strategy, block_set))
        }
        paired_param_keys: Set[str] = set()
        for sample in samples[:20]:
            sample_params = sample.get("extracted_parameters") or {}
            paired_delta = sample.get("paired_delta")
            score = float(sample.get("similarity") or 0.0) + float(sample.get("quality_score") or 0.0) * 0.25
            if isinstance(paired_delta, dict) and paired_delta.get("improves_risk_adjusted"):
                score += 1.0
                delta_text = _format_paired_delta(paired_delta, request_params)
                if delta_text:
                    changed = paired_delta.get("changed_parameter")
                    if isinstance(changed, dict):
                        paired_param_keys.update(str(key) for key in changed)
                    change_axis = str(paired_delta.get("change_axis") or delta_text)
                    previous = candidates.get(change_axis)
                    if previous is None or score > previous[0]:
                        candidates[change_axis] = (score, delta_text)
            for key in ("stop_loss_pct", "trailing_stop_pct", "take_profit_pct", "hold_period_days", "max_positions"):
                if key in paired_param_keys:
                    continue
                value = sample_params.get(key)
                if value is None:
                    continue
                current = request_params.get(key)
                if current is not None and _safe_float(current) == _safe_float(value):
                    continue
                text = _format_param_candidate(key, value, current)
                if not text:
                    continue
                previous = candidates.get(key)
                if previous is None or score > previous[0]:
                    candidates[key] = (score, text)

        ordered = [
            item[1]
            for _, item in sorted(candidates.items(), key=lambda pair: pair[1][0], reverse=True)
        ]
        if ordered:
            return ordered[:3]

        if rules:
            actions = rules[0].get("suggested_actions") or []
            return [str(action) for action in actions[:3]]

        suggestions = []
        if parsed_strategy.get("stop_loss_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            suggestions.append("손절 또는 트레일링 스탑 조건 비교")
        if parsed_strategy.get("take_profit_pct") is None and parsed_strategy.get("trailing_stop_pct") is None:
            suggestions.append("익절 조건 비교")
        if parsed_strategy.get("hold_period_days") is None:
            suggestions.append("최대 보유기간 제한 비교")
        return suggestions[:3]

    def _build_warnings(
        self,
        confidence: str,
        combinations: List[Dict[str, Any]],
        negative_samples: List[Dict[str, Any]],
    ) -> List[str]:
        warnings: List[str] = []
        if confidence == "low":
            warnings.append("실험 샘플이 부족해 단정적으로 해석하면 안 됩니다.")
        if combinations:
            warnings.extend(str(item) for item in combinations[0].get("warnings") or [])
        if negative_samples:
            flags = []
            for sample in negative_samples[:5]:
                flags.extend(str(flag) for flag in sample.get("risk_flags") or [])
            flag_text = ", ".join(list(dict.fromkeys(flags))[:3])
            if flag_text:
                warnings.append(
                    f"유사 실패 패턴도 확인됐습니다({flag_text}). 같은 조건을 반복하지 말고 리스크 조건을 분리해 비교하세요."
                )
        return list(dict.fromkeys(warnings))

    @staticmethod
    def _is_flat_evidence(evidence: Dict[str, Any]) -> bool:
        values = [
            evidence.get("median_cagr"),
            evidence.get("median_sharpe"),
            evidence.get("median_mdd"),
        ]
        return all(isinstance(value, (int, float)) and abs(value) < 1e-9 for value in values)


def build_experiment_learning_advice(insight: Dict[str, Any]) -> Optional[str]:
    sample_count = int(insight.get("similar_strategy_count") or 0)
    if sample_count <= 0:
        return None

    is_flat_evidence = all(
        isinstance(insight.get(key), (int, float)) and abs(insight.get(key)) < 1e-9
        for key in ("median_cagr", "median_sharpe", "median_mdd")
    )
    judgment = _evidence_judgment(insight)

    if is_flat_evidence:
        return (
            f"비슷한 전략들의 과거 사례를 보면 {judgment}. "
            "성과 신호가 약하므로 현재 전략은 먼저 같은 기간과 비용 조건으로 백테스트하고, "
            "이후 진입 조건, 청산 규칙, 보유기간 변경은 한 번에 하나씩만 비교하세요."
        )

    risk_warning = ""
    if int(insight.get("negative_sample_count") or 0) > 0:
        warning = next((str(item) for item in insight.get("warnings") or [] if "유사 실패 패턴" in str(item)), "")
        risk_warning = f" {warning}" if warning else " 유사 실패 패턴도 있으므로 같은 조건 반복은 피하세요."

    return (
        f"비슷한 전략들의 과거 사례를 보면 {judgment}. "
        "현재 전략은 먼저 같은 기간과 비용 조건으로 백테스트하고, "
        "이후 변경은 한 번에 하나씩만 비교하세요."
        f"{risk_warning}"
    )
