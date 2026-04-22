import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";

function pruneUndefined(val: any): any {
  if (Array.isArray(val)) return val.map(pruneUndefined);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.entries(val)
        .filter(([, value]) => value !== undefined)
        .map(([key, value]) => [key, pruneUndefined(value)])
    );
  }
  return val;
}

function sortDeep(val: any): any {
  if (Array.isArray(val)) return val.map(sortDeep);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.keys(val)
        .sort()
        .map((key) => [key, sortDeep(val[key])])
    );
  }
  return val;
}

function sha256(input: string): string {
  return createHash("sha256").update(input).digest("hex");
}

function stableStringify(value: any): string {
  return JSON.stringify(sortDeep(pruneUndefined(value)));
}

export function canonicalizeStrategyDsl(dsl: any): any {
  if (!dsl || typeof dsl !== "object") return {};

  const {
    id: _id,
    name: _name,
    description: _description,
    version: _version,
    created_at: _createdAt,
    updated_at: _updatedAt,
    strategy_id: _strategyId,
    canonical_strategy_dsl: _canonicalDsl,
    ...rest
  } = dsl;

  return sortDeep(pruneUndefined(rest));
}

export function computeStrategyIdFromDsl(dsl: any): string {
  return sha256(stableStringify(canonicalizeStrategyDsl(dsl)));
}

export function resolveStrategyId(payload: any): string | null {
  const directId = payload?.strategy_id ?? payload?.strategyId;
  if (typeof directId === "string" && directId.trim()) {
    return directId.trim();
  }

  const canonicalDsl = payload?.canonical_strategy_dsl ?? payload?.canonicalStrategyDsl;
  if (canonicalDsl) {
    const canonical =
      typeof canonicalDsl === "string"
        ? canonicalDsl
        : stableStringify(canonicalDsl);
    return sha256(canonical);
  }

  if (payload?.dsl) {
    return computeStrategyIdFromDsl(payload.dsl);
  }

  return null;
}

