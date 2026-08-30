// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// PayPal 웹훅 가드 — 유료 플랜 승격의 정본 경로다:
// - 서명 검증에 실패하면 아무것도 반영하지 않는다(위조 이벤트로 유료 플랜을 받아갈 수 없다)
// - 검증 자체가 불가능하면(웹훅 ID 미설정) 받지 않는다(fail closed)
// - 같은 이벤트가 재전송돼도 두 번 반영되지 않는다
// - 우리 플랜이 아닌 plan_id는 반영하지 않는다

const verifyWebhookSignature = vi.fn();
const activatePaypalSubscription = vi.fn();
const recordPaypalSubscriptionPayment = vi.fn();
const markPaypalSubscriptionCanceled = vi.fn();
const downgradePaypalSubscriber = vi.fn();
const webhookEventCreate = vi.fn();
const webhookEventDeleteMany = vi.fn();
const userFindUnique = vi.fn();

const getSubscription = vi.fn();

vi.mock("@/lib/payment/PaypalProvider", () => ({
  verifyWebhookSignature: (...a) => verifyWebhookSignature(...a),
  PaypalProvider: class {
    getSubscription(...a) {
      return getSubscription(...a);
    }
  },
}));

const schedulePaypalPlanChange = vi.fn();

vi.mock("@/lib/server/paypalSubscription", () => ({
  activatePaypalSubscription: (...a) => activatePaypalSubscription(...a),
  recordPaypalSubscriptionPayment: (...a) => recordPaypalSubscriptionPayment(...a),
  markPaypalSubscriptionCanceled: (...a) => markPaypalSubscriptionCanceled(...a),
  downgradePaypalSubscriber: (...a) => downgradePaypalSubscriber(...a),
  schedulePaypalPlanChange: (...a) => schedulePaypalPlanChange(...a),
}));

vi.mock("@/lib/prisma", () => ({
  prisma: {
    paymentWebhookEvent: {
      create: (...a) => webhookEventCreate(...a),
      deleteMany: (...a) => webhookEventDeleteMany(...a),
    },
    user: {
      findUnique: (...a) => userFindUnique(...a),
    },
  },
}));

let POST;

function req(event, headers = {}) {
  const raw = JSON.stringify(event);
  return { text: async () => raw, headers: new Headers(headers) };
}

function activatedEvent(overrides = {}) {
  return {
    id: "WH-EVENT-1",
    event_type: "BILLING.SUBSCRIPTION.ACTIVATED",
    resource: {
      id: "I-SUB-1",
      plan_id: "P-PRO-1",
      custom_id: "42",
      subscriber: { payer_id: "PAYER-1" },
      billing_info: { next_billing_time: "2026-09-30T10:00:00Z" },
    },
    ...overrides,
  };
}

beforeEach(async () => {
  vi.clearAllMocks();
  vi.stubEnv("PAYPAL_PLAN_PRO", "P-PRO-1");
  vi.stubEnv("PAYPAL_PLAN_PREMIUM", "P-PREMIUM-1");
  ({ POST } = await import("./route"));
  verifyWebhookSignature.mockResolvedValue(true);
  webhookEventCreate.mockResolvedValue({});
  webhookEventDeleteMany.mockResolvedValue({});
});

