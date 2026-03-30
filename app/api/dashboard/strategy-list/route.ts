import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export interface StrategyListItem {
  id: string;
  name: string;
  description: string | null;
  type: string;         // 전략 방식 — DB 저장값 (AI전략 / 가치투자 / 모멘텀 등)
  universe: string;     // 유니버스 — settings 파싱 (KOSPI / KOSDAQ / 미국주식 등)
  avgReturnPct: number;
  totalProfit: number;
  accountCount: number;
  createdAt: string;
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
      // universe: settings에서 파싱
      let universe = "기타";
      try {
        const settings = JSON.parse(s.settings);
        const u: string = settings?.universe?.id ?? settings?.universe ?? "";
        if (u.toUpperCase().includes("KOSPI") || u === "KOSPI200") universe = "KOSPI";
        else if (u.toUpperCase().includes("KOSDAQ")) universe = "KOSDAQ";
        else if (u.includes("US") || u.includes("미국") || u.includes("NYSE") || u.includes("NASDAQ")) universe = "미국주식";
        else if (u) universe = u;
      } catch {}

      // 전략 타입: DB 저장값 사용 (저장 시 inferStrategyType으로 결정됨)
      const type = s.strategyType || "기타";

      // 이 전략을 쓰는 계좌
      const accs = accounts.filter((a) => a.strategyId === s.id);
      if (accs.length === 0) {
        return { id: s.id, name: s.name, description: s.description ?? null, type, universe, avgReturnPct: 0, totalProfit: 0, accountCount: 0, createdAt: s.createdAt.toISOString() };
      }

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
        description: s.description ?? null,
        type,
        universe,
        avgReturnPct,
        totalProfit,
        accountCount: accs.length,
        createdAt: s.createdAt.toISOString(),
      };
    });

    return NextResponse.json({ strategies: result } satisfies StrategyListData);
  } catch (error) {
    console.error("Failed to fetch strategy list:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
