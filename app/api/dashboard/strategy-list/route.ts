import { totalContributed } from "@/lib/virtual-account/contributions";
import { NextResponse } from "next/server";
import { Prisma } from "@prisma/client";
import { prisma } from "@/lib/prisma";
import {
  getOwnershipContext,
  isUnauthorizedAccessError,
  withOwnership,
} from "@/lib/get-user";
import { moneyToNumber, resolveAccountTotalValue } from "@/lib/server/assetService";
import { fetchLivePriceMap, positionsMarketValue } from "@/lib/server/accountValuation";

function calcScore(m: { cagr?: number; maxDrawdown?: number; sharpe?: number; profitFactor?: number | null; winRate?: number }): number {
  const scoreCagr = (v?: number) => { if (v == null) return 50; if (v >= 20) return 100; if (v >= 10) return 70; return Math.max(0, Math.round(v / 10 * 70)); };
  const scoreMdd  = (v?: number) => { if (v == null) return 50; const a = Math.abs(v); if (a <= 10) return 100; if (a <= 20) return 70; if (a <= 30) return 40; return Math.max(0, Math.round(100 - a * 2)); };
  const scoreSharpe = (v?: number) => { if (v == null) return 50; if (v >= 1.5) return 100; if (v >= 1.0) return 70; if (v >= 0.5) return 40; return Math.max(0, Math.round(v / 1.5 * 100)); };
  const scorePf   = (v?: number) => { if (v == null) return 50; if (v >= 2.0) return 100; if (v >= 1.5) return 70; if (v >= 1.0) return 40; return Math.max(0, Math.round(v / 2.0 * 100)); };
  const scoreWr   = (v?: number) => { if (v == null) return 50; if (v >= 55) return 100; if (v >= 50) return 70; if (v >= 45) return 40; return Math.max(0, Math.round(v / 55 * 100)); };
  return Math.round(scoreCagr(m.cagr) * 0.30 + scoreMdd(m.maxDrawdown) * 0.25 + scoreSharpe(m.sharpe) * 0.20 + scorePf(m.profitFactor === null ? 999 : m.profitFactor) * 0.15 + scoreWr(m.winRate) * 0.10);
}

// 키가 없으면 SQL NULL(→ undefined), JSON null이면 문자열 'null'(→ null) — 종전 summary 파싱과 같은 구분.
type SummaryMetricRow = { strategyId: string } & Record<
  "score" | "aiScore" | "cagr" | "maxDrawdown" | "sharpe" | "profitFactor" | "winRate",
  unknown
>;

function parseMetric(value: unknown): unknown {
  if (value === null || value === undefined) return undefined;
  return typeof value === "string" ? JSON.parse(value) : value;
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
  isPublic: boolean;        // '전략공유' 화면 공개 여부
  createdAt: string;
}

export interface StrategyListData {
  strategies: StrategyListItem[];
}

