import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { getAccountSettlementValues, moneyToNumber, resolveAccountTotalValue } from "@/lib/server/assetService";

export interface VirtualAccountListItem {
  id: string;
  name: string;
  status: "ACTIVE" | "CLOSED";
  strategyName: string | null;
  initialAmount: number;
  totalValue: number;
  profit: number;
  returnPct: number;
  createdAt: string;
  closedAt: string | null;
}

export interface VirtualAccountListData {
  accounts: VirtualAccountListItem[];
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const accounts = await prisma.virtualAccount.findMany({
      where: withOwnership({}, userId),
      include: { VirtualPosition: true },
      orderBy: { createdAt: "desc" },
    });

    const settlementValues = await getAccountSettlementValues(prisma, accounts.map((a) => a.id));

    const result: VirtualAccountListItem[] = accounts.map((a) => {
      const posValue = (a.VirtualPosition ?? []).reduce(
        (sum, p) => sum + p.quantity * moneyToNumber(p.currentPrice ?? p.avgPrice),
        0
      );
      const initialAmount = moneyToNumber(a.initialCash);
      const liveValue = moneyToNumber(a.currentCash) + posValue;
      const totalValue = resolveAccountTotalValue(a, liveValue, settlementValues);
      const profit = totalValue - initialAmount;
      const returnPct = initialAmount > 0 ? (profit / initialAmount) * 100 : 0;

      return {
        id: a.id,
        name: a.name,
        status: a.status === "CLOSED" ? "CLOSED" : "ACTIVE",
        strategyName: a.strategyName ?? null,
        initialAmount,
        totalValue,
        profit,
        returnPct,
        createdAt: a.createdAt.toISOString(),
        closedAt: a.closedAt ? a.closedAt.toISOString() : null,
      };
    });

    return NextResponse.json({ accounts: result } satisfies VirtualAccountListData);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch virtual account list:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
