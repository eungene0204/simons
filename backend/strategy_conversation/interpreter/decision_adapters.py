"""Adapters for existing normalized checker results; no new semantic inference."""
from .decisions import record


def _emit(stage, subject, status, value):
    record(stage, subject, status, "VERDICT_" + status, value)


def record_verdicts(stage, adapter, args, kwargs, output):
    if adapter == "quote":
        from .quote_check import quote_does_not_express
        for condition, role in args[1]:
            verdict = output.get(condition) if output is not None else None
            status = ("REJECT" if quote_does_not_express(output, condition) else
                      "ACCEPT" if verdict and verdict.expresses == "yes" else "UNRESOLVED")
            _emit(stage, condition, status, {"role": role, "verdict": verdict})
    elif adapter == "trading":
        pairs = {id(condition): verdict for condition, verdict in output or []}
        for condition in args[1]:
            verdict = pairs.get(id(condition))
            kind = getattr(verdict, "compares", None)
            _emit(stage, condition, "REJECT" if kind == "volume" else
                  "ACCEPT" if kind in ("own_average", "amount") else "UNRESOLVED", verdict)
    elif adapter in ("numeric", "scope"):
        for index, patch in args[0]:
            value = index in output if adapter == "numeric" and index in output else (
                output.get(index) if adapter == "scope" else None)
            _emit(stage, patch, "ACCEPT" if value is True else "REJECT" if value is False else "UNRESOLVED", value)
    elif adapter == "market_scope":
        _emit(stage, args[0], "ACCEPT" if output is True else "REJECT" if output is False else "UNRESOLVED", output)
    elif adapter == "market":
        for term in args[0]:
            value = (output or {}).get(term)
            # Classification success is not approval of a strategy's market change.
            _emit(stage, term, "ACCEPT" if value in ("KR", "US", "OTHER") else "UNRESOLVED", value)
    elif adapter == "pair":
        _emit(stage, {"field": args[2], "old": args[3], "new": args[4]},
              "ACCEPT" if output in ("replace", "add") else "UNRESOLVED", output)
    elif adapter == "return":
        _emit(stage, args[1], "ACCEPT" if output and output != "unclear" else "UNRESOLVED", output)
    elif adapter == "holding":
        _emit(stage, args[1], "ACCEPT" if output is not None else "UNRESOLVED", output)
    elif adapter == "us_market_explicit":
        _emit(stage, args[1], "ACCEPT" if output is not None else "UNRESOLVED", output)
