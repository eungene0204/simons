"""평가 하니스 — 데이터셋을 LLM Interpreter 파이프라인에 통과시켜 지표를 산출한다.

실제 LLM(Ollama)이 필요하므로 CI가 아닌 로컬에서 실행한다:

    cd backend && python -m strategy_conversation.evaluation.evaluator [--limit N] [--legacy]

--legacy를 주면 동일 케이스를 기존 규칙 파서(parse_rule_based)에도 통과시켜
규칙 파서가 처리 가능한 비율을 함께 보고한다(신구 구조 비교 평가).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

DATASET_PATH = os.path.join(os.path.dirname(__file__), "datasets", "parse_cases.json")


def run_case(interpreter, case: Dict[str, Any]) -> Dict[str, Any]:
    from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterError
    from strategy_conversation.validation.pipeline import run_validation

    outcome: Dict[str, Any] = {"id": case["id"]}
    started = time.perf_counter()
    try:
        result = interpreter.interpret(case["input"], draft=case.get("draft"))
        validated, report = run_validation(result.intent)
        outcome.update({
            "intent_dump": validated.model_dump(),
            "report_dump": report.model_dump(),
            "repair_attempts": result.repair_attempts,
        })
        if report.is_valid:
            from strategy_conversation.compiler.strategy_compiler import (
                StrategyCompileError,
                compile_strategy,
            )
            try:
                compiled = compile_strategy(validated, report, case["input"])
                outcome["compiled"] = compiled.model_dump()
            except StrategyCompileError as exc:
                outcome["compile_error"] = str(exc)
    except InterpreterError as exc:
        outcome["schema_failed"] = True
        outcome["error"] = str(exc)[:300]
    except Exception as exc:  # noqa: BLE001 — 평가 하니스는 케이스 단위로 계속 진행
        outcome["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    outcome["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return outcome


def run_legacy_case(parser, case: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    parsed = parser.parse_rule_based(case["input"])
    return {
        "id": case["id"],
        "rule_parse_handled": parsed is not None,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def main() -> int:
    argp = argparse.ArgumentParser()
    argp.add_argument("--limit", type=int, default=None)
    argp.add_argument("--legacy", action="store_true", help="기존 규칙 파서 비교 실행")
    argp.add_argument("--out", type=str, default=None, help="상세 결과 JSONL 저장 경로")
    args = argp.parse_args()

    with open(DATASET_PATH, encoding="utf-8") as f:
        cases: List[Dict[str, Any]] = json.load(f)["cases"]
    if args.limit:
        cases = cases[: args.limit]

    from strategy_conversation.evaluation.metrics import aggregate, evaluate_case
    from strategy_conversation.interpreter.llm_strategy_interpreter import StrategyInterpreter

    interpreter = StrategyInterpreter()
    legacy_parser = None
    if args.legacy:
        from engine.nl_parser import NLStrategyParser
        legacy_parser = NLStrategyParser()

    outcomes: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    legacy_results: List[Dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} …", flush=True)
        outcome = run_case(interpreter, case)
        outcomes.append(outcome)
        results.append(evaluate_case(case, outcome))
        if legacy_parser is not None:
            legacy_results.append(run_legacy_case(legacy_parser, case))

    summary = aggregate(results, outcomes)
    if legacy_results:
        handled = sum(1 for r in legacy_results if r["rule_parse_handled"])
        summary["legacy_rule_parse_handled_rate"] = round(handled / len(legacy_results), 4)

    failed = [r for r in results if not r.get("passed")]
    print("\n=== 실패 케이스 ===")
    for r in failed:
        bad = [k for k, v in (r.get("checks") or {}).items() if not v]
        print(f"- {r['id']}: {'schema 실패' if r.get('schema_failed') else ', '.join(bad)}")

    print("\n=== 종합 지표 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for case, outcome, result in zip(cases, outcomes, results):
                f.write(json.dumps(
                    {"case": case, "outcome": outcome, "result": result},
                    ensure_ascii=False, default=str,
                ) + "\n")
        print(f"\n상세 결과 저장: {args.out}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
