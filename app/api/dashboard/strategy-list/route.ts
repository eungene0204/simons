import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { moneyToNumber } from "@/lib/server/assetService";

function calcScore(m: { cagr?: number; maxDrawdown?: number; sharpe?: number; profitFactor?: number; winRate?: number }): number {
  const scoreCagr = (v?: number) => { if (v == null) return 50; if (v >= 20) return 100; if (v >= 10) return 70; return Math.max(0, Math.round(v / 10 * 70)); };
  const scoreMdd  = (v?: number) => { if (v == null) return 50; const a = Math.abs(v); if (a <= 10) return 100; if (a <= 20) return 70; if (a <= 30) return 40; return Math.max(0, Math.round(100 - a * 2)); };
  const scoreSharpe = (v?: number) => { if (v == null) return 50; if (v >= 1.5) return 100; if (v >= 1.0) return 70; if (v >= 0.5) return 40; return Math.max(0, Math.round(v / 1.5 * 100)); };
  const scorePf   = (v?: number) => { if (v == null) return 50; if (v >= 2.0) return 100; if (v >= 1.5) return 70; if (v >= 1.0) return 40; return Math.max(0, Math.round(v / 2.0 * 100)); };
  const scoreWr   = (v?: number) => { if (v == null) return 50; if (v >= 55) return 100; if (v >= 50) return 70; if (v >= 45) return 40; return Math.max(0, Math.round(v / 55 * 100)); };
  return Math.round(scoreCagr(m.cagr) * 0.30 + scoreMdd(m.maxDrawdown) * 0.25 + scoreSharpe(m.sharpe) * 0.20 + scorePf(m.profitFactor) * 0.15 + scoreWr(m.winRate) * 0.10);
}

export interface StrategyListItem {
  id: string;
  name: string;
  description: string | null;
  type: string;         // 전략 방식 — DB 저장값 (AI전략 / 가치투자 / 모멘텀 등)
  universe: string;     // 유니버스 — settings 파싱 (KOSPI / KOSDAQ / 미국주식 등)
  aiScore: number | null;
  avgReturnPct: number;
  totalProfit: number;
  accountCount: number;
  autoTradingCount: number; // 자동매매 중인 계좌 수
  createdAt: string;
}

export interface StrategyListData {
  strategies: StrategyListItem[];
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    const [strategies, accounts, backtestHistories] = await Promise.all([
      prisma.strategy.findMany({
        where: withOwnership({ isSaved: true }, userId),
        orderBy: { createdAt: "desc" },
        include: { BacktestResult: { orderBy: { createdAt: "desc" }, take: 1 } },
      }),
      prisma.virtualAccount.findMany({
        where: withOwnership({ strategyId: { not: null } }, userId),
        include: { VirtualPosition: true },
      }),
      prisma.backtestHistory.findMany({ orderBy: { createdAt: "desc" } }),
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

      // score 우선순위: BacktestHistory.metrics.score → BacktestResult.summary.score → aiScore → 지표 재계산
      let aiScore: number | null = null;
      try {
        const historyItem =
          backtestHistories.find((h) => h.strategyId === s.id) ??
          backtestHistories.find((h) => h.strategyName === s.name);
        if (historyItem) {
          const hMetrics = JSON.parse(historyItem.metrics);
          if (hMetrics.score != null) {
            aiScore = hMetrics.score;
          }
        }
        if (aiScore == null) {
          const summary = JSON.parse(s.BacktestResult[0]?.summary ?? "{}");
          if (summary.score != null) aiScore = summary.score;
          else if (summary.aiScore != null) aiScore = summary.aiScore;
          else if (summary.cagr != null || summary.maxDrawdown != null) aiScore = calcScore(summary);
        }
      } catch {}

      // 이 전략을 쓰는 계좌
      const accs = accounts.filter((a) => a.strategyId === s.id);
      if (accs.length === 0) {
        return { id: s.id, name: s.name, description: s.description ?? null, type, universe, aiScore, avgReturnPct: 0, totalProfit: 0, accountCount: 0, autoTradingCount: 0, createdAt: s.createdAt.toISOString() };
      }

      const stats = accs.map((a) => {
        const posValue = (a.VirtualPosition ?? []).reduce(
          (sum, p) => sum + p.quantity * moneyToNumber(p.currentPrice ?? p.avgPrice),
          0
        );
        const initialCash = moneyToNumber(a.initialCash);
        const totalValue = moneyToNumber(a.currentCash) + posValue;
        const profit = totalValue - initialCash;
        const returnPct = initialCash > 0 ? (profit / initialCash) * 100 : 0;
        return { profit, returnPct };
      });

      const totalProfit = stats.reduce((s, x) => s + x.profit, 0);
      const avgReturnPct = stats.reduce((s, x) => s + x.returnPct, 0) / stats.length;
      const autoTradingCount = accs.filter((a) => a.tradingMode !== "manual").length;

      return {
        id: s.id,
        name: s.name,
        description: s.description ?? null,
        type,
        universe,
        aiScore,
        avgReturnPct,
        totalProfit,
        accountCount: accs.length,
        autoTradingCount,
        createdAt: s.createdAt.toISOString(),
      };
    });

    return NextResponse.json({ strategies: result } satisfies StrategyListData);
  } catch (error) {
    if (isUnauthorizedAccessError(error)) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    console.error("Failed to fetch strategy list:", error);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
