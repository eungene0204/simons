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
    """유니버스 구절이 전부 시장 전체를 가리키면 planner 없이 시장 관찰을 만든다.

    구절마다 정본 표 대조(classify_universe)가 먼저다. 표가 모르는 표기(CONCEPT — "다우지수 종목"·
    "KOSPI stocks")만 보조 추출 LLM이 구절별로 옮겨 적은 정본 시장 코드로 대신한다 —
    시장만 가리키는지의 판정은 LLM 몫이고, 여기서는 코드의 정본 소속만 본다(파서가 검증).
    한 구절이라도 시장이 아니면(업종·테마 한정, null) planner가 그대로 돈다.
    """
    if not evidence.universe_terms:
        return None
    markets = evidence.universe_markets or [None] * len(evidence.universe_terms)
    executed = {}
    try:
        for index, (term, market) in enumerate(zip(evidence.universe_terms, markets)):
            observation = call("classify_universe", text=term).model_dump()
            # 표가 모르는 표기(CONCEPT)일 때만 대신한다 — 표가 종목·업종·ETF로 짚은 구절은 덮지 않는다.
            if observation.get("universe_type") == "CONCEPT" and market is not None:
                observation = {"universe_type": "MARKET", "canonical": market}
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
