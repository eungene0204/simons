"""Deterministic validation for strategy definitions before backtesting."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


class StrategyValidationAgent:
    """Validate structure and executability without evaluating strategy quality."""

    _SUPPORTED_CONDITIONS = {
        "adx",
        "ai_drop_model",
        "ai_model",
        "bollinger_bands",
        "breakout",
        "cci",
        "debt_ratio",
        "ema",
        "ma_crossover",
        "macd",
        "market_cap",
        "max_mdd_limit_pct",
        "max_holding_days",
        "pbr",
        "per",
        "price",
        "price_level",
        "price_limit_exit",
        "roe_or_gpa",
        "rsi",
        "stop_loss_pct",
        "stochastic",
        "take_profit_pct",
        "trading_value",
        "trailing_stop",
        "volume_spike",
    }
    _SUPPORTED_PRICE_FIELDS = {"open", "high", "low", "close", "volume"}
    _DAILY_FREQUENCIES = {"1d", "day", "daily"}
    _OPERATORS = {"<", "<=", ">", ">=", "=="}

    def validate(self, strategy: Any) -> dict[str, Any]:
        """Return the stable validation contract consumed before a backtest."""
        payload = self._as_mapping(strategy)
        if payload is None:
            return self._response([
                self._issue(
                    "INVALID_STRATEGY_TYPE",
                    "error",
                    "invalid_parameter",
                    "strategy",
                    "전략은 JSON 객체 형식이어야 합니다.",
                )
            ])

        issues: list[dict[str, str]] = []
        issues.extend(self._validate_required_fields(payload))
        issues.extend(self._validate_stop_loss(payload))
        issues.extend(self._validate_take_profit(payload))
        issues.extend(self._validate_supported_data(payload))
        issues.extend(self._validate_parameters(payload))
        issues.extend(self._validate_logical_conflicts(payload))
        issues.extend(self._validate_impossible_conditions(payload))
        issues.extend(self._validate_empty_universe_risk(payload))
        return self._response(self._deduplicate(issues))

    def validate_json(self, strategy: Any) -> str:
        """Serialize a validation result without any surrounding prose."""
        return json.dumps(self.validate(strategy), ensure_ascii=False)

    @staticmethod
    def _as_mapping(strategy: Any) -> Mapping[str, Any] | None:
        if isinstance(strategy, Mapping):
            return strategy
        model_dump = getattr(strategy, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            return dumped if isinstance(dumped, Mapping) else None
        return None

    def _validate_required_fields(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        fields = {
            "universe": self._first(strategy, ("universe",), ("symbols",)),
            "entry_rule": self._first(strategy, ("entry_rule",), ("entry",), ("entry_signals",)),
            "rebalance_rule": self._first(
                strategy, ("rebalance_rule",), ("rebalancing_period",), ("risk", "rebalancing_period")
            ),
            "position_sizing": self._first(
                strategy, ("position_sizing",), ("position_size_pct",), ("risk", "position_size_pct")
            ),
            "max_positions": self._first(strategy, ("max_positions",), ("risk", "max_positions")),
            "data_frequency": self._first(
                strategy, ("data_frequency",), ("timeframe",), ("interval",), ("options", "timeframe")
            ),
            "backtest_period": self._first(strategy, ("backtest_period",), ("period",)),
        }
        messages = {
            "universe": "투자 대상 유니버스가 정의되어 있지 않습니다.",
            "entry_rule": "진입 조건이 정의되어 있지 않습니다.",
            "rebalance_rule": "리밸런싱 규칙이 정의되어 있지 않습니다.",
            "position_sizing": "매수 수량 계산 방식이 정의되어 있지 않습니다.",
            "max_positions": "최대 보유 종목 수가 정의되어 있지 않습니다.",
            "data_frequency": "데이터 주기가 정의되어 있지 않습니다.",
            "backtest_period": "백테스트 기간이 정의되어 있지 않습니다.",
        }
        issues = [
            self._issue(f"MISSING_{field.upper()}", "error", "missing_field", field, messages[field])
            for field, value in fields.items()
            if self._is_empty(value)
        ]

        exit_rule = self._first(strategy, ("exit_rule",), ("exit",), ("exit_signals",))
        holding_period = self._first(
            strategy, ("holding_period",), ("hold_period_days",), ("risk", "max_holding_days")
        )
        if self._is_empty(exit_rule) and self._is_empty(holding_period):
            issues.append(self._issue(
                "MISSING_EXIT_RULE", "error", "missing_field", "exit_rule",
                "청산 조건이 정의되어 있지 않습니다.",
            ))
        return issues

    def _validate_stop_loss(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        stop_loss = self._first(strategy, ("stop_loss_pct",), ("risk", "stop_loss_pct"))
        if stop_loss is not None or self._has_condition_identifier(strategy, {"stop_loss", "stop_loss_pct"}):
            return []

        return [self._issue(
            "MISSING_STOP_LOSS", "warning", "missing_field", "stop_loss_pct",
            "손절 조건이 정의되어 있지 않습니다.",
        )]

    def _validate_take_profit(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        take_profit = self._first(strategy, ("take_profit_pct",), ("risk", "take_profit_pct"))
        if take_profit is not None or self._has_condition_identifier(strategy, {"take_profit", "take_profit_pct"}):
            return []

        return [self._issue(
            "MISSING_TAKE_PROFIT", "warning", "missing_field", "take_profit_pct",
            "익절 조건이 정의되어 있지 않습니다.",
        )]

    def _validate_supported_data(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        frequency = self._first(
            strategy, ("data_frequency",), ("timeframe",), ("interval",), ("options", "timeframe")
        )
        if isinstance(frequency, str) and frequency.lower() not in self._DAILY_FREQUENCIES:
            issues.append(self._issue(
                "UNSUPPORTED_DATA_FREQUENCY", "error", "unsupported_field", "data_frequency",
                "현재 시스템에서 지원하지 않는 데이터 주기입니다.",
            ))

        for condition in self._all_conditions(strategy):
            params = condition.get("params") if isinstance(condition.get("params"), Mapping) else {}
            identifier = (
                condition.get("metric") or condition.get("indicator")
                or condition.get("id") or condition.get("field")
            )
            if identifier and str(identifier).lower() not in self._SUPPORTED_CONDITIONS:
                issues.append(self._issue(
                    f"UNSUPPORTED_FIELD_{self._code(identifier)}", "error", "unsupported_field",
                    str(identifier), "현재 시스템에서 지원하지 않는 필드입니다.",
                ))
            price_field = condition.get("price_field") or params.get("priceField") or params.get("price_field")
            if price_field and str(price_field).lower() not in self._SUPPORTED_PRICE_FIELDS:
                issues.append(self._issue(
                    f"UNSUPPORTED_PRICE_FIELD_{self._code(price_field)}", "error", "unsupported_field",
                    "price_field", "현재 시스템에서 지원하지 않는 가격 필드입니다.",
                ))
        return issues

    def _validate_parameters(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        positive_names = {
            "max_positions", "period", "short_period", "long_period", "short_ma", "long_ma",
            "fast_period", "slow_period", "signal_period", "lookback_period", "ranking_lookback_days",
            "holding_period", "hold_period_days", "max_holding_days", "rebalance_interval",
        }
        nonnegative_names = {
            "stop_loss_pct", "take_profit_pct", "trailing_stop_pct", "max_mdd_limit_pct",
            "fee_rate", "slippage_rate",
        }
        for path, value in self._walk_values(strategy):
            name = self._snake_case(path[-1])
            if not self._is_number(value):
                continue
            if name in positive_names and value <= 0:
                issues.append(self._issue(
                    f"INVALID_{name.upper()}", "error", "invalid_parameter", name,
                    f"{name}은(는) 0보다 큰 값이어야 합니다.",
                ))
            elif name in nonnegative_names and value < 0:
                issues.append(self._issue(
                    f"INVALID_{name.upper()}", "error", "invalid_parameter", name,
                    f"{name}은(는) 0 이상의 값이어야 합니다.",
                ))
            elif name == "weight" and not 0 <= value <= 1:
                issues.append(self._issue(
                    "INVALID_WEIGHT", "error", "invalid_parameter", "weight",
                    "weight는 0 이상 1 이하의 값이어야 합니다.",
                ))
            elif name in {"position_size_pct", "position_sizing_pct"} and not 0 < value <= 100:
                issues.append(self._issue(
                    "INVALID_POSITION_SIZE", "error", "invalid_parameter", name,
                    "포지션 비중은 0보다 크고 100 이하여야 합니다.",
                ))
        return issues

    def _validate_logical_conflicts(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        for scope in self._condition_scopes(strategy):
            constraints: dict[str, list[tuple[str, float]]] = {}
            ranks: dict[str, list[tuple[str, float]]] = {}
            for condition in self._iter_condition_dicts(scope):
                params = condition.get("params") if isinstance(condition.get("params"), Mapping) else {}
                variable = condition.get("metric") or condition.get("field") or condition.get("indicator") or condition.get("id")
                if not variable:
                    continue
                variable = str(variable).lower()
                operator = condition.get("operator") or params.get("operator")
                value = condition.get("value", params.get("value"))
                if operator in self._OPERATORS and self._is_number(value):
                    constraints.setdefault(variable, []).append((operator, float(value)))
                direction = condition.get("rank_direction") or condition.get("direction")
                if direction is None and operator in {"top", "bottom"}:
                    direction = operator
                percentile = condition.get("percentile", value)
                if direction in {"top", "bottom"} and self._is_number(percentile):
                    ranks.setdefault(variable, []).append((str(direction), float(percentile)))

            for variable, values in constraints.items():
                if self._interval_is_empty(values):
                    issues.append(self._issue(
                        f"LOGICAL_CONFLICT_{self._code(variable)}", "error", "logical_conflict",
                        variable, "동일 변수에 대해 서로 충돌하는 조건이 존재합니다.",
                    ))
            for variable, values in ranks.items():
                tops = [value for direction, value in values if direction == "top"]
                bottoms = [value for direction, value in values if direction == "bottom"]
                if tops and bottoms and min(tops) + min(bottoms) <= 100:
                    issues.append(self._issue(
                        f"LOGICAL_CONFLICT_{self._code(variable)}_RANK", "error", "logical_conflict",
                        variable, "동일 변수에 대해 서로 충돌하는 순위 조건이 존재합니다.",
                    ))
        return issues

    def _validate_impossible_conditions(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        max_positions = self._first(strategy, ("max_positions",), ("risk", "max_positions"))
        universe_size = self._universe_size(strategy)
        if self._is_number(max_positions) and universe_size is not None and max_positions > universe_size:
            issues.append(self._issue(
                "MAX_POSITIONS_EXCEEDS_UNIVERSE", "error", "impossible_condition", "max_positions",
                "보유 종목 수가 선택 가능한 유니버스보다 많습니다.",
            ))

        data_frequency = self._first(
            strategy, ("data_frequency",), ("timeframe",), ("interval",), ("options", "timeframe")
        )
        data_minutes = self._frequency_minutes(data_frequency)
        if data_minutes is not None:
            for condition in self._all_conditions(strategy):
                params = condition.get("params") if isinstance(condition.get("params"), Mapping) else {}
                frequency = condition.get("frequency") or condition.get("timeframe") or params.get("frequency")
                condition_minutes = self._frequency_minutes(frequency)
                if condition_minutes is not None and condition_minutes < data_minutes:
                    issues.append(self._issue(
                        "CONDITION_FREQUENCY_TOO_SHORT", "error", "impossible_condition", "data_frequency",
                        "데이터 주기보다 더 짧은 조건은 실행할 수 없습니다.",
                    ))
                    break
        return issues

    def _validate_empty_universe_risk(self, strategy: Mapping[str, Any]) -> list[dict[str, str]]:
        extreme_rank_count = 0
        for condition in self._all_conditions(strategy):
            params = condition.get("params") if isinstance(condition.get("params"), Mapping) else {}
            metric = str(condition.get("metric") or condition.get("field") or condition.get("id") or "").lower()
            operator = condition.get("operator") or params.get("operator")
            value = condition.get("value", params.get("value"))
            if self._is_number(value):
                if metric == "per" and operator in {"<", "<="} and value <= 1:
                    return [self._empty_universe_issue()]
                if metric == "pbr" and operator in {"<", "<="} and value <= 0.1:
                    return [self._empty_universe_issue()]
                roe_is_extreme = (
                    (operator == ">" and value >= 50)
                    or (operator == ">=" and value > 50)
                )
                if metric in {"roe", "roe_or_gpa"} and roe_is_extreme:
                    return [self._empty_universe_issue()]
            direction = condition.get("rank_direction") or condition.get("direction")
            percentile = condition.get("percentile", value)
            if direction in {"top", "bottom"} and self._is_number(percentile) and percentile <= 1:
                extreme_rank_count += 1
        return [self._empty_universe_issue()] if extreme_rank_count >= 2 else []

    @classmethod
    def _condition_scopes(cls, strategy: Mapping[str, Any]) -> list[list[Any]]:
        entry = [strategy.get("fundamental_filters", [])]
        entry.append(cls._first(strategy, ("entry_rule",), ("entry",), ("entry_signals",)) or [])
        exit_scope = cls._first(strategy, ("exit_rule",), ("exit",), ("exit_signals",)) or []
        return [entry, [exit_scope]]

    @classmethod
    def _all_conditions(cls, strategy: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        return [condition for scope in cls._condition_scopes(strategy) for condition in cls._iter_condition_dicts(scope)]

    @classmethod
    def _has_condition_identifier(cls, strategy: Mapping[str, Any], identifiers: set[str]) -> bool:
        normalized = {identifier.lower() for identifier in identifiers}
        for condition in cls._all_conditions(strategy):
            identifier = (
                condition.get("id") or condition.get("field")
                or condition.get("indicator") or condition.get("metric")
            )
            if str(identifier).lower() in normalized:
                return True
        return False

    @classmethod
    def _iter_condition_dicts(cls, value: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            if any(key in value for key in ("id", "indicator", "metric", "field")):
                yield value
            for nested in value.values():
                yield from cls._iter_condition_dicts(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                yield from cls._iter_condition_dicts(nested)

    @staticmethod
    def _interval_is_empty(values: list[tuple[str, float]]) -> bool:
        lowers = [(value, operator == ">=") for operator, value in values if operator in {">", ">="}]
        uppers = [(value, operator == "<=") for operator, value in values if operator in {"<", "<="}]
        equals = [value for operator, value in values if operator == "=="]
        if equals and any(value != equals[0] for value in equals[1:]):
            return True
        if equals:
            lowers.append((equals[0], True))
            uppers.append((equals[0], True))
        if not lowers or not uppers:
            return False
        lower = max(lowers, key=lambda item: item[0])
        upper = min(uppers, key=lambda item: item[0])
        return lower[0] > upper[0] or (lower[0] == upper[0] and not (lower[1] and upper[1]))

    @classmethod
    def _universe_size(cls, strategy: Mapping[str, Any]) -> int | None:
        explicit = cls._first(strategy, ("universe_size",), ("symbol_count",))
        if cls._is_number(explicit) and explicit >= 0:
            return int(explicit)
        universe = strategy.get("universe")
        if isinstance(universe, Mapping) and isinstance(universe.get("symbols"), list):
            return len(universe["symbols"])
        if (
            isinstance(universe, list)
            and all(isinstance(item, str) for item in universe)
            and set(universe) == {"KOSPI200"}
        ):
            return 200
        symbols = strategy.get("symbols")
        if isinstance(symbols, list):
            return len(symbols)
        return None

    @staticmethod
    def _frequency_minutes(value: Any) -> int | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower()
        named = {"daily": 1440, "day": 1440, "weekly": 10080, "monthly": 43200}
        if normalized in named:
            return named[normalized]
        match = re.fullmatch(r"(\d+)(min|m|h|d|w)", normalized)
        if not match:
            return None
        amount = int(match.group(1))
        factor = {"min": 1, "m": 1, "h": 60, "d": 1440, "w": 10080}[match.group(2)]
        return amount * factor

    @staticmethod
    def _walk_values(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                current = path + (str(key),)
                yield current, nested
                yield from StrategyValidationAgent._walk_values(nested, current)
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                yield from StrategyValidationAgent._walk_values(nested, path + (str(index),))

    @staticmethod
    def _first(data: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
        for path in paths:
            current: Any = data
            for key in path:
                if not isinstance(current, Mapping) or key not in current:
                    break
                current = current[key]
            else:
                return current
        return None

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None or value == "":
            return True
        if isinstance(value, Mapping):
            return not value or (set(value) == {"conditions"} and not value["conditions"])
        return isinstance(value, (list, tuple, set)) and not value

    @staticmethod
    def _is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @staticmethod
    def _snake_case(value: str) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()

    @staticmethod
    def _code(value: Any) -> str:
        return re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_") or "UNKNOWN"

    @staticmethod
    def _issue(code: str, severity: str, category: str, field: str, message: str) -> dict[str, str]:
        return {"code": code, "severity": severity, "category": category, "field": field, "message": message}

    @classmethod
    def _empty_universe_issue(cls) -> dict[str, str]:
        return cls._issue(
            "EMPTY_UNIVERSE_POSSIBLE", "warning", "impossible_condition", "universe",
            "조건으로 인해 대상 종목이 존재하지 않을 수 있습니다.",
        )

    @staticmethod
    def _deduplicate(issues: list[dict[str, str]]) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        result = []
        for issue in issues:
            key = (issue["code"], issue["field"])
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result

    @staticmethod
    def _response(issues: list[dict[str, str]]) -> dict[str, Any]:
        return {"is_valid": not any(issue["severity"] == "error" for issue in issues), "issues": issues}
