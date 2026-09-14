// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 구독 생성 가드:
// - 결제 대상 플랜만 구독할 수 있다
// - 토스 자동결제가 살아 있는 계정은 PayPal 구독을 겹쳐 만들 수 없다(이중 청구 방지)
// - 승인 전에는 플랜을 올리지 않는다 — 구독 ID만 저장한다

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const createSubscription = vi.fn();

vi.mock("@/lib/get-user", () => ({ getCurrentUser: (...a) => getCurrentUser(...a) }));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
  },
}));

vi.mock("@/lib/payment/PaypalProvider", () => ({
  PaypalProvider: class {
    createSubscription(...a) {
      return createSubscription(...a);
    }
  },
  PaypalError: class extends Error {},
  isPaypalConfigured: () => true,
}));

let POST;

// 회귀(2026-08-31 prod): 컨테이너 안 Next.js는 request.url을 localhost:3000으로 재구성한다.
// 복귀 URL은 request.url이 아니라 방문자의 Host 헤더에서 만들어야 한다 — 이 목은 그 상황을
// 그대로 재현한다(내부 URL + 실제 Host 헤더).
function req(body, headers = { host: "www.nullstock.im", "x-forwarded-proto": "https" }) {
  return {
    url: "http://localhost:3000/api/payment/paypal/subscription",
    headers: new Headers(headers),
    json: async () => body,
  };
}

beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubEnv("PAYPAL_PLAN_PRO", "P-PRO-1");
  vi.stubEnv("PAYPAL_PLAN_PREMIUM", "P-PREMIUM-1");
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 42, email: "u@example.com", name: "User" });
  userFindUnique.mockResolvedValue({ paymentProvider: "toss", subscriptionPlanId: null });
  userUpdate.mockResolvedValue({});
  createSubscription.mockResolvedValue({
    providerId: "paypal",
    subscriptionId: "I-SUB-1",
    approveUrl: "https://paypal.com/subscribe/I-SUB-1",
    status: "APPROVAL_PENDING",
  });
});

describe("/api/payment/paypal/subscription", () => {
  it("미로그인 요청은 401", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(401);
    expect(createSubscription).not.toHaveBeenCalled();
  });

  it("FREE·잘못된 플랜은 400", async () => {
    expect((await POST(req({ planId: "FREE" }))).status).toBe(400);
    expect((await POST(req({ planId: "ULTRA" }))).status).toBe(400);
    expect(createSubscription).not.toHaveBeenCalled();
  });

  it("토스 구독이 살아 있으면 409 — 이중 청구를 막는다", async () => {
    userFindUnique.mockResolvedValue({ paymentProvider: "toss", subscriptionPlanId: "PRO" });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(409);
    expect(createSubscription).not.toHaveBeenCalled();
  });

  // PayPal 구독은 저쪽에 계약으로 살아 있어서 겹쳐 만들면 두 구독이 동시에 청구된다
  it("PayPal 구독이 살아 있어도 409 — 플랜 변경은 revise 경로가 담당한다", async () => {
    userFindUnique.mockResolvedValue({ paymentProvider: "paypal", subscriptionPlanId: "PREMIUM" });
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(409);
    expect(createSubscription).not.toHaveBeenCalled();
  });

  it("승인 URL을 돌려주고 구독 ID만 저장한다(플랜은 아직 올리지 않는다)", async () => {
    const res = await POST(req({ planId: "PRO" }));

    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({
      subscriptionId: "I-SUB-1",
      approveUrl: "https://paypal.com/subscribe/I-SUB-1",
    });
    expect(createSubscription).toHaveBeenCalledWith(
      expect.objectContaining({
        providerPlanId: "P-PRO-1",
        userRef: "42",
        // request.url(localhost:3000)이 아니라 Host 헤더 기준이어야 한다
        returnUrl: "https://www.nullstock.im/us/pricing/success",
        cancelUrl: "https://www.nullstock.im/us/pricing",
      })
    );
    const updateData = userUpdate.mock.calls[0][0].data;
    expect(updateData).toEqual({ paypalSubscriptionId: "I-SUB-1" });
    expect(updateData.planTier).toBeUndefined();
  });
});

describe("/api/payment/paypal/subscription 게스트(특별 계정) 가드", () => {
  it("게스트는 PayPal 구독을 만들 수 없다 — 403, PayPal 호출 없음", async () => {
    getCurrentUser.mockResolvedValue({
      id: 19,
      email: "guest_1234@guest.nullstock.im",
      name: "guest_1234",
    });

    const res = await POST(req({ planId: "PRO" }));
    const body = await res.json();

    expect(res.status).toBe(403);
    expect(body.error).toContain("특별 계정");
    expect(createSubscription).not.toHaveBeenCalled();
  });
});
