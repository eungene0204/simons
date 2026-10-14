"""Build an in-memory replay from complete local evidence and independent human gold."""
from copy import deepcopy

from interpretation_replay_contract import digest, validate_case


def snapshot(node, key):
    value = node.get("metadata", {}).get(key, {})
    if (value.get("complete") is not True or value.get("sha256") != digest(value.get("values"))):
        raise ValueError(f"Incomplete local snapshot: {key}")
    return value["values"]


def from_trace(record, annotation):
    """Old previews, missing dependencies and missing served models are never repaired."""
    root = record["span"]
    if root.get("metadata", {}).get("replay_completed") is not True:
        raise ValueError("Incomplete root execution")
    evidence = snapshot(root, "replay_evidence")
    request = evidence["request"]
    api = evidence["api_response"]
    if (api.get("runtime") or {}).get("cache_hit"):
        raise ValueError("Cached response has no interpreter execution to replay")
    calls, models, interpreter_llms, checkpoints = [], [], [], []

    def walk(node, interpreter=False, suppressed=False):
        metadata = node.get("metadata", {})
        local = snapshot(node, "replay_evidence") if "replay_evidence" in metadata else {}
        inside = interpreter or "interpreter_result" in local
        if "interpreter_result" in local:
            checkpoints.append(local["interpreter_result"])
        if node.get("role") == "llm":
            if not local.get("requested_model") or not local.get("response_model"):
                raise ValueError("Missing actual model identity")
            models.append({k: local.get(k) for k in
                           ("requested_model", "response_model", "response_provider")})
            models[-1]["generation"] = snapshot(node, "replay_initial_metadata")
            output = snapshot(node, "replay_outputs")["response"]
            inputs = local["chat_arguments"]
            if inside:
                interpreter_llms.append({"inputs": inputs, "output": output, "model": models[-1]})
            elif not suppressed:
                calls.append({"target": "auxiliary_llm", "inputs": inputs, "output": output})
        dependency = local.get("recorded_call")
        if dependency and not suppressed:
            if dependency.get("input_complete") is not True:
                raise ValueError("Incomplete dependency inputs")
            calls.append(deepcopy(dependency))
        for child in node.get("children", []):
            walk(child, inside, suppressed or bool(dependency))

    walk(root)
    if len(checkpoints) != 1 or not interpreter_llms:
        raise ValueError("Missing or ambiguous interpreter checkpoint")
    first = interpreter_llms[0]
    messages = [{"role": role, "content": first["inputs"][key]}
                for role, key in (("system", "system"), ("user", "user"))]
    initial = checkpoints[0]
    if (annotation.get("mode") == "create") != (request.get("previous_parsed") is None):
        raise ValueError("Human mode differs from captured previous strategy")
    case = {**deepcopy(annotation), "region": evidence["region"],
            "user_input": request["prompt"], "previous_parsed": request.get("previous_parsed"),
            "question": request.get("pending_question"), "pending_ask": request.get("pending_ask"),
            "explicit_fields": request.get("previous_explicit_fields") or [],
            "previous_coach_text": request.get("previous_coach_text"),
            "previous_declined_fields": request.get("previous_declined_fields"),
            "request": messages, "request_hash": digest(messages),
            "initial_output": first["output"], "normalized_intent": initial["intent"],
            "unreflected_numbers": initial.get("unreflected_numbers"),
            "interpreter_recordings": interpreter_llms, "recorded_calls": calls,
            "configuration": evidence["configuration"], "api": True, "api_request": request,
            "measurement": {**first["model"], "models": models, "cache": False,
                            "completed": True, "origin": "captured", "versions": evidence["versions"]}}
    invalid = validate_case(case)
    if invalid:
        raise ValueError(invalid)
    return case
