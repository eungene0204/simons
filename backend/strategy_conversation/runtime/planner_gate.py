"""Skip planning only when two independent interpretations agree on plain markets."""
from strategy_conversation.planner.dag import DagNode
from strategy_conversation.planner.dag_planner import DagPlanResult, ExecutedNode
from strategy_conversation.tools import call


def settle_plain_markets(intent, evidence):
    strategy = getattr(intent, "strategy", None)
    terms = evidence.universe_terms
    if strategy is None or not terms or getattr(intent, "unsupported_features", None):
        return None
    universe = strategy.universe
    # Every other universe restriction, including exclusions, needs the original path.
    if any(value for name, value in universe.model_dump().items() if name != "markets"):
        return None
    expected = set(universe.markets)
    if not expected or expected & {"ETF", "US_ETF"}:
        return None
    plan = observe_plain_markets(evidence)
    if plan is None or {item.observation["canonical"] for item in plan.executed.values()} != expected:
        return None
    return plan


def observe_plain_markets(evidence):
    if not evidence.universe_terms:
        return None
    executed = {}
    try:
        for index, term in enumerate(evidence.universe_terms):
            observation = call("classify_universe", text=term).model_dump()
            if observation.get("universe_type") != "MARKET":
                return None
            if observation.get("canonical") in (None, "ETF", "US_ETF"):
                return None
            node = DagNode(id=f"market_{index}", type="tool", tool="classify_universe",
                           args={"text": term})
            executed[node.id] = ExecutedNode(node, observation)
    except Exception:
        return None
    return DagPlanResult(outcome="universe_settled", question=None, chips=[], sector=None,
                         companies=[], nodes=[item.node for item in executed.values()],
                         executed=executed)


def plan_after_evidence(evidence_future, user_input, plan):
    """Start complex planning as soon as evidence arrives, alongside the main interpreter."""
    candidate = observe_plain_markets(evidence_future.result())
    return (candidate, True) if candidate is not None else (plan(user_input), False)
