"""Run the existing API postprocessing after a fixed primary result."""
import time
from datetime import datetime, timezone
from unittest.mock import patch


def finalize_api(case, primary_result):
    import main
    from strategy_conversation.primary import apply_primary_meta
    request = main.NLParseRequest(**case.get("api_request", {
        "prompt": case["user_input"], "previous_parsed": case["previous_parsed"],
        "pending_question": case["question"], "pending_ask": case["pending_ask"],
        "previous_explicit_fields": case["explicit_fields"],
    }))
    result = main._build_parse_result(request, request.backend or "ollama",
        primary_result["parsed"], None, load_ms=0, parse_ms=0,
        request_started=time.perf_counter(), scan_prompt_for_sector=False,
        pending_conditions=primary_result.get("pending_conditions"),
        declined_fields=primary_result.get("declined_fields"))
    apply_primary_meta(result, primary_result)
    class ReplayClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2000, 1, 1, tzinfo=timezone.utc).astimezone(tz)
    with patch.object(main, "datetime", ReplayClock):
        return main._finalize_parse_result(result, request)
