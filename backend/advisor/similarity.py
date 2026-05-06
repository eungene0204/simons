"""
Text and structural similarity retrieval for strategy advisor memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

TEXT_WEIGHT = 0.30
STRUCTURE_WEIGHT = 0.70
DEFAULT_MIN_COMBINED_SCORE = 0.25
DEFAULT_MIN_STRUCTURE_SCORE = 0.30
TEXT_ONLY_SCORE_THRESHOLD = 0.35
TEXT_ONLY_MIN_STRUCTURE_SCORE = 0.40


TEXT_FIELDS = (
    "user_prompt",
    "userPrompt",
    "strategy_summary",
    "strategySummary",
    "indicator_names",
    "indicatorNames",
    "entry_condition_description",
    "entryConditionText",
    "exit_condition_description",
    "exitConditionText",
    "risk_management_description",
    "riskManagementText",
    "agent_advice_text",
    "agentAdviceText",
    "lesson",
)

INDICATOR_ALIASES = {
    "golden_cross": "ma_crossover",
    "moving_average": "ma_crossover",
    "ma_cross": "ma_crossover",
    "ma": "ma_crossover",
    "sma": "ma_crossover",
    "ema": "ema",
    "rsi": "rsi",
    "macd": "macd",
    "bollinger": "bollinger_band",
    "bollinger_band": "bollinger_band",
    "volume": "volume_spike",
    "volume_spike": "volume_spike",
    "pbr": "pbr",
    "per": "per",
    "roe": "roe",
    "trading_value": "trading_value",
    "market_cap": "market_cap",
}

KOREAN_ALIASES = {
    "골든크로스": "ma_crossover",
    "이동평균": "ma_crossover",
    "과매도": "rsi",
    "과매수": "rsi",
    "거래량": "volume_spike",
    "손절": "stop_loss",
    "익절": "take_profit",
}


@dataclass(frozen=True)
class StructuralFeatures:
    indicators: Set[str]
    entry_rules: Set[str]
    exit_rules: Set[str]
    risk_rules: Set[str]
    position_sizing: Set[str]
    universe: Optional[str]
    timeframe: Optional[str]
    parameters: Dict[str, float]


@dataclass(frozen=True)
class SimilarityResult:
    strategy_id: str
    text_score: float
    structure_score: float
    combined_score: float
    similarity_reason: str
    case: Dict[str, Any]


def _normalize_indicator(value: Any) -> Optional[str]:
    key = str(value or "").strip().lower()
    if not key:
        return None
    return INDICATOR_ALIASES.get(key, key)


def _tokenize(text: str) -> Set[str]:
    normalized = text.lower()
    for source, target in KOREAN_ALIASES.items():
        normalized = normalized.replace(source, f" {target} ")
    tokens = set(re.findall(r"[a-z0-9가-힣_.%]+", normalized))
    return {INDICATOR_ALIASES.get(token, token) for token in tokens if len(token) >= 2}


def build_text_document(case: Dict[str, Any]) -> str:
    parts: List[str] = []
    for field in TEXT_FIELDS:
        value = case.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value)
        elif isinstance(value, (list, tuple)):
            parts.extend(str(item) for item in value if item)
    for field in ("strategy_dsl", "strategyDsl", "dsl"):
        dsl = case.get(field)
        if isinstance(dsl, dict):
            features = extract_structural_features(dsl)
            parts.extend(sorted(features.indicators))
            parts.extend(sorted(features.entry_rules))
            parts.extend(sorted(features.exit_rules))
            parts.extend(sorted(features.risk_rules))
            parts.extend(sorted(features.position_sizing))
            if features.universe:
                parts.append(features.universe)
            if features.timeframe:
                parts.append(features.timeframe)
    return " ".join(parts)


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _rule_token(prefix: str, identifier: Any, params: Dict[str, Any]) -> str:
    operator = params.get("operator") or params.get("op") or params.get("comparison") or ""
    value = params.get("value") or params.get("threshold") or params.get("pct") or ""
    return f"{prefix}:{_normalize_indicator(identifier) or identifier}:{operator}:{value}"


def _iter_condition_rules(strategy_dsl: Dict[str, Any], key: str) -> Iterable[Tuple[str, Dict[str, Any]]]:
    raw = strategy_dsl.get(key)
    if isinstance(raw, dict):
        raw = raw.get("conditions")
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        identifier = item.get("indicator") or item.get("type") or item.get("id") or item.get("metric")
        params = item.get("params") if isinstance(item.get("params"), dict) else item
        yield str(identifier or ""), params


def _collect_signal_rules(strategy_dsl: Dict[str, Any], source_key: str, prefix: str) -> Tuple[Set[str], Set[str], Dict[str, float]]:
    indicators: Set[str] = set()
    rules: Set[str] = set()
    params: Dict[str, float] = {}
    for identifier, payload in _iter_condition_rules(strategy_dsl, source_key):
        indicator = _normalize_indicator(identifier)
        if indicator:
            indicators.add(indicator)
            operator = payload.get("operator") or payload.get("op") or payload.get("comparison") or ""
            rules.add(f"{prefix}:{indicator}:{operator}")
        rules.add(_rule_token(prefix, indicator or identifier, payload))
        threshold = _safe_float(payload.get("threshold") or payload.get("value"))
        if indicator and threshold is not None:
            params[f"{prefix}_{indicator}_threshold"] = threshold
        period = _safe_float(payload.get("period") or payload.get("lookback_period") or payload.get("lookbackPeriod"))
        if indicator and period is not None:
            params[f"{prefix}_{indicator}_period"] = period
    return indicators, rules, params


def extract_structural_features(strategy_dsl: Dict[str, Any]) -> StructuralFeatures:
    strategy_dsl = strategy_dsl or {}
    indicators: Set[str] = set()
    entry_rules: Set[str] = set()
    exit_rules: Set[str] = set()
    risk_rules: Set[str] = set()
    position_sizing: Set[str] = set()
    parameters: Dict[str, float] = {}

    for item in strategy_dsl.get("fundamental_filters") or []:
        if not isinstance(item, dict):
            continue
        metric = _normalize_indicator(item.get("metric"))
        if metric:
            indicators.add(metric)
            entry_rules.add(_rule_token("filter", metric, item))
            value = _safe_float(item.get("value"))
            if value is not None:
                parameters[f"filter_{metric}"] = value

    for source_key, prefix in (("entry_signals", "entry"), ("entry", "entry")):
        found_indicators, found_rules, found_params = _collect_signal_rules(strategy_dsl, source_key, prefix)
        indicators.update(found_indicators)
        entry_rules.update(found_rules)
        parameters.update(found_params)

    for source_key, prefix in (("exit_signals", "exit"), ("exit", "exit")):
        found_indicators, found_rules, found_params = _collect_signal_rules(strategy_dsl, source_key, prefix)
        indicators.update(found_indicators)
        exit_rules.update(found_rules)
        parameters.update(found_params)

    risk_payload = strategy_dsl.get("risk") if isinstance(strategy_dsl.get("risk"), dict) else strategy_dsl
    for key in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_holding_days", "hold_period_days"):
        value = _safe_float(risk_payload.get(key) if isinstance(risk_payload, dict) else None)
        if value is not None:
            risk_name = "max_holding_days" if key == "hold_period_days" else key
            risk_rules.add(f"{risk_name}={value:g}")
            parameters[risk_name] = value

    max_positions = _safe_float(strategy_dsl.get("max_positions") or risk_payload.get("max_positions"))
    if max_positions is not None:
        position_sizing.add(f"max_positions={max_positions:g}")
        parameters["max_positions"] = max_positions

    allocation = risk_payload.get("allocation_type") if isinstance(risk_payload, dict) else None
    if allocation:
        position_sizing.add(f"allocation={allocation}")

    universe_value = strategy_dsl.get("universe_id") or strategy_dsl.get("universe")
    if isinstance(universe_value, list):
        universe = "_".join(sorted(str(item).lower() for item in universe_value))
    elif universe_value:
        universe = str(universe_value).lower()
    else:
        universe = None

    timeframe = strategy_dsl.get("timeframe") or strategy_dsl.get("interval") or "1d"
    return StructuralFeatures(
        indicators=indicators,
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        risk_rules=risk_rules,
        position_sizing=position_sizing,
        universe=universe,
        timeframe=str(timeframe).lower() if timeframe else None,
        parameters=parameters,
    )


def _parameter_distance_score(left: Dict[str, float], right: Dict[str, float]) -> float:
    shared = sorted(set(left) & set(right))
    if not shared:
        return 0.0
    scores = []
    for key in shared:
        left_value = abs(left[key])
        right_value = abs(right[key])
        denominator = max(left_value, right_value, 1.0)
        scores.append(max(0.0, 1.0 - abs(left[key] - right[key]) / denominator))
    return sum(scores) / len(scores)


def structural_similarity(left: StructuralFeatures, right: StructuralFeatures) -> float:
    universe_timeframe = 0.0
    if left.universe and right.universe and left.universe == right.universe:
        universe_timeframe += 0.6
    if left.timeframe and right.timeframe and left.timeframe == right.timeframe:
        universe_timeframe += 0.4

    score = (
        0.25 * _jaccard(left.indicators, right.indicators)
        + 0.25 * _jaccard(left.entry_rules, right.entry_rules)
        + 0.15 * _jaccard(left.exit_rules, right.exit_rules)
        + 0.10 * _jaccard(left.risk_rules, right.risk_rules)
        + 0.10 * universe_timeframe
        + 0.10 * _parameter_distance_score(left.parameters, right.parameters)
        + 0.05 * _jaccard(left.position_sizing, right.position_sizing)
    )
    return round(min(score, 1.0), 4)


def text_similarity(query_prompt: str, query_dsl: Dict[str, Any], case: Dict[str, Any]) -> float:
    query_text = " ".join([
        query_prompt or "",
        build_text_document({"strategy_dsl": query_dsl}),
        " ".join(extract_structural_features(query_dsl).indicators),
    ])
    query_tokens = _tokenize(query_text)
    case_tokens = _tokenize(build_text_document(case))
    return round(_jaccard(query_tokens, case_tokens), 4)


def _case_strategy_id(case: Dict[str, Any]) -> str:
    return str(case.get("strategy_id") or case.get("strategyId") or case.get("id") or "")


def _case_dsl(case: Dict[str, Any]) -> Dict[str, Any]:
    dsl = case.get("strategy_dsl") or case.get("strategyDsl") or case.get("dsl")
    return dsl if isinstance(dsl, dict) else {}


def _similarity_reason(text_score: float, structure_score: float) -> str:
    if structure_score >= 0.55 and text_score < 0.2:
        return "표현은 다르지만 DSL 구조와 파라미터가 유사합니다."
    if text_score >= 0.35 and structure_score >= 0.35:
        return "전략 설명과 DSL 구조가 모두 유사합니다."
    if text_score >= 0.35:
        return "전략 설명 텍스트가 유사하지만 구조 검증이 필요합니다."
    return "DSL 구조 기준으로 일부 유사한 전략입니다."


def _passes_quality_gate(
    current: StructuralFeatures,
    candidate: StructuralFeatures,
    text_score: float,
    structure_score: float,
    combined_score: float,
    min_score: float,
    min_structure_score: float,
) -> bool:
    if combined_score < min_score or structure_score < min_structure_score:
        return False
    if current.indicators and candidate.indicators and not (current.indicators & candidate.indicators):
        return False
    if text_score >= TEXT_ONLY_SCORE_THRESHOLD and structure_score < TEXT_ONLY_MIN_STRUCTURE_SCORE:
        return False
    return True


def search_similar_strategies(
    user_prompt: str,
    strategy_dsl: Dict[str, Any],
    cases: Sequence[Dict[str, Any]],
    top_k: int = 5,
    min_score: float = DEFAULT_MIN_COMBINED_SCORE,
    min_structure_score: float = DEFAULT_MIN_STRUCTURE_SCORE,
) -> List[SimilarityResult]:
    current_features = extract_structural_features(strategy_dsl)
    best_by_strategy_id: Dict[str, SimilarityResult] = {}
    for case in cases:
        strategy_id = _case_strategy_id(case)
        if not strategy_id:
            continue
        text_score = text_similarity(user_prompt, strategy_dsl, case)
        candidate_features = extract_structural_features(_case_dsl(case))
        structure_score = structural_similarity(current_features, candidate_features)
        combined = round((TEXT_WEIGHT * text_score) + (STRUCTURE_WEIGHT * structure_score), 4)
        if not _passes_quality_gate(
            current_features,
            candidate_features,
            text_score,
            structure_score,
            combined,
            min_score,
            min_structure_score,
        ):
            continue
        result = SimilarityResult(
            strategy_id=strategy_id,
            text_score=text_score,
            structure_score=structure_score,
            combined_score=combined,
            similarity_reason=_similarity_reason(text_score, structure_score),
            case=case,
        )
        previous = best_by_strategy_id.get(strategy_id)
        if previous is None or (
            result.combined_score,
            result.structure_score,
            result.text_score,
        ) > (
            previous.combined_score,
            previous.structure_score,
            previous.text_score,
        ):
            best_by_strategy_id[strategy_id] = result
    return sorted(
        best_by_strategy_id.values(),
        key=lambda item: (item.combined_score, item.structure_score, item.text_score),
        reverse=True,
    )[:top_k]


def summarize_similarity_results(results: Sequence[SimilarityResult]) -> List[Dict[str, Any]]:
    return [
        {
            "strategy_id": item.strategy_id,
            "text_score": item.text_score,
            "structure_score": item.structure_score,
            "combined_score": item.combined_score,
            "similarity_reason": item.similarity_reason,
        }
        for item in results
    ]
