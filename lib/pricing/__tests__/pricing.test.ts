import { describe, expect, it } from "vitest";
import { PLAN_ORDER, PLANS } from "@/lib/plans";
import { getRegionPricing, KR_PRICING, US_PRICING } from "@/lib/pricing";

describe("지역별 가격표", () => {
  it("한국 가격은 lib/plans.ts(토스 결제 경로의 진실 원천)와 항상 일치한다", () => {
    for (const planId of PLAN_ORDER) {
      expect(KR_PRICING.monthlyPrice[planId]).toBe(PLANS[planId].monthlyPrice);
    }
    expect(KR_PRICING.currency).toBe("KRW");
  });

  it("글로벌 가격은 모든 플랜을 USD로 정의한다", () => {
    expect(US_PRICING.currency).toBe("USD");
    expect(US_PRICING.planOrder).toEqual(PLAN_ORDER);
    for (const planId of PLAN_ORDER) {
      expect(US_PRICING.monthlyPrice[planId]).toBeGreaterThanOrEqual(0);
    }
    expect(US_PRICING.monthlyPrice.FREE).toBe(0);
  });

  it("getRegionPricing은 지역에 맞는 가격표를 돌려준다", () => {
    expect(getRegionPricing("kr")).toBe(KR_PRICING);
    expect(getRegionPricing("us")).toBe(US_PRICING);
  });
});
