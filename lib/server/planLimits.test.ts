import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  assertCanCreateAccount,
  assertCanSaveStrategy,
  consumeBacktestQuota,
  currentPlanCycle,
  currentUsageMonth,
  currentUsagePeriodKey,
  getEffectivePlan,
  getUserUsage,
  PLAN_LIMIT_ACCOUNTS,
  PLAN_LIMIT_BACKTESTS,
  PLAN_LIMIT_STRATEGIES,
} from "@/lib/server/planLimits";

function createClient(opts: {
  planTier?: string;
  accounts?: number;
  strategies?: number;
  planStartDate?: Date | null;
  backtestUsageMonth?: string | null;
  backtestCountThisMonth?: number;
} = {}) {
  return {
    user: {
      findUnique: vi.fn().mockResolvedValue({
        planTier: opts.planTier ?? "FREE",
        planStartDate: opts.planStartDate ?? null,
        backtestUsageMonth: opts.backtestUsageMonth ?? null,
        backtestCountThisMonth: opts.backtestCountThisMonth ?? 0,
      }),
      update: vi.fn().mockResolvedValue({}),
    },
    virtualAccount: {
      count: vi.fn().mockResolvedValue(opts.accounts ?? 0),
    },
    strategy: {
      count: vi.fn().mockResolvedValue(opts.strategies ?? 0),
    },
  };
}

describe("planLimits — 가상계좌 한도", () => {
  it("FREE 사용자는 계좌가 0개일 때 생성 가능", async () => {
    const client = createClient({ planTier: "FREE", accounts: 0 });
    await expect(assertCanCreateAccount(client as any, 1)).resolves.toBeUndefined();
  });

  it("FREE 사용자는 계좌 1개 이후 생성 불가(2개째 차단)", async () => {
    const client = createClient({ planTier: "FREE", accounts: 1 });
    await expect(assertCanCreateAccount(client as any, 1)).rejects.toThrow(PLAN_LIMIT_ACCOUNTS);
  });

  it("PRO 사용자는 계좌 10개 이후 생성 불가(11개째 차단)", async () => {
    const client = createClient({ planTier: "PRO", accounts: 10 });
    await expect(assertCanCreateAccount(client as any, 1)).rejects.toThrow(PLAN_LIMIT_ACCOUNTS);
  });

  it("PREMIUM 사용자는 계좌 30개 이후 생성 불가(31개째 차단)", async () => {
    const client = createClient({ planTier: "PREMIUM", accounts: 30 });
    await expect(assertCanCreateAccount(client as any, 1)).rejects.toThrow(PLAN_LIMIT_ACCOUNTS);
  });
});

describe("planLimits — 전략 저장 한도", () => {
  it("FREE 사용자는 전략 3개 이후 저장 불가(4개째 차단)", async () => {
    const client = createClient({ planTier: "FREE", strategies: 3 });
    await expect(assertCanSaveStrategy(client as any, 1)).rejects.toThrow(PLAN_LIMIT_STRATEGIES);
  });

  it("PRO 사용자는 전략 50개 이후 저장 불가(51개째 차단)", async () => {
    const client = createClient({ planTier: "PRO", strategies: 50 });
    await expect(assertCanSaveStrategy(client as any, 1)).rejects.toThrow(PLAN_LIMIT_STRATEGIES);
  });

  it("PREMIUM 사용자는 전략을 제한 없이 저장 가능", async () => {
    const client = createClient({ planTier: "PREMIUM", strategies: 10_000 });
    await expect(assertCanSaveStrategy(client as any, 1)).resolves.toBeUndefined();
    // 무제한이면 count 조회 자체를 하지 않는다
    expect(client.strategy.count).not.toHaveBeenCalled();
  });
});

