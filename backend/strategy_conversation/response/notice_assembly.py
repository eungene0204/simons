"""KR notices projected from diagnostics, application receipts, and final state."""
from copy import deepcopy


def _key(value):
    return str(value or "").replace(" ", "").lower()


def remember_resolution(receipts, term, parsed, stage, field=None):
    """Capture only an applied universe result; a nonempty unrelated field is not evidence."""
    if receipts is None:
        return
    field = field or ("target_symbols" if getattr(parsed, "target_symbols", None) else "sector")
    value = getattr(parsed, field, None)
    if value:
        receipts.append({"term": term, "field": field, "value": deepcopy(value), "stage": stage})


def inherit_resolution(receipts, alias, canonical):
    if receipts is None:
        return
    for receipt in list(receipts):
        if _key(receipt["term"]) == _key(canonical):
            receipts.append({**deepcopy(receipt), "term": alias, "stage": "planner_first_alias"})


def initial_validation_notices(report):
    """Reserve KR catalog findings for final assembly; preserve all other diagnostics."""
    reserved = {finding["message"] for finding in report._universe_findings}
    return list(report.warnings) + [error for error in report.errors if error not in reserved]


def _reflected(receipt, parsed):
    expected = receipt["value"]
    actual = getattr(parsed, receipt["field"], None)
    if isinstance(expected, list):
        return bool(expected) and isinstance(actual, list) and set(expected) <= set(actual)
    return bool(expected) and expected == actual


def assemble_sector_notices(report, parsed, receipts, scope_terms=()):
    """Keep raw validation evidence intact; return final user-facing projections."""
    notices, decisions, owned_labels = [], [], set()
    for finding in report._universe_findings:
        matched = [receipt for receipt in receipts if _key(receipt["term"]) == _key(finding["term"])]
        resolved = any(_reflected(receipt, parsed) for receipt in matched)
        awaiting_scope = not resolved and _key(finding["term"]) in {_key(term) for term in scope_terms}
        decisions.append({**finding, "resolved": resolved, "awaiting_scope": awaiting_scope,
                          "resolution_evidence": matched,
                          "bound_features": [feature for feature in report.unsupported_features
                                             if _key(finding["term"]) and _key(finding["term"]) in _key(feature)],
                          "final_stage": "create_universe_notice_assembly"})
        owned_labels.update((_key(finding["term"]), _key(finding["feature"])))
        if not resolved and not awaiting_scope and finding["message"] not in notices:
            notices.append(finding["message"])
    # Explicit application and scope receipts also own labels that never reached
    # the KR sector validator (ETF and modification turns).
    known = {_key(d["term"]) for d in decisions}
    for term in list(dict.fromkeys([r["term"] for r in receipts] + list(scope_terms))):
        if _key(term) in known:
            continue
        matched = [r for r in receipts if _key(r["term"]) == _key(term)]
        resolved = any(_reflected(r, parsed) for r in matched)
        awaiting = not resolved and _key(term) in {_key(t) for t in scope_terms}
        if resolved or awaiting:
            decisions.append({"term": term, "feature": term, "resolved": resolved,
                "awaiting_scope": awaiting, "resolution_evidence": matched,
                "final_stage": "final_universe_notice_assembly"})
            known.add(_key(term))

    def consume_label(feature):
        # Preserve the existing LLM-label literal association, with per-term final-state proof.
        bound = [decision for decision in decisions
                 if _key(decision["term"]) and _key(decision["term"]) in _key(feature)]
        handled = [decision for decision in bound if decision["resolved"] or decision["awaiting_scope"]]
        if handled and len(handled) < len(bound):
            # Preserve the whole LLM report while distinguishing the known final-state outcomes.
            states = []
            for decision in bound:
                if decision["resolved"]:
                    status = "반영됨"
                elif decision["awaiting_scope"]:
                    status = "범위 선택 대기"
                else:
                    status = "미해결"
                states.append(f"'{decision['term']}' 투자 대상: {status}")
            notices.append(f"'{feature}' 표현의 일부가 미지원으로 보고됐어요. " + "; ".join(states))
            return True
        if bound and len(handled) == len(bound):
            # A compound free-form LLM label is not proof that its other words
            # were supported. Preserve the ambiguity without claiming nonapplication.
            if not any(_key(feature) in (_key(d["term"]), _key(d["feature"])) for d in handled):
                states = [f"'{d['term']}' 투자 대상: " + ("반영됨" if d["resolved"] else "범위 선택 대기")
                          for d in handled]
                notices.append(f"'{feature}' 표현의 처리 상태를 확인해 주세요. " + "; ".join(states))
            return True
        return False
    unsupported = [feature for feature in report.unsupported_features
                   if _key(feature) not in owned_labels and not consume_label(feature)]
    return {"notices": notices, "unsupported_features": unsupported, "decisions": decisions}


def notice_context(report, strategy, utterance, receipts=(), scope_terms=(), pending=(), dropped=()):
    """Internal handoff only; the API removes it before emitting its public response."""
    return {"report": report.model_dump(mode="json"), "findings": deepcopy(report._universe_findings),
            "strategy": strategy.model_dump(mode="json") if strategy else None,
            "utterance": utterance, "receipts": deepcopy(list(receipts or [])),
            "scope_terms": list(scope_terms), "pending": list(pending), "dropped": list(dropped),
            "generated": []}


def _reflected_conditions(strategy, parsed):
    from strategy_conversation.compiler.strategy_compiler import _compile_condition, StrategyCompileError

    reflected = []
    if strategy is None:
        return reflected
    for role in ("entry", "exit"):
        for condition in getattr(strategy, role + "_conditions"):
            try:
                field, value = _compile_condition(condition, role)
            except (StrategyCompileError, TypeError, ValueError):
                continue
            values = list(getattr(parsed, field, None) or [])
            if role == "entry" and field == "entry_signals":
                values += list(getattr(parsed, "entry_filters", None) or [])
            if value in values:
                reflected.append(condition)
    return reflected


