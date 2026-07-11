// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 결제 우회 방지 회귀 가드: /api/user/plan POST는 FREE 전환(다운그레이드)만 허용한다.
// 유료 플랜(PRO/PREMIUM)은 반드시 결제 승인(/api/payment/confirm)을 거쳐야 한다.

const getOwnershipContext = vi.fn();
const getSessionUserId = vi.fn();
const assertActiveUser = vi.fn();
const userUpdate = vi.fn();
const getUserUsage = vi.fn();

class FakeUnauthorizedError extends Error {}

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: (...a) => getOwnershipContext(...a),
  getSessionUserId: (...a) => getSessionUserId(...a),
  assertActiveUser: (...a) => assertActiveUser(...a),
  isUnauthorizedAccessError: (e) => e instanceof FakeUnauthorizedError,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { update: (...a) => userUpdate(...a) },
  },
}));

vi.mock("@/lib/server/planLimits", () => ({
  getUserUsage: (...a) => getUserUsage(...a),
}));

let GET;
let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ GET, POST } = await import("./route"));
  getOwnershipContext.mockResolvedValue({ userId: 7 });
  getSessionUserId.mockResolvedValue(7);
  assertActiveUser.mockResolvedValue(undefined);
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

describe("/api/user/plan GET", () => {
  it("활성 세션이면 플랜 사용량을 반환한다 (상태 검증은 사용량 조회와 병렬)", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.plan.planId).toBe("FREE");
    expect(assertActiveUser).toHaveBeenCalledWith(7);
    expect(getUserUsage).toHaveBeenCalled();
  });

  it("세션이 없으면 401을 반환하고 사용량을 조회하지 않는다", async () => {
    getSessionUserId.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(401);
    expect(getUserUsage).not.toHaveBeenCalled();
  });

  it("정지/삭제 계정은 유효한 토큰이 있어도 401을 반환한다", async () => {
    assertActiveUser.mockRejectedValue(new FakeUnauthorizedError());
    const res = await GET();
    expect(res.status).toBe(401);
  });
});

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
