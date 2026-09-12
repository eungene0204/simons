import { describe, expect, it } from "vitest";

import {
  PLANS,
  YEARLY_DISCOUNT_PERCENT,
  orderNameFor,
  priceFor,
  isValidBillingCycle,
  yearlyDiscountPercent,
} from "./plans";

describe("연간 결제 가격", () => {
  it("연 가격은 월 가격 × 12에서 20% 이상 할인된 금액이다", () => {
    for (const planId of ["PRO", "PREMIUM"] as const) {
      const plan = PLANS[planId];
      expect(plan.yearlyPrice).toBeLessThanOrEqual(plan.monthlyPrice * 12 * 0.8);
    }
    expect(PLANS.PRO.yearlyPrice).toBe(240_000);
    expect(PLANS.PREMIUM.yearlyPrice).toBe(470_000);
  });

  it("할인율은 20%로 표기된다 — 부동소수 오차로 19%가 되지 않는다", () => {
    expect(yearlyDiscountPercent(PLANS.PRO)).toBe(20);
    expect(yearlyDiscountPercent(PLANS.PREMIUM)).toBe(20);
    expect(YEARLY_DISCOUNT_PERCENT).toBe(20);
  });

  it("표기 할인율은 모든 유료 플랜에서 실제 할인율 이하다(과장 금지)", () => {
    for (const planId of ["PRO", "PREMIUM"] as const) {
      const plan = PLANS[planId];
      const twelveMonths = plan.monthlyPrice * 12;
      const actual = ((twelveMonths - plan.yearlyPrice) * 100) / twelveMonths;
      expect(YEARLY_DISCOUNT_PERCENT).toBeLessThanOrEqual(actual);
    }
  });

  it("무료 플랜은 주기와 무관하게 0원이고 할인율도 0이다", () => {
    expect(priceFor(PLANS.FREE, "yearly")).toBe(0);
    expect(yearlyDiscountPercent(PLANS.FREE)).toBe(0);
  });

  it("priceFor는 주기별 1회 결제 금액을 돌려준다", () => {
    expect(priceFor(PLANS.PRO, "monthly")).toBe(25_000);
    expect(priceFor(PLANS.PRO, "yearly")).toBe(240_000);
  });

  it("주문명은 주기를 구분한다 — 월간 주문명은 기존 표기를 유지한다", () => {
    expect(orderNameFor(PLANS.PRO, "monthly")).toBe("널스탁 Pro 플랜 월 이용료");
    expect(orderNameFor(PLANS.PREMIUM, "yearly")).toBe("널스탁 Premium 플랜 연간 이용료");
  });

  it("isValidBillingCycle은 monthly/yearly만 통과시킨다", () => {
    expect(isValidBillingCycle("monthly")).toBe(true);
    expect(isValidBillingCycle("yearly")).toBe(true);
    expect(isValidBillingCycle("weekly")).toBe(false);
    expect(isValidBillingCycle(undefined)).toBe(false);
  });
});
