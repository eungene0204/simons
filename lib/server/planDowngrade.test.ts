import { describe, expect, it } from "vitest";
import { backtestUsageCarryOnDowngrade } from "./planDowngrade";
import { currentUsagePeriodKey } from "./planLimits";

// FREE 강등 시 이번 주기 백테스트 사용량이 0으로 되돌아가던 구멍(2026-09-03 감사)의 회귀 가드.
describe("backtestUsageCarryOnDowngrade", () => {
  const createdAt = new Date("2026-01-15T00:00:00Z");
  const planStartDate = new Date("2026-08-20T00:00:00Z");
  const now = new Date("2026-09-03T00:00:00Z");

  it("유료 주기에 쓴 횟수를 가입일 기준 주기 키로 옮겨 적는다", () => {
    const carry = backtestUsageCarryOnDowngrade(
      {
        planStartDate,
        createdAt,
        backtestUsageMonth: currentUsagePeriodKey(planStartDate, now),
        backtestCountThisMonth: 212,
      },
      now
    );
    expect(carry.backtestUsageMonth).toBe(currentUsagePeriodKey(createdAt, now));
    expect(carry.backtestCountThisMonth).toBe(212);
  });

  it("사용량 기록이 지난 주기 것이면 0으로 시작한다", () => {
    const carry = backtestUsageCarryOnDowngrade(
      { planStartDate, createdAt, backtestUsageMonth: "stale-key", backtestCountThisMonth: 40 },
      now
    );
    expect(carry.backtestCountThisMonth).toBe(0);
  });

  it("업그레이드 보너스(음수)는 FREE로 가져가지 않는다", () => {
    const carry = backtestUsageCarryOnDowngrade(
      {
        planStartDate,
        createdAt,
        backtestUsageMonth: currentUsagePeriodKey(planStartDate, now),
        backtestCountThisMonth: -12,
      },
      now
    );
    expect(carry.backtestCountThisMonth).toBe(0);
  });

  it("이미 FREE(planStartDate 없음)면 키가 바뀌지 않아 그대로 이어진다", () => {
    const key = currentUsagePeriodKey(createdAt, now);
    const carry = backtestUsageCarryOnDowngrade(
      { planStartDate: null, createdAt, backtestUsageMonth: key, backtestCountThisMonth: 7 },
      now
    );
    expect(carry).toEqual({ backtestUsageMonth: key, backtestCountThisMonth: 7 });
  });
});
