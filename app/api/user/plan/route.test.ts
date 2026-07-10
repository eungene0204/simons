// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 결제 우회 방지 회귀 가드: /api/user/plan POST는 FREE 전환(다운그레이드)만 허용한다.
// 유료 플랜(PRO/PREMIUM)은 반드시 결제 승인(/api/payment/confirm)을 거쳐야 한다.

const getOwnershipContext = vi.fn();
const userUpdate = vi.fn();
const getUserUsage = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: (...a) => getOwnershipContext(...a),
  isUnauthorizedAccessError: () => false,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { update: (...a) => userUpdate(...a) },
  },
}));

vi.mock("@/lib/server/planLimits", () => ({
  getUserUsage: (...a) => getUserUsage(...a),
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ POST } = await import("./route"));
  getOwnershipContext.mockResolvedValue({ userId: 7 });
  userUpdate.mockResolvedValue({});
  getUserUsage.mockResolvedValue({
    plan: {
      planId: "FREE",
      name: "Free",
      monthlyPrice: 0,
      initialInvestmentAmount: 10_000_000,
      maxVirtualAccounts: 1,
      maxStrategies: 3,
      monthlyBacktestLimit: 30,
      isUnlimitedStrategies: false,
    },
    planStartDate: null,
    planEndDate: null,
    accounts: { used: 0, limit: 1 },
    strategies: { used: 0, limit: 3, unlimited: false },
    backtests: { used: 0, limit: 30 },
  });
});

function req(body) {
  return { json: async () => body };
}

describe("/api/user/plan POST", () => {
  it("유료 플랜(PRO)으로의 무결제 전환을 거부한다", async () => {
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(400);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("유료 플랜(PREMIUM)으로의 무결제 전환을 거부한다", async () => {
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(400);
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("FREE 전환은 허용하고 planStartDate와 자동결제(빌링) 상태를 모두 비운다", async () => {
    const res = await POST(req({ planId: "FREE" }));
    expect(res.status).toBe(200);
    // 빌링키가 남아 있으면 갱신 잡이 계속 청구하므로 반드시 함께 해제되어야 한다
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: {
          planTier: "FREE",
          planStartDate: null,
          tossBillingKey: null,
          subscriptionPlanId: null,
          nextBillingAt: null,
          subscriptionCanceledAt: null,
          billingFailCount: 0,
        },
      })
    );
  });
});
