import { NextResponse } from "next/server";
import {
  assertActiveUser,
  getOwnershipContext,
  getSessionUserId,
  isUnauthorizedAccessError,
} from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getUserUsage } from "@/lib/server/planLimits";
import { isValidPlanId } from "@/lib/plans";
import { cancelUserSubscription } from "@/lib/server/subscriptionCancel";
import { backtestUsageCarryOnDowngrade, USAGE_CARRY_SELECT } from "@/lib/server/planDowngrade";
import { GUEST_PAYMENT_BLOCKED_MESSAGE, isGuestEmail } from "@/lib/server/guestAccounts";

function serializeUsage(
  usage: Awaited<ReturnType<typeof getUserUsage>>,
  isGuest: boolean = false
) {
  const { plan } = usage;
  return {
    plan: {
      planId: plan.planId,
      name: plan.name,
      monthlyPrice: plan.monthlyPrice,
      initialInvestmentAmount: plan.initialInvestmentAmount,
      maxVirtualAccounts: plan.maxVirtualAccounts,
      maxStrategies: plan.isUnlimitedStrategies ? null : plan.maxStrategies,
      monthlyBacktestLimit: plan.monthlyBacktestLimit,
      isUnlimitedStrategies: plan.isUnlimitedStrategies,
      planStartDate: usage.planStartDate?.toISOString() ?? null,
      planEndDate: usage.planEndDate?.toISOString() ?? null,
    },
    subscription: usage.subscription
      ? {
          planId: usage.subscription.planId,
          cycle: usage.subscription.cycle,
          nextBillingAt: usage.subscription.nextBillingAt?.toISOString() ?? null,
          canceled: usage.subscription.canceled,
        }
      : null,
    // 게스트(특별 계정) 여부 — 결제·계정 삭제 안내를 화면이 미리 띄우는 데 쓴다.
    // 판정 정본은 서버다(화면이 이 값을 못 받아도 라우트 가드가 막는다).
    isGuest,
    accounts: usage.accounts,
    strategies: {
      used: usage.strategies.used,
      limit: usage.strategies.unlimited ? null : usage.strategies.limit,
      unlimited: usage.strategies.unlimited,
    },
    backtests: usage.backtests,
  };
}

// GET: 현재 플랜 + 사용량
// 원격 DB(Supabase) 왕복 지연이 커서, 토큰은 DB 없이 해석하고
// 계정 상태 검증과 사용량 조회를 한 번의 병렬 배치로 실행한다.
export async function GET() {
  try {
    const userId = await getSessionUserId();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    // 이메일 조회는 기존 배치에 얹는다 — 원격 DB라 직렬로 기다리면 왕복이 하나 늘어난다.
    const [, usage, account] = await Promise.all([
      assertActiveUser(userId),
      getUserUsage(prisma, userId),
      prisma.user.findUnique({ where: { id: userId }, select: { email: true } }),
    ]);
    return NextResponse.json(
      serializeUsage(usage, account ? isGuestEmail(account.email) : false)
    );
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch plan/usage:", error);
    return NextResponse.json({ error: "Failed to fetch plan" }, { status: 500 });
  }
}

// POST: 플랜 변경 — FREE 전환(다운그레이드)만 허용한다.
// 유료 플랜(PRO/PREMIUM) 전환은 결제 승인(토스 /api/payment/confirm, PayPal 웹훅)에서만 수행해
// 결제 없이 planTier가 바뀌는 우회를 막는다.
//
// 자동갱신 구독 중이면 즉시 내리지 않고 해지를 예약한다 — 설정 모달의 "요금제 취소"·/us와
// 같은 의미(남은 결제 기간까지 이용, 약관 제12조 8항). 결제 수단 분기(토스/PayPal)는
// cancelUserSubscription이 맡는다 — 2026-09-03 감사 전에는 여기서 토스 필드만 비워 PayPal
// 구독자는 등급만 FREE가 되고 청구는 계속됐다.
// 구독이 없는데 유료 등급이면(관리자 부여 등) 즉시 FREE로 내리고 빌링 상태를 모두 비운다.
export async function POST(request: Request) {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { planId } = await request.json();
    if (!isValidPlanId(planId)) {
      return NextResponse.json({ error: "Invalid planId" }, { status: 400 });
    }
    if (planId !== "FREE") {
      return NextResponse.json(
        { error: "유료 플랜은 결제를 통해서만 변경할 수 있습니다." },
        { status: 400 }
      );
    }

    const record = await prisma.user.findUnique({
      where: { id: userId },
      select: { email: true, subscriptionPlanId: true, ...USAGE_CARRY_SELECT },
    });

    // 게스트(특별 계정)는 구독 없이 PREMIUM이라 이 경로가 즉시 FREE로 내려 버린다.
    // 다시 올릴 방법이 결제뿐인데 결제도 막혀 있으므로, 발급받은 등급을 잃는 편도 여행이 된다.
    if (record && isGuestEmail(record.email)) {
      return NextResponse.json({ error: GUEST_PAYMENT_BLOCKED_MESSAGE }, { status: 403 });
    }

    if (record?.subscriptionPlanId) {
      const outcome = await cancelUserSubscription(prisma, userId);
      const usage = await getUserUsage(prisma, userId);
      return NextResponse.json({
        ...serializeUsage(usage),
        cancellation: outcome.status === "none" ? null : outcome,
      });
    }

    await prisma.user.update({
      where: { id: userId },
      data: {
        ...backtestUsageCarryOnDowngrade(record ?? {}),
        planTier: planId,
        planStartDate: null,
        billingCycle: "monthly",
        tossBillingKey: null,
        paypalSubscriptionId: null,
        subscriptionPlanId: null,
        nextBillingAt: null,
        subscriptionCanceledAt: null,
        billingFailCount: 0,
      },
    });

    const usage = await getUserUsage(prisma, userId);
    return NextResponse.json(serializeUsage(usage));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to change plan:", error);
    return NextResponse.json({ error: "Failed to change plan" }, { status: 500 });
  }
}
