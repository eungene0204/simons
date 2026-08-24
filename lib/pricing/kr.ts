// 한국 서비스 가격 — 통화 KRW.
//
// 가격의 단일 진실 원천은 lib/plans.ts다(토스페이먼츠 결제 경로가 그대로 읽는다 —
// 심사 중이라 동결). 이 파일은 지역별 가격 조회 인터페이스(lib/pricing)에 한국 가격을
// 노출하는 어댑터다. 한국 가격을 바꿀 때는 lib/plans.ts를 수정한다.

import { PLAN_ORDER, PLANS, type PlanId } from "@/lib/plans";
import type { RegionPricing } from "./types";

export const KR_PRICING: RegionPricing = {
  region: "kr",
  currency: "KRW",
  planOrder: PLAN_ORDER,
  monthlyPrice: Object.fromEntries(
    PLAN_ORDER.map((planId) => [planId, PLANS[planId].monthlyPrice])
  ) as Record<PlanId, number>,
};
