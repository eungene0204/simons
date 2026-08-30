// 결제 프로바이더 공통 인터페이스 — 지역별 PSP(토스/PayPal, 향후 Stripe)를 하나의
// 계약으로 추상화한다. 모든 구현은 서버 전용이다(시크릿 키 사용).
//
// 현재 배선 상태:
// - 한국(KRW): 토스페이먼츠 — 기존 결제 경로(app/api/payment/*)가 심사 중이라 동결 상태이며,
//   TossProvider는 그 경로를 건드리지 않는 병렬 어댑터다. 심사 종료 후 기존 라우트를 이
//   인터페이스 위로 이관한다.
// - 글로벌(USD): PaypalProvider — PAYPAL_* 환경변수가 설정되면 동작한다.

export type PaymentProviderId = "toss" | "paypal" | "stripe";

export interface CheckoutInput {
  /** 우리 쪽 주문 ID (PaymentOrder.orderId) */
  orderId: string;
  planId: string;
  /** 서버가 계산한 금액 — 클라이언트 값 금지. KRW는 원 단위 정수, USD는 달러 단위. */
  amount: number;
  currency: "KRW" | "USD";
  /** 결제 승인 후 돌아올 URL */
  successUrl: string;
  /** 사용자가 결제를 중단했을 때 돌아올 URL */
  cancelUrl: string;
  customerKey?: string;
  customerEmail?: string;
  orderName?: string;
}

export interface CheckoutSession {
  providerId: PaymentProviderId;
  /** 사용자를 보낼 결제 승인 페이지 URL (리다이렉트형 PSP) */
  checkoutUrl?: string;
  /** PSP 쪽 주문/세션 식별자 */
  providerOrderId?: string;
}

export interface VerifyInput {
  /** createCheckout이 돌려준 PSP 주문 식별자 (PayPal order id 등) */
  providerOrderId?: string;
  /** 리다이렉트형 PSP가 successUrl에 실어 준 일회성 토큰 (토스 authKey 등) */
  authToken?: string;
  customerKey?: string;
  /** 우리 쪽 주문 ID·금액 — 승인 금액 대조용 */
  orderId?: string;
  amount?: number;
  orderName?: string;
  customerEmail?: string;
  idempotencyKey?: string;
}

export interface PaymentResult {
  approved: boolean;
  /** 취소·환불에 쓰는 PSP 결제 식별자 (토스 paymentKey, PayPal capture id) */
  providerPaymentKey?: string;
  approvedAt?: string;
  raw?: unknown;
}

export interface PaymentProvider {
  readonly id: PaymentProviderId;
  /** 결제 세션(주문)을 만들고 사용자를 보낼 곳을 돌려준다. */
  createCheckout(input: CheckoutInput): Promise<CheckoutSession>;
  /** 사용자가 승인하고 돌아온 뒤 결제를 확정·검증한다. */
  verifyPayment(input: VerifyInput): Promise<PaymentResult>;
  /** 아직 확정되지 않은 결제 세션을 중단한다. */
  cancel(providerOrderId: string): Promise<void>;
  /** 확정된 결제를 환불한다. amount 생략 시 전액. */
  refund(providerPaymentKey: string, amount?: number): Promise<void>;
}

// ── 정기구독(Subscription) ──────────────────────────────────────────────────
// 1회성 결제와 갈리는 지점: 월 갱신 청구를 PSP가 수행한다. 우리 서버는 구독을 만들고,
// 승인·청구·해지 결과를 웹훅으로 받아 반영하고, 해지를 요청할 뿐 직접 청구하지 않는다.
// (한국 토스 자동결제는 반대로 우리 스케줄러가 청구한다 — lib/server/billingRenewal.ts)

export interface CreateSubscriptionInput {
  /** PSP에 미리 만들어 둔 빌링 플랜 식별자 (PayPal plan_id) — 플랜마다 1개, 사용자별로 만들지 않는다 */
  providerPlanId: string;
  /** 구독과 우리 사용자를 잇는 참조값 — 웹훅에서 이 값으로 사용자를 찾는다 */
  userRef: string;
  /** 사용자가 승인한 뒤 돌아올 URL */
  returnUrl: string;
  /** 사용자가 승인을 중단했을 때 돌아올 URL */
  cancelUrl: string;
  subscriberEmail?: string;
  /** 재시도가 중복 구독을 만들지 않게 하는 멱등키 */
  requestId?: string;
}

export interface SubscriptionSession {
  providerId: PaymentProviderId;
  subscriptionId: string;
  /** 사용자를 보낼 구독 승인 페이지 URL */
  approveUrl: string;
  /** PSP 원본 상태 — 생성 직후는 승인 대기 */
  status: string;
}

export interface SubscriptionState {
  subscriptionId: string;
  /** PSP 원본 상태 문자열 (PayPal: APPROVAL_PENDING | APPROVED | ACTIVE | SUSPENDED | CANCELLED | EXPIRED) */
  status: string;
  /** 유료 플랜을 부여해도 되는 상태인지 */
  active: boolean;
  providerPlanId?: string;
  /** createSubscription에 넘긴 userRef */
  userRef?: string;
  /** PSP 쪽 결제자 식별자 */
  payerId?: string;
  /** 다음 청구 예정 시각 (ISO 8601) */
  nextBillingTime?: string;
}

export interface SubscriptionProvider {
  readonly id: PaymentProviderId;
  /** 구독을 만들고 사용자를 보낼 승인 페이지를 돌려준다. 승인 전까지 청구는 일어나지 않는다. */
  createSubscription(input: CreateSubscriptionInput): Promise<SubscriptionSession>;
  /** 구독의 현재 상태를 조회한다 — 승인 복귀 화면·웹훅 대사에 쓴다. */
  getSubscription(subscriptionId: string): Promise<SubscriptionState>;
  /**
   * 구독을 해지한다. PSP는 즉시 해지하며(다음 청구 없음), 남은 기간 동안 유료 플랜을
   * 유지하는 정책(약관 제12조)은 우리 쪽 기록으로 처리한다.
   */
  cancelSubscription(subscriptionId: string, reason?: string): Promise<void>;
}
