import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export interface StrategyListItem {
  id: string;
  name: string;
  type: string;         // universe (e.g. "KOSPI", "KOSDAQ", "미국주식")
  avgReturnPct: number; // 이 전략을 쓰는 계좌들의 평균 수익률 (%)
  totalProfit: number;  // 이 전략을 쓰는 계좌들의 총 수익금 (원)
  accountCount: number;
}

export interface StrategyListData {
  strategies: StrategyListItem[];
}

export async function GET() {
  try {
    const [strategies, accounts] = await Promise.all([
      prisma.strategy.findMany({ orderBy: { createdAt: "desc" } }),
      prisma.virtualAccount.findMany({
        where: { strategyId: { not: null } },
        include: { VirtualPosition: true },
      }),
    ]);

    const result: StrategyListItem[] = strategies.map((s) => {
      // universe 파싱
      let type = "기타";
      try {
        const settings = JSON.parse(s.settings);
        const u: string = settings?.universe ?? "";
        if (u.includes("KOSPI") || u === "KOSPI200" || u === "KOSPI") type = "KOSPI";
        else if (u.includes("KOSDAQ")) type = "KOSDAQ";
        else if (u.includes("US") || u.includes("미국") || u.includes("NYSE") || u.includes("NASDAQ")) type = "미국주식";
        else if (u) type = u;
      } catch {}

      // 이 전략을 쓰는 계좌
      const accs = accounts.filter((a) => a.strategyId === s.id);
      if (accs.length === 0) {
        return { id: s.id, name: s.name, type, avgReturnPct: 0, totalProfit: 0, accountCount: 0 };
      }

      // totalValue = currentCash + positions * avgPrice (실시간 가격 없이 평균 단가 사용)
      const stats = accs.map((a) => {
        const posValue = (a.VirtualPosition ?? []).reduce(
          (sum, p) => sum + p.quantity * (p.currentPrice ?? p.avgPrice),
          0
        );
        const totalValue = a.currentCash + posValue;
        const profit = totalValue - a.initialCash;
        const returnPct = a.initialCash > 0 ? (profit / a.initialCash) * 100 : 0;
        return { profit, returnPct };
      });

      const totalProfit = stats.reduce((s, x) => s + x.profit, 0);
      const avgReturnPct = stats.reduce((s, x) => s + x.returnPct, 0) / stats.length;

      return {
        id: s.id,
        name: s.name,
        type,
        avgReturnPct,
        totalProfit,
        accountCount: accs.length,
      };
    });

    return NextResponse.json({ strategies: result } satisfies StrategyListData);
  } catch (error) {
    console.error("Failed to fetch strategy list:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