describe("planLimits — 월 백테스트 한도", () => {
  const now = new Date("2026-06-15T03:00:00Z");
  const thisMonth = currentUsageMonth(now);

  it("한도 미만이면 카운트를 1 증가시킨다", async () => {
    const client = createClient({
      planTier: "FREE",
      backtestUsageMonth: thisMonth,
      backtestCountThisMonth: 5,
    });
    await consumeBacktestQuota(client as any, 1, now);
    expect(client.user.update).toHaveBeenCalledWith({
      where: { id: 1 },
      data: { backtestUsageMonth: thisMonth, backtestCountThisMonth: 6 },
    });
  });

  it("이번 달 한도(FREE 30회)에 도달하면 차단하고 카운트를 증가시키지 않는다", async () => {
    const client = createClient({
      planTier: "FREE",
      backtestUsageMonth: thisMonth,
      backtestCountThisMonth: 30,
    });
    await expect(consumeBacktestQuota(client as any, 1, now)).rejects.toThrow(PLAN_LIMIT_BACKTESTS);
    expect(client.user.update).not.toHaveBeenCalled();
  });

  it("저장된 달이 지난 달이면 카운트를 리셋하고 1부터 다시 센다", async () => {
    const client = createClient({
      planTier: "FREE",
      backtestUsageMonth: "2026-05",
      backtestCountThisMonth: 30,
    });
    await consumeBacktestQuota(client as any, 1, now);
    expect(client.user.update).toHaveBeenCalledWith({
      where: { id: 1 },
      data: { backtestUsageMonth: thisMonth, backtestCountThisMonth: 1 },
    });
  });
});

describe("planLimits — 사용량 요약", () => {
  it("getUserUsage는 플랜 한도와 사용량을 반환한다", async () => {
    const now = new Date("2026-06-15T03:00:00Z");
    const client = createClient({
      planTier: "PRO",
      accounts: 3,
      strategies: 12,
      backtestUsageMonth: currentUsageMonth(now),
      backtestCountThisMonth: 7,
    });
    const usage = await getUserUsage(client as any, 1, now);
    expect(usage.plan.planId).toBe("PRO");
    expect(usage.accounts).toEqual({ used: 3, limit: 10 });
    expect(usage.strategies).toEqual({ used: 12, limit: 50, unlimited: false });
    expect(usage.backtests).toEqual({ used: 7, limit: 200 });
  });

  it("지난 달 사용량은 이번 달 used=0으로 보고한다", async () => {
    const now = new Date("2026-06-15T03:00:00Z");
    const client = createClient({
      planTier: "FREE",
      backtestUsageMonth: "2026-05",
      backtestCountThisMonth: 25,
    });
    const usage = await getUserUsage(client as any, 1, now);
    expect(usage.backtests.used).toBe(0);
  });
});

describe("planLimits — PlanConfig 오버라이드 (관리자 콘솔)", () => {
  function withPlanConfig(client: ReturnType<typeof createClient>, override: unknown) {
    return {
      ...client,
      planConfig: { findUnique: vi.fn().mockResolvedValue(override) },
    };
  }

  it("오버라이드가 없으면 기본값을 그대로 쓴다", async () => {
    const client = withPlanConfig(createClient({ planTier: "FREE" }), null);
    const plan = await getEffectivePlan(client as any, "FREE");
    expect(plan.monthlyBacktestLimit).toBe(30);
    expect(plan.maxVirtualAccounts).toBe(1);
  });

  it("planConfig 미지원 클라이언트(기존 코드 경로)도 기본값으로 동작한다", async () => {
    const client = createClient({ planTier: "FREE" });
    const plan = await getEffectivePlan(client as any, "FREE");
    expect(plan.monthlyBacktestLimit).toBe(30);
  });

  it("오버라이드 필드는 덮어쓰고 null 필드는 기본값을 유지한다", async () => {
    const client = withPlanConfig(createClient({ planTier: "FREE" }), {
      planId: "FREE",
      monthlyBacktestLimit: 100,
      maxStrategies: null,
      maxVirtualAccounts: null,
    });
    const plan = await getEffectivePlan(client as any, "FREE");
    expect(plan.monthlyBacktestLimit).toBe(100);
    expect(plan.maxStrategies).toBe(3);
    expect(plan.maxVirtualAccounts).toBe(1);
  });

  it("maxStrategies = -1 은 무제한으로 해석한다", async () => {
    const client = withPlanConfig(createClient({ planTier: "FREE" }), {
      planId: "FREE",
      monthlyBacktestLimit: null,
      maxStrategies: -1,
      maxVirtualAccounts: null,
    });
    const plan = await getEffectivePlan(client as any, "FREE");
    expect(plan.isUnlimitedStrategies).toBe(true);
    expect(plan.maxStrategies).toBe(Infinity);
  });

  it("오버라이드된 백테스트 한도가 소비(consume)에 실제로 반영된다", async () => {
    const now = new Date("2026-06-15T03:00:00Z");
    const client = withPlanConfig(
      createClient({
        planTier: "FREE",
        backtestUsageMonth: currentUsageMonth(now),
        backtestCountThisMonth: 30, // 기본 한도(30)에는 이미 도달
      }),
      { planId: "FREE", monthlyBacktestLimit: 50, maxStrategies: null, maxVirtualAccounts: null }
    );
    // 오버라이드 한도 50이므로 통과해야 한다
    await expect(consumeBacktestQuota(client as any, 1, now)).resolves.toBeUndefined();
  });
});

