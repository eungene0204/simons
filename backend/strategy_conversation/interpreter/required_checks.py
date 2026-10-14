"""Request-local requirements within the existing auxiliary checker targets."""
from .decisions import current_log, digest, record


QUESTIONS = {
    "quote": "보류한 조건의 지표와 매수·청산 기준을 다시 알려주시겠어요?",
    "trading": "거래대금은 금액 기준인가요, 자신의 평균 대비 배수인가요?",
    "return": "수익률은 시장과 비교할까요, 종목 간 순위로 정할까요?",
    "market": "변경할 시장 범위를 다시 알려주시겠어요?",
    "condition": "보류한 조건의 지표와 기준값을 다시 알려주시겠어요?",
    "numeric": "보류한 변경의 수량과 단위를 다시 알려주시겠어요?",
    "holding": "최대·최소 보유 기간의 수량과 단위를 다시 알려주시겠어요?",
    "region": "변경할 종목과 상장 시장을 다시 알려주시겠어요?",
    "pair": "기존 조건을 새 조건으로 바꿀까요, 아니면 새 조건을 추가할까요?",
}


class RequiredChecks:
    def __init__(self):
        self.items = []
        self.recoveries = {}

    def recover(self, condition, evidence):
        if any(i["subject"] is condition and i["status"] == "REJECT" for i in self.items):
            return
        log = current_log()
        parent = log.bindings.get(id(condition)) if log else None
        if parent:
            log.bind(condition, parent[1] + ":recovery:" + digest(condition)[:16], parent[1])
        row = record("condition_recovery", condition, "ACCEPT", "VERIFIED_TRANSFORMATION",
                     {"parent_candidate": parent[0] if parent else None, "evidence": evidence,
                      "replacement": condition.model_dump()})
        if row is None:
            if parent:
                log.bind(condition, *parent)
            return
        if parent:
            log.superseded.add(parent[0])
        self.recoveries[id(condition)] = row

    def plan(self, kind, subjects):
        log = current_log()
        if log is None:
            return
        for subject in subjects:
            if id(subject) not in log.bindings:
                identity = "required:" + digest(subject)[:20]
                log.bind(subject, identity, identity)
        log.groups.append({"stage": "required_plan", "kind": kind,
            "applicability": "REQUIRED" if subjects else "NOT_APPLICABLE",
            "candidate_ids": [log.bindings[id(s)][0] for s in subjects]})

    def note(self, kind, subject, status, field, evidence=None):
        self.plan(kind, [subject])
        log = current_log()
        if log is not None and id(subject) not in log.bindings:
            identity = "required:" + digest(subject)[:20]
            log.bind(subject, identity, identity)
        row = record("required_" + kind, subject, status,
                     "REQUIRED_CONFIRMED" if status == "ACCEPT" else
                     "REQUIRED_REJECTED" if status == "REJECT" else "REQUIRED_RESULT_MISSING",
                     evidence)
        self.items.append({"subject": subject, "kind": kind, "status": status,
                           "field": field, "row": row, "evidence": evidence})
        if log is not None:
            log.groups.append({"stage": "required_verdict", "required": True,
                               "field": field, **(row or {"status": status})})

    def conditions(self, intent, user_input, only=None):
        from .quote_check import targets_for_intent
        from .trading_value_check import conditions_to_check
        targets = (targets_for_intent(intent, user_input, only),
                   conditions_to_check(intent.strategy, only) if intent.strategy else [])
        self.plan("quote", [c for c, _ in targets[0]])
        self.plan("trading", targets[1])
        return targets

    def settle(self, targets, verdicts):
        from .quote_check import quote_does_not_express
        quotes, trading = targets
        for condition, role in quotes:
            verdict = verdicts.get(condition) if verdicts is not None else None
            status = ("REJECT" if quote_does_not_express(verdicts, condition) else
                      "ACCEPT" if verdict and verdict.expresses == "yes" else "UNRESOLVED")
            self.note("quote", condition, status, role, verdict)
        log = current_log()
        for condition in trading:
            identity = log.bindings.get(id(condition)) if log else None
            rows = [r for r in log.results if identity and r["candidate_id"] == identity[0]
                    and r["stage"] == "check_trading_value_quotes"] if log else []
            self.note("trading", condition, rows[-1]["status"] if rows else "UNRESOLVED",
                      "conditions", rows[-1] if rows else None)

    def blocked(self, subject):
        return any(i["subject"] is subject and i["status"] != "ACCEPT" for i in self.items)

    def filter_conditions(self, strategy):
        held = []
        for field in ("entry_conditions", "exit_conditions"):
            kept = []
            for condition in getattr(strategy, field):
                failures = [i for i in self.items if i["subject"] is condition and i["status"] != "ACCEPT"]
                # A classified breakout is a distinct, supported recovery of a
                # misfiled MA, not approval of the original condition.
                recovered = condition.factor == "technical.breakout" and failures and all(
                    i["kind"] == "quote" and getattr(i["evidence"], "describes", None)
                    == "new_high_breakout" for i in failures)
                recovered = recovered or (id(condition) in self.recoveries and failures and all(
                    i["kind"] == "quote" and i["status"] == "UNRESOLVED"
                    and getattr(i["evidence"], "describes", None) == "moving_average" for i in failures))
                if failures and not recovered:
                    held.extend(failures)
                else:
                    if recovered and condition.factor == "technical.breakout":
                        self.recover(condition, {"source_evidence": [i["row"] for i in failures]})
                    kept.append(condition)
            setattr(strategy, field, kept)
        return held

    def question(self, items=None):
        failures = [i for i in (items if items is not None else self.items) if i["status"] == "UNRESOLVED"]
        questions = list(dict.fromkeys(QUESTIONS[i["kind"]] for i in failures))
        if not questions:
            return None
        ask = {"question": questions[0], "topic": "보류한 변경", "chips": []}
        if len(questions) > 1:
            ask["queue"] = [{"question": q, "topic": "보류한 변경", "chips": []} for q in questions[1:]]
        return questions[0], None, ask


def policy():
    return getattr(current_log(), "required_checks", None)


def note(kind, subject, status, field, evidence=None):
    checks = policy()
    if checks is not None:
        checks.note(kind, subject, status, field, evidence)
