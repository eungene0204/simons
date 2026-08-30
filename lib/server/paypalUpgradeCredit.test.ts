import { describe, expect, it } from "vitest";
import { upgradeCreditDays, upgradeFirstPeriodDays } from "./paypalUpgradeCredit";

// 업그레이드 크레딧: 남은 PRO 가치를 PREMIUM 일수로 환산해 첫 주기에 더한다(즉시 $39 청구 정책의 보상)
describe("upgradeCreditDays", () => {
  const base = { fromMonthlyPrice: 19, toMonthlyPrice: 39 };

  it("PRO 15일 남음 → $9.50 → PREMIUM 약 7일 크레딧", () => {
    expect(
      upgradeCreditDays({
        ...base,
        now: new Date("2026-09-15T10:00:00Z"),
        nextBillingAt: new Date("2026-09-30T10:00:00Z"),
      })
    ).toBe(7);
  });

  it("결제 직후(30일 남음) 업그레이드하면 크레딧이 최대", () => {
    expect(
      upgradeCreditDays({
        ...base,
        now: new Date("2026-09-30T10:00:00Z"),
        nextBillingAt: new Date("2026-10-30T10:00:00Z"),
      })
    ).toBe(14); // $19 전액 → 39/30일 기준 14.6일 → 내림 14
  });

  it("결제일 당일·지난 뒤에는 크레딧이 없다", () => {
    const now = new Date("2026-09-30T10:00:00Z");
    expect(upgradeCreditDays({ ...base, now, nextBillingAt: now })).toBe(0);
    expect(
      upgradeCreditDays({ ...base, now, nextBillingAt: new Date("2026-09-29T10:00:00Z") })
    ).toBe(0);
  });

  it("첫 주기는 기본 30일 + 크레딧", () => {
    expect(
      upgradeFirstPeriodDays({
        ...base,
        now: new Date("2026-09-15T10:00:00Z"),
        nextBillingAt: new Date("2026-09-30T10:00:00Z"),
      })
    ).toBe(37);
  });
});
