// 토스페이먼츠 자동결제(빌링) API 헬퍼 — 시크릿 키는 서버 전용이며 절대 클라이언트에 노출하지 않는다.
// https://docs.tosspayments.com/guides/v2/billing/integration

const TOSS_API_BASE = "https://api.tosspayments.com";

/** 토스페이먼츠 API가 에러를 반환했을 때 던지는 에러 (code/message는 토스 응답 그대로) */
export class TossPaymentError extends Error {
  readonly code: string;
  readonly httpStatus: number;

  constructor(code: string, message: string, httpStatus: number) {
    super(message);
    this.name = "TossPaymentError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

function authHeader(): string {
  const secretKey = process.env.TOSS_SECRET_KEY;
  if (!secretKey) {
    throw new Error("TOSS_SECRET_KEY 환경변수가 설정되지 않았습니다.");
  }
  // Basic base64("시크릿키:") — 시크릿 키 뒤 콜론 필수
  return `Basic ${Buffer.from(`${secretKey}:`).toString("base64")}`;
}

async function tossPost<T>(
  path: string,
  body: Record<string, unknown>,
  options: { idempotencyKey?: string; failMessage: string }
): Promise<T> {
  const headers: Record<string, string> = {
    Authorization: authHeader(),
    "Content-Type": "application/json",
  };
  if (options.idempotencyKey) {
    // 동일 요청 재시도 시 중복 처리를 막는다 (15일간 첫 응답 재사용)
    headers["Idempotency-Key"] = options.idempotencyKey;
  }

  const res = await fetch(`${TOSS_API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });

  const data = (await res.json().catch(() => null)) as
    | (T & { code?: string; message?: string })
    | null;

  if (!res.ok) {
    throw new TossPaymentError(
      data?.code ?? "UNKNOWN_PAYMENT_ERROR",
      data?.message ?? options.failMessage,
      res.status
    );
  }
  if (!data) {
    throw new TossPaymentError("INVALID_RESPONSE", "토스페이먼츠 응답을 해석할 수 없습니다.", 502);
  }
  return data;
}

export interface TossBillingKey {
  billingKey: string;
  customerKey: string;
  [key: string]: unknown;
}

/**
 * 빌링키 발급 API(/v1/billing/authorizations/issue) 호출.
 * 카드 등록창 successUrl로 받은 일회성 authKey를 빌링키로 교환한다.
 * 발급된 빌링키는 다시 조회할 수 없으므로 반드시 customerKey와 매핑해 저장한다.
 */
export async function issueBillingKey(params: {
  authKey: string;
  customerKey: string;
}): Promise<TossBillingKey> {
  return tossPost<TossBillingKey>(
    "/v1/billing/authorizations/issue",
    { authKey: params.authKey, customerKey: params.customerKey },
    { failMessage: "빌링키 발급에 실패했습니다." }
  );
}

export interface TossBillingPayment {
  paymentKey: string;
  orderId: string;
  status: string; // DONE 등
  totalAmount: number;
  method?: string;
  approvedAt?: string;
  [key: string]: unknown;
}

/**
 * 빌링키 자동결제 승인 API(/v1/billing/{billingKey}) 호출.
 * amount는 반드시 서버의 플랜 정의/주문 금액을 사용한다(클라이언트 값 금지).
 */
export async function chargeBillingKey(params: {
  billingKey: string;
  customerKey: string;
  amount: number;
  orderId: string;
  orderName: string;
  customerEmail?: string;
  idempotencyKey: string;
}): Promise<TossBillingPayment> {
  return tossPost<TossBillingPayment>(
    `/v1/billing/${encodeURIComponent(params.billingKey)}`,
    {
      customerKey: params.customerKey,
      amount: params.amount,
      orderId: params.orderId,
      orderName: params.orderName,
      ...(params.customerEmail ? { customerEmail: params.customerEmail } : {}),
    },
    { idempotencyKey: params.idempotencyKey, failMessage: "자동결제 승인에 실패했습니다." }
  );
}
