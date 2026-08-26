// PayPal Checkout 어댑터 — Orders v2 API. 글로벌 서비스(USD) 결제용.
// https://developer.paypal.com/docs/api/orders/v2/
//
// 환경변수: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_API_BASE(선택 — 기본 sandbox).
// 흐름: createCheckout(주문 생성) → 사용자를 approve URL로 → 돌아오면 verifyPayment(캡처).

import type {
  CheckoutInput,
  CheckoutSession,
  PaymentProvider,
  PaymentResult,
  VerifyInput,
} from "./PaymentProvider";

const DEFAULT_API_BASE = "https://api-m.sandbox.paypal.com";

export class PaypalError extends Error {
  readonly httpStatus: number;

  constructor(message: string, httpStatus: number) {
    super(message);
    this.name = "PaypalError";
    this.httpStatus = httpStatus;
  }
}

function apiBase(): string {
  return process.env.PAYPAL_API_BASE?.trim() || DEFAULT_API_BASE;
}

export function isPaypalConfigured(): boolean {
  return Boolean(process.env.PAYPAL_CLIENT_ID && process.env.PAYPAL_CLIENT_SECRET);
}

async function getAccessToken(): Promise<string> {
  const clientId = process.env.PAYPAL_CLIENT_ID;
  const clientSecret = process.env.PAYPAL_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    throw new Error("PAYPAL_CLIENT_ID/PAYPAL_CLIENT_SECRET 환경변수가 설정되지 않았습니다.");
  }

  const res = await fetch(`${apiBase()}/v1/oauth2/token`, {
    method: "POST",
    headers: {
      Authorization: `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString("base64")}`,
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: "grant_type=client_credentials",
  });
  const data = (await res.json().catch(() => null)) as { access_token?: string } | null;
  if (!res.ok || !data?.access_token) {
    throw new PaypalError("PayPal 인증 토큰 발급에 실패했습니다.", res.status);
  }
  return data.access_token;
}

async function paypalRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>
): Promise<T> {
  const token = await getAccessToken();
  const res = await fetch(`${apiBase()}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = (await res.json().catch(() => null)) as
    | (T & { message?: string; details?: Array<{ description?: string }> })
    | null;
  if (!res.ok) {
    const detail = data?.details?.[0]?.description ?? data?.message ?? "PayPal API 요청에 실패했습니다.";
    throw new PaypalError(detail, res.status);
  }
  if (!data) {
    throw new PaypalError("PayPal 응답을 해석할 수 없습니다.", 502);
  }
  return data;
}

interface PaypalOrder {
  id: string;
  status: string;
  links?: Array<{ rel: string; href: string }>;
  purchase_units?: Array<{
    payments?: { captures?: Array<{ id: string; status: string; create_time?: string }> };
  }>;
}

export class PaypalProvider implements PaymentProvider {
  readonly id = "paypal" as const;

  async createCheckout(input: CheckoutInput): Promise<CheckoutSession> {
    if (input.currency !== "USD") {
      throw new Error(`PayPal 결제는 USD만 지원합니다: ${input.currency}`);
    }
    const order = await paypalRequest<PaypalOrder>("POST", "/v2/checkout/orders", {
      intent: "CAPTURE",
      purchase_units: [
        {
          reference_id: input.orderId,
          description: input.orderName,
          amount: { currency_code: "USD", value: input.amount.toFixed(2) },
        },
      ],
      application_context: {
        return_url: input.successUrl,
        cancel_url: input.cancelUrl,
        user_action: "PAY_NOW",
      },
    });

    const approveUrl = order.links?.find((link) => link.rel === "approve")?.href;
    if (!approveUrl) {
      throw new PaypalError("PayPal 승인 URL이 응답에 없습니다.", 502);
    }
    return { providerId: this.id, checkoutUrl: approveUrl, providerOrderId: order.id };
  }

  /** 사용자가 승인하고 돌아온 주문을 캡처(확정)한다. */
  async verifyPayment(input: VerifyInput): Promise<PaymentResult> {
    if (!input.providerOrderId) {
      throw new Error("PayPal 결제 확정에는 providerOrderId가 필요합니다.");
    }
    const order = await paypalRequest<PaypalOrder>(
      "POST",
      `/v2/checkout/orders/${encodeURIComponent(input.providerOrderId)}/capture`
    );
    const capture = order.purchase_units?.[0]?.payments?.captures?.[0];
    return {
      approved: order.status === "COMPLETED" && capture?.status === "COMPLETED",
      providerPaymentKey: capture?.id,
      approvedAt: capture?.create_time,
      raw: order,
    };
  }

  async cancel(_providerOrderId: string): Promise<void> {
    // 승인되지 않은 PayPal 주문은 일정 시간 후 자동 만료된다 — 서버가 정리할 것이 없다.
  }

  /** 캡처된 결제를 환불한다. amount 생략 시 전액 환불. */
  async refund(providerPaymentKey: string, amount?: number): Promise<void> {
    await paypalRequest(
      "POST",
      `/v2/payments/captures/${encodeURIComponent(providerPaymentKey)}/refund`,
      amount === undefined
        ? {}
        : { amount: { currency_code: "USD", value: amount.toFixed(2) } }
    );
  }
}
