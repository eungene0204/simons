// 토스페이먼츠 어댑터 — 기존 lib/server/tossPayments.ts(심사 중, 동결)를 감싸기만 한다.
// 이 파일은 토스 구현을 수정하지 않으며, 기존 결제 라우트(app/api/payment/*)도 아직 이
// 어댑터를 쓰지 않는다. 심사 종료 후 라우트를 PaymentProvider 계약 위로 이관할 때 쓴다.
//
// 토스 빌링은 리다이렉트형 카드 등록창(클라이언트 SDK requestBillingAuth)이 결제 세션을
// 시작하므로 서버 createCheckout이 만들 것이 없다 — successUrl로 돌아온 authKey를
// verifyPayment에서 빌링키로 교환하고 첫 결제를 승인하는 것이 서버 몫이다.

import { chargeBillingKey, issueBillingKey } from "@/lib/server/tossPayments";
import type {
  CheckoutInput,
  CheckoutSession,
  PaymentProvider,
  PaymentResult,
  VerifyInput,
} from "./PaymentProvider";

export class TossProvider implements PaymentProvider {
  readonly id = "toss" as const;

  // 결제 세션은 클라이언트 SDK(requestBillingAuth)가 연다 — 서버는 만들 것이 없다.
  async createCheckout(_input: CheckoutInput): Promise<CheckoutSession> {
    return { providerId: this.id };
  }

  /** successUrl의 authKey를 빌링키로 교환하고 첫 자동결제를 승인한다. */
  async verifyPayment(input: VerifyInput): Promise<PaymentResult> {
    if (!input.authToken || !input.customerKey) {
      throw new Error("토스 결제 확정에는 authToken(authKey)과 customerKey가 필요합니다.");
    }
    if (!input.orderId || input.amount === undefined || !input.orderName || !input.idempotencyKey) {
      throw new Error("토스 결제 확정에는 orderId·amount·orderName·idempotencyKey가 필요합니다.");
    }

    const billing = await issueBillingKey({
      authKey: input.authToken,
      customerKey: input.customerKey,
    });
    const payment = await chargeBillingKey({
      billingKey: billing.billingKey,
      customerKey: input.customerKey,
      amount: input.amount,
      orderId: input.orderId,
      orderName: input.orderName,
      customerEmail: input.customerEmail,
      idempotencyKey: input.idempotencyKey,
    });

    return {
      approved: payment.status === "DONE",
      providerPaymentKey: payment.paymentKey,
      approvedAt: payment.approvedAt,
      raw: payment,
    };
  }

  async cancel(_providerOrderId: string): Promise<void> {
    // 카드 등록창을 중단하면 세션이 그대로 소멸한다 — 서버가 정리할 것이 없다.
  }

  async refund(_providerPaymentKey: string, _amount?: number): Promise<void> {
    // 결제 취소 API(/v1/payments/{paymentKey}/cancel)는 아직 배선되지 않았다.
    // 현행 운영은 갱신 중단(subscriptionCanceledAt)만 제공한다 — 필요 시점에 구현한다.
    throw new Error("토스 환불은 아직 지원하지 않습니다.");
  }
}
