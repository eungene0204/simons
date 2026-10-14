"""Offline primary-lane replay; missing recordings must never invoke live tools."""
import json
import hashlib
import socket
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import ui_language
from strategy_conversation import primary
from strategy_conversation.interpreter.llm_strategy_interpreter import InterpreterResult
from strategy_conversation.interpreter.models import StrategyIntent
from strategy_conversation.interpreter.output_repair import extract_json_object


class ReplayBlocked(BaseException):
    """Bypass auxiliary fail-open exception handlers when the recording is incomplete."""


_EXTERNAL = (
    "engine.nl_parser.apply_theme_companies", "engine.nl_parser.replace_theme_universe",
    "engine.knowledge_graph.catalog_theme_candidates",
    "strategy_conversation.primary._ground_sector_term",
    "strategy_conversation.primary._searched_unresolved_lexicon_entry",
    "strategy_conversation.primary._apply_theme_via_canonical_match",
    "strategy_conversation.primary._plan_first",
    "strategy_conversation.primary._dag_planner_clarification",
    "strategy_conversation.primary._apply_us_theme_companies",
    "strategy_conversation.primary._apply_us_company_related",
    "strategy_conversation.primary._apply_us_industry",
    "strategy_conversation.primary._ground_us_theme_term",
    "engine.strategy_converter._load_universe",
    "stock_analysis.symbol_resolver.resolve_by_symbol",
    "engine.single_asset_review.review_single_asset_strategy",
)


def _json(value):
    if hasattr(value, "model_dump"):
        return _json(value.model_dump())
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json(v) for v in value]
    if isinstance(value, SimpleNamespace):
        return _json(vars(value))
    return value


class Recording:
    def __init__(self, calls):
        self.remaining = deepcopy(calls)
        self.events = []

    def consume(self, target, inputs):
        self.attempted = {"target": target, "inputs": inputs}
        if not self.remaining:
            raise ReplayBlocked(f"Missing recorded result: {target}")
        record = self.remaining.pop(0)
        if record["target"] != target or record["inputs"] != inputs:
            raise ReplayBlocked(f"Recorded request differs: {target}")
        self.events.append(record)
        return record

    def chat(self, system, user, **kwargs):
        record = self.consume("auxiliary_llm", {"system": system, "user": user, **kwargs})
        if record.get("error"):
            raise RuntimeError(record["error"])
        return record["output"]

    def external(self, target):
        def call(*args, **kwargs):
            state = args[0] if args and hasattr(args[0], "model_dump") else None
            inputs = {"args": _json(args[1:] if state is not None else args),
                      "kwargs": _json({k: v for k, v in kwargs.items() if k != "on_stage"})}
            record = self.consume(target, inputs)
            if state is not None:
                for key, value in record.get("updates", {}).items():
                    if key not in ("target_symbols", "theme_universe", "sector", "universe", "etf_theme"):
                        raise ReplayBlocked("Recorded knowledge result changes a non-universe field")
                    setattr(state, key, deepcopy(value))
            output = deepcopy(record["output"])
            if record.get("result_type") == "planner":
                from strategy_conversation.planner.dag import DagNode
                from strategy_conversation.planner.dag_planner import DagPlanResult, ExecutedNode
                output["nodes"] = [DagNode.model_validate(n) for n in output.get("nodes", [])]
                output["executed"] = {k: ExecutedNode(DagNode.model_validate(v["node"]), v["observation"])
                                      for k, v in output.get("executed", {}).items()}
                return DagPlanResult(**output)
            if record.get("result_type") == "stock_ref":
                return SimpleNamespace(**output) if output is not None else None
            return tuple(output) if record.get("result_type") == "tuple" else output
        return call


def replay_interpreter_requirements(result, user_input, recordings, stages):
    """Restore checks inside the completed Interpreter checkpoint from their tapes."""
    from strategy_conversation.interpreter.holding_period_check import _SYSTEM, reconcile_holding_days
    completed = deepcopy(result)
    for saved in recordings:
        if saved.get("inputs", {}).get("system") != _SYSTEM:
            continue
        request = json.loads(saved["inputs"]["user"])
        if request.get("utterance") != user_input:
            raise ReplayBlocked("Holding checkpoint utterance differs")
        patches = list(completed.intent.patches)
        used = set()
        for row in request["patches"]:
            index = next((i for i, p in enumerate(patches) if i not in used
                          and p.path == row["path"] and p.source_text == row["source_text"]), None)
            if index is None:
                raise ReplayBlocked("Holding checkpoint candidate differs")
            used.add(index)
            patches[index] = patches[index].model_copy(update={"value": row["value"]})
        tape = Recording([{"target": "auxiliary_llm", **saved}])
        completed.intent = reconcile_holding_days(
            completed.intent.model_copy(update={"patches": patches}), user_input, tape.chat)
        if tape.remaining or not tape.events:
            raise ReplayBlocked("Holding checkpoint request differs")
        stages.append({"stage": "required_interpreter_replay", "recorded_calls": tape.events,
                       "intent": _json(completed.intent)})
    return completed


