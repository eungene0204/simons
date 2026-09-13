// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 중도 해지 정산(부분 환불) 회귀 테스트 — 약관 제12조 제9항:
// - 월간·연간이 같은 일할 기준을 쓴다(이용 개시일 = 1일)
// - 결제사 부분 취소가 성공한 뒤에만 우리 기록을 바꾼다(실패하면 등급도 그대로)
// - 화면에서 확인한 금액과 실제 정산액이 다르면 집행하지 않는다

const cancelPayment = vi.fn();

vi.mock("@/lib/server/tossPayments", async () => {
  const actual = await vi.importActual("@/lib/server/tossPayments");
  return {
    TossPaymentError: actual.TossPaymentError,
    cancelPayment: (...a) => cancelPayment(...a),
  };
});

let computeProratedRefund;
let loadRefundPreview;
let settleRefund;
let settleFullRefund;
let RefundSettlementError;

const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const orderFindFirst = vi.fn();
const orderUpdate = vi.fn();
const strategyCount = vi.fn();
const accountCount = vi.fn();
const validationCount = vi.fn();

const prisma = {
  user: {
    findUnique: (...a) => userFindUnique(...a),
    update: (...a) => userUpdate(...a),
  },
  paymentOrder: {
    findFirst: (...a) => orderFindFirst(...a),
    update: (...a) => orderUpdate(...a),
  },
  strategy: { count: (...a) => strategyCount(...a) },
  virtualAccount: { count: (...a) => accountCount(...a) },
  savedValidation: { count: (...a) => validationCount(...a) },
  $transaction: async (ops) => Promise.all(ops),
};

const PAID_AT = new Date("2026-09-13T01:29:24.000Z");

function readyState({
  cycle = "yearly",
  amount = 240_000,
  provider = "toss",
  backtestCountThisMonth = 0,
} = {}) {
  userFindUnique.mockImplementation(({ select }) =>
    Promise.resolve(
      select?.subscriptionPlanId
        ? { subscriptionPlanId: "PRO", paymentProvider: provider }
        : {
            planStartDate: PAID_AT,
            createdAt: new Date("2026-07-11T00:00:00Z"),
            // 주기 키 = 앵커(planStartDate) 기준 롤링 주기 시작 시각의 ISO 문자열(planLimits와 동일)
            backtestUsageMonth: PAID_AT.toISOString(),
            backtestCountThisMonth,
          }
    )
  );
  strategyCount.mockResolvedValue(0);
  accountCount.mockResolvedValue(0);
  validationCount.mockResolvedValue(0);
  orderFindFirst.mockResolvedValue({
    orderId: "order-1",
    paymentKey: "tviva-1",
    planId: "PRO",
    billingCycle: cycle,
    amount,
    approvedAt: PAID_AT,
  });
}

beforeEach(async () => {
  vi.clearAllMocks();
  ({
    computeProratedRefund,
    loadRefundPreview,
    settleRefund,
    settleFullRefund,
    RefundSettlementError,
  } = await import("./refundSettlement"));
  cancelPayment.mockResolvedValue({ status: "DONE" });
});

describe("computeProratedRefund", () => {
  it("연간 결제는 잔여 일수 비율로 환불액을 정한다", () => {
    // 2026-09-13 → 2027-09-13 = 365일. 개시 당일 해지 = 이용 1일, 잔여 364일.
    const s = computeProratedRefund({
      amount: 240_000,
      paidAt: PAID_AT,
      cycle: "yearly",
      now: PAID_AT,
    });
    expect(s.totalDays).toBe(365);
    expect(s.usedDays).toBe(1);
    expect(s.remainingDays).toBe(364);
    expect(s.refundAmount).toBe(Math.floor((240_000 * 364) / 365));
  });

  it("월간 결제도 같은 일할 기준을 쓴다", () => {
    // 2026-09-13 → 2026-10-13 = 30일. 5일째 해지 = 이용 5일, 잔여 25일.
    const s = computeProratedRefund({
      amount: 25_000,
      paidAt: PAID_AT,
      cycle: "monthly",
      now: new Date("2026-09-17T10:00:00Z"),
    });
    expect(s.totalDays).toBe(30);
    expect(s.usedDays).toBe(5);
    expect(s.remainingDays).toBe(25);
    expect(s.refundAmount).toBe(Math.floor((25_000 * 25) / 30));
  });

  it("기간을 다 쓴 뒤에는 환불액이 0원이다", () => {
    const s = computeProratedRefund({
      amount: 25_000,
      paidAt: PAID_AT,
      cycle: "monthly",
      now: new Date("2026-10-20T00:00:00Z"),
    });
    expect(s.usedDays).toBe(s.totalDays);
    expect(s.remainingDays).toBe(0);
    expect(s.refundAmount).toBe(0);
  });

  it("원 단위 미만은 버린다(회사가 아니라 계산식이 정한다)", () => {
    const s = computeProratedRefund({
      amount: 470_000,
      paidAt: PAID_AT,
      cycle: "yearly",
      now: new Date("2026-12-13T00:00:00Z"),
    });
    expect(Number.isInteger(s.refundAmount)).toBe(true);
    expect(s.refundAmount).toBe(Math.floor((470_000 * s.remainingDays) / s.totalDays));
  });
});

