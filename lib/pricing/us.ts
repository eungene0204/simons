// 글로벌 서비스 가격 — 통화 USD. 한국 가격(lib/plans.ts)과 독립적으로 관리한다.
//
// ⚠️ 아래 금액은 출시 전 확정이 필요한 초기값(placeholder)이다 — 한국 가격
// (PRO 25,000원 / PREMIUM 49,000원)을 통상적인 SaaS 가격대로 환산해 두었다.

import { PLAN_ORDER, type PlanId } from "@/lib/plans";
import type { RegionPricing } from "./types";

export const US_PRICING: RegionPricing = {
  region: "us",
  currency: "USD",
  planOrder: PLAN_ORDER,
  monthlyPrice: {
    FREE: 0,
    PRO: 19,
    PREMIUM: 39,
  } satisfies Record<PlanId, number>,
};
