import { totalContributed } from "@/lib/virtual-account/contributions";
import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { moneyToNumber } from "@/lib/server/assetService";

export interface AccountMonthlyData {
  months: string[];           // ["2025/01", "2025/02", ...]
  accounts: {
    id: string;
    name: string;
    initialCash: number;
    createdAt: string;           // ISO — 개설 월 이전 달은 차트에서 숨긴다
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
          .reduce((sum, o) => sum + moneyToNumber(o.realizedPnl), 0);

        const initialCash = totalContributed(acc.initialCash, acc.contributedCash);
        return initialCash > 0 ? (cumPnl / initialCash) * 100 : 0;
      });

      return {
        id: acc.id,
        name: acc.name,
        // 포트폴리오 가중 평균의 가중치 — 월별 수익률과 같은 분모(총 납입액)여야 한다.
        initialCash: totalContributed(acc.initialCash, acc.contributedCash),
        createdAt: acc.createdAt.toISOString(),
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
