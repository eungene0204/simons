import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { PLANS, isValidPlanId } from "@/lib/plans";
import {
  TossPaymentError,
  chargeBillingKey,
  issueBillingKey,
} from "@/lib/server/tossPayments";
import { addMonthsClamped } from "@/lib/server/planLimits";

// POST: 자동결제(빌링) 구독 확정. 카드 등록창 successUrl로 돌아온 authKey/customerKey와
// 서버에 저장된 주문(orderId)을 대조한 뒤 빌링키를 발급하고 첫 달 결제를 즉시 승인한다.
// 성공 시 사용자의 플랜 전환 + 빌링키/다음 결제일을 저장한다 — 유료 전환은 이 경로에서만 일어난다.
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const authKey = typeof body.authKey === "string" ? body.authKey : "";
    const customerKey = typeof body.customerKey === "string" ? body.customerKey : "";
    const orderId = typeof body.orderId === "string" ? body.orderId : "";
    if (!authKey || !customerKey || !orderId) {
      return NextResponse.json({ error: "잘못된 결제 승인 요청입니다." }, { status: 400 });
    }

    const order = await prisma.paymentOrder.findUnique({ where: { orderId } });
    if (!order || order.userId !== user.id) {
      return NextResponse.json({ error: "주문을 찾을 수 없습니다." }, { status: 404 });
    }
    if (!isValidPlanId(order.planId)) {
      return NextResponse.json({ error: "주문의 플랜 정보가 올바르지 않습니다." }, { status: 500 });
    }
    const plan = PLANS[order.planId];

    // customerKey 위변조 검증: 카드 등록창에 전달한 값(서버 저장 tossCustomerKey)과 다르면 거부
    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { tossCustomerKey: true },
    });
    if (!record?.tossCustomerKey || record.tossCustomerKey !== customerKey) {
      return NextResponse.json(
        { error: "구매자 식별 정보가 일치하지 않습니다." },
        { status: 400 }
      );
    }

    // 성공 페이지 새로고침 등으로 같은 승인 요청이 다시 오면 이미 완료된 결과를 그대로 돌려준다
    if (order.status === "DONE") {
      return NextResponse.json({ ok: true, planId: order.planId, planName: plan.name });
    }
    if (order.status !== "PENDING") {
      return NextResponse.json(
        { error: "이미 종료된 주문입니다. 결제를 다시 시도해주세요." },
        { status: 409 }
      );
    }

    try {
      // 1) 일회성 authKey → 빌링키 교환
      const billing = await issueBillingKey({ authKey, customerKey });

      // 2) 첫 달 즉시 결제 — 금액은 서버 저장 주문 금액만 사용한다
      const payment = await chargeBillingKey({
        billingKey: billing.billingKey,
        customerKey,
        amount: order.amount,
        orderId: order.orderId,
        orderName: `널스탁 ${plan.name} 플랜 월 이용료`,
        customerEmail: user.email,
        idempotencyKey: order.orderId,
      });

      const now = new Date();
      await prisma.$transaction([
        prisma.paymentOrder.update({
          where: { orderId },
          data: {
            status: "DONE",
            paymentKey: payment.paymentKey,
            approvedAt: payment.approvedAt ? new Date(payment.approvedAt) : now,
          },
        }),
        prisma.user.update({
          where: { id: user.id },
          data: {
            planTier: order.planId,
            planStartDate: now,
            tossBillingKey: billing.billingKey,
            subscriptionPlanId: order.planId,
            nextBillingAt: addMonthsClamped(now, 1),
            subscriptionCanceledAt: null,
            billingFailCount: 0,
          },
        }),
      ]);

      return NextResponse.json({ ok: true, planId: order.planId, planName: plan.name });
    } catch (error) {
      if (error instanceof TossPaymentError) {
        await prisma.paymentOrder.update({
          where: { orderId },
          data: { status: "FAILED", failReason: error.code },
        });
        return NextResponse.json(
          { error: error.message, code: error.code },
          { status: error.httpStatus >= 500 ? 502 : 400 }
        );
      }
      throw error;
    }
  } catch (error) {
    console.error("Failed to confirm billing payment:", error);
    return NextResponse.json({ error: "결제 승인에 실패했습니다." }, { status: 500 });
  }
}
