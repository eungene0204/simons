import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { PLANS, isValidPlanId } from "@/lib/plans";

// POST: 유료 플랜(PRO/PREMIUM) 자동결제(빌링) 구독 주문 생성.
// 결제 금액은 서버의 플랜 정의(lib/plans.ts)에서만 계산한다 — 클라이언트가 보낸 금액은 신뢰하지 않는다.
// 승인 단계(/api/payment/confirm)에서 이 주문의 amount로 첫 달 자동결제를 청구한다.
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { planId } = await request.json();
    if (!isValidPlanId(planId) || PLANS[planId].monthlyPrice <= 0) {
      return NextResponse.json(
        { error: "결제가 필요한 플랜(PRO/PREMIUM)만 주문할 수 있습니다." },
        { status: 400 }
      );
    }

    const plan = PLANS[planId];

    // customerKey는 유추 불가능한 값이어야 한다(이메일·회원번호 금지) — 사용자당 UUID를 1회 생성해 재사용
    let record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { tossCustomerKey: true },
    });
    let customerKey = record?.tossCustomerKey;
    if (!customerKey) {
      customerKey = crypto.randomUUID();
      await prisma.user.update({
        where: { id: user.id },
        data: { tossCustomerKey: customerKey },
      });
    }

    const order = await prisma.paymentOrder.create({
      data: {
        orderId: crypto.randomUUID(),
        userId: user.id,
        planId,
        amount: plan.monthlyPrice,
      },
    });

    return NextResponse.json({
      orderId: order.orderId,
      orderName: `널스탁 ${plan.name} 플랜 월 이용료`,
      amount: order.amount,
      customerKey,
      customerEmail: user.email,
      customerName: user.name,
    });
  } catch (error) {
    console.error("Failed to create payment order:", error);
    return NextResponse.json(
      { error: "결제 주문 생성에 실패했습니다." },
      { status: 500 }
    );
  }
}
