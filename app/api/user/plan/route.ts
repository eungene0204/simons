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

// POST: 플랜 변경 (무료 mock — planTier만 변경, 기존 계좌 초기 투자금은 소급 변경하지 않음)
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

    await prisma.user.update({
      where: { id: userId },
      data: { planTier: planId },
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
