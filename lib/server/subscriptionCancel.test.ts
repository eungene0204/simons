// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 해지 예약의 결제 수단 분기 — PayPal 구독은 PayPal 쪽 취소가 반드시 선행해야 한다.
// (2026-09-03 감사: KR 요금제 페이지·설정 모달이 PayPal 구독자에게도 토스 경로만 타서
// 등급만 내려가고 청구는 계속됐다.)
const { cancelSubscription, markPaypalSubscriptionCanceled } = vi.hoisted(() => ({
  cancelSubscription: vi.fn(),
  markPaypalSubscriptionCanceled: vi.fn(),
}));

class PaypalError extends Error {
  constructor(message, httpStatus) {
    super(message);
    this.httpStatus = httpStatus;
  }
}

vi.mock("@/lib/payment/PaypalProvider", () => ({
  PaypalError,
  PaypalProvider: class {
    cancelSubscription = cancelSubscription;
  },
}));
vi.mock("@/lib/server/paypalSubscription", () => ({ markPaypalSubscriptionCanceled }));

const { cancelUserSubscription } = await import("./subscriptionCancel");

const userFindUnique = vi.fn();
const userUpdate = vi.fn();
const prisma = { user: { findUnique: userFindUnique, update: userUpdate } };
const NEXT = new Date("2026-10-01T00:00:00Z");

describe("cancelUserSubscription", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    userUpdate.mockResolvedValue({});
  });

  it("구독이 없으면 none", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: null });
    await expect(cancelUserSubscription(prisma, 7)).resolves.toEqual({ status: "none" });
    expect(userUpdate).not.toHaveBeenCalled();
  });

  it("이미 해지 예약이면 already(멱등)", async () => {
    userFindUnique.mockResolvedValue({
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: new Date(),
      nextBillingAt: NEXT,
    });
    await expect(cancelUserSubscription(prisma, 7)).resolves.toEqual({
      status: "already",
      expiresAt: NEXT.toISOString(),
    });
    expect(userUpdate).not.toHaveBeenCalled();
    expect(cancelSubscription).not.toHaveBeenCalled();
  });

  it("토스 구독은 해지 예약만 기록하고 PayPal을 부르지 않는다", async () => {
    userFindUnique.mockResolvedValue({
      paymentProvider: "toss",
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
      nextBillingAt: NEXT,
    });
    const outcome = await cancelUserSubscription(prisma, 7);
    expect(outcome).toEqual({ status: "scheduled", expiresAt: NEXT.toISOString() });
    expect(userUpdate).toHaveBeenCalledWith(
      expect.objectContaining({ where: { id: 7 }, data: { subscriptionCanceledAt: expect.any(Date) } })
    );
    expect(cancelSubscription).not.toHaveBeenCalled();
  });

  it("PayPal 구독은 PayPal 쪽 구독을 먼저 취소한 뒤 해지 예약을 기록한다", async () => {
    userFindUnique.mockResolvedValue({
      paymentProvider: "paypal",
      paypalSubscriptionId: "I-ABC",
      subscriptionPlanId: "PREMIUM",
      subscriptionCanceledAt: null,
      nextBillingAt: NEXT,
    });
    cancelSubscription.mockResolvedValue(undefined);

    const outcome = await cancelUserSubscription(prisma, 7);

    expect(outcome.status).toBe("scheduled");
    expect(cancelSubscription).toHaveBeenCalledWith("I-ABC");
    expect(markPaypalSubscriptionCanceled).toHaveBeenCalledWith(prisma, 7);
  });

  it("PayPal 쪽에서 이미 취소된 구독(4xx)이면 우리 기록만 맞춘다", async () => {
    userFindUnique.mockResolvedValue({
      paymentProvider: "paypal",
      paypalSubscriptionId: "I-ABC",
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
      nextBillingAt: NEXT,
    });
    cancelSubscription.mockRejectedValue(new PaypalError("already cancelled", 422));

    await expect(cancelUserSubscription(prisma, 7)).resolves.toMatchObject({ status: "scheduled" });
    expect(markPaypalSubscriptionCanceled).toHaveBeenCalled();
  });

  it("PayPal 5xx면 기록을 바꾸지 않고 실패를 올린다", async () => {
    userFindUnique.mockResolvedValue({
      paymentProvider: "paypal",
      paypalSubscriptionId: "I-ABC",
      subscriptionPlanId: "PRO",
      subscriptionCanceledAt: null,
      nextBillingAt: NEXT,
    });
    cancelSubscription.mockRejectedValue(new PaypalError("down", 503));

    await expect(cancelUserSubscription(prisma, 7)).rejects.toThrow("down");
    expect(markPaypalSubscriptionCanceled).not.toHaveBeenCalled();
  });
});
