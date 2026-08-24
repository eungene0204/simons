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
  // 계좌당 초기 모의 투자금(가상계좌 시뮬레이션용 모의 자금) — 한국 금액
  // (1천만/5천만/1억원)을 달러 단위로 옮긴 초기값(placeholder)이다.
  initialInvestmentAmount: {
    FREE: 10_000,
    PRO: 50_000,
    PREMIUM: 100_000,
  } satisfies Record<PlanId, number>,
};