def replay(case):
    """Return execution evidence, without asserting that the product result is correct."""
    from interpretation_replay_contract import validate_case, judge
    invalid = validate_case(case)
    if invalid:
        return {"case_id": case.get("case_id") if isinstance(case, dict) else None,
                "status": "HARNESS_INVALID", "reason": invalid}
    recording = Recording(case["recorded_calls"])
    from strategy_conversation.interpreter.decisions import DecisionLog
    decision_log = DecisionLog()
    try:
        result = InterpreterResult(
            intent=StrategyIntent.model_validate(case.get("normalized_intent")
                or json.loads(extract_json_object(case["initial_output"]))),
            raw_output=case["initial_output"], repair_attempts=0, latency_ms=0,
            model_name=case["measurement"]["response_model"],
            unreflected_numbers=case.get("unreflected_numbers"),
        )
    except (ValueError, TypeError) as exc:
        return {"case_id": case["case_id"], "status": "HARNESS_INVALID", "reason": str(exc)}
    stages = []
    interpreter = SimpleNamespace(interpret=lambda user_input, **k: replay_interpreter_requirements(
        result, user_input, case.get("interpreter_recordings", []), stages), _chat=recording.chat)
    def blocked(*a, **k):
        raise ReplayBlocked("Unrecorded external access")
    from strategy_conversation import tools
    real_tool = tools.call
    from strategy_conversation.conversation import patch_applier
    real_patch = patch_applier.apply_patches
    real_assembly = primary.assemble_sector_notices
    def assemble(report, parsed, receipts, **kwargs):
        output = real_assembly(report, parsed, receipts, **kwargs)
        stages.append({"stage": "universe_notice_assembly", "inputs": {
            "findings": deepcopy(report._universe_findings), "resolutions": deepcopy(receipts),
            "scope_terms": sorted(kwargs.get("scope_terms", ()))},
            "output": deepcopy(output)})
        return output
    real_observed_call = primary.observed_call
    def observed(target, function, *args, **kwargs):
        if target == "engine.nl_parser._extract_sector":
            return recording.external(target)(*args, **kwargs)
        return real_observed_call(target, function, *args, **kwargs)
    def apply(state, patches):
        output = real_patch(state, patches)
        stages.append({"stage": "patch_attempt", "patches": _json(patches), "output": _json(output)})
        return output
    def tool(name, **kwargs):
        if name not in ("validate_intent", "compile_strategy"):
            raise ReplayBlocked(f"Unrecorded tool: {name}")
        output = real_tool(name, **kwargs)
        stages.append({"stage": name, "inputs": _json(kwargs), "output": _json(output)})
        return output
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.dict("os.environ", {**case["configuration"],
                "AGENT_TRACE_LOCAL": "0", "LANGSMITH_TRACING": "false"}))
            stack.enter_context(ui_language.bind("en" if case["region"] == "US" else "ko"))
            stack.enter_context(patch.object(primary, "_interpreter_singleton", interpreter))
            stack.enter_context(patch("strategy_conversation.interpreter.decisions.DecisionLog",
                                      return_value=decision_log))
            stack.enter_context(patch("strategy_conversation.planner.shadow._default_chat",
                                      return_value=recording.chat))
            stack.enter_context(patch.object(tools, "call", tool))
            stack.enter_context(patch.object(patch_applier, "apply_patches", apply))
            stack.enter_context(patch.object(primary, "observed_call", observed))
            stack.enter_context(patch.object(primary, "assemble_sector_notices", assemble))
            for target in _EXTERNAL:
                stack.enter_context(patch(target, recording.external(target)))
            for target in ("engine.knowledge_graph.get_graph", "engine.term_grounding.lexicon_entry",
                           "engine.term_grounding._load_lexicon_cached"):
                stack.enter_context(patch(target, blocked))
            for method in ("connect", "connect_ex"):
                stack.enter_context(patch.object(socket.socket, method, blocked))
            stack.enter_context(patch.object(socket, "getaddrinfo", blocked))
            if case.get("api"):
                stack.enter_context(patch("time.perf_counter", return_value=0))
            if case["mode"] == "create":
                output = primary.run_primary_parse(case["user_input"],
                    previous_explicit_fields=case["explicit_fields"])
            else:
                output = primary.run_primary_modification(case["user_input"], case["previous_parsed"],
                    pending_question=case["question"], pending_ask=case["pending_ask"],
                    previous_explicit_fields=case["explicit_fields"],
                    previous_coach_text=case.get("previous_coach_text"),
                    previous_declined_fields=case.get("previous_declined_fields"))
            primary_output = _json(output)
            if case.get("api") and output is not None:
                from interpretation_api_replay import finalize_api
                output = finalize_api(case, output)
                stages.append({"stage": "api_postprocessing", "output": _json(output)})
            if recording.remaining:
                raise ReplayBlocked("Unused recorded results; execution differs")
        final = _json(output)
        from observability.tracing import replay_snapshot
        decision_evidence = replay_snapshot({"results": decision_log.results,
            "evidence": decision_log.evidence, "groups": decision_log.groups,
            "review": decision_log.review()})
        stages.append({"stage": "common_decision_approval", "output": decision_evidence})
        failures = judge(case["expected"], final)
        backend = Path(__file__).resolve().parents[1]
        sources = sorted((backend / "strategy_conversation").rglob("*.py"))
        source_hash = hashlib.sha256(b"".join(p.relative_to(backend).as_posix().encode()
                                              + p.read_bytes() for p in sources)).hexdigest()
        return {"case_id": case["case_id"], "status": "FAIL" if failures else "PASS",
                "mode": case["mode"], "region": case["region"],
                "failures": failures, "final": final, "stages": stages,
                "primary_final": primary_output,
                "recorded_calls": recording.events, "measurement": case["measurement"],
                "execution_mode": "replay", "new_model_calls": 0,
                "execution_identity": {"strategy_conversation_hash": source_hash}}
    except ReplayBlocked as exc:
        return {"case_id": case["case_id"], "status": "HARNESS_INVALID", "reason": str(exc),
                "stages": stages, "recorded_calls": recording.events, "new_model_calls": 0,
                "blocked_request": getattr(recording, "attempted", None)}
    except Exception as exc:
        return {"case_id": case["case_id"], "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}",
                "stages": stages, "recorded_calls": recording.events, "new_model_calls": 0}
