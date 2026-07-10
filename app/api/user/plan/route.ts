import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getUserUsage } from "@/lib/server/planLimits";
import { isValidPlanId } from "@/lib/plans";

function serializeUsage(usage: Awaited<ReturnType<typeof getUserUsage>>) {
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
export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    const usage = await getUserUsage(prisma, userId);
    return NextResponse.json(serializeUsage(usage));
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch plan/usage:", error);
    return NextResponse.json({ error: "Failed to fetch plan" }, { status: 500 });
  }
}

// POST: 플랜 변경 — FREE 전환(다운그레이드)만 허용한다.
// 유료 플랜(PRO/PREMIUM) 전환은 토스페이먼츠 결제 승인(/api/payment/confirm)에서만 수행해
// 결제 없이 planTier가 바뀌는 우회를 막는다.
// FREE로 전환하면 구독 이력이 없는 상태이므로 planStartDate와 자동결제(빌링) 상태를 모두 비운다
// — 남은 빌링키로 갱신 잡이 청구하는 일이 없도록 즉시 자동갱신을 중단한다.
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

    await prisma.user.update({
      where: { id: userId },
      data: {
        planTier: planId,
        planStartDate: null,
        tossBillingKey: null,
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
