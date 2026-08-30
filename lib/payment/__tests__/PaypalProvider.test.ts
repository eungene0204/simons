import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PaypalProvider, isPaypalConfigured } from "@/lib/payment/PaypalProvider";

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

/** 204 No Content — 본문이 없어 json() 파싱이 실패한다(구독 해지 응답). */
function noContentResponse() {
  return {
    ok: true,
    status: 204,
    json: async () => {
      throw new SyntaxError("Unexpected end of JSON input");
    },
  } as unknown as Response;
}

function tokenResponse() {
  return jsonResponse(200, { access_token: "token-1" });
}

const fetchMock = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("PAYPAL_CLIENT_ID", "client-id");
  vi.stubEnv("PAYPAL_CLIENT_SECRET", "client-secret");
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("PaypalProvider", () => {
  it("isPaypalConfigured — 키가 둘 다 있어야 true", () => {
    expect(isPaypalConfigured()).toBe(true);
    vi.stubEnv("PAYPAL_CLIENT_SECRET", "");
    expect(isPaypalConfigured()).toBe(false);
  });

  it("createCheckout — 주문을 만들고 approve URL을 돌려준다", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "token-1" }))
      .mockResolvedValueOnce(
        jsonResponse(201, {
          id: "ORDER-1",
          status: "CREATED",
          links: [
            { rel: "self", href: "https://api/self" },
            { rel: "approve", href: "https://paypal.com/approve/ORDER-1" },
          ],
        })
      );

    const session = await new PaypalProvider().createCheckout({
      orderId: "order-1",
      planId: "PRO",
      amount: 19,
      currency: "USD",
      successUrl: "https://www.nullstock.im/us/pricing/success",
      cancelUrl: "https://www.nullstock.im/us/pricing",
      orderName: "NullStock Pro",
    });

    expect(session).toEqual({
      providerId: "paypal",
      checkoutUrl: "https://paypal.com/approve/ORDER-1",
      providerOrderId: "ORDER-1",
    });
    const orderCall = fetchMock.mock.calls[1];
    expect(orderCall[0]).toContain("/v2/checkout/orders");
    const body = JSON.parse((orderCall[1] as RequestInit).body as string);
    expect(body.purchase_units[0].amount).toEqual({ currency_code: "USD", value: "19.00" });
  });

  it("createCheckout — USD 외 통화는 거부한다", async () => {
    await expect(
      new PaypalProvider().createCheckout({
        orderId: "order-1",
        planId: "PRO",
        amount: 25000,
        currency: "KRW",
        successUrl: "https://x/success",
        cancelUrl: "https://x/cancel",
      })
    ).rejects.toThrow("USD");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("verifyPayment — 캡처가 완료되면 approved", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "token-1" }))
      .mockResolvedValueOnce(
        jsonResponse(201, {
          id: "ORDER-1",
          status: "COMPLETED",
          purchase_units: [
            {
              payments: {
                captures: [
                  { id: "CAP-1", status: "COMPLETED", create_time: "2026-08-24T00:00:00Z" },
                ],
              },
            },
          ],
        })
      );

    const result = await new PaypalProvider().verifyPayment({ providerOrderId: "ORDER-1" });
    expect(result.approved).toBe(true);
    expect(result.providerPaymentKey).toBe("CAP-1");
  });

  it("API 오류는 상세 메시지와 함께 던진다", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(200, { access_token: "token-1" }))
      .mockResolvedValueOnce(
        jsonResponse(422, {
          message: "UNPROCESSABLE_ENTITY",
          details: [{ description: "Order already captured." }],
        })
      );

    await expect(
      new PaypalProvider().verifyPayment({ providerOrderId: "ORDER-1" })
    ).rejects.toThrow("Order already captured.");
  });
});

