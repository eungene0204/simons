import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";

/** 객체/배열을 재귀적으로 키 정렬해 JSON.stringify 결과를 결정적으로 만든다 */
function sortDeep(val: any): any {
  if (Array.isArray(val)) return val.map(sortDeep);
  if (val !== null && typeof val === "object") {
    return Object.fromEntries(
      Object.keys(val)
        .sort()
        .map((k) => [k, sortDeep(val[k])])
    );
  }
  return val;
}

export function computeCacheKey(body: any): string {
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
  return createHash("sha256")
    .update(JSON.stringify(normalized))
    .digest("hex");
}

export async function findCachedResult(cacheKey: string) {
  const existing = await prisma.backtestHistory.findUnique({
    where: { cacheKey },
  });
  if (!existing?.result) return null;

  await prisma.backtestHistory.update({
    where: { cacheKey },
    data: { hitCount: { increment: 1 } },
  });

  const result = JSON.parse(existing.result);
  const metrics = existing.metrics ? JSON.parse(existing.metrics) : {};

  return {
    ...result,
    fromCache: true,
    cacheKey,
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
    const metrics = {
      totalReturn: result.totalReturn ?? 0,
      cagr: result.cagr ?? 0,
      mdd: result.maxDrawdown ?? 0,
      winRate: result.winRate ?? 0,
      profitFactor: result.profitFactor ?? 0,
      buyHold: result.buyAndHoldReturn ?? 0,
      trades: result.trades ?? 0,
      executionTime: result.executionTime ?? 0,
    };

    await prisma.backtestHistory.create({
      data: {
        strategyName: "",
        universe: (body.symbols ?? []).slice(0, 3).join(","),
        conditions: JSON.stringify({ entry: body.entry, exit: body.exit }),
        metrics: JSON.stringify(metrics),
        result: JSON.stringify(result),
        cacheKey,
        isVisible: false,
      },
    });
  } catch (err) {
    console.error("[BacktestHistory] 자동 저장 실패:", err);
  }
}
