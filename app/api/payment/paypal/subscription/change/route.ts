import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isValidPlanId } from "@/lib/plans";
import { PaypalProvider, PaypalError, isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured, paypalPlanIdFor } from "@/lib/payment/paypalPlans";
import { US_PRICING } from "@/lib/pricing/us";
import { publicOriginFrom } from "@/lib/server/publicOrigin";

// POST: 구독 중 플랜 변경(업/다운그레이드). 구독을 새로 만들지 않고 PayPal revise API로
// 기존 구독의 빌링 플랜만 바꾼다 — 새 구독을 겹쳐 만들면 이중 청구가 된다.
//
// 전환 시점 정책: 남은 기간은 현재 플랜을 유지하고, 다음 결제일부터 새 플랜 가격이 청구되며
// 그 결제가 확인될 때 등급(planTier)이 바뀐다. 구매자 재승인이 필요하면 approve URL을
// 돌려주고, 승인 후 BILLING.SUBSCRIPTION.UPDATED 웹훅이 예약을 기록한다.
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
        { error: "결제가 필요한 플랜(PRO/PREMIUM)으로만 변경할 수 있습니다." },
        { status: 400 }
      );
    }

    const record = await prisma.user.findUnique({
      where: { id: user.id },
      select: {
        paymentProvider: true,
        paypalSubscriptionId: true,
        subscriptionPlanId: true,
        subscriptionCanceledAt: true,
      },
    });
    if (
      record?.paymentProvider !== "paypal" ||
      !record.paypalSubscriptionId ||
      !record.subscriptionPlanId
    ) {
      return NextResponse.json({ error: "변경할 구독이 없습니다." }, { status: 400 });
    }
    if (record.subscriptionCanceledAt) {
      return NextResponse.json(
        { error: "해지 예약된 구독은 플랜을 변경할 수 없습니다. 만료 후 다시 구독해주세요." },
        { status: 409 }
      );
    }
    if (record.subscriptionPlanId === planId) {
      return NextResponse.json({ error: "이미 해당 플랜으로 청구될 예정입니다." }, { status: 400 });
    }

    const origin = publicOriginFrom(request);
    const session = await new PaypalProvider().reviseSubscriptionPlan({
      subscriptionId: record.paypalSubscriptionId,
      providerPlanId: paypalPlanIdFor(planId),
      // 변경은 성공 화면이 아니라 요금제 화면으로 돌아온다 — 성공 화면의 sync는 초기 구독
      // 승인용이고, 예약 전환의 반영은 UPDATED 웹훅이 담당한다
      returnUrl: `${origin}/us/pricing`,
      cancelUrl: `${origin}/us/pricing`,
    });

    return NextResponse.json({ approveUrl: session.approveUrl ?? null });
  } catch (error) {
    if (error instanceof PaypalError) {
      return NextResponse.json(
        { error: error.message },
        { status: error.httpStatus >= 500 ? 502 : 400 }
      );
    }
    console.error("Failed to revise PayPal subscription:", error);
    return NextResponse.json({ error: "플랜 변경에 실패했습니다." }, { status: 500 });
  }
}
