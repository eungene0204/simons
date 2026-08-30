import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isValidPlanId } from "@/lib/plans";
import { PaypalProvider, PaypalError, isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured, paypalPlanIdFor } from "@/lib/payment/paypalPlans";
import { US_PRICING } from "@/lib/pricing/us";

// POST: 글로벌(/us) 정기구독 생성. PayPal에 구독을 만들고 사용자를 보낼 승인 URL을 돌려준다.
// 이 시점에는 청구가 일어나지 않으며, 유료 전환은 승인 뒤 웹훅(정본)이 처리한다.
// 한국(토스) 결제 경로는 건드리지 않는다 — 별도 라우트다.
export async function POST(request: Request) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    if (!isPaypalConfigured() || !isPaypalSubscriptionConfigured()) {
      return NextResponse.json(
        { error: "PayPal 결제가 아직 설정되지 않았습니다." },
        { status: 503 }
      );
    }

    const { planId } = await request.json();
    if (!isValidPlanId(planId) || US_PRICING.monthlyPrice[planId] <= 0) {
      return NextResponse.json(
        { error: "결제가 필요한 플랜(PRO/PREMIUM)만 구독할 수 있습니다." },
        { status: 400 }
      );
    }

    // 한국(토스) 자동결제가 살아 있는 계정이 PayPal 구독까지 만들면 이중 청구가 된다
    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { paymentProvider: true, subscriptionPlanId: true, tossBillingKey: true },
    });
    if (record?.subscriptionPlanId && record.paymentProvider === "toss") {
      return NextResponse.json(
        { error: "이미 진행 중인 구독이 있습니다. 기존 구독을 해지한 뒤 다시 시도해주세요." },
        { status: 409 }
      );
    }

    const origin = new URL(request.url).origin;
    const session = await new PaypalProvider().createSubscription({
      providerPlanId: paypalPlanIdFor(planId),
      // 웹훅이 이 값으로 사용자를 되찾는다
      userRef: String(user.id),
      returnUrl: `${origin}/us/pricing/success`,
      cancelUrl: `${origin}/us/pricing`,
      subscriberEmail: user.email,
      requestId: `sub-${user.id}-${planId}-${Date.now()}`,
    });

    // 승인 전이지만 해지·조회에 필요하므로 구독 ID는 지금 저장한다.
    // 플랜 승격은 하지 않는다 — 승인되지 않은 구독으로 유료 기능이 열리면 안 된다.
    await prisma.user.update({
      where: { id: user.id },
      data: { paypalSubscriptionId: session.subscriptionId },
    });

    return NextResponse.json({
      subscriptionId: session.subscriptionId,
      approveUrl: session.approveUrl,
      status: session.status,
    });
  } catch (error) {
    if (error instanceof PaypalError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.httpStatus >= 500 ? 502 : 400 }
      );
    }
    console.error("Failed to create PayPal subscription:", error);
    return NextResponse.json({ error: "구독 생성에 실패했습니다." }, { status: 500 });
  }
}
