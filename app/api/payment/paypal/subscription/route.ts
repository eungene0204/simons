import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isValidPlanId } from "@/lib/plans";
import { PaypalProvider, PaypalError, isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured, paypalPlanIdFor } from "@/lib/payment/paypalPlans";
import { US_PRICING } from "@/lib/pricing/us";
import { publicOriginFrom } from "@/lib/server/publicOrigin";

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

    // 구독이 하나라도 살아 있으면 새 구독을 만들지 않는다 — PayPal 구독은 저쪽에 계약으로
    // 남아 있어서, 겹쳐 만들면 두 구독이 동시에 청구된다(이중 청구). 플랜 변경은 revise
    // 경로(subscription/change)가 담당하고, 해지 예약 중에는 만료 후에만 재구독할 수 있다.
    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: { paymentProvider: true, subscriptionPlanId: true },
    });
    if (record?.subscriptionPlanId) {
      return NextResponse.json(
        { error: "이미 진행 중인 구독이 있습니다. 플랜 변경은 요금제 화면에서, 재구독은 기존 구독 만료 후에 할 수 있습니다." },
        { status: 409 }
      );
    }

    // request.url의 origin은 컨테이너 내부 주소(localhost:3000)라 복귀 URL에 쓰면 안 된다
    const origin = publicOriginFrom(request);
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
