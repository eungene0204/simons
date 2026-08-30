// PayPal 빌링 플랜 ↔ 우리 플랜(PlanId) 매핑.
//
// 플랜은 사용자마다 만들지 않고 PayPal에 미리 하나씩 만들어 두고(scripts/paypal-create-plans.ts)
// 그 plan_id를 환경변수로 주입한다. 구독 생성은 우리 PlanId → PayPal plan_id 방향으로,
// 웹훅 처리는 그 반대 방향으로 조회한다.

import { isValidPlanId, type PlanId } from "@/lib/plans";
import { US_PRICING } from "@/lib/pricing/us";

type PaidPlanId = Exclude<PlanId, "FREE">;

const PLAN_ENV_KEYS: Record<PaidPlanId, string> = {
  PRO: "PAYPAL_PLAN_PRO",
  PREMIUM: "PAYPAL_PLAN_PREMIUM",
};

function readPlanEnv(planId: PaidPlanId): string | undefined {
  return process.env[PLAN_ENV_KEYS[planId]]?.trim() || undefined;
}

/** 유료 플랜 2개의 PayPal plan_id가 모두 주입돼 있는지 — 하나라도 없으면 구독 경로를 열지 않는다. */
export function isPaypalSubscriptionConfigured(): boolean {
  return Boolean(readPlanEnv("PRO") && readPlanEnv("PREMIUM"));
}

/** 우리 플랜 → PayPal plan_id. 미설정이면 던진다(잘못된 플랜으로 구독이 생기는 것보다 낫다). */
export function paypalPlanIdFor(planId: PlanId): string {
  if (planId === "FREE") {
    throw new Error("FREE 플랜은 구독을 만들 수 없습니다.");
  }
  const paypalPlanId = readPlanEnv(planId);
  if (!paypalPlanId) {
    throw new Error(`${PLAN_ENV_KEYS[planId]} 환경변수가 설정되지 않았습니다.`);
  }
  return paypalPlanId;
}

/** PayPal plan_id → 우리 플랜. 모르는 플랜이면 null (웹훅이 남의 플랜을 물고 와도 반영하지 않는다). */
export function planIdFromPaypalPlan(paypalPlanId: string | undefined): PlanId | null {
  if (!paypalPlanId) return null;
  for (const planId of Object.keys(PLAN_ENV_KEYS) as PaidPlanId[]) {
    if (readPlanEnv(planId) === paypalPlanId) return planId;
  }
  return null;
}

/**
 * 결제 이력(PaymentOrder.amount)에 남길 금액 — USD는 통화 최소 단위(센트)로 저장한다.
 * 표시 금액은 lib/pricing/us.ts가 정본이며, 실제 청구 금액은 PayPal 플랜에 고정돼 있다.
 */
export function usdCentsFor(planId: PlanId): number {
  if (!isValidPlanId(planId)) {
    throw new Error(`알 수 없는 플랜입니다: ${planId}`);
  }
  return Math.round(US_PRICING.monthlyPrice[planId] * 100);
}