def assemble_response_notices(result, *, consume=False):
    """One final projection for KR primary and the API's later postprocessing."""
    import ui_language
    if ui_language.get_ui_language() == "en":
        if consume:
            result.pop("_notice_context", None)
            result.pop("_notice_evidence", None)
        return result
    from .notice_evidence import collect, project
    collect(result)
    context = result.get("_notice_context")
    candidates = list(result.get("notices") or [])
    if context:
        import re
        import ui_language
        from engine.nl_parser import ParsedStrategy, concepts_expressed_in_strategy, MacroFilter
        from strategy_conversation import primary as p
        from strategy_conversation.interpreter.models import StrategySpec, ValidationReport
        from strategy_conversation.registry.indicator_registry import ranking_covers

        parsed = result.get("parsed")
        if isinstance(parsed, dict):
            parsed = ParsedStrategy.model_validate(parsed)
        report = ValidationReport.model_validate(context["report"])
        report._universe_findings = deepcopy(context["findings"])
        strategy = StrategySpec.model_validate(context["strategy"]) if context["strategy"] else None
        candidates = [n for n in candidates if n not in context["generated"]]
        reserved = {finding["message"] for finding in report._universe_findings}
        candidates = [n for n in candidates if n not in reserved]
        assembled = assemble_sector_notices(report, parsed, context["receipts"], context["scope_terms"])
        generated = list(assembled["notices"])
        generated += p.pending_value_notices(context["dropped"], context["pending"],
            clarification_question=result.get("clarification_question"),
            clarification_suggestions=result.get("clarification_suggestions"),
            pending_ask=result.get("pending_ask"), notices=candidates + generated)
        reflected = _reflected_conditions(strategy, parsed)
        reflected_texts = [c.source_text or "" for c in reflected]
        if strategy:
            executable_macro = MacroFilter.executable(parsed.macro_filters)
            reflected_texts += [spec.source_text or "" for spec, compiled in
                zip(strategy.macro_filters, parsed.macro_filters) if compiled in executable_macro]
            reflected_strategy = strategy.model_copy(deep=True)
            reflected_strategy.entry_conditions = [c for c in strategy.entry_conditions if c in reflected]
            reflected_strategy.exit_conditions = [c for c in strategy.exit_conditions if c in reflected]
            generated += p._approximation_notices(reflected_strategy)
        covered = " ".join([result.get("clarification_question") or "",
            p._queued_ask_text(result.get("pending_ask"))] + candidates + generated
            + [str(item.get("label") or "") for item in context["pending"]])
        features = assembled["unsupported_features"]
        # 이중 기입 대조는 값 대기로 최종 전략에 못 들어간 근사 조건의 인용도 포함한다 — 그 문장은
        # 근사 조건이 맡고 있어 조각을 "지원하지 않아"로 알리면 모순이다(안내 문구만 반영된 조건 기준).
        validated_conditions = (list(strategy.entry_conditions) + list(strategy.exit_conditions)) if strategy else []
        if features and not p._reported_features_echo_input(features, context["utterance"]):
            expressed = concepts_expressed_in_strategy(parsed, context["utterance"])
            ranking_ids = [rank.metric for rank in (strategy.ranking if strategy else [])]
            leftovers = p._drop_fragments_wrapping_others([f for f in p._humanize_features(features)
                if f and f not in covered and not p._concept_expressed(f, expressed)
                and not p._covered_by_pending_texts(f, context["pending"])
                and not p._covered_by_source_texts(f, reflected_texts)
                and not p._covered_by_risk_values(f, parsed)
                and not p._covered_by_approximated_texts(f, validated_conditions)
                and not ranking_covers(f, ranking_ids)
                and not re.search(r"\b[a-z_]{2,}\.[a-z_0-9]{2,}", f)
                and not p._INTERNAL_FIELD_NAME_RE.search(f)])
            short = [f for f in leftovers if len(f) <= p._QUOTED_FEATURE_MAX_LEN]
            long = [f for f in leftovers if len(f) > p._QUOTED_FEATURE_MAX_LEN]
            for names in ([", ".join(short)] if short else []) + long:
                generated.append(ui_language.msg(
                    "'{names}' 조건은 지원하지 않아 전략에 반영하지 못했어요.",
                    "The condition '{names}' is not supported, so it was not reflected in the strategy.", names=names))
        context["generated"] = generated
        candidates += generated
        from observability import span
        with span("Final KR notice assembly", "chain") as trace:
            trace.local_evidence(universe_notice_decisions=assembled["decisions"])
    result["notices"] = list(dict.fromkeys(n for n in candidates if n))
    # Replaced projections cannot survive as old candidates after an API change.
    active = {str(n) for n in result["notices"]}
    result["_notice_evidence"] = [item for item in result.get("_notice_evidence", []) if item["text"] in active]
    regenerated = set(context["generated"]) if context else set()
    result["_notice_evidence"] = [item for item in result["_notice_evidence"] if item["text"] not in regenerated]
    decisions = project(result)
    from observability import span
    with span("Final notice producer evidence", "chain") as trace:
        trace.local_evidence(notice_decisions=decisions)
    if consume:
        result.pop("_notice_context", None)
        result.pop("_notice_evidence", None)
    return result


def finalize_user_response(result):
    from strategy_conversation.response.output_guard import finalize_user_response as guard

    return guard(assemble_response_notices(result))
