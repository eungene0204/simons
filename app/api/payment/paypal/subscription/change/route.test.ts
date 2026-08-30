// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 플랜 변경(revise) 가드:
// - 새 구독을 만들지 않고 기존 구독의 빌링 플랜만 바꾼다(이중 청구 방지)
// - 활성 PayPal 구독이 있어야 하고, 해지 예약 중에는 변경할 수 없다
// - 같은 플랜으로의 변경은 거절한다

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const reviseSubscriptionPlan = vi.fn();

vi.mock("@/lib/get-user", () => ({ getCurrentUser: (...a) => getCurrentUser(...a) }));
vi.mock("@/lib/prisma", () => ({
  prisma: { user: { findUnique: (...a) => userFindUnique(...a) } },
}));
vi.mock("@/lib/payment/PaypalProvider", () => ({
  PaypalProvider: class {
    reviseSubscriptionPlan(...a) {
      return reviseSubscriptionPlan(...a);
    }
  },
  PaypalError: class extends Error {},
  isPaypalConfigured: () => true,
}));

let POST;

function req(body) {
  return {
    url: "http://localhost:3000/api/payment/paypal/subscription/change",
    headers: new Headers({ host: "www.nullstock.im", "x-forwarded-proto": "https" }),
    json: async () => body,
  };
}

function paypalSubscriber(overrides = {}) {
  return {
    paymentProvider: "paypal",
    paypalSubscriptionId: "I-SUB-1",
    subscriptionPlanId: "PREMIUM",
    subscriptionCanceledAt: null,
    ...overrides,
  };
}

beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubEnv("PAYPAL_PLAN_PRO", "P-PRO-1");
  vi.stubEnv("PAYPAL_PLAN_PREMIUM", "P-PREMIUM-1");
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 42, email: "u@example.com", name: "User" });
  userFindUnique.mockResolvedValue(paypalSubscriber());
  reviseSubscriptionPlan.mockResolvedValue({ approveUrl: "https://paypal.com/revise/1" });
});

describe("/api/payment/paypal/subscription/change", () => {
  it("PREMIUM 구독자가 PRO로 다운그레이드하면 revise를 호출하고 승인 URL을 돌려준다", async () => {
    const res = await POST(req({ planId: "PRO" }));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ approveUrl: "https://paypal.com/revise/1" });
    expect(reviseSubscriptionPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        subscriptionId: "I-SUB-1",
        providerPlanId: "P-PRO-1",
        // 복귀는 성공 화면이 아니라 요금제 화면 — 반영 정본은 UPDATED 웹훅이다
        returnUrl: "https://www.nullstock.im/us/pricing",
      })
    );
  });

  it("활성 PayPal 구독이 없으면 400 — 새 구독 생성 경로와 섞이지 않는다", async () => {
    userFindUnique.mockResolvedValue({ paymentProvider: "toss", subscriptionPlanId: "PRO" });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(400);
    expect(reviseSubscriptionPlan).not.toHaveBeenCalled();
  });

  it("해지 예약 중에는 변경할 수 없다(409)", async () => {
    userFindUnique.mockResolvedValue(
      paypalSubscriber({ subscriptionCanceledAt: new Date("2026-08-30T00:00:00Z") })
    );
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(409);
    expect(reviseSubscriptionPlan).not.toHaveBeenCalled();
  });

  it("같은 플랜·FREE·잘못된 플랜은 400", async () => {
    expect((await POST(req({ planId: "PREMIUM" }))).status).toBe(400);
    expect((await POST(req({ planId: "FREE" }))).status).toBe(400);
    expect((await POST(req({ planId: "ULTRA" }))).status).toBe(400);
    expect(reviseSubscriptionPlan).not.toHaveBeenCalled();
  });
});
