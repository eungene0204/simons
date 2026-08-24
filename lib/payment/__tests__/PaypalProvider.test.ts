import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PaypalProvider, isPaypalConfigured } from "@/lib/payment/PaypalProvider";

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
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
