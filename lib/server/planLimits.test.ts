import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  assertCanCreateAccount,
  assertCanSaveStrategy,
  consumeBacktestQuota,
  currentUsageMonth,
  getUserUsage,
  PLAN_LIMIT_ACCOUNTS,
  PLAN_LIMIT_BACKTESTS,
  PLAN_LIMIT_STRATEGIES,
} from "@/lib/server/planLimits";

function createClient(opts: {
  planTier?: string;
  accounts?: number;
  strategies?: number;
  backtestUsageMonth?: string | null;
  backtestCountThisMonth?: number;
} = {}) {
  return {
    user: {
      findUnique: vi.fn().mockResolvedValue({
        planTier: opts.planTier ?? "FREE",
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
    expect(usage.backtests).toEqual({ used: 7, limit: 100 });
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
