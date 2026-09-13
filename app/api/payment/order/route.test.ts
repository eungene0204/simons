// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 정책 스위치(lib/plans.ts)는 기본 OFF다 — 켜진 경로를 검증하고, 꺼진 케이스는 flags를 내려 확인한다.
const flags = { ANNUAL_BILLING_ENABLED: true };
vi.mock("@/lib/plans", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/plans")>();
  return {
    ...actual,
    get ANNUAL_BILLING_ENABLED() { return flags.ANNUAL_BILLING_ENABLED; },
  };
});

// 결제 주문 생성 가드:
// - 결제 금액은 클라이언트가 아니라 서버의 플랜 정의(lib/plans.ts)에서 계산
// - customerKey는 유추 불가능한 UUID를 사용자당 1회 생성해 재사용

const getCurrentUser = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const orderCreate = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getCurrentUser: (...a) => getCurrentUser(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
    paymentOrder: {
      create: (...a) => orderCreate(...a),
    },
  },
}));

let POST;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ POST } = await import("./route"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com", name: "유저" });
  userUpdate.mockResolvedValue({});
  orderCreate.mockImplementation(async ({ data }) => data);
});

function req(body) {
  return { json: async () => body };
}

describe("/api/payment/order", () => {
  it("미로그인 요청은 401", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(401);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("FREE 플랜은 결제 주문을 만들 수 없다", async () => {
    const res = await POST(req({ planId: "FREE" }));
    expect(res.status).toBe(400);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("잘못된 planId는 400", async () => {
    const res = await POST(req({ planId: "ULTRA" }));
    expect(res.status).toBe(400);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("PRO 주문은 서버 정의 금액(25,000원)으로 생성된다 — 클라이언트 금액 무시", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: "existing-key-1" });
    const res = await POST(req({ planId: "PRO", amount: 100 }));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.amount).toBe(25000);
    expect(body.customerKey).toBe("existing-key-1");
    expect(body.orderName).toBe("널스탁 Pro 플랜 월 이용료");
    expect(orderCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ userId: 7, planId: "PRO", amount: 25000 }),
      })
    );
    // 기존 customerKey가 있으면 새로 만들지 않는다
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("연간 주문은 서버 정의 연 가격(240,000원)과 연간 주문명으로 생성된다", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: "existing-key-1" });
    const res = await POST(req({ planId: "PRO", billingCycle: "yearly" }));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.amount).toBe(240000);
    expect(body.billingCycle).toBe("yearly");
    expect(body.orderName).toBe("널스탁 Pro 플랜 연간 이용료");
    expect(orderCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ planId: "PRO", billingCycle: "yearly", amount: 240000 }),
      })
    );
  });

  it("잘못된 결제 주기는 400 — 임의로 월간으로 보정하지 않는다", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: "existing-key-1" });
    const res = await POST(req({ planId: "PRO", billingCycle: "weekly" }));
    expect(res.status).toBe(400);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("연간 스위치가 꺼져 있으면 연간 주문을 만들지 않는다(화면 우회 차단)", async () => {
    flags.ANNUAL_BILLING_ENABLED = false;
    try {
      const res = await POST(req({ planId: "PRO", billingCycle: "yearly" }));
      expect(res.status).toBe(400);
      expect((await res.json()).error).toMatch(/연간 결제는 현재 제공하지 않습니다/);
      expect(orderCreate).not.toHaveBeenCalled();
    } finally {
      flags.ANNUAL_BILLING_ENABLED = true;
    }
  });

  it("연간 구독 기간 중에는 주문을 만들 수 없다 (남은 기간 소멸 방지)", async () => {
    userFindUnique.mockResolvedValue({
      tossCustomerKey: "existing-key-1",
      subscriptionPlanId: "PRO",
      billingCycle: "yearly",
      subscriptionCanceledAt: null,
    });
    const res = await POST(req({ planId: "PREMIUM", billingCycle: "yearly" }));
    expect(res.status).toBe(409);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("PayPal 구독이 살아 있으면 409 — 토스로 겹쳐 결제하면 이중 청구다 (US→KR 교차)", async () => {
    userFindUnique.mockResolvedValue({
      tossCustomerKey: "existing-key-1",
      subscriptionPlanId: "PRO",
      billingCycle: "monthly",
      subscriptionCanceledAt: null,
      paymentProvider: "paypal",
    });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(409);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("해지 예약된 PayPal 구독도 만료 전에는 409 — 재구독은 만료 후에 한다", async () => {
    userFindUnique.mockResolvedValue({
      tossCustomerKey: "existing-key-1",
      subscriptionPlanId: "PRO",
      billingCycle: "monthly",
      subscriptionCanceledAt: new Date("2026-09-01"),
      paymentProvider: "paypal",
    });
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(409);
    expect(orderCreate).not.toHaveBeenCalled();
  });

  it("과거 PayPal 이력만 남은 사용자(활성 구독 없음)는 주문을 만들 수 있다", async () => {
    userFindUnique.mockResolvedValue({
      tossCustomerKey: "existing-key-1",
      subscriptionPlanId: null,
      paymentProvider: "paypal",
    });
    const res = await POST(req({ planId: "PRO" }));
    expect(res.status).toBe(200);
    expect(orderCreate).toHaveBeenCalled();
  });

  it("월간 구독 중에는 다른 플랜 주문을 그대로 만들 수 있다", async () => {
    userFindUnique.mockResolvedValue({
      tossCustomerKey: "existing-key-1",
      subscriptionPlanId: "PRO",
      billingCycle: "monthly",
      subscriptionCanceledAt: null,
    });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(200);
    expect(orderCreate).toHaveBeenCalled();
  });

  it("customerKey가 없으면 UUID를 생성해 저장한다 (이메일 등 유추 가능한 값 금지)", async () => {
    userFindUnique.mockResolvedValue({ tossCustomerKey: null });
    const res = await POST(req({ planId: "PREMIUM" }));
    expect(res.status).toBe(200);
    const body = await res.json();

    expect(body.amount).toBe(49000);
    expect(body.customerKey).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
    );
    expect(body.customerKey).not.toBe("u@example.com");
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: { tossCustomerKey: body.customerKey },
      })
    );
  });
});
