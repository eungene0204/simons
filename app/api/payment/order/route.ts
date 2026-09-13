import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import {
  ANNUAL_BILLING_ENABLED,
  PLANS,
  isValidBillingCycle,
  isValidPlanId,
  orderNameFor,
  priceFor,
  type BillingCycle,
} from "@/lib/plans";

// POST: 유료 플랜(PRO/PREMIUM) 자동결제(빌링) 구독 주문 생성.
// 결제 금액은 서버의 플랜 정의(lib/plans.ts)에서만 계산한다 — 클라이언트가 보낸 금액은 신뢰하지 않는다.
// 승인 단계(/api/payment/confirm)에서 이 주문의 amount로 첫 주기 자동결제를 청구한다.
// 청구 주기(monthly | yearly)도 여기서 확정해 주문에 박아 둔다 — 승인 단계가 이 값으로
// 다음 결제일을 정하므로, 클라이언트가 승인 시점에 주기를 바꿔치기할 수 없다.
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const planId = body?.planId;
    if (!isValidPlanId(planId) || PLANS[planId].monthlyPrice <= 0) {
      return NextResponse.json(
        { error: "결제가 필요한 플랜(PRO/PREMIUM)만 주문할 수 있습니다." },
        { status: 400 }
      );
    }
    // 주기 미지정은 기존 동작(월간)으로 둔다 — 잘못된 값은 임의 보정하지 않고 거부한다.
    const billingCycle: BillingCycle = body?.billingCycle === undefined ? "monthly" : body.billingCycle;
    if (!isValidBillingCycle(billingCycle)) {
      return NextResponse.json({ error: "잘못된 결제 주기입니다." }, { status: 400 });
    }
    // 연간 상품이 꺼져 있으면 새 연간 주문을 만들지 않는다 — 약관에 없는 상품을 팔면 안 된다.
    if (billingCycle === "yearly" && !ANNUAL_BILLING_ENABLED) {
      return NextResponse.json({ error: "연간 결제는 현재 제공하지 않습니다." }, { status: 400 });
    }

    const plan = PLANS[planId];

    // customerKey는 유추 불가능한 값이어야 한다(이메일·회원번호 금지) — 사용자당 UUID를 1회 생성해 재사용
    let record = await prisma.user.findUnique({
      where: { id: user.id },
      select: {
        tossCustomerKey: true,
        subscriptionPlanId: true,
        billingCycle: true,
        subscriptionCanceledAt: true,
        paymentProvider: true,
      },
    });

    // PayPal 구독이 살아 있는 동안에는 토스 주문을 만들지 않는다 — 계정은 KR/US 공용이라
    // 글로벌(/us)에서 PayPal로 결제한 사용자가 이 화면에 올 수 있고, 여기서 겹쳐 결제하면
    // 두 구독이 동시에 청구된다(이중 청구). PayPal 쪽(paypal/subscription)의 토스 가드와
    // 대칭이다. 해지 예약 중에도 만료 전까지는 막는다 — 재구독은 만료 후에 한다.
    if (record?.subscriptionPlanId && record.paymentProvider === "paypal") {
      return NextResponse.json(
        {
          error:
            "해외(PayPal) 구독이 이용 중이라 토스 결제를 진행할 수 없습니다. 플랜 변경과 해지는 글로벌 요금제(/us/pricing)에서 할 수 있습니다.",
        },
        { status: 409 }
      );
    }

    // 연간 구독은 남은 기간이 길어(최대 11개월) 즉시 재결제로 갈아타면 그만큼이 소멸한다.
    // 만료일까지는 플랜·주기 변경을 막는다 — 화면 잠금과 같은 규칙을 서버에서도 강제한다.
    if (
      record?.subscriptionPlanId &&
      record.billingCycle === "yearly" &&
      record.subscriptionCanceledAt == null
    ) {
      return NextResponse.json(
        { error: "연간 구독 기간 중에는 플랜을 변경할 수 없습니다. 만료일 이후 변경할 수 있습니다." },
        { status: 409 }
      );
    }

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
        billingCycle,
        amount: priceFor(plan, billingCycle),
      },
    });

    return NextResponse.json({
      orderId: order.orderId,
      orderName: orderNameFor(plan, billingCycle),
      amount: order.amount,
      billingCycle: order.billingCycle,
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
