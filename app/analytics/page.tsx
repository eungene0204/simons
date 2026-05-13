import { prisma } from "@/lib/prisma";
import StrategyLabClient from "./StrategyLabClient";

export default async function StrategyLabPage() {
  const [strategies, accounts] = await Promise.all([
    prisma.strategy.findMany({ orderBy: { createdAt: "desc" } }).catch((error) => {
      console.error("[StrategyLabPage] Failed to load strategies", error);
      return [];
    }),
    prisma.virtualAccount
      .findMany({
        where: { strategyId: { not: null } },
        include: { VirtualPosition: true },
      })
      .catch((error) => {
        console.error("[StrategyLabPage] Failed to load virtual accounts", error);
        return [];
      }),
  ]);

  const strategyList = strategies.map((s) => {
    let universe = "기타";
    try {
      const settings = JSON.parse(s.settings);
      const u: string = settings?.universe?.id ?? settings?.universe ?? "";
      if (u.toUpperCase().includes("KOSPI") || u === "KOSPI200") universe = "KOSPI";
      else if (u.toUpperCase().includes("KOSDAQ")) universe = "KOSDAQ";
      else if (u.includes("US") || u.includes("미국") || u.includes("NYSE") || u.includes("NASDAQ")) universe = "미국주식";
      else if (u) universe = u;
    } catch {}

    const type = s.strategyType || "기타";
    const accs = accounts.filter((a) => a.strategyId === s.id);

    if (accs.length === 0) {
      return { id: s.id, name: s.name, description: s.description ?? null, type, universe, aiScore: null, avgReturnPct: 0, totalProfit: 0, accountCount: 0, autoTradingCount: 0, createdAt: s.createdAt.toISOString() };
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
    const autoTradingCount = accs.filter((a) => a.tradingMode !== "manual").length;

    return { id: s.id, name: s.name, description: s.description ?? null, type, universe, aiScore: null, avgReturnPct, totalProfit, accountCount: accs.length, autoTradingCount, createdAt: s.createdAt.toISOString() };
  });

  return <StrategyLabClient strategies={strategyList} />;
}
