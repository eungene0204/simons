// PayPal 어댑터 — 글로벌 서비스(/us, USD) 결제용.
//
// 두 가지 흐름을 담는다:
// - 정기구독(Subscriptions v1, 유료 플랜 경로): createSubscription(구독 생성) → 사용자를
//   approve URL로 → 승인 후 월 갱신은 PayPal이 수행하고 우리는 웹훅으로 반영한다.
//   https://developer.paypal.com/docs/subscriptions/
// - 1회성 결제(Orders v2): createCheckout → approve → verifyPayment(캡처).
//   https://developer.paypal.com/docs/api/orders/v2/
//
// 환경변수: PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_API_BASE(선택 — 기본 sandbox).

import type {
  CheckoutInput,
  CheckoutSession,
  CreateSubscriptionInput,
  PaymentProvider,
  PaymentResult,
  SubscriptionProvider,
  SubscriptionSession,
  SubscriptionState,
  VerifyInput,
} from "./PaymentProvider";

const DEFAULT_API_BASE = "https://api-m.sandbox.paypal.com";
/** 승인 화면에 노출되는 판매자 이름 — 글로벌 서비스는 영문 표기를 쓴다. */
const BRAND_NAME = "NullStock";

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

/**
 * 웹훅 서명 검증 — PayPal에 "이 요청이 정말 당신이 보낸 것인가"를 되묻는다.
 * 웹훅은 인증 없이 열려 있는 입구라, 이 검증이 없으면 누구나 구독 활성화 이벤트를
 * 위조해 유료 플랜을 받아갈 수 있다. 그래서 실패·미설정은 전부 거절(fail closed)이다.
 *
 * rawBody는 반드시 수신한 원문이어야 한다 — JSON을 파싱했다가 다시 직렬화하면
 * 서명 대상이 달라질 수 있다.
 */
export async function verifyWebhookSignature(
  headers: Headers,
  rawBody: string
): Promise<boolean> {
  const webhookId = process.env.PAYPAL_WEBHOOK_ID?.trim();
  if (!webhookId) {
    throw new Error("PAYPAL_WEBHOOK_ID 환경변수가 설정되지 않았습니다.");
  }

  const transmissionId = headers.get("paypal-transmission-id");
  const transmissionTime = headers.get("paypal-transmission-time");
  const transmissionSig = headers.get("paypal-transmission-sig");
  const certUrl = headers.get("paypal-cert-url");
  const authAlgo = headers.get("paypal-auth-algo");
  if (!transmissionId || !transmissionTime || !transmissionSig || !certUrl || !authAlgo) {
    return false;
  }

  let webhookEvent: unknown;
  try {
    webhookEvent = JSON.parse(rawBody);
  } catch {
    return false;
  }

  const result = await paypalRequest<{ verification_status?: string }>(
    "POST",
    "/v1/notifications/verify-webhook-signature",
    {
      auth_algo: authAlgo,
      cert_url: certUrl,
      transmission_id: transmissionId,
      transmission_sig: transmissionSig,
      transmission_time: transmissionTime,
      webhook_id: webhookId,
      webhook_event: webhookEvent,
    }
  );
  return result.verification_status === "SUCCESS";
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

async function paypalFetch(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>,
  extraHeaders?: Record<string, string>
): Promise<unknown | null> {
  const token = await getAccessToken();
  const res = await fetch(`${apiBase()}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...extraHeaders,
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const data = (await res.json().catch(() => null)) as
    | { message?: string; details?: Array<{ description?: string }> }
    | null;
  if (!res.ok) {
    const detail = data?.details?.[0]?.description ?? data?.message ?? "PayPal API 요청에 실패했습니다.";
    throw new PaypalError(detail, res.status);
  }
  return data;
}

async function paypalRequest<T>(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>,
  extraHeaders?: Record<string, string>
): Promise<T> {
  const data = await paypalFetch(method, path, body, extraHeaders);
  if (!data) {
    throw new PaypalError("PayPal 응답을 해석할 수 없습니다.", 502);
  }
  return data as T;
}

/** 성공 시 본문이 없는 요청(구독 해지 등 204 No Content)용. */
async function paypalRequestVoid(
  method: "GET" | "POST",
  path: string,
  body?: Record<string, unknown>
): Promise<void> {
  await paypalFetch(method, path, body);
}

interface PaypalSubscription {
  id: string;
  status: string;
  plan_id?: string;
  custom_id?: string;
  links?: Array<{ rel: string; href: string }>;
  subscriber?: { payer_id?: string };
  billing_info?: { next_billing_time?: string };
}

interface PaypalOrder {
  id: string;
  status: string;
  links?: Array<{ rel: string; href: string }>;
  purchase_units?: Array<{
    payments?: { captures?: Array<{ id: string; status: string; create_time?: string }> };
  }>;
}

export class PaypalProvider implements PaymentProvider, SubscriptionProvider {
  readonly id = "paypal" as const;

  /**
   * 정기구독을 만든다. 이 시점에는 청구가 일어나지 않고, 사용자가 approve URL에서
   * 승인해야 활성화된다 — 플랜 승격은 승인 복귀가 아니라 웹훅을 정본으로 처리한다.
   */
  async createSubscription(input: CreateSubscriptionInput): Promise<SubscriptionSession> {
    const subscription = await paypalRequest<PaypalSubscription>(
      "POST",
      "/v1/billing/subscriptions",
      {
        plan_id: input.providerPlanId,
        // 웹훅이 실어 보내는 값 — 이걸로 우리 사용자를 찾는다(이메일·회원번호 대신 참조값)
        custom_id: input.userRef,
        ...(input.subscriberEmail ? { subscriber: { email_address: input.subscriberEmail } } : {}),
        application_context: {
          brand_name: BRAND_NAME,
          user_action: "SUBSCRIBE_NOW",
          return_url: input.returnUrl,
          cancel_url: input.cancelUrl,
        },
      },
      // 같은 요청이 재시도돼도 구독이 두 개 생기지 않게 한다
      input.requestId ? { "PayPal-Request-Id": input.requestId } : undefined
    );

    const approveUrl = subscription.links?.find((link) => link.rel === "approve")?.href;
    if (!approveUrl) {
      throw new PaypalError("PayPal 구독 승인 URL이 응답에 없습니다.", 502);
    }
    return {
      providerId: this.id,
      subscriptionId: subscription.id,
      approveUrl,
      status: subscription.status,
    };
  }

  async getSubscription(subscriptionId: string): Promise<SubscriptionState> {
    const subscription = await paypalRequest<PaypalSubscription>(
      "GET",
      `/v1/billing/subscriptions/${encodeURIComponent(subscriptionId)}`
    );
    return {
      subscriptionId: subscription.id,
      status: subscription.status,
      active: subscription.status === "ACTIVE",
      providerPlanId: subscription.plan_id,
      userRef: subscription.custom_id,
      payerId: subscription.subscriber?.payer_id,
      nextBillingTime: subscription.billing_info?.next_billing_time,
    };
  }

  /** 즉시 해지 — 다음 청구가 일어나지 않는다. 남은 기간 플랜 유지는 우리 쪽 기록으로 처리한다. */
  async cancelSubscription(subscriptionId: string, reason?: string): Promise<void> {
    await paypalRequestVoid(
      "POST",
      `/v1/billing/subscriptions/${encodeURIComponent(subscriptionId)}/cancel`,
      { reason: reason ?? "Canceled by subscriber" }
    );
  }

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
