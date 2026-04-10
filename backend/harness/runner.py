import argparse
import copy
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


def _ensure_runtime_cache_dirs() -> str:
    cache_dir = os.environ.get("NUMBA_CACHE_DIR")
    if not cache_dir:
        cache_dir = os.path.join(tempfile.gettempdir(), "simons-numba-cache")
        os.environ["NUMBA_CACHE_DIR"] = cache_dir
    os.makedirs(cache_dir, exist_ok=True)

    mpl_config_dir = os.environ.get("MPLCONFIGDIR")
    if not mpl_config_dir:
        mpl_config_dir = os.path.join(tempfile.gettempdir(), "simons-matplotlib")
        os.environ["MPLCONFIGDIR"] = mpl_config_dir
    os.makedirs(mpl_config_dir, exist_ok=True)

    return cache_dir


def _load_backtest_engine():
    _ensure_runtime_cache_dirs()
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from backtest_engine import BacktestEngine

    return BacktestEngine


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_suite(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        suite = json.load(handle)

    if not isinstance(suite, dict):
        raise ValueError("Harness suite root must be a JSON object")
    if not isinstance(suite.get("cases"), list) or not suite["cases"]:
        raise ValueError("Harness suite must define at least one case")
    return suite


@dataclass
class CaseEvaluation:
    case_id: str
    passed: bool
    failures: List[str]
    summary: Dict[str, Any]
    duration_ms: int


def _check_numeric(label: str, actual: Any, rule: Dict[str, Any], failures: List[str]) -> None:
    if actual is None:
        failures.append(f"{label}: expected numeric value, got None")
        return

    if "equals" in rule and actual != rule["equals"]:
        failures.append(f"{label}: expected {rule['equals']}, got {actual}")

    if "min" in rule and actual < rule["min"]:
        failures.append(f"{label}: expected >= {rule['min']}, got {actual}")

    if "max" in rule and actual > rule["max"]:
        failures.append(f"{label}: expected <= {rule['max']}, got {actual}")

    if "approx" in rule:
        tolerance = rule.get("tolerance", 0.0)
        if abs(actual - rule["approx"]) > tolerance:
            failures.append(
                f"{label}: expected {rule['approx']} ± {tolerance}, got {actual}"
            )


def _signal_matches(signal: Dict[str, Any], matcher: Dict[str, Any]) -> bool:
    for field in ("type", "date", "symbol"):
        expected = matcher.get(field)
        if expected is not None and signal.get(field) != expected:
            return False

    expected_price = matcher.get("price")
    if expected_price is not None:
        tolerance = matcher.get("price_tolerance", 0.0)
        actual_price = signal.get("price")
        if actual_price is None or abs(actual_price - expected_price) > tolerance:
            return False

    condition_contains = matcher.get("condition_contains")
    if condition_contains and condition_contains not in str(signal.get("condition", "")):
        return False

    return True


def evaluate_result(case: Dict[str, Any], result: Dict[str, Any]) -> List[str]:
    expect = case.get("expect", {})
    failures: List[str] = []

    if expect.get("status") == "success" and result.get("error"):
        failures.append(f"engine error: {result['error']}")

    metric_ranges = expect.get("metric_ranges", {})
    for key, rule in metric_ranges.items():
        _check_numeric(key, result.get(key), rule, failures)

    derived_values = {
        "signal_count": len(result.get("signals", [])),
        "warning_count": len(result.get("warnings", [])),
        "date_count": len(result.get("dates", [])),
    }
    for key in ("signal_count", "warning_count", "date_count"):
        if key in expect:
            _check_numeric(key, derived_values[key], expect[key], failures)

    warnings = [str(item) for item in result.get("warnings", [])]
    for fragment in expect.get("warnings_include", []):
        if not any(fragment in warning for warning in warnings):
            failures.append(f"warnings_include: missing '{fragment}'")

    signals = result.get("signals", [])
    for matcher in expect.get("signals_include", []):
        if not any(_signal_matches(signal, matcher) for signal in signals):
            failures.append(f"signals_include: missing match {json.dumps(matcher, ensure_ascii=False)}")

    return failures


def _build_case_request(default_request: Dict[str, Any], case_request: Dict[str, Any]) -> Dict[str, Any]:
    return _deep_merge(default_request, case_request)


def _build_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "totalReturn": result.get("totalReturn"),
        "cagr": result.get("cagr"),
        "maxDrawdown": result.get("maxDrawdown"),
        "profitFactor": result.get("profitFactor"),
        "winRate": result.get("winRate"),
        "trades": result.get("trades"),
        "signal_count": len(result.get("signals", [])),
        "warning_count": len(result.get("warnings", [])),
        "date_count": len(result.get("dates", [])),
    }


def run_suite(suite_path: str, engine_factory=None) -> Dict[str, Any]:
    suite = load_suite(suite_path)
    defaults = suite.get("defaults", {})
    default_request = defaults.get("request", {})
    default_data_dir = defaults.get("data_dir")

    if engine_factory is None:
        engine_factory = _load_backtest_engine()

    evaluations: List[CaseEvaluation] = []

    for case in suite["cases"]:
        case_id = case["id"]
        data_dir = case.get("data_dir", default_data_dir)
        request = _build_case_request(default_request, case.get("request", {}))

        case_started_at = time.time()
        try:
            engine = engine_factory(data_dir=data_dir) if data_dir else engine_factory()
            result = engine.run_backtest(request)
        except Exception as exc:
            result = {"error": str(exc), "signals": [], "warnings": [], "dates": []}

        failures = evaluate_result(case, result)
        evaluations.append(
            CaseEvaluation(
                case_id=case_id,
                passed=not failures,
                failures=failures,
                summary=_build_summary(result),
                duration_ms=int((time.time() - case_started_at) * 1000),
            )
        )

    passed = sum(1 for item in evaluations if item.passed)
    failed = len(evaluations) - passed

    return {
        "suite_name": suite.get("suite_name", Path(suite_path).stem),
        "suite_path": str(Path(suite_path).resolve()),
        "numba_cache_dir": os.environ.get("NUMBA_CACHE_DIR"),
        "totals": {
            "cases": len(evaluations),
            "passed": passed,
            "failed": failed,
        },
        "cases": [
            {
                "id": item.case_id,
                "passed": item.passed,
                "failures": item.failures,
                "summary": item.summary,
                "duration_ms": item.duration_ms,
            }
            for item in evaluations
        ],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic backtest harness suites.")
    parser.add_argument("suite", help="Path to the harness suite JSON file")
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report",
    )
    args = parser.parse_args(argv)

    report = run_suite(args.suite)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    return 0 if report["totals"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
