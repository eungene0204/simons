// 요금제 페이지 표시용 — 세 플랜 전부에 관리자 한도 오버라이드(PlanConfig)를 병합한다.
// 한도 강제(lib/server/planLimits)는 오버라이드를 반영하는데 카드가 기본값만 보여주면
// 페이지 문구와 실제 한도가 어긋난다(2026-09-03 감사).
import { PLAN_ORDER, type Plan, type PlanId } from "@/lib/plans";
import { getEffectivePlan } from "@/lib/server/planLimits";
import { prisma } from "@/lib/prisma";

export async function getEffectivePlans(): Promise<Record<PlanId, Plan>> {
  const entries = await Promise.all(
    PLAN_ORDER.map(async (planId) => [planId, await getEffectivePlan(prisma, planId)] as const)
  );
  return Object.fromEntries(entries) as Record<PlanId, Plan>;
}
