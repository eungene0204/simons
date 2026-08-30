import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { isValidPlanId } from "@/lib/plans";
import { PaypalProvider, PaypalError, isPaypalConfigured } from "@/lib/payment/PaypalProvider";
import { isPaypalSubscriptionConfigured, paypalPlanIdFor } from "@/lib/payment/paypalPlans";
import { US_PRICING } from "@/lib/pricing/us";
import { publicOriginFrom } from "@/lib/server/publicOrigin";
import { upgradeFirstPeriodDays } from "@/lib/server/paypalUpgradeCredit";

// POST: 구독 중 플랜 변경. 방향에 따라 정책이 다르다(2026-08-31 확정):
//
// - 다운그레이드: PayPal revise로 빌링 플랜만 예약 교체 — 남은 기간은 현재 플랜 유지,
//   다음 결제일부터 새 가격·등급(그 결제가 확인될 때 planTier 전환).
// - 업그레이드: 즉시 전환 + 상위 플랜 월액 즉시 청구. 남은 하위 플랜 가치는 기간으로
//   환산해 첫 주기에 더한다(연장된 첫 주기의 1회성 플랜 + 새 구독). 이전 구독은 새 구독
//   활성화가 확인된 뒤 웹훅이 해지한다 — 먼저 해지하면 승인 이탈 시 구독을 잃는다.
// - 예약된 다운그레이드 취소(현 등급으로 되돌리기): revise로 원 플랜 복귀, 추가 청구 없음.
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
        planTier: true,
        paymentProvider: true,
        paypalSubscriptionId: true,
        subscriptionPlanId: true,
        subscriptionCanceledAt: true,
        nextBillingAt: true,
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
    const provider = new PaypalProvider();

    const targetPrice = US_PRICING.monthlyPrice[planId as "PRO" | "PREMIUM"];
    const billedPrice =
      US_PRICING.monthlyPrice[record.subscriptionPlanId as "PRO" | "PREMIUM"] ?? 0;
    // 예약된 다운그레이드를 되돌리는 경우(현 등급으로 복귀)는 추가 청구 없는 revise다
    const isRevertOfPendingChange = planId === record.planTier;

    if (targetPrice > billedPrice && !isRevertOfPendingChange) {
      // 업그레이드: 연장된 첫 주기 플랜을 만들어 새 구독으로 갈아탄다(즉시 청구)
      const firstPeriodDays = upgradeFirstPeriodDays({
        nextBillingAt: record.nextBillingAt ?? new Date(),
        now: new Date(),
        fromMonthlyPrice: billedPrice,
        toMonthlyPrice: targetPrice,
      });
      const upgradePlanId = await provider.createUpgradePlan({
        basePlanId: paypalPlanIdFor(planId),
        planName: `NullStock ${planId === "PREMIUM" ? "Premium" : "Pro"} Upgrade ${firstPeriodDays}d`,
        firstPeriodDays,
        monthlyPrice: targetPrice,
        requestId: `upg-plan-${user.id}-${firstPeriodDays}-${Date.now()}`,
      });
      const session = await provider.createSubscription({
        providerPlanId: upgradePlanId,
        userRef: String(user.id),
        returnUrl: `${origin}/us/pricing/success`,
        cancelUrl: `${origin}/us/pricing`,
        subscriberEmail: user.email,
        requestId: `upg-sub-${user.id}-${planId}-${Date.now()}`,
      });
      // 이전 구독은 보관만 한다 — 새 구독 활성화(웹훅) 확인 후에 해지한다
      await prisma.user.update({
        where: { id: user.id },
        data: {
          paypalPriorSubscriptionId: record.paypalSubscriptionId,
          paypalSubscriptionId: session.subscriptionId,
        },
      });
      return NextResponse.json({ approveUrl: session.approveUrl });
    }

    const session = await provider.reviseSubscriptionPlan({
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