export function computeCacheKey(body: any): string {
  const strategyId = resolveStrategyId(body);
  if (strategyId) {
    return strategyId;
  }

  const normalized = sortDeep({
    symbols: [...(body.symbols ?? [])].sort(),
    entry: {
      conditions: [...(body.entry?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    exit: {
      conditions: [...(body.exit?.conditions ?? [])].sort((a: any, b: any) =>
        (a.id ?? "").localeCompare(b.id ?? "")
      ),
    },
    risk: body.risk ?? {},
    period: (body.period ?? "5Y").toUpperCase(),
    options: body.options ?? {},
  });

  return sha256(JSON.stringify(normalized));
}

function buildBacktestMetrics(result: any) {
  return {
    totalReturn: result.totalReturn ?? 0,
    cagr: result.cagr ?? 0,
    mdd: result.maxDrawdown ?? 0,
    winRate: result.winRate ?? 0,
    profitFactor: result.profitFactor ?? 0,
    buyHold: result.buyAndHoldReturn ?? 0,
    trades: result.trades ?? 0,
    executionTime: result.executionTime ?? 0,
    perAssetStats: result.perAssetStats ?? null,
    topSymbols: result.topSymbols ?? null,
  };
}

function buildBacktestSummary(result: any) {
  return {
    totalReturn: result.totalReturn ?? 0,
    cagr: result.cagr ?? 0,
    maxDrawdown: result.maxDrawdown ?? 0,
    profitFactor: result.profitFactor ?? 0,
    sharpe: result.sharpe ?? 0,
    sortino: result.sortino ?? 0,
    kelly: result.kelly ?? 0,
    volatility: result.volatility ?? 0,
    buyAndHoldReturn: result.buyAndHoldReturn ?? 0,
    trades: result.trades ?? 0,
    avgProfit: result.avgProfit ?? 0,
    avgLoss: result.avgLoss ?? 0,
    maxConsecutiveWins: result.maxConsecutiveWins ?? 0,
    maxConsecutiveLosses: result.maxConsecutiveLosses ?? 0,
    initialCapital: result.initialCapital ?? 0,
    finalEquity: result.finalEquity ?? 0,
    symbols: result.symbols ?? [],
    perAssetStats: result.perAssetStats ?? null,
    equity: result.equity ?? [],
    benchmarkEquity: result.benchmark_equity ?? result.benchmarkEquity ?? [],
    dates: result.dates ?? [],
    warnings: result.warnings ?? [],
    executionTime: result.executionTime ?? 0,
    topSymbols: result.topSymbols ?? [],
  };
}

async function upsertStrategyForResult(strategyId: string, body: any) {
  const canonicalDsl = body?.canonical_strategy_dsl ?? body?.canonicalStrategyDsl;
  if (!canonicalDsl) return;

  const settingsObject =
    typeof canonicalDsl === "string" ? JSON.parse(canonicalDsl) : canonicalDsl;
  const settingsPayload = JSON.stringify({
    ...settingsObject,
    id: strategyId,
  });

  await prisma.strategy.upsert({
    where: { id: strategyId },
    update: {
      settings: settingsPayload,
    },
    create: {
      id: strategyId,
      name: `전략 ${strategyId.slice(0, 8)}`,
      description: null,
      settings: settingsPayload,
      strategyType: "기타",
    },
  });
}

export async function findCachedResult(cacheKey: string) {
  const existing = await prisma.backtestHistory.findFirst({
    where: {
      OR: [
        { strategyId: cacheKey },
        { cacheKey },
      ],
    },
    orderBy: { createdAt: "desc" },
  });
  if (!existing?.result) return null;

  await prisma.backtestHistory.update({
    where: { id: existing.id },
    data: { hitCount: { increment: 1 } },
  });

  const result = JSON.parse(existing.result);
  const metrics = existing.metrics ? JSON.parse(existing.metrics) : {};

  return {
    ...result,
    strategy_id: existing.strategyId ?? result.strategy_id ?? cacheKey,
    strategyId: existing.strategyId ?? result.strategyId ?? cacheKey,
    fromCache: true,
    cacheKey: existing.strategyId ?? existing.cacheKey ?? cacheKey,
    cachedAt: existing.createdAt,
    aiSummary: metrics.aiSummary ?? null,
    aiScore: metrics.aiScore ?? null,
    aiStrengths: metrics.aiStrengths ?? null,
    aiRisks: metrics.aiRisks ?? null,
  };
}

export async function saveCachedResult(
  cacheKey: string,
  body: any,
  result: any
) {
  try {
    const strategyId = resolveStrategyId({
      ...body,
      strategy_id: body?.strategy_id ?? result?.strategy_id ?? result?.strategyId,
    }) ?? cacheKey;
    const metrics = buildBacktestMetrics(result);
    const summary = buildBacktestSummary(result);

    await upsertStrategyForResult(strategyId, body);

    const existingBacktestResult = await prisma.backtestResult.findFirst({
      where: { strategyId },
      orderBy: { createdAt: "desc" },
    });

    if (existingBacktestResult) {
      await prisma.backtestResult.update({
        where: { id: existingBacktestResult.id },
        data: {
          summary: JSON.stringify(summary),
          trades: JSON.stringify(result.tradesList ?? []),
        },
      });
    } else {
      await prisma.backtestResult.create({
        data: {
          strategyId,
          summary: JSON.stringify(summary),
          trades: JSON.stringify(result.tradesList ?? []),
        },
      });
    }

    const existingHistory = await prisma.backtestHistory.findFirst({
      where: {
        OR: [
          { strategyId },
          { cacheKey },
        ],
      },
      orderBy: { createdAt: "desc" },
    });

    const historyData = {
      strategyId,
      strategyName: body?.strategy_name ?? `전략 ${strategyId.slice(0, 8)}`,
      universe: body?.universe_id ?? (body.symbols ?? []).slice(0, 3).join(","),
      conditions: JSON.stringify({ entry: body.entry, exit: body.exit }),
      metrics: JSON.stringify(metrics),
      result: JSON.stringify({
        ...result,
        strategy_id: strategyId,
      }),
      cacheKey: strategyId,
      isVisible: false,
    };

    if (existingHistory) {
      await prisma.backtestHistory.update({
        where: { id: existingHistory.id },
        data: historyData,
      });
      return;
    }

    await prisma.backtestHistory.create({
      data: historyData,
    });
  } catch (err) {
    console.error("[BacktestHistory] 자동 저장 실패:", err);
  }
}