describe("PaypalProvider — 정기구독", () => {
  it("createSubscription — 구독을 만들고 승인 URL을 돌려준다", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse()).mockResolvedValueOnce(
      jsonResponse(201, {
        id: "I-SUB-1",
        status: "APPROVAL_PENDING",
        links: [
          { rel: "self", href: "https://api/self" },
          { rel: "approve", href: "https://paypal.com/subscribe/I-SUB-1" },
        ],
      })
    );

    const session = await new PaypalProvider().createSubscription({
      providerPlanId: "P-PRO-MONTHLY",
      userRef: "42",
      returnUrl: "https://www.nullstock.im/us/pricing/success",
      cancelUrl: "https://www.nullstock.im/us/pricing",
      subscriberEmail: "u@example.com",
      requestId: "req-1",
    });

    expect(session).toEqual({
      providerId: "paypal",
      subscriptionId: "I-SUB-1",
      approveUrl: "https://paypal.com/subscribe/I-SUB-1",
      status: "APPROVAL_PENDING",
    });

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toContain("/v1/billing/subscriptions");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.plan_id).toBe("P-PRO-MONTHLY");
    // 웹훅에서 사용자를 되찾는 참조값 — 빠지면 승인된 구독이 주인을 잃는다
    expect(body.custom_id).toBe("42");
    expect(body.application_context.return_url).toContain("/us/pricing/success");
    // 재시도가 구독을 중복 생성하지 않게 하는 멱등키
    expect((init as RequestInit).headers).toMatchObject({ "PayPal-Request-Id": "req-1" });
  });

  it("createSubscription — 승인 URL이 없으면 오류", async () => {
    fetchMock
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse(201, { id: "I-SUB-1", status: "APPROVAL_PENDING", links: [] }));

    await expect(
      new PaypalProvider().createSubscription({
        providerPlanId: "P-PRO-MONTHLY",
        userRef: "42",
        returnUrl: "https://x/success",
        cancelUrl: "https://x/cancel",
      })
    ).rejects.toThrow("승인 URL");
  });

  it("getSubscription — 상태·다음 결제일·참조값을 매핑한다", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse()).mockResolvedValueOnce(
      jsonResponse(200, {
        id: "I-SUB-1",
        status: "ACTIVE",
        plan_id: "P-PRO-MONTHLY",
        custom_id: "42",
        subscriber: { payer_id: "PAYER-1" },
        billing_info: { next_billing_time: "2026-09-30T10:00:00Z" },
      })
    );

    const state = await new PaypalProvider().getSubscription("I-SUB-1");

    expect(state).toEqual({
      subscriptionId: "I-SUB-1",
      status: "ACTIVE",
      active: true,
      providerPlanId: "P-PRO-MONTHLY",
      userRef: "42",
      payerId: "PAYER-1",
      nextBillingTime: "2026-09-30T10:00:00Z",
    });
  });

  it("getSubscription — ACTIVE가 아니면 active=false", async () => {
    fetchMock
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(jsonResponse(200, { id: "I-SUB-1", status: "SUSPENDED" }));

    const state = await new PaypalProvider().getSubscription("I-SUB-1");
    expect(state.active).toBe(false);
  });

  it("cancelSubscription — 본문 없는 204 응답을 오류로 보지 않는다", async () => {
    fetchMock.mockResolvedValueOnce(tokenResponse()).mockResolvedValueOnce(noContentResponse());

    await expect(
      new PaypalProvider().cancelSubscription("I-SUB-1", "User requested")
    ).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toContain("/v1/billing/subscriptions/I-SUB-1/cancel");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ reason: "User requested" });
  });

  it("cancelSubscription — PayPal 오류는 그대로 전달한다", async () => {
    fetchMock
      .mockResolvedValueOnce(tokenResponse())
      .mockResolvedValueOnce(
        jsonResponse(422, { details: [{ description: "Subscription is already cancelled." }] })
      );

    await expect(new PaypalProvider().cancelSubscription("I-SUB-1")).rejects.toThrow(
      "already cancelled"
    );
  });
});
