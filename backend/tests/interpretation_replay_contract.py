"""Validate replay provenance and compare human-authored semantic expectations."""
import hashlib
import importlib.util
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _canonical(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def validate_case(case):
    if not isinstance(case, dict):
        return "Replay case must be an object"
    required = {"case_id", "mode", "region", "user_input", "previous_parsed", "question",
                "pending_ask", "explicit_fields", "operation", "request", "request_hash",
                "initial_output", "recorded_calls", "configuration", "measurement", "expected"}
    if not required <= case.keys():
        return "Missing replay fields"
    if (not all(isinstance(case[k], dict) for k in ("configuration", "measurement", "expected"))
            or not isinstance(case["request"], list) or not isinstance(case["recorded_calls"], list)
            or not isinstance(case["initial_output"], str)
            or not isinstance(case["expected"].get("channels"), dict)):
        return "Malformed replay fields"
    if case["mode"] not in ("create", "modify", "fill") or case["region"] not in ("KR", "US"):
        return "Invalid mode or region"
    if case["operation"] not in ("create", "add", "replace", "remove"):
        return "Missing explicit change intent"
    request = case["request"]
    if (not isinstance(request, list) or not request
            or any(not isinstance(m, dict) or not isinstance(m.get("content"), str) for m in request)
            or any(m["content"].endswith("…(생략)") for m in request)
            or digest(request) != case["request_hash"]):
        return "Incomplete or mismatched request prompt"
    measurement = case["measurement"]
    versions = {"code", "schema", "catalog", "questions", "engine"}
    if (not {"requested_model", "response_model", "cache", "completed", "origin", "versions"}
            <= measurement.keys() or not isinstance(measurement["versions"], dict)
            or not versions <= measurement["versions"].keys()
            or any(not measurement["versions"][k] for k in versions)
            or not measurement["response_model"] or not measurement["requested_model"]
            or not isinstance(measurement["cache"], bool)):
        return "Missing measurement identity"
    if measurement["completed"] is not True:
        return "Incomplete recorded execution"
    if measurement["origin"] not in ("synthetic", "captured"):
        return "Unknown recording origin"
    if case["mode"] != "create":
        if not isinstance(case["previous_parsed"], dict):
            return "Missing previous strategy"
        if case["mode"] == "fill" or case.get("slot"):
            spec = importlib.util.spec_from_file_location("replay_qa", Path(__file__).resolve().parents[2]
                                                        / "scripts/qa_free_input.py")
            qa = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(qa)
            invalid = qa.fixture_error(case["mode"], case.get("slot"), case["previous_parsed"],
                                       case["question"], case["pending_ask"])
            if invalid:
                return invalid
    if not case["expected"].get("equal") and not case["expected"].get("all_items"):
        return "Missing human-reviewed state expectations"
    if not {"notices", "clarification_question", "clarification_suggestions"} <= case["expected"]["channels"].keys():
        return "Missing human-reviewed notice channels"
    return None


def pointer(value, path):
    for token in path.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def judge(expected, final):
    if final is None:
        return ["No final response"]
    failures = []
    for path, wanted in expected.get("equal", {}).items():
        try:
            if pointer(final, path) != wanted:
                failures.append(path)
        except (KeyError, IndexError, TypeError):
            failures.append(path)
    for path, rule in expected.get("all_items", {}).items():
        try:
            actual = [{key: item.get(key) for key in rule["keys"]} for item in pointer(final, path)]
            canonical = lambda items: sorted(json.dumps(_canonical(i), sort_keys=True) for i in items)
            if canonical(actual) != canonical(rule["items"]):
                failures.append(path)
        except (KeyError, TypeError):
            failures.append(path)
    for channel, rule in expected["channels"].items():
        value = final.get(channel)
        if "equal" in rule and value != rule["equal"]:
            failures.append(channel)
        text = "\n".join(value) if isinstance(value, list) else str(value or "")
        if any(s in text for s in rule.get("forbid", [])):
            failures.append(channel)
        if any(s not in text for s in rule.get("require", [])):
            failures.append(channel)
    return failures


def summarize(results):
    """Never pool cached, unfinished, synthetic, or different-model measurements."""
    groups = {}
    for result in results:
        identity = {**result.get("measurement", {}), "execution_mode": result.get("execution_mode"),
                    "execution_identity": result.get("execution_identity"),
                    "mode": result.get("mode"), "region": result.get("region")}
        key = json.dumps(identity, sort_keys=True)
        counts = groups.setdefault(key, {})
        status = result["status"]
        counts[status] = counts.get(status, 0) + 1
    return [{"identity": json.loads(key), "counts": counts} for key, counts in groups.items()]
