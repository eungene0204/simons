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
