import { unstable_cache } from "next/cache";
import { prisma } from "@/lib/prisma";
import { withOwnership } from "@/lib/get-user";
import { getAccountSettlementValues, moneyToNumber, resolveAccountTotalValue } from "@/lib/server/assetService";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";
import type { AccountMonthlyData } from "@/app/api/dashboard/account-monthly/route";
import type { VirtualAccountListData, VirtualAccountListItem } from "@/app/api/dashboard/virtual-account-list/route";
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
  accountList: VirtualAccountListData;
  backtestRecords: DashboardBacktestRecord[];
}

async function fetchDashboardFromDB(userId: number | null): Promise<DashboardInitialData> {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);

  // AccountMonthly 차트는 6개월치만 필요
  const sixMonthsAgo = new Date();
  sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
  sixMonthsAgo.setDate(1);
  sixMonthsAgo.setHours(0, 0, 0, 0);

  // 사용자 소유 계좌를 먼저 조회 → 주문/포지션/시장상태 집계를 이 계좌들로 한정한다.
  const accounts = await prisma.virtualAccount.findMany({
    where: withOwnership({}, userId),
    include: { VirtualPosition: true },
  });
  const accountIds = accounts.map((a) => a.id);
  // userId==null(비인증/테스트)이면 기존처럼 전역 집계를 유지한다.
  const accountScope = userId == null ? {} : { accountId: { in: accountIds } };

  // 백테스트 목록은 사용자별 "내 목록"(UserBacktestHistory)에서 가져온다.
  // userId==null(비인증/테스트)이면 레거시 전역(isVisible) 조회로 폴백한다.
  const backtestHistoryPromise =
    userId == null
      ? prisma.backtestHistory.findMany({ where: { isVisible: true }, orderBy: { createdAt: "desc" }, take: 50 })
      : prisma.userBacktestHistory
          .findMany({
            where: { userId },
            orderBy: { savedAt: "desc" },
            take: 50,
            include: { BacktestHistory: true },
          })
          .then((links) => links.map((link) => link.BacktestHistory));

  const [
    runningAccounts,
    todayFilledOrders,
    dailyPnlAgg,
    backtestHistory,
    sellOrders,
  ] = await Promise.all([
    prisma.virtualMarketState.count({ where: { status: "running", ...accountScope } }),
    prisma.virtualOrder.count({ where: { status: "FILLED", filledAt: { gte: todayStart }, ...accountScope } }),
    prisma.virtualOrder.aggregate({
      where: { status: "FILLED", side: "SELL", filledAt: { gte: todayStart }, ...accountScope },
      _sum: { realizedPnl: true },
    }),
    backtestHistoryPromise,
    prisma.virtualOrder.findMany({
      where: {
        side: "SELL",
        status: "FILLED",
        realizedPnl: { not: null },
        filledAt: { gte: sixMonthsAgo },
        ...accountScope,
      },
      select: { accountId: true, realizedPnl: true, filledAt: true },
    }),
  ]);

  // 계좌 단위 집계는 별도 쿼리 없이 accounts에서 파생
  const totalAccounts = accounts.length;
  const autoAccounts = accounts.filter((a) => a.tradingMode === "auto").length;
  const totalPositions = accounts.reduce((s, a) => s + (a.VirtualPosition?.length ?? 0), 0);

  // CLOSED 계좌는 정산 후 currentCash/포지션이 0/삭제되므로, 정산금(ACCOUNT_LIQUIDATION_RETURN)을 대신 사용한다.
  const settlementValues = await getAccountSettlementValues(prisma, accountIds);

  // ── PortfolioStats ──────────────────────────────────────────
  const dailyPnl = moneyToNumber(dailyPnlAgg._sum.realizedPnl);
  const totalInvested = accounts.reduce((s, a) => s + moneyToNumber(a.initialCash), 0);
  const totalValue = accounts.reduce((s, a) => {
    const posValue = (a.VirtualPosition ?? []).reduce(
      (sum, p) => sum + p.quantity * moneyToNumber(p.currentPrice ?? p.avgPrice),
      0
    );
    const liveValue = moneyToNumber(a.currentCash) + posValue;
    return s + resolveAccountTotalValue(a, liveValue, settlementValues);
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
          .reduce((sum, o) => sum + moneyToNumber(o.realizedPnl), 0);
        const initialCash = moneyToNumber(acc.initialCash);
        return initialCash > 0 ? (cumPnl / initialCash) * 100 : 0;
      });
      return { id: acc.id, name: acc.name, initialCash: moneyToNumber(acc.initialCash), monthlyProfitPct };
    }),
  };

  // ── VirtualAccountList ──────────────────────────────────────
  const accountItems: VirtualAccountListItem[] = accounts.map((a) => {
    const posValue = (a.VirtualPosition ?? []).reduce(
      (sum, p) => sum + p.quantity * moneyToNumber(p.currentPrice ?? p.avgPrice),
      0
    );
    const initialAmount = moneyToNumber(a.initialCash);
    const liveValue = moneyToNumber(a.currentCash) + posValue;
    const tv = resolveAccountTotalValue(a, liveValue, settlementValues);
    const profit = tv - initialAmount;
    const returnPct = initialAmount > 0 ? (profit / initialAmount) * 100 : 0;

    return {
      id: a.id,
      name: a.name,
      status: a.status === "CLOSED" ? "CLOSED" : "ACTIVE",
      strategyName: a.strategyName ?? null,
      initialAmount,
      totalValue: tv,
      profit,
      returnPct,
      createdAt: a.createdAt.toISOString(),
      closedAt: a.closedAt ? a.closedAt.toISOString() : null,
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
    accountList: { accounts: accountItems },
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
    accountList: {
      accounts: [
        { id: "1", name: "계좌 A", status: "ACTIVE", strategyName: "모멘텀 전략 v2", initialAmount: 10_000_000, totalValue: 12_480_000, profit: 2_480_000, returnPct: 24.8, createdAt: new Date().toISOString(), closedAt: null },
        { id: "2", name: "계좌 B", status: "ACTIVE", strategyName: "RSI 역추세 전략", initialAmount: 5_000_000, totalValue: 5_390_000, profit: 390_000, returnPct: 7.8, createdAt: new Date().toISOString(), closedAt: null },
        { id: "3", name: "계좌 C", status: "CLOSED", strategyName: "가치투자 퀀트", initialAmount: 8_000_000, totalValue: 7_680_000, profit: -320_000, returnPct: -4.0, createdAt: new Date().toISOString(), closedAt: new Date().toISOString() },
        { id: "4", name: "계좌 D", status: "ACTIVE", strategyName: "AI 예측 기반", initialAmount: 3_000_000, totalValue: 9_450_000, profit: 6_450_000, returnPct: 215.0, createdAt: new Date().toISOString(), closedAt: null },
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

// userId를 인자로 받아 캐시 키가 사용자별로 분리되게 한다(전역 캐시 누출 방지).
const getCachedDashboardData = unstable_cache(
  (userId: number | null) => fetchDashboardFromDB(userId),
  ["dashboard-initial-data"],
  { revalidate: 30 }
);

export async function getDashboardInitialData(
  userId: number | null
): Promise<DashboardInitialData> {
  if (process.env.DASHBOARD_MOCK === "true") {
    return getMockDashboardData();
  }
  return getCachedDashboardData(userId);
}