describe("/api/payment/paypal/webhook", () => {
  it("서명 검증에 실패하면 401이고 아무것도 반영하지 않는다", async () => {
    verifyWebhookSignature.mockResolvedValue(false);

    const res = await POST(req(activatedEvent()));

    expect(res.status).toBe(401);
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
    expect(webhookEventCreate).not.toHaveBeenCalled();
  });

  it("검증 자체가 불가능하면(웹훅 ID 미설정) 503으로 거절한다", async () => {
    verifyWebhookSignature.mockRejectedValue(new Error("PAYPAL_WEBHOOK_ID 없음"));

    const res = await POST(req(activatedEvent()));

    expect(res.status).toBe(503);
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
  });

  it("구독 활성화 이벤트로 유료 플랜을 반영한다", async () => {
    const res = await POST(req(activatedEvent()));

    expect(res.status).toBe(200);
    expect(activatePaypalSubscription).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        userId: 42,
        planId: "PRO",
        subscriptionId: "I-SUB-1",
        payerId: "PAYER-1",
        nextBillingTime: "2026-09-30T10:00:00Z",
      })
    );
  });

  it("같은 이벤트가 재전송되면 두 번 반영하지 않는다", async () => {
    webhookEventCreate.mockRejectedValue(new Error("unique constraint"));

    const res = await POST(req(activatedEvent()));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true, duplicate: true });
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
  });

  it("우리 플랜이 아닌 plan_id는 반영하지 않는다", async () => {
    const res = await POST(
      req(activatedEvent({ resource: { id: "I-SUB-9", plan_id: "P-STRANGER", custom_id: "42" } }))
    );

    expect(res.status).toBe(200);
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
  });

  it("사용자를 찾을 수 없으면 반영하지 않고 200으로 닫는다(재전송 유발 방지)", async () => {
    userFindUnique.mockResolvedValue(null);

    const res = await POST(
      req(activatedEvent({ resource: { id: "I-UNKNOWN", plan_id: "P-PRO-1" } }))
    );

    expect(res.status).toBe(200);
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
  });

  it("월 청구 성공은 현재 구독 플랜으로 이력을 남기고 다음 청구일은 PayPal 값을 쓴다", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: "PREMIUM" });
    getSubscription.mockResolvedValue({
      subscriptionId: "I-SUB-1",
      status: "ACTIVE",
      active: true,
      providerPlanId: "P-PREMIUM-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });

    const res = await POST(
      req({
        id: "WH-EVENT-2",
        event_type: "PAYMENT.SALE.COMPLETED",
        resource: {
          id: "SALE-1",
          billing_agreement_id: "I-SUB-1",
          custom_id: "42",
          create_time: "2026-09-30T10:00:00Z",
        },
      })
    );

    expect(res.status).toBe(200);
    expect(recordPaypalSubscriptionPayment).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        userId: 42,
        planId: "PREMIUM",
        saleId: "SALE-1",
        // 우리가 +1개월을 더하면 활성화가 넣어 둔 정본 날짜에서 한 달이 밀린다
        nextBillingTime: "2026-09-30T10:00:00Z",
      })
    );
  });

  // 회귀(2026-08-31 prod E2E): PayPal이 첫 달 청구를 활성화보다 먼저 보내 우리 DB에
  // 구독 플랜이 아직 없었고, 그 결과 첫 결제 이력이 조용히 사라졌다.
  it("활성화보다 결제 통지가 먼저 와도 구독을 조회해 이력을 남긴다", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: null });
    getSubscription.mockResolvedValue({
      subscriptionId: "I-SUB-1",
      status: "ACTIVE",
      active: true,
      providerPlanId: "P-PRO-1",
    });

    const res = await POST(
      req({
        id: "WH-EVENT-EARLY",
        event_type: "PAYMENT.SALE.COMPLETED",
        resource: { id: "SALE-EARLY", billing_agreement_id: "I-SUB-1", custom_id: "42" },
      })
    );

    expect(res.status).toBe(200);
    expect(getSubscription).toHaveBeenCalledWith("I-SUB-1");
    expect(recordPaypalSubscriptionPayment).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ userId: 42, planId: "PRO", saleId: "SALE-EARLY" })
    );
  });

  it("구독을 조회해도 우리 플랜이 아니면 이력을 남기지 않는다", async () => {
    userFindUnique.mockResolvedValue({ subscriptionPlanId: null });
    getSubscription.mockResolvedValue({
      subscriptionId: "I-SUB-9",
      status: "ACTIVE",
      active: true,
      providerPlanId: "P-STRANGER",
    });

    const res = await POST(
      req({
        id: "WH-EVENT-STRANGER",
        event_type: "PAYMENT.SALE.COMPLETED",
        resource: { id: "SALE-9", billing_agreement_id: "I-SUB-9", custom_id: "42" },
      })
    );

    expect(res.status).toBe(200);
    expect(recordPaypalSubscriptionPayment).not.toHaveBeenCalled();
  });

  it("해지 통지는 남은 기간을 유지하고, 정지·만료는 즉시 FREE로 내린다", async () => {
    await POST(
      req({
        id: "WH-EVENT-3",
        event_type: "BILLING.SUBSCRIPTION.CANCELLED",
        resource: { id: "I-SUB-1", custom_id: "42" },
      })
    );
    expect(markPaypalSubscriptionCanceled).toHaveBeenCalledWith(expect.anything(), 42);
    expect(downgradePaypalSubscriber).not.toHaveBeenCalled();

    await POST(
      req({
        id: "WH-EVENT-4",
        event_type: "BILLING.SUBSCRIPTION.SUSPENDED",
        resource: { id: "I-SUB-1", custom_id: "42" },
      })
    );
    expect(downgradePaypalSubscriber).toHaveBeenCalledWith(expect.anything(), 42);
  });

  it("플랜 변경(UPDATED)은 청구 플랜만 예약하고 등급 전환은 하지 않는다", async () => {
    const res = await POST(
      req({
        id: "WH-EVENT-REVISE",
        event_type: "BILLING.SUBSCRIPTION.UPDATED",
        resource: {
          id: "I-SUB-1",
          plan_id: "P-PRO-1",
          custom_id: "42",
          billing_info: { next_billing_time: "2026-09-30T10:00:00Z" },
        },
      })
    );

    expect(res.status).toBe(200);
    expect(schedulePaypalPlanChange).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ userId: 42, planId: "PRO", nextBillingTime: "2026-09-30T10:00:00Z" })
    );
    // 남은 기간의 등급을 빼앗으면 안 된다 — 전환은 다음 결제가 수행한다
    expect(activatePaypalSubscription).not.toHaveBeenCalled();
  });

  it("처리 중 실패하면 이벤트 기록을 되돌려 재처리를 허용한다", async () => {
    activatePaypalSubscription.mockRejectedValue(new Error("db down"));

    const res = await POST(req(activatedEvent()));

    expect(res.status).toBe(500);
    expect(webhookEventDeleteMany).toHaveBeenCalledWith(
      expect.objectContaining({ where: { provider: "paypal", eventId: "WH-EVENT-1" } })
    );
  });
});