export async function GET() {
  try {
    const { userId } = await getOwnershipContext();
    // 원격 DB라 왕복 하나가 ~0.6초다 — 서로 기다릴 필요 없는 조회는 한 번에 띄운다(2026-10-21: 직렬 4단 → 병렬 2단).
    // 소유 필터는 id 목록을 기다려 만들지 않고 관계 조건(Strategy.userId 등)으로 건다.
    const ownedStrategy = withOwnership({ isSaved: true }, userId);
    const ownedAccount = withOwnership({ strategyId: { not: null } }, userId);
    const [strategies, summaryRows, accounts, positions, backtestHistories, ledgerRows] = await Promise.all([
      prisma.strategy.findMany({ where: ownedStrategy, orderBy: { createdAt: "desc" } }),
      // 점수 대체 계산에 쓰는 최신 결과의 지표 몇 개만 DB에서 뽑는다 — summary 전체(전략당 수백 KB)와
      // trades 본문을 내려받지 않는다. 실패해도 목록은 나가야 하므로 점수 대체만 포기한다.
      prisma.$queryRaw<SummaryMetricRow[]>(Prisma.sql`
        SELECT DISTINCT ON (r."strategyId") r."strategyId",
          r."summary"::jsonb->'score' AS "score", r."summary"::jsonb->'aiScore' AS "aiScore",
          r."summary"::jsonb->'cagr' AS "cagr", r."summary"::jsonb->'maxDrawdown' AS "maxDrawdown",
          r."summary"::jsonb->'sharpe' AS "sharpe", r."summary"::jsonb->'profitFactor' AS "profitFactor",
          r."summary"::jsonb->'winRate' AS "winRate"
        FROM "BacktestResult" r JOIN "Strategy" st ON st."id" = r."strategyId"
        WHERE st."isSaved" = true ${userId == null ? Prisma.empty : Prisma.sql`AND st."userId" = ${userId}`}
        ORDER BY r."strategyId", r."createdAt" DESC`).catch(() => [] as SummaryMetricRow[]),
      prisma.virtualAccount.findMany({ where: ownedAccount }),
      prisma.virtualPosition.findMany({ where: { VirtualAccount: ownedAccount } }),
      prisma.backtestHistory.findMany({
        where: {
          OR: [
            { Strategy: ownedStrategy },
            ...(userId == null ? [] : [{ UserBacktestHistory: { some: { userId } } }]),
          ],
        },
        orderBy: { createdAt: "desc" },
        select: { strategyId: true, strategyName: true, metrics: true },
      }),
      prisma.assetLedger.findMany({
        where: { type: "ACCOUNT_LIQUIDATION_RETURN", VirtualAccount: ownedAccount },
        orderBy: { createdAt: "desc" },
        select: { accountId: true, amount: true },
      }),
    ]);
    const summaryByStrategyId = new Map(summaryRows.map((row) => [row.strategyId, row]));
    const latestHistoryByStrategyId = new Map<string, (typeof backtestHistories)[number]>();
    const latestHistoryByStrategyName = new Map<string, (typeof backtestHistories)[number]>();
    for (const history of backtestHistories) {
      if (history.strategyId && !latestHistoryByStrategyId.has(history.strategyId)) {
        latestHistoryByStrategyId.set(history.strategyId, history);
      }
      if (!latestHistoryByStrategyName.has(history.strategyName)) {
        latestHistoryByStrategyName.set(history.strategyName, history);
      }
    }

    // 정산금은 계좌별 가장 최근 항목(getAccountSettlementValues와 같은 규칙).
    const settlementValues: Record<string, number> = {};
    for (const entry of ledgerRows) {
      if (entry.accountId && !(entry.accountId in settlementValues)) {
        settlementValues[entry.accountId] = moneyToNumber(entry.amount);
      }
    }
    const priceMap = await fetchLivePriceMap(positions.map((position) => position.symbol));
    const positionsByAccount = new Map<string, typeof positions>();
    for (const position of positions) {
      const list = positionsByAccount.get(position.accountId) ?? [];
      list.push(position);
      positionsByAccount.set(position.accountId, list);
    }

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
          latestHistoryByStrategyId.get(s.id) ??
          latestHistoryByStrategyName.get(s.name);
        if (historyItem) {
          const hMetrics = JSON.parse(historyItem.metrics);
          if (hMetrics.score != null) {
            aiScore = hMetrics.score;
          }
        }
        if (aiScore == null) {
          const row = summaryByStrategyId.get(s.id);
          const summary: Record<string, any> = row
            ? Object.fromEntries(
                ["score", "aiScore", "cagr", "maxDrawdown", "sharpe", "profitFactor", "winRate"]
                  .map((key) => [key, parseMetric(row[key as keyof SummaryMetricRow])])
                  .filter(([, value]) => value !== undefined)
              )
            : {};
          if (summary.score != null) aiScore = summary.score;
          else if (summary.aiScore != null) aiScore = summary.aiScore;
          else if (summary.cagr != null || summary.maxDrawdown != null) aiScore = calcScore(summary);
        }
      } catch {}

      // 이 전략을 쓰는 계좌
      const accs = accounts.filter((a) => a.strategyId === s.id);
      if (accs.length === 0) {
        return { id: s.id, name: s.name, description: s.description ?? null, type, universe, aiScore, avgReturnPct: 0, totalProfit: 0, accountCount: 0, autoTradingCount: 0, isPublic: s.isPublic, createdAt: s.createdAt.toISOString() };
      }

      const stats = accs.map((a) => {
        const posValue = positionsMarketValue(positionsByAccount.get(a.id), priceMap);
        // 수익률의 분모는 총 납입액이다(정액 적립식 — 납입이 없는 계좌는 초기 자본과 같다).
        const initialCash = totalContributed(a.initialCash, a.contributedCash);
        const liveValue = moneyToNumber(a.currentCash) + posValue;
        const totalValue = resolveAccountTotalValue(a, liveValue, settlementValues);
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
        isPublic: s.isPublic,
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
