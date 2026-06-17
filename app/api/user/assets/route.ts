import { NextResponse } from "next/server";
import { getOwnershipContext, isUnauthorizedAccessError } from "@/lib/get-user";
import { prisma } from "@/lib/prisma";
import { getUserAssetSummary, moneyToNumber } from "@/lib/server/assetService";

function mapAccount(account: any) {
  return {
    id: account.id,
    name: account.name,
    initialAmount: moneyToNumber(account.initialCash),
    currentBalance: moneyToNumber(account.currentCash),
    status: account.status ?? "ACTIVE",
    strategyId: account.strategyId ?? undefined,
    strategyName: account.strategyName ?? undefined,
    tradingMode: account.tradingMode ?? "manual",
    createdAt: account.createdAt.toISOString(),
    updatedAt: account.updatedAt.toISOString(),
  };
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    if (userId == null) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const summary = await prisma.$transaction((tx) =>
      getUserAssetSummary(tx, userId)
    );

    return NextResponse.json({
      availableCash: summary.availableCash.toNumber(),
      activeAccountValue: summary.activeAccountValue.toNumber(),
      initialGrantAmount: summary.initialGrantAmount.toNumber(),
      totalAssets: summary.totalAssets.toNumber(),
      totalProfitLoss: summary.totalProfitLoss.toNumber(),
      accounts: summary.accounts.map(mapAccount),
    });
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch user assets:", error);
    return NextResponse.json({ error: "Failed to fetch user assets" }, { status: 500 });
  }
}
