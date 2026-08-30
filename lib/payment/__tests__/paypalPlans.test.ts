import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  isPaypalSubscriptionConfigured,
  paypalPlanIdFor,
  planIdFromPaypalPlan,
  usdCentsFor,
} from "@/lib/payment/paypalPlans";

beforeEach(() => {
  vi.stubEnv("PAYPAL_PLAN_PRO", "P-PRO-1");
  vi.stubEnv("PAYPAL_PLAN_PREMIUM", "P-PREMIUM-1");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("paypalPlans", () => {
  it("플랜 ID가 둘 다 있어야 구독 경로를 연다", () => {
    expect(isPaypalSubscriptionConfigured()).toBe(true);
    vi.stubEnv("PAYPAL_PLAN_PREMIUM", "");
    expect(isPaypalSubscriptionConfigured()).toBe(false);
  });

  it("우리 플랜 ↔ PayPal 플랜을 양방향으로 매핑한다", () => {
    expect(paypalPlanIdFor("PRO")).toBe("P-PRO-1");
    expect(planIdFromPaypalPlan("P-PREMIUM-1")).toBe("PREMIUM");
  });

  it("모르는 PayPal 플랜은 null — 남의 플랜을 물고 온 웹훅을 반영하지 않는다", () => {
    expect(planIdFromPaypalPlan("P-SOMEONE-ELSE")).toBeNull();
    expect(planIdFromPaypalPlan(undefined)).toBeNull();
  });

  it("환경변수가 없으면 구독을 만들지 않고 던진다", () => {
    vi.stubEnv("PAYPAL_PLAN_PRO", "");
    expect(() => paypalPlanIdFor("PRO")).toThrow("PAYPAL_PLAN_PRO");
  });

  it("FREE 플랜은 구독 대상이 아니다", () => {
    expect(() => paypalPlanIdFor("FREE")).toThrow("FREE");
  });

  it("결제 이력 금액은 센트 단위로 환산한다", () => {
    // 표시가 $19이면 이력에는 1900이 남는다 — 19로 남기면 KRW 이력과 자릿수가 뒤섞인다
    expect(usdCentsFor("PRO")).toBe(1900);
    expect(usdCentsFor("PREMIUM")).toBe(3900);
  });
});