describe("loadRefundPreview", () => {
  it("PayPal 구독은 이 경로로 정산하지 않는다", async () => {
    readyState({ provider: "paypal" });
    const preview = await loadRefundPreview(prisma, 2, PAID_AT);
    expect(preview.status).toBe("unavailable");
    expect(preview.reason).toMatch(/PayPal/);
  });

  it("구독이 없으면 정산 대상이 아니다", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: null, paymentProvider: "toss" });
    const preview = await loadRefundPreview(prisma, 2, PAID_AT);
    expect(preview.status).toBe("unavailable");
  });

  it("결제 이후 유료 기능 사용 흔적을 함께 돌려준다(2항 판단 근거)", async () => {
    readyState();
    strategyCount.mockResolvedValue(2);
    accountCount.mockResolvedValue(1);
    validationCount.mockResolvedValue(0);

    const preview = await loadRefundPreview(prisma, 2, PAID_AT);

    expect(preview.status).toBe("ready");
    expect(preview.usage).toEqual({
      backtestsThisPeriod: 0,
      strategiesSincePaid: 2,
      accountsSincePaid: 1,
      validationsSincePaid: 0,
    });
    // 결제 시각 이후로만 센다 — 결제 전에 만든 것은 유료 기능 사용이 아니다
    expect(strategyCount).toHaveBeenCalledWith(
      expect.objectContaining({
        where: expect.objectContaining({ createdAt: { gte: PAID_AT } }),
      })
    );
  });
});

describe("settleRefund", () => {
  it("부분 취소 성공 후 주문에 환불액을 적고 즉시 FREE로 내린다", async () => {
    readyState();
    const now = new Date("2026-10-13T00:00:00Z");
    const expected = computeProratedRefund({
      amount: 240_000,
      paidAt: PAID_AT,
      cycle: "yearly",
      now,
    }).refundAmount;

    const result = await settleRefund(prisma, 2, { expectedRefundAmount: expected, now });

    expect(cancelPayment).toHaveBeenCalledWith(
      expect.objectContaining({
        paymentKey: "tviva-1",
        cancelAmount: expected,
        idempotencyKey: "refund:order-1",
      })
    );
    expect(orderUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        where: { orderId: "order-1" },
        data: expect.objectContaining({ refundedAmount: expected, refundedAt: now }),
      })
    );
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          planTier: "FREE",
          subscriptionPlanId: null,
          nextBillingAt: null,
          tossBillingKey: null,
        }),
      })
    );
    expect(result.settlement.refundAmount).toBe(expected);
  });

  it("확인한 금액과 실제 정산액이 다르면 집행하지 않는다", async () => {
    readyState();
    await expect(
      settleRefund(prisma, 2, { expectedRefundAmount: 999, now: PAID_AT })
    ).rejects.toBeInstanceOf(RefundSettlementError);
    expect(cancelPayment).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("결제사 취소가 실패하면 우리 기록은 그대로 둔다", async () => {
    readyState();
    cancelPayment.mockRejectedValue(new Error("toss down"));
    const expected = computeProratedRefund({
      amount: 240_000,
      paidAt: PAID_AT,
      cycle: "yearly",
      now: PAID_AT,
    }).refundAmount;

    await expect(
      settleRefund(prisma, 2, { expectedRefundAmount: expected, now: PAID_AT })
    ).rejects.toThrow("toss down");
    expect(orderUpdate).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("잔여 일수가 없으면 환불을 시도하지 않는다", async () => {
    readyState({ cycle: "monthly", amount: 25_000 });
    await expect(
      settleRefund(prisma, 2, {
        expectedRefundAmount: 1,
        now: new Date("2026-10-20T00:00:00Z"),
      })
    ).rejects.toThrow(/환불할 금액이 없습니다/);
    expect(cancelPayment).not.toHaveBeenCalled();
  });
});

describe("settleFullRefund (약관 제12조 2항)", () => {
  it("결제 금액 전액을 cancelAmount 없이 취소하고 즉시 FREE로 내린다", async () => {
    readyState({ cycle: "yearly", amount: 240_000 });

    const result = await settleFullRefund(prisma, 2, {
      expectedRefundAmount: 240_000,
      now: PAID_AT,
    });

    const call = cancelPayment.mock.calls[0][0];
    expect(call.paymentKey).toBe("tviva-1");
    expect(call).not.toHaveProperty("cancelAmount");
    expect(call.idempotencyKey).toBe("refund:order-1");
    expect(orderUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ refundedAmount: 240_000, refundedAt: PAID_AT }),
      })
    );
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({ planTier: "FREE", subscriptionPlanId: null }),
      })
    );
    expect(result.mode).toBe("full");
    expect(result.refundedAmount).toBe(240_000);
  });

  it("되돌려 보낸 금액이 결제 금액과 다르면 집행하지 않는다", async () => {
    readyState({ amount: 240_000 });
    await expect(
      settleFullRefund(prisma, 2, { expectedRefundAmount: 219_616, now: PAID_AT })
    ).rejects.toBeInstanceOf(RefundSettlementError);
    expect(cancelPayment).not.toHaveBeenCalled();
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("사용 흔적이 있어도 코드가 막지 않는다 — 2항 판단은 관리자 몫", async () => {
    readyState({ amount: 240_000, backtestCountThisMonth: 3 });
    const preview = await loadRefundPreview(prisma, 2, PAID_AT);
    expect(preview.usage.backtestsThisPeriod).toBe(3);

    await expect(
      settleFullRefund(prisma, 2, { expectedRefundAmount: 240_000, now: PAID_AT })
    ).resolves.toMatchObject({ mode: "full" });
  });
});
