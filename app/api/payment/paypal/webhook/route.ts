import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import type { PlanId } from "@/lib/plans";
import { PaypalError, PaypalProvider, verifyWebhookSignature } from "@/lib/payment/PaypalProvider";
import { planIdFromPaypalPlan } from "@/lib/payment/paypalPlans";
import {
  activatePaypalSubscription,
  downgradePaypalSubscriberById,
  markPaypalSubscriptionCanceled,
  recordPaypalSubscriptionPayment,
  schedulePaypalPlanChange,
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
        if (!resource?.id) {
          return NextResponse.json({ ok: true, ignored: "no-subscription-id" });
        }
        // 업그레이드 구독의 plan_id는 1회성 플랜이라 env 매핑에 없다 — 그 경우 구독 생성 때
        // 저장해 둔 청구 예정 플랜(subscriptionPlanId)을 정본으로 쓴다(구독 ID 일치 확인).
        // 이 폴백이 없으면 활성화가 "모르는 플랜"으로 무시돼 등급 미전환·이전 구독 미해지로
        // 이중 청구가 난다(2026-08-31 실사고).
        let planId = planIdFromPaypalPlan(resource.plan_id);
        if (!planId) {
          const stored = await prisma.user.findUnique({
            where: { id: userId },
            select: { paypalSubscriptionId: true, subscriptionPlanId: true },
          });
          if (
            stored?.paypalSubscriptionId === resource.id &&
            (stored.subscriptionPlanId === "PRO" || stored.subscriptionPlanId === "PREMIUM")
          ) {
            planId = stored.subscriptionPlanId;
          }
        }
        if (!planId) {
          return NextResponse.json({ ok: true, ignored: "unknown-plan" });
        }
        await activatePaypalSubscription(prisma, {
          userId,
          planId,
          subscriptionId: resource.id,
          payerId: resource.subscriber?.payer_id,
          nextBillingTime: resource.billing_info?.next_billing_time,
        });
        // 업그레이드 전환: 새 구독이 활성화됐으니 보관해 둔 이전 구독을 이제 해지한다.
        // (먼저 해지하면 사용자가 승인을 이탈했을 때 구독을 잃는다.)
        const prior = await prisma.user.findUnique({
          where: { id: userId },
          select: { paypalPriorSubscriptionId: true },
        });
        if (prior?.paypalPriorSubscriptionId && prior.paypalPriorSubscriptionId !== resource.id) {
          try {
            await new PaypalProvider().cancelSubscription(
              prior.paypalPriorSubscriptionId,
              "Upgraded to a new subscription"
            );
          } catch (error) {
            // 이미 해지·만료된 구독(4xx)은 목적 달성으로 간주한다 — 여기서 던지면 재전송이
            // 무한 재시도에 빠진다. 5xx(일시 장애)만 드러내 재전송이 재시도하게 한다.
            if (!(error instanceof PaypalError) || error.httpStatus >= 500) {
              throw error;
            }
          }
          await prisma.user.update({
            where: { id: userId },
            data: { paypalPriorSubscriptionId: null },
          });
        }
        break;
      }

      case "PAYMENT.SALE.COMPLETED": {
        if (!resource?.id) {
          return NextResponse.json({ ok: true, ignored: "no-sale-id" });
        }
        const record = await prisma.user.findUnique({
          where: { id: userId },
          select: { subscriptionPlanId: true },
        });
        const storedPlanId: PlanId | null =
          record?.subscriptionPlanId && record.subscriptionPlanId !== "FREE"
            ? (record.subscriptionPlanId as PlanId)
            : null;

        // 구독을 조회해 플랜과 다음 청구일을 PayPal에서 받아온다. 세 가지를 동시에 푼다:
        // ① 첫 달 청구가 활성화 통지보다 먼저 와도(PayPal은 순서를 보장하지 않는다) 플랜을
        //    알아내 이력을 남긴다 ② 다음 청구일을 우리가 계산하지 않는다 — 갱신 주체가
        //    PayPal이라 저쪽 값이 정본이다 ③ 실제로 청구한 구독의 플랜 매핑을 저장값보다
        //    우선한다 — 업그레이드 승인 이탈 상태에서 옛 구독의 갱신이 새 플랜으로
        //    오기록되면 안 된다. 매핑 불가(1회성 업그레이드 플랜)일 때만 저장값을 쓴다.
        let planId: PlanId | null = null;
        let nextBillingTime: string | undefined;
        if (resource.billing_agreement_id) {
          const state = await new PaypalProvider().getSubscription(resource.billing_agreement_id);
          planId = planIdFromPaypalPlan(state.providerPlanId) ?? storedPlanId;
          nextBillingTime = state.nextBillingTime;
        } else {
          planId = storedPlanId;
        }
        if (!planId) {
          return NextResponse.json({ ok: true, ignored: "no-active-plan" });
        }

        await recordPaypalSubscriptionPayment(prisma, {
          userId,
          planId,
          saleId: resource.id,
          approvedAt: resource.create_time,
          nextBillingTime,
        });
        break;
      }

      // 플랜 변경(revise) 승인 — 다음 청구 플랜만 예약하고 등급은 다음 결제에서 바뀐다
      case "BILLING.SUBSCRIPTION.UPDATED": {
        const planId = planIdFromPaypalPlan(resource?.plan_id);
        if (!planId) {
          return NextResponse.json({ ok: true, ignored: "unknown-plan" });
        }
        await schedulePaypalPlanChange(prisma, {
          userId,
          planId,
          nextBillingTime: resource?.billing_info?.next_billing_time,
        });
        break;
      }

      // 해지·정지·만료 통지 — 반드시 "현재 구독"의 통지일 때만 반영한다. 업그레이드는
      // 우리가 옛 구독을 해지하므로 그 CANCELLED가 뒤따라오는데, 이걸 그대로 반영하면
      // 방금 활성화된 새 구독이 해지 예약으로 물들고 만료 스윕이 유료 사용자를 FREE로
      // 내린다(PayPal은 계속 청구 — 2026-08-31 재검증에서 실제 발생, 데이터 수동 정정).
      case "BILLING.SUBSCRIPTION.CANCELLED":
      case "BILLING.SUBSCRIPTION.SUSPENDED":
      case "BILLING.SUBSCRIPTION.EXPIRED": {
        const rec = await prisma.user.findUnique({
          where: { id: userId },
          select: { paypalSubscriptionId: true },
        });
        if (rec?.paypalSubscriptionId !== resource?.id) {
          return NextResponse.json({ ok: true, ignored: "stale-subscription" });
        }
        if (eventType === "BILLING.SUBSCRIPTION.CANCELLED") {
          // 해지 — 남은 기간은 유지하고 만료 스윕이 FREE로 내린다
          await markPaypalSubscriptionCanceled(prisma, userId);
        } else {
          // 정지·만료는 더 이상 청구되지 않으므로 즉시 FREE로 내린다
          await downgradePaypalSubscriberById(prisma, userId);
        }
        break;
      }

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
