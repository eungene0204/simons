import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { verifyWebhookSignature } from "@/lib/payment/PaypalProvider";
import { planIdFromPaypalPlan } from "@/lib/payment/paypalPlans";
import {
  activatePaypalSubscription,
  downgradePaypalSubscriber,
  markPaypalSubscriptionCanceled,
  recordPaypalSubscriptionPayment,
} from "@/lib/server/paypalSubscription";

// POST: PayPal 웹훅 수신. 유료 플랜의 승격·강등은 이 경로가 정본이다.
//
// 두 가지를 반드시 지킨다:
// 1) 서명 검증 — 인증 없이 열린 입구라, 위조 이벤트로 유료 플랜을 받아가지 못하게 한다.
//    본문은 파싱 전 원문(text)으로 읽어 검증에 넘긴다.
// 2) 멱등 — PayPal은 같은 이벤트를 재전송한다. 이벤트 ID를 먼저 기록해 두 번 반영되지 않게 한다.

interface PaypalWebhookEvent {
  id?: string;
  event_type?: string;
  resource?: {
    id?: string;
    plan_id?: string;
    custom_id?: string;
    status?: string;
    create_time?: string;
    subscriber?: { payer_id?: string };
    billing_info?: { next_billing_time?: string };
    /** PAYMENT.SALE.* 이벤트는 구독 ID를 이 필드로 준다 */
    billing_agreement_id?: string;
  };
}

/** custom_id(구독 생성 때 넣은 사용자 참조값) → 사용자. 없으면 구독 ID로 되찾는다. */
async function resolveUserId(resource: PaypalWebhookEvent["resource"]): Promise<number | null> {
  const ref = Number(resource?.custom_id);
  if (Number.isInteger(ref) && ref > 0) return ref;

  const subscriptionId = resource?.billing_agreement_id ?? resource?.id;
  if (!subscriptionId) return null;
  const user = await prisma.user.findUnique({
    where: { paypalSubscriptionId: subscriptionId },
    select: { id: true },
  });
  return user?.id ?? null;
}

export async function POST(request: Request) {
  // 서명 검증 대상은 수신 원문이다 — 파싱 후 재직렬화하면 서명이 어긋날 수 있다
  const rawBody = await request.text();

  let verified: boolean;
  try {
    verified = await verifyWebhookSignature(request.headers, rawBody);
  } catch (error) {
    // PAYPAL_WEBHOOK_ID 미설정 등 — 검증할 수 없으면 받지 않는다(fail closed)
    console.error("PayPal webhook verification unavailable:", error);
    return NextResponse.json({ error: "Webhook verification unavailable" }, { status: 503 });
  }
  if (!verified) {
    return NextResponse.json({ error: "Invalid signature" }, { status: 401 });
  }

  let event: PaypalWebhookEvent;
  try {
    event = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: "Invalid payload" }, { status: 400 });
  }

  const eventId = event.id;
  const eventType = event.event_type ?? "";
  if (!eventId) {
    return NextResponse.json({ error: "Missing event id" }, { status: 400 });
  }

  // 재전송 차단 — 먼저 기록해 두 번째부터는 처리 자체를 건너뛴다
  try {
    await prisma.paymentWebhookEvent.create({
      data: { provider: "paypal", eventId, eventType },
    });
  } catch {
    return NextResponse.json({ ok: true, duplicate: true });
  }

  try {
    const resource = event.resource;
    const userId = await resolveUserId(resource);
    if (!userId) {
      // 우리 사용자와 이을 수 없는 이벤트 — 재전송을 유발하지 않도록 200으로 닫는다
      console.warn(`[PaypalWebhook] 사용자 매칭 실패: ${eventType} (${eventId})`);
      return NextResponse.json({ ok: true, ignored: "unknown-subscriber" });
    }

    switch (eventType) {
      case "BILLING.SUBSCRIPTION.ACTIVATED": {
        const planId = planIdFromPaypalPlan(resource?.plan_id);
        if (!planId || !resource?.id) {
          return NextResponse.json({ ok: true, ignored: "unknown-plan" });
        }
        await activatePaypalSubscription(prisma, {
          userId,
          planId,
          subscriptionId: resource.id,
          payerId: resource.subscriber?.payer_id,
          nextBillingTime: resource.billing_info?.next_billing_time,
        });
        break;
      }

      case "PAYMENT.SALE.COMPLETED": {
        const record = await prisma.user.findUnique({
          where: { id: userId },
          select: { subscriptionPlanId: true },
        });
        const planId = record?.subscriptionPlanId;
        if (!planId || planId === "FREE" || !resource?.id) {
          return NextResponse.json({ ok: true, ignored: "no-active-plan" });
        }
        await recordPaypalSubscriptionPayment(prisma, {
          userId,
          planId: planId as "PRO" | "PREMIUM",
          saleId: resource.id,
          approvedAt: resource.create_time,
        });
        break;
      }

      // 해지 통지 — 남은 기간은 유지하고 만료 스윕이 FREE로 내린다
      case "BILLING.SUBSCRIPTION.CANCELLED":
        await markPaypalSubscriptionCanceled(prisma, userId);
        break;

      // 정지·만료는 더 이상 청구되지 않으므로 즉시 FREE로 내린다
      case "BILLING.SUBSCRIPTION.SUSPENDED":
      case "BILLING.SUBSCRIPTION.EXPIRED":
        await downgradePaypalSubscriber(prisma, userId);
        break;

      default:
        // 관심 없는 이벤트도 기록만 남기고 200으로 닫는다(재전송 방지)
        break;
    }

    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error(`[PaypalWebhook] 처리 실패 ${eventType} (${eventId}):`, error);
    // 500을 돌려주면 PayPal이 재전송한다 — 이미 기록된 이벤트 ID는 지워 재처리를 허용한다
    await prisma.paymentWebhookEvent
      .deleteMany({ where: { provider: "paypal", eventId } })
      .catch(() => {});
    return NextResponse.json({ error: "Webhook handling failed" }, { status: 500 });
  }
}
