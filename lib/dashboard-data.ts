import { unstable_cache } from "next/cache";
import { prisma } from "@/lib/prisma";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";
import type { AccountMonthlyData } from "@/app/api/dashboard/account-monthly/route";
import type { StrategyListData, StrategyListItem } from "@/app/api/dashboard/strategy-list/route";
import type { DashboardBacktestRecord } from "@/types/dashboard";

export interface PortfolioStats {
  totalInvested: number;
  totalValue: number;
  totalProfit: number;
  totalReturnPct: number;
  accountCount: number;
  dailyPnl: number;
}

export interface DashboardInitialData {
  portfolioStats: PortfolioStats;
  tradingStatus: TradingStatusData;
  accountMonthly: AccountMonthlyData;
  strategyList: StrategyListData;
  backtestRecords: DashboardBacktestRecord[];
}

async function fetchDashboardFromDB(): Promise<DashboardInitialData> {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  // AccountMonthly 차트는 6개월치만 필요
  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
  sixMonthsAgo.setDate(1);
  sixMonthsAgo.setHours(0, 0, 0, 0);

  const [
    accounts,
    totalAccounts,
    runningAccounts,
    autoAccounts,
    todayFilledOrders,
    totalPositions,
    dailyPnlAgg,
    strategies,
    backtestHistory,
    sellOrders,
  ] = await Promise.all([
    prisma.virtualAccount.findMany({ include: { VirtualPosition: true } }),
    prisma.virtualAccount.count(),
    prisma.virtualMarketState.count({ where: { status: "running" } }),
    prisma.virtualAccount.count({ where: { tradingMode: "auto" } }),
    prisma.virtualOrder.count({ where: { status: "FILLED", filledAt: { gte: todayStart } } }),
    prisma.virtualPosition.count(),
    prisma.virtualOrder.aggregate({
      where: { status: "FILLED", side: "SELL", filledAt: { gte: todayStart } },
      _sum: { realizedPnl: true },
    }),
    prisma.strategy.findMany({ orderBy: { createdAt: "desc" } }),
    prisma.backtestHistory.findMany({ where: { isVisible: true }, orderBy: { createdAt: "desc" }, take: 50 }),
    prisma.virtualOrder.findMany({
      where: {
        side: "SELL",
        status: "FILLED",
        realizedPnl: { not: null },
        filledAt: { gte: sixMonthsAgo },
      },
      select: { accountId: true, realizedPnl: true, filledAt: true },
    }),
  ]);

  // strategyAccounts: 별도 쿼리 없이 accounts에서 파생
  const strategyAccounts = accounts.filter((a) => a.strategyId !== null);

  // ── PortfolioStats ──────────────────────────────────────────
  const dailyPnl = dailyPnlAgg._sum.realizedPnl ?? 0;
  const totalInvested = accounts.reduce((s, a) => s + a.initialCash, 0);
  const totalValue = accounts.reduce((s, a) => {
    const posValue = (a.VirtualPosition ?? []).reduce(
      (sum, p) => sum + p.quantity * (p.currentPrice ?? p.avgPrice),
      0
    );
    return s + a.currentCash + posValue;
  }, 0);
  const totalProfit = totalValue - totalInvested;
  const totalReturnPct = totalInvested > 0 ? (totalProfit / totalInvested) * 100 : 0;

  const portfolioStats: PortfolioStats = {
    totalInvested,
    totalValue,
    totalProfit,
    totalReturnPct,
    accountCount: accounts.length,
    dailyPnl,
  };

  // ── TradingStatus ───────────────────────────────────────────
  const tradingStatus: TradingStatusData = {
    totalAccounts,
    runningAccounts,
    autoAccounts,
    todayFilledOrders,
    totalPositions,
    dailyPnl,
    totalEvaluation: totalValue,
  };

  // ── AccountMonthly ──────────────────────────────────────────
  const now = new Date();
  const months: string[] = [];
  for (let i = 5; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    months.push(`${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  const accountMonthly: AccountMonthlyData = {
    months,
    accounts: accounts.map((acc) => {
      const accOrders = sellOrders.filter((o) => o.accountId === acc.id);
      const monthlyProfitPct = months.map((ym) => {
        const [y, m] = ym.split("/").map(Number);
        const monthEnd = new Date(y, m, 1).getTime();
        const cumPnl = accOrders
          .filter((o) => o.filledAt && o.filledAt.getTime() < monthEnd)
          .reduce((sum, o) => sum + (o.realizedPnl ?? 0), 0);
        return acc.initialCash > 0 ? (cumPnl / acc.initialCash) * 100 : 0;
      });
      return { id: acc.id, name: acc.name, initialCash: acc.initialCash, monthlyProfitPct };
    }),
  };

  // ── StrategyList ────────────────────────────────────────────
  const strategyItems: StrategyListItem[] = strategies.map((s) => {
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

    let aiScore: number | null = null;
    try {
      const historyItem = backtestHistory.find((h) => h.strategyName === s.name);
      if (historyItem) {
        const m = JSON.parse(historyItem.metrics);
        if (m.score != null) aiScore = m.score;
      }
    } catch {}

    const accs = strategyAccounts.filter((a) => a.strategyId === s.id);
    if (accs.length === 0) {
      return {
        id: s.id,
        name: s.name,
        description: s.description ?? null,
        type,
        universe,
        aiScore,
        avgReturnPct: 0,
        totalProfit: 0,
        accountCount: 0,
        autoTradingCount: 0,
        createdAt: s.createdAt.toISOString(),
      };
    }

    const stats = accs.map((a) => {
      const posValue = (a.VirtualPosition ?? []).reduce(
        (sum, p) => sum + p.quantity * (p.currentPrice ?? p.avgPrice),
        0
      );
      const tv = a.currentCash + posValue;
      const profit = tv - a.initialCash;
      const returnPct = a.initialCash > 0 ? (profit / a.initialCash) * 100 : 0;
      return { profit, returnPct };
    });

    return {
      id: s.id,
      name: s.name,
      description: s.description ?? null,
      type,
      universe,
      aiScore,
      avgReturnPct: stats.reduce((s, x) => s + x.returnPct, 0) / stats.length,
      totalProfit: stats.reduce((s, x) => s + x.profit, 0),
      accountCount: accs.length,
      autoTradingCount: accs.filter((a) => a.tradingMode !== "manual").length,
      createdAt: s.createdAt.toISOString(),
    };
  });

  // ── BacktestRecords ─────────────────────────────────────────
  const backtestRecords: DashboardBacktestRecord[] = backtestHistory.map((item) => ({
    id: item.id,
    timestamp: item.createdAt.getTime(),
    strategyName: item.strategyName,
    universe: item.universe,
    conditions: JSON.parse(item.conditions),
    metrics: JSON.parse(item.metrics),
  }));

  return {
    portfolioStats,
    tradingStatus,
    accountMonthly,
    strategyList: { strategies: strategyItems },
    backtestRecords,
  };
}

function getMockDashboardData(): DashboardInitialData {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const backtestRecords: DashboardBacktestRecord[] = [
    { id: "1", timestamp: today.getTime() - 86400000 * 0, strategyName: "모멘텀 전략 v2", universe: "KOSPI",   metrics: { totalReturn: 12.4, cagr: 8.2, sharpe: 1.31, mdd: -8.3, score: 74 } },
    { id: "2", timestamp: today.getTime() - 86400000 * 1, strategyName: "RSI 역추세",    universe: "KOSDAQ",  metrics: { totalReturn:  7.8, cagr: 5.1, sharpe: 0.95, mdd: -6.1, score: 61 } },
    { id: "3", timestamp: today.getTime() - 86400000 * 1, strategyName: "가치투자 퀀트", universe: "KOSPI",   metrics: { totalReturn: -3.2, cagr:-2.1, sharpe:-0.42, mdd:-12.5, score: 18 } },
    { id: "4", timestamp: today.getTime() - 86400000 * 2, strategyName: "AI 예측 기반",  universe: "미국주식", metrics: { totalReturn: 21.5, cagr:14.8, sharpe: 1.87, mdd: -5.2, score: 88 } },
    { id: "5", timestamp: today.getTime() - 86400000 * 3, strategyName: "모멘텀 전략 v2", universe: "KOSPI",  metrics: { totalReturn: 10.1, cagr: 7.0, sharpe: 1.15, mdd: -9.0, score: 70 } },
    { id: "6", timestamp: today.getTime() - 86400000 * 4, strategyName: "RSI 역추세",    universe: "KOSDAQ",  metrics: { totalReturn:  5.5, cagr: 3.8, sharpe: 0.80, mdd: -7.2, score: 55 } },
    { id: "7", timestamp: today.getTime() - 86400000 * 4, strategyName: "AI 예측 기반",  universe: "미국주식", metrics: { totalReturn: 18.2, cagr:12.5, sharpe: 1.65, mdd: -4.8, score: 83 } },
    { id: "8", timestamp: today.getTime() - 86400000 * 6, strategyName: "가치투자 퀀트", universe: "KOSPI",   metrics: { totalReturn: -1.0, cagr:-0.7, sharpe:-0.18, mdd:-10.1, score: 22 } },
  ];

  return {
    portfolioStats: {
      totalInvested:  26_000_000,
      totalValue:     29_320_000,
      totalProfit:     3_320_000,
      totalReturnPct:      12.77,
      accountCount:            4,
      dailyPnl:          84_000,
    },
    tradingStatus: {
      totalAccounts:      4,
      runningAccounts:    2,
      autoAccounts:       3,
      todayFilledOrders:  5,
      totalPositions:     8,
      dailyPnl:      84_000,
      totalEvaluation: 29_320_000,
    },
    accountMonthly: MOCK_ACCOUNT_MONTHLY,
    strategyList: {
      strategies: [
        { id: "1", name: "모멘텀 전략 v2", description: null, type: "모멘텀", universe: "KOSPI", aiScore: null, avgReturnPct: 12.4, totalProfit: 2_480_000, accountCount: 2, autoTradingCount: 1, createdAt: new Date().toISOString() },
        { id: "2", name: "RSI 역추세 전략", description: null, type: "역추세", universe: "KOSDAQ", aiScore: null, avgReturnPct: 7.8, totalProfit: 390_000, accountCount: 1, autoTradingCount: 1, createdAt: new Date().toISOString() },
        { id: "3", name: "가치투자 퀀트", description: null, type: "가치투자", universe: "KOSPI", aiScore: null, avgReturnPct: -3.2, totalProfit: -320_000, accountCount: 1, autoTradingCount: 0, createdAt: new Date().toISOString() },
        { id: "4", name: "AI 예측 기반", description: null, type: "AI전략", universe: "미국주식", aiScore: null, avgReturnPct: 21.5, totalProfit: 6_450_000, accountCount: 3, autoTradingCount: 2, createdAt: new Date().toISOString() },
      ],
    },
    backtestRecords,
  };
}

const MOCK_ACCOUNT_MONTHLY: AccountMonthlyData = {
  months: ["2024/10", "2024/11", "2024/12", "2025/01", "2025/02", "2025/03"],
  accounts: [
    { id: "1", name: "계좌 A", initialCash: 10_000_000, monthlyProfitPct: [0.8, 1.2, 3.5, 5.1, 4.8,  7.3] },
    { id: "2", name: "계좌 B", initialCash:  5_000_000, monthlyProfitPct: [0.2, 0.5, 1.8, 2.2, 3.9,  5.0] },
    { id: "3", name: "계좌 C", initialCash:  8_000_000, monthlyProfitPct: [0.5,-0.8, 0.4,-1.2, 2.1,  3.4] },
    { id: "4", name: "계좌 D", initialCash:  3_000_000, monthlyProfitPct: [1.0, 2.1, 4.2, 6.0, 5.5,  9.1] },
  ],
};

const getCachedDashboardData = unstable_cache(
  fetchDashboardFromDB,
  ["dashboard-initial-data"],
  { revalidate: 30 }
);

export async function getDashboardInitialData(): Promise<DashboardInitialData> {
  if (process.env.DASHBOARD_MOCK === "true") {
    return getMockDashboardData();
  }
  return getCachedDashboardData();
}
