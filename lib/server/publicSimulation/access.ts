import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";
import { pickExecutedRequest } from "@/lib/server/backtestCache";

// 전략 시뮬레이션(docs/development/strategy-simulation.md §3.1) — 공개 조건과 공개 응답 허용 목록의 단일 정의.
// 목록·상세·실행·캐시 응답·결과 저장의 모든 지점이 이 조건으로 DB를 다시 확인한다.
export const PUBLIC_STRATEGY_WHERE = { isPublic: true, isSaved: true, deletedAt: null } as const;

export type Snapshot = Record<string, unknown>;

export class NotPublicError extends Error {
  constructor() {
    super("STRATEGY_NOT_PUBLIC");
  }
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${stableStringify(v)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function sha256(value: unknown): string {
  return createHash("sha256").update(stableStringify(value)).digest("hex");
}

function parseSettings(settings: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(settings);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

/** 저장 설정에서 엔진 요청형 스냅샷만 고른다. 메타만 저장된 전략은 null(시뮬레이션 불가). */
export function snapshotFromSettings(settings: string): Snapshot | null {
  const parsed = parseSettings(settings);
  return parsed ? (pickExecutedRequest(parsed) as Snapshot | null) : null;
}

export function snapshotHash(snapshot: Snapshot | null): string {
  return sha256(snapshot ?? {});
}

const pickTargetStocks = (value: unknown) =>
  Array.isArray(value)
    ? value
        .filter((s): s is Record<string, unknown> => !!s && typeof s === "object")
        .map((s) => ({ symbol: s.symbol ?? s.code ?? null, name: s.name ?? null }))
    : undefined;

/** 공개 응답에 싣는 전략 조건 — 허용 목록. 전략 ID·소유자·종목 코드 전체 목록(symbols)은 싣지 않는다. */
export function publicStrategyFields(settings: string): Record<string, unknown> {
  const parsed = parseSettings(settings) ?? {};
  const out: Record<string, unknown> = {};
  for (const key of ["entry", "exit", "risk", "universe_id", "sector", "etf_theme", "exclude_sectors", "listing_from", "listing_to", "backtest_mode"]) {
    if (parsed[key] !== undefined) out[key] = parsed[key];
  }
  const targets = pickTargetStocks(parsed.target_stocks);
  if (targets) out.target_stocks = targets;
  return out;
}

export const RESULT_ROW_SELECT = {
  id: true,
  strategyId: true,
  snapshotHash: true,
  dataAsOf: true,
  engineVersion: true,
  status: true,
  reason: true,
  result: true,
  computedAt: true,
  refreshLeaseUntil: true,
  lastAttemptAt: true,
  lastError: true,
} as const;

const PAGE_SIZE = 20;

export type PublicStrategyRow = {
  name: string;
  description: string | null;
  settings: string;
  row: {
    id: string; strategyId: string; snapshotHash: string; dataAsOf: string | null; engineVersion: string | null;
    status: string; reason: string | null; result: string | null; computedAt: Date | null;
    refreshLeaseUntil: Date | null; lastAttemptAt: Date | null; lastError: string | null;
  };
};

/** publicId로 공개 전략과 원본 결과 행을 읽는다. 비공개·삭제·없음은 모두 null. */
export async function findPublicStrategy(publicId: string): Promise<PublicStrategyRow | null> {
  const found = await prisma.publicSimulationResult.findFirst({
    where: { id: publicId, Strategy: { is: { ...PUBLIC_STRATEGY_WHERE } } },
    select: { ...RESULT_ROW_SELECT, Strategy: { select: { name: true, description: true, settings: true } } },
  });
  if (!found) return null;
  const { Strategy, ...row } = found;
  return { name: Strategy.name, description: Strategy.description, settings: Strategy.settings, row };
}

const SCAN_BATCH = 200;

/** 목록에 올릴 수 없는 전략: 실행 가능한 스냅샷이 없거나, 현재 스냅샷으로 이미 '시뮬레이션 불가'로 판정된 전략. */
function isUnsimulatable(r: { settings: string; PublicSimulationResult: { status: string; snapshotHash: string } | null }): boolean {
  const snapshot = snapshotFromSettings(r.settings);
  if (!snapshot) return true;
  const stored = r.PublicSimulationResult;
  return !!stored && stored.status === "unavailable" && stored.snapshotHash === snapshotHash(snapshot);
}

/**
 * 전략명순(동명은 내부 ID순) 한 페이지. 시뮬레이션할 수 없는 전략은 목록에서 뺀다.
 * 실행 가능 여부는 저장 설정을 읽어야 알 수 있어 DB 조건으로 거를 수 없다 — 배치로 훑어 거른 뒤 쪽을 자른다.
 * 결과 행이 없는 공개 전략은 pending 행을 만든다. 다음 페이지는 21번째 행으로 판단.
 */
export async function listPublicStrategies(
  { q, page }: { q?: string; page: number }
): Promise<{ items: PublicStrategyRow[]; hasNext: boolean }> {
  const where = { ...PUBLIC_STRATEGY_WHERE, ...(q ? { name: { contains: q, mode: "insensitive" as const } } : {}) };
  const skip = (Math.max(1, page) - 1) * PAGE_SIZE;
  const wanted = skip + PAGE_SIZE + 1;
  const eligible: Awaited<ReturnType<typeof fetchBatch>> = [];
  for (let offset = 0; eligible.length < wanted; offset += SCAN_BATCH) {
    const batch = await fetchBatch(where, offset);
    eligible.push(...batch.filter((r) => !isUnsimulatable(r)));
    if (batch.length < SCAN_BATCH) break;
  }
  const hasNext = eligible.length > skip + PAGE_SIZE;
  const pageRows = eligible.slice(skip, skip + PAGE_SIZE);

  const missing = pageRows.filter((r) => !r.PublicSimulationResult);
  let created: Record<string, PublicStrategyRow["row"]> = {};
  if (missing.length > 0) {
    await prisma.publicSimulationResult.createMany({
      data: missing.map((r) => ({ strategyId: r.id, snapshotHash: snapshotHash(snapshotFromSettings(r.settings)) })),
      skipDuplicates: true,
    });
    const made = await prisma.publicSimulationResult.findMany({
      where: { strategyId: { in: missing.map((r) => r.id) } },
      select: RESULT_ROW_SELECT,
    });
    created = Object.fromEntries(made.map((m) => [m.strategyId, m]));
  }

  const items = pageRows.flatMap((r) => {
    const row = r.PublicSimulationResult ?? created[r.id];
    return row ? [{ name: r.name, description: r.description, settings: r.settings, row }] : [];
  });
  return { items, hasNext };
}

function fetchBatch(where: Record<string, unknown>, offset: number) {
  return prisma.strategy.findMany({
    where,
    orderBy: [{ name: "asc" }, { id: "asc" }],
    skip: offset,
    take: SCAN_BATCH,
    select: { id: true, name: true, description: true, settings: true, PublicSimulationResult: { select: RESULT_ROW_SELECT } },
  });
}
