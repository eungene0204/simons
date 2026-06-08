import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";

export interface AccountMonthlyData {
  months: string[];           // ["2025/01", "2025/02", ...]
  accounts: {
    id: string;
    name: string;
    initialCash: number;
    monthlyProfitPct: number[];  // 각 달의 누적 수익률 (%)
  }[];
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const accounts = await prisma.virtualAccount.findMany({
      where: withOwnership({}, userId),
      orderBy: { createdAt: "asc" },
    });

    if (accounts.length === 0) {
      return NextResponse.json({ months: [], accounts: [] });
    }

    // 최근 6개월 구성
    const now = new Date();
    const months: string[] = [];
    for (let i = 5; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push(`${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}`);
    }

    // 모든 계좌의 FILLED SELL 주문 (realizedPnl 있는 것만)
    const orders = await prisma.virtualOrder.findMany({
      where: {
        accountId: { in: accounts.map((a) => a.id) },
        side: "SELL",
        status: "FILLED",
        realizedPnl: { not: null },
        filledAt: { not: null },
      },
      select: {
        accountId: true,
        realizedPnl: true,
        filledAt: true,
      },
    });

    const result = accounts.map((acc) => {
      const accOrders = orders.filter((o) => o.accountId === acc.id);

      const monthlyProfitPct = months.map((ym) => {
        const [y, m] = ym.split("/").map(Number);
        const monthEnd = new Date(y, m, 1).getTime(); // 해당 월 말(=다음 달 1일)

        // 해당 월 말까지의 누적 실현손익
        const cumPnl = accOrders
          .filter((o) => o.filledAt && o.filledAt.getTime() < monthEnd)
          .reduce((sum, o) => sum + (o.realizedPnl ?? 0), 0);

        return acc.initialCash > 0 ? (cumPnl / acc.initialCash) * 100 : 0;
      });

      return {
        id: acc.id,
        name: acc.name,
        initialCash: acc.initialCash,
        monthlyProfitPct,
      };
    });

    return NextResponse.json({ months, accounts: result } satisfies AccountMonthlyData);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch account monthly data:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