describe("planLimits — 구독 시작일 기준 롤링 결제 주기", () => {
  it("currentPlanCycle은 구독 시작일로부터 1개월 주기를 계산한다", () => {
    const start = new Date("2026-06-10T00:00:00Z");
    const now = new Date("2026-06-15T00:00:00Z"); // 같은 주기 내
    const cycle = currentPlanCycle(start, now);
    expect(cycle.start.toISOString()).toBe(start.toISOString());
    expect(cycle.end.toISOString()).toBe("2026-07-10T00:00:00.000Z");
  });

  it("currentPlanCycle은 여러 달이 지나도 now를 포함하는 주기까지 롤링한다", () => {
    const start = new Date("2026-01-10T00:00:00Z");
    const now = new Date("2026-06-15T00:00:00Z"); // 5개월 경과
    const cycle = currentPlanCycle(start, now);
    expect(cycle.start.toISOString()).toBe("2026-06-10T00:00:00.000Z");
    expect(cycle.end.toISOString()).toBe("2026-07-10T00:00:00.000Z");
  });

  it("currentPlanCycle은 월말 시작일(1/31)을 다음 달 말일로 clamp한다", () => {
    const start = new Date("2026-01-31T00:00:00Z");
    const now = new Date("2026-02-01T00:00:00Z");
    const cycle = currentPlanCycle(start, now);
    expect(cycle.end.toISOString()).toBe("2026-02-28T00:00:00.000Z"); // 2026은 평년
  });

  it("currentUsagePeriodKey는 planStartDate가 없으면 캘린더 월로 폴백한다", () => {
    const now = new Date("2026-06-15T03:00:00Z");
    expect(currentUsagePeriodKey(null, now)).toBe(currentUsageMonth(now));
  });

  it("구독 주기가 지나면 백테스트 카운트를 리셋한다(캘린더 월이 아직 안 바뀌었어도)", async () => {
    // 구독 시작일 6/20, 현재 6/25 → 이전 주기(5/20~6/20)에 쌓인 사용량은 리셋되어야 한다
    const planStartDate = new Date("2026-06-20T00:00:00Z");
    const now = new Date("2026-06-25T00:00:00Z");
    const client = createClient({
      planTier: "FREE",
      planStartDate,
      backtestUsageMonth: "2026-05-20T00:00:00.000Z", // 이전 주기 키
      backtestCountThisMonth: 30,
    });
    await consumeBacktestQuota(client as any, 1, now);
    expect(client.user.update).toHaveBeenCalledWith({
      where: { id: 1 },
      data: {
        backtestUsageMonth: "2026-06-20T00:00:00.000Z",
        backtestCountThisMonth: 1,
      },
    });
  });

  it("getUserUsage는 구독 시작일이 있으면 롤링 주기 종료일을 planEndDate로 반환한다", async () => {
    const planStartDate = new Date("2026-06-10T00:00:00Z");
    const now = new Date("2026-06-15T00:00:00Z");
    const client = createClient({ planTier: "PRO", planStartDate });
    const usage = await getUserUsage(client as any, 1, now);
    expect(usage.planStartDate?.toISOString()).toBe(planStartDate.toISOString());
    expect(usage.planEndDate?.toISOString()).toBe("2026-07-10T00:00:00.000Z");
  });

  it("getUserUsage는 구독 이력이 없으면 planStartDate/planEndDate를 null로 반환한다", async () => {
    const now = new Date("2026-06-15T00:00:00Z");
    const client = createClient({ planTier: "FREE", planStartDate: null });
    const usage = await getUserUsage(client as any, 1, now);
    expect(usage.planStartDate).toBeNull();
    expect(usage.planEndDate).toBeNull();
  });
});
