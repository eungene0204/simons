import { beforeEach, describe, expect, it, vi } from "vitest";

const getSessionUserId = vi.fn();
const findUnique = vi.fn();
vi.mock("@/lib/get-user", () => ({ getSessionUserId: () => getSessionUserId() }));
vi.mock("@/lib/prisma", () => ({ prisma: { user: { findUnique: (a: any) => findUnique(a) } } }));
vi.mock("@/lib/server/billingRenewal", () => ({ BILLING_MAX_FAIL_COUNT: 3 }));

const { GET } = await import("./route");

const failing = (o = {}) => ({
  billingFailCount: 1,
  nextBillingAt: new Date("2026-12-02T01:00:00Z"),
  subscriptionPlanId: "PRO",
  subscriptionCanceledAt: null,
  paymentProvider: "toss",
  ...o,
});

describe("/api/user/billing-status", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSessionUserId.mockResolvedValue(1);
  });

  it("비로그인은 실패 없음", async () => {
    getSessionUserId.mockResolvedValue(null);
    expect(await (await GET()).json()).toEqual({ failure: null });
    expect(findUnique).not.toHaveBeenCalled();
  });

  it("토스 자동결제 실패 중이면 횟수·다음 시도 시각을 준다", async () => {
    findUnique.mockResolvedValue(failing());
    expect(await (await GET()).json()).toEqual({
      failure: { planName: "Pro", failCount: 1, maxFailCount: 3, nextRetryAt: "2026-12-02T01:00:00.000Z" },
    });
  });

  it.each([
    ["실패 0회", { billingFailCount: 0 }],
    ["구독 없음", { subscriptionPlanId: null }],
    ["해지 예약", { subscriptionCanceledAt: new Date() }],
    ["PayPal 구독", { paymentProvider: "paypal" }],
  ])("%s이면 배너를 띄우지 않는다", async (_label, override) => {
    findUnique.mockResolvedValue(failing(override));
    expect(await (await GET()).json()).toEqual({ failure: null });
  });

  it("조회가 실패해도 화면을 깨뜨리지 않는다", async () => {
    findUnique.mockRejectedValue(new Error("db down"));
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(await (await GET()).json()).toEqual({ failure: null });
    spy.mockRestore();
  });
});
