// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 자동결제(빌링) 월 갱신 잡 회귀 테스트:
// - 결제일 도래 구독 청구 성공 → nextBillingAt이 예정 시각 기준 +1개월로 굴러간다
// - 해지 예약 구독 → 청구 없이 FREE 전환 + 빌링 상태 초기화
// - 청구 실패 → 다음 날 재시도 예약, 연속 실패 한도 도달 시 FREE 전환

const chargeBillingKey = vi.fn();

vi.mock("@/lib/server/tossPayments", async () => {
  const actual = await vi.importActual("@/lib/server/tossPayments");
  return {
    TossPaymentError: actual.TossPaymentError,
    chargeBillingKey: (...a) => chargeBillingKey(...a),
  };
});

let processDueBillingRenewals;
let BILLING_MAX_FAIL_COUNT;
let TossPaymentError;

const userFindMany = vi.fn();
const userUpdate = vi.fn();
const orderCreate = vi.fn();
const orderUpdate = vi.fn();

const prisma = {
  user: {
    findMany: (...a) => userFindMany(...a),
    update: (...a) => userUpdate(...a),
  },
  paymentOrder: {
    create: (...a) => orderCreate(...a),
    update: (...a) => orderUpdate(...a),
  },
  $transaction: async (ops) => Promise.all(ops),
};

const NOW = new Date("2026-08-10T01:00:00Z");

function subscriber(overrides = {}) {
  return {
    id: 7,
    email: "u@example.com",
    subscriptionPlanId: "PRO",
    tossBillingKey: "billing-key-1",
    tossCustomerKey: "customer-uuid-7",
    subscriptionCanceledAt: null,
    billingFailCount: 0,
    nextBillingAt: new Date("2026-08-10T00:00:00Z"),
    ...overrides,
  };
}

beforeEach(async () => {
  vi.clearAllMocks();
  ({ processDueBillingRenewals, BILLING_MAX_FAIL_COUNT } = await import("./billingRenewal"));
  ({ TossPaymentError } = await vi.importActual("@/lib/server/tossPayments"));
  userUpdate.mockResolvedValue({});
  orderUpdate.mockResolvedValue({});
  orderCreate.mockImplementation(async ({ data }) => ({ ...data }));
});

describe("processDueBillingRenewals", () => {
  it("결제일이 온 구독을 서버 금액으로 청구하고 다음 결제일을 예정 시각 기준 +1개월로 굴린다", async () => {
    userFindMany.mockResolvedValue([subscriber()]);
    chargeBillingKey.mockResolvedValue({
      paymentKey: "pk-renewal",
      status: "DONE",
      approvedAt: "2026-08-10T10:00:00+09:00",
    });

    const summary = await processDueBillingRenewals(prisma, NOW);

    expect(summary).toEqual({ renewed: 1, retried: 0, downgraded: 0 });
    expect(orderCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ userId: 7, planId: "PRO", amount: 25000 }),
      })
    );
    expect(chargeBillingKey).toHaveBeenCalledWith(
      expect.objectContaining({
        billingKey: "billing-key-1",
        customerKey: "customer-uuid-7",
        amount: 25000,
      })
    );
    // 예정 시각(8/10) 기준 +1개월 — 재시도 지연으로 주기가 밀리지 않는다
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: expect.objectContaining({
          planTier: "PRO",
          billingFailCount: 0,
          nextBillingAt: new Date("2026-09-10T00:00:00Z"),
        }),
      })
    );
  });

  it("해지 예약된 구독은 청구 없이 FREE로 전환하고 빌링 상태를 비운다", async () => {
    userFindMany.mockResolvedValue([
      subscriber({ subscriptionCanceledAt: new Date("2026-07-20T00:00:00Z") }),
    ]);

    const summary = await processDueBillingRenewals(prisma, NOW);

    expect(summary).toEqual({ renewed: 0, retried: 0, downgraded: 1 });
    expect(chargeBillingKey).not.toHaveBeenCalled();
    expect(orderCreate).not.toHaveBeenCalled();
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { id: 7 },
        data: expect.objectContaining({
          planTier: "FREE",
          tossBillingKey: null,
          subscriptionPlanId: null,
          nextBillingAt: null,
        }),
      })
    );
  });

  it("청구 실패 시 실패 횟수를 올리고 다음 날 재시도를 예약한다", async () => {
    userFindMany.mockResolvedValue([subscriber()]);
    chargeBillingKey.mockRejectedValue(
      new TossPaymentError("INSUFFICIENT_FUNDS", "잔액 부족", 400)
    );

    const summary = await processDueBillingRenewals(prisma, NOW);

    expect(summary).toEqual({ renewed: 0, retried: 1, downgraded: 0 });
    expect(orderUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ status: "FAILED", failReason: "INSUFFICIENT_FUNDS" }),
      })
    );
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          billingFailCount: 1,
          nextBillingAt: new Date(NOW.getTime() + 24 * 60 * 60 * 1000),
        }),
      })
    );
  });

  it("연속 실패 한도에 도달하면 FREE로 전환한다", async () => {
    userFindMany.mockResolvedValue([
      subscriber({ billingFailCount: BILLING_MAX_FAIL_COUNT - 1 }),
    ]);
    chargeBillingKey.mockRejectedValue(
      new TossPaymentError("INSUFFICIENT_FUNDS", "잔액 부족", 400)
    );

    const summary = await processDueBillingRenewals(prisma, NOW);

    expect(summary).toEqual({ renewed: 0, retried: 0, downgraded: 1 });
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ planTier: "FREE", tossBillingKey: null }),
      })
    );
  });

  it("한 구독의 처리 실패가 다른 구독 갱신을 막지 않는다", async () => {
    userFindMany.mockResolvedValue([
      subscriber({ id: 1, tossCustomerKey: "c-1" }),
      subscriber({ id: 2, tossCustomerKey: "c-2" }),
    ]);
    // 첫 사용자는 주문 생성 자체가 실패, 두 번째는 정상 청구
    orderCreate
      .mockRejectedValueOnce(new Error("db down"))
      .mockImplementation(async ({ data }) => ({ ...data }));
    chargeBillingKey.mockResolvedValue({ paymentKey: "pk", status: "DONE" });

    const summary = await processDueBillingRenewals(prisma, NOW);

    expect(summary).toEqual({ renewed: 1, retried: 0, downgraded: 0 });
    expect(chargeBillingKey).toHaveBeenCalledTimes(1);
  });
});
