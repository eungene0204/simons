// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 자동결제(빌링) 승인 보안 가드 회귀 테스트:
// - 서버 저장 주문/customerKey와 대조 후에만 빌링키 발급·첫 결제 승인
// - 청구 금액은 항상 서버 저장 주문 금액 사용
// - 승인 성공 시에만 planTier 전환 + 빌링키/다음 결제일 저장
// - 승인 재요청(성공 페이지 새로고침) 멱등 처리

const getCurrentUser = vi.fn();
const orderFindUnique = vi.fn();
const orderUpdate = vi.fn();
const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const issueBillingKey = vi.fn();
const chargeBillingKey = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getCurrentUser: (...a) => getCurrentUser(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    paymentOrder: {
      findUnique: (...a) => orderFindUnique(...a),
      update: (...a) => orderUpdate(...a),
    },
    user: {
      findUnique: (...a) => userFindUnique(...a),
      update: (...a) => userUpdate(...a),
    },
    $transaction: async (ops) => Promise.all(ops),
  },
}));

vi.mock("@/lib/server/tossPayments", async () => {
  const actual = await vi.importActual("@/lib/server/tossPayments");
  return {
    TossPaymentError: actual.TossPaymentError,
    issueBillingKey: (...a) => issueBillingKey(...a),
    chargeBillingKey: (...a) => chargeBillingKey(...a),
  };
});

let POST;
let TossPaymentError;

beforeEach(async () => {
  vi.clearAllMocks();
  ({ POST } = await import("./route"));
  ({ TossPaymentError } = await vi.importActual("@/lib/server/tossPayments"));
  getCurrentUser.mockResolvedValue({ id: 7, email: "u@example.com", name: "유저" });
  userFindUnique.mockResolvedValue({ tossCustomerKey: "customer-uuid-7" });
  orderUpdate.mockResolvedValue({});
  userUpdate.mockResolvedValue({});
});

function req(body) {
  return { json: async () => body };
}

const pendingOrder = {
  orderId: "order-uuid-1",
  userId: 7,
  planId: "PRO",
  amount: 25000,
  status: "PENDING",
};

const validBody = {
  authKey: "auth-key-1",
  customerKey: "customer-uuid-7",
  orderId: "order-uuid-1",
};

describe("/api/payment/confirm (빌링)", () => {
  it("미로그인 요청은 401", async () => {
    getCurrentUser.mockResolvedValue(null);
    const res = await POST(req(validBody));
    expect(res.status).toBe(401);
    expect(issueBillingKey).not.toHaveBeenCalled();
  });

  it("다른 사용자의 주문이면 404, 빌링키 발급을 호출하지 않는다", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder, userId: 99 });
    const res = await POST(req(validBody));
    expect(res.status).toBe(404);
    expect(issueBillingKey).not.toHaveBeenCalled();
  });

  it("customerKey가 서버 저장 값과 다르면 400, 빌링키 발급을 호출하지 않는다", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder });
    const res = await POST(req({ ...validBody, customerKey: "forged-key" }));
    expect(res.status).toBe(400);
    expect(issueBillingKey).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("승인 성공: 빌링키 발급 → 서버 저장 금액으로 첫 결제 → 플랜·빌링 상태 저장", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder });
    issueBillingKey.mockResolvedValue({
      billingKey: "billing-key-1",
      customerKey: "customer-uuid-7",
    });
    chargeBillingKey.mockResolvedValue({
      paymentKey: "pk-1",
      orderId: "order-uuid-1",
      status: "DONE",
      totalAmount: 25000,
      approvedAt: "2026-07-10T12:00:00+09:00",
    });

    const res = await POST(req(validBody));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ ok: true, planId: "PRO" });

    expect(issueBillingKey).toHaveBeenCalledWith({
      authKey: "auth-key-1",
      customerKey: "customer-uuid-7",
    });
    // 청구 금액은 클라이언트 값이 아니라 서버 저장 주문 금액
    expect(chargeBillingKey).toHaveBeenCalledWith(
      expect.objectContaining({
        billingKey: "billing-key-1",
        amount: 25000,
        orderId: "order-uuid-1",
      })
    );
    expect(orderUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ status: "DONE", paymentKey: "pk-1" }),
      })
    );
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: expect.objectContaining({
          planTier: "PRO",
          tossBillingKey: "billing-key-1",
          subscriptionPlanId: "PRO",
          subscriptionCanceledAt: null,
          billingFailCount: 0,
          nextBillingAt: expect.any(Date),
        }),
      })
    );
  });

  it("첫 결제 청구 실패 시 FAILED 기록 후 에러 코드를 전달하고 플랜을 바꾸지 않는다", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder });
    issueBillingKey.mockResolvedValue({
      billingKey: "billing-key-1",
      customerKey: "customer-uuid-7",
    });
    chargeBillingKey.mockRejectedValue(
      new TossPaymentError("REJECT_CARD_COMPANY", "카드사 거절", 403)
    );

    const res = await POST(req(validBody));
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.code).toBe("REJECT_CARD_COMPANY");
    expect(userUpdate).not.toHaveBeenCalled();
    expect(orderUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ status: "FAILED", failReason: "REJECT_CARD_COMPANY" }),
      })
    );
  });

  it("이미 DONE인 주문은 재승인 없이 성공을 반환한다(성공 페이지 새로고침 멱등)", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder, status: "DONE" });
    const res = await POST(req(validBody));
    expect(res.status).toBe(200);
    expect(issueBillingKey).not.toHaveBeenCalled();
    expect(chargeBillingKey).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("FAILED로 종료된 주문 재승인 요청은 409", async () => {
    orderFindUnique.mockResolvedValue({ ...pendingOrder, status: "FAILED" });
    const res = await POST(req(validBody));
    expect(res.status).toBe(409);
    expect(issueBillingKey).not.toHaveBeenCalled();
  });
});
