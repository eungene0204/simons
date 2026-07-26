"""Mini-Planner 레이어(Phase 3) — 테마/유니버스 해석 구간 한정 동적 도구 계획.

기본 off. STRATEGY_PLANNER_MODE=shadow에서 관측 전용으로만 실행된다 — primary 승격은
shadow 로그 비교(고정 체인 대비 해석률·되묻기 품질·지연)로 판정한 뒤다.
"""

from strategy_conversation.planner.mini_planner import (  # noqa: F401
    PlannerResult,
    PlannerStep,
    plan_universe_resolution,
)
from strategy_conversation.planner.shadow import maybe_shadow_plan  # noqa: F401
