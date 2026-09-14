// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 결제 우회 방지 회귀 가드: /api/user/plan POST는 FREE 전환(다운그레이드)만 허용한다.
// 유료 플랜(PRO/PREMIUM)은 반드시 결제 승인(/api/payment/confirm)을 거쳐야 한다.

const getOwnershipContext = vi.fn();
const getSessionUserId = vi.fn();
const assertActiveUser = vi.fn();
const userUpdate = vi.fn();
const userFindUnique = vi.fn();
const getUserUsage = vi.fn();
const cancelUserSubscription = vi.fn();

class FakeUnauthorizedError extends Error {}

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: (...a) => getOwnershipContext(...a),
  getSessionUserId: (...a) => getSessionUserId(...a),
  assertActiveUser: (...a) => assertActiveUser(...a),
  isUnauthorizedAccessError: (e) => e instanceof FakeUnauthorizedError,
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: { update: (...a) => userUpdate(...a), findUnique: (...a) => userFindUnique(...a) },
  },
}));

vi.mock("@/lib/server/planDowngrade", () => ({
  backtestUsageCarryOnDowngrade: () => ({ backtestUsageMonth: "2026-09", backtestCountThisMonth: 3 }),
  USAGE_CARRY_SELECT: {},
}));

vi.mock("@/lib/server/subscriptionCancel", () => ({
  cancelUserSubscription: (...a) => cancelUserSubscription(...a),
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
  userFindUnique.mockResolvedValue({ subscriptionPlanId: null, createdAt: new Date("2026-01-01") });
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

  it("구독이 없는 유료 등급의 FREE 전환은 즉시 내리고 빌링 상태(토스·PayPal)를 모두 비운다", async () => {
    const res = await POST(req({ planId: "FREE" }));
    expect(res.status).toBe(200);
    expect(cancelUserSubscription).not.toHaveBeenCalled();
    // 빌링키·구독 ID가 남아 있으면 갱신 잡·웹훅이 계속 청구/승격하므로 반드시 함께 해제되어야 한다
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: expect.objectContaining({
          planTier: "FREE",
          planStartDate: null,
          tossBillingKey: null,
          paypalSubscriptionId: null,
          subscriptionPlanId: null,
          nextBillingAt: null,
          subscriptionCanceledAt: null,
          billingFailCount: 0,
          // 이번 주기 백테스트 사용량은 이어 간다(0으로 리셋되던 구멍)
          backtestUsageMonth: expect.any(String),
          backtestCountThisMonth: expect.any(Number),
        }),
      })
    );
  });

  it("자동갱신 구독 중이면 즉시 내리지 않고 해지를 예약한다(결제 수단 분기는 헬퍼)", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: "PRO", createdAt: new Date("2026-01-01") });
    cancelUserSubscription.mockResolvedValue({ status: "scheduled", expiresAt: "2026-10-01T00:00:00.000Z" });

    const res = await POST(req({ planId: "FREE" }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(cancelUserSubscription).toHaveBeenCalledWith(expect.anything(), 7);
    expect(userUpdate).not.toHaveBeenCalled();
    expect(data.cancellation).toEqual({ status: "scheduled", expiresAt: "2026-10-01T00:00:00.000Z" });
  });
});

describe("/api/user/plan 게스트(특별 계정) 가드", () => {
  const guestRecord = {
    email: "guest_1234@guest.nullstock.im",
    subscriptionPlanId: null,
    createdAt: new Date("2026-09-14"),
  };

  it("게스트는 FREE 전환이 막힌다 — 403, 등급이 내려가지 않는다", async () => {
    userFindUnique.mockResolvedValue(guestRecord);

    const res = await POST({ json: async () => ({ planId: "FREE" }) });
    const body = await res.json();

    expect(res.status).toBe(403);
    expect(body.error).toContain("특별 계정");
    // 구독 없는 PREMIUM이라 막지 않으면 즉시 FREE로 내려가고 되돌릴 길이 없다
    expect(userUpdate).not.toHaveBeenCalled();
    expect(cancelUserSubscription).not.toHaveBeenCalled();
  });

  it("일반 회원의 FREE 전환은 종전대로 동작한다(가드가 과잉 차단하지 않는다)", async () => {
    userFindUnique.mockResolvedValue({
      email: "u@example.com",
      subscriptionPlanId: null,
      createdAt: new Date("2026-01-01"),
    });

    const res = await POST({ json: async () => ({ planId: "FREE" }) });

    expect(res.status).toBe(200);
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ where: { id: 7 } })
    );
  });

  it("GET은 게스트 여부를 함께 돌려준다 — 화면이 안내를 먼저 띄운다", async () => {
    userFindUnique.mockResolvedValue({ email: "guest_1234@guest.nullstock.im" });

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.isGuest).toBe(true);
  });

  it("GET은 일반 회원에게 isGuest=false를 준다", async () => {
    userFindUnique.mockResolvedValue({ email: "u@example.com" });

    const body = await (await GET()).json();

    expect(body.isGuest).toBe(false);
  });
});
