import { createHash } from "crypto";
import { prisma } from "@/lib/prisma";
import { pickExecutedRequest } from "@/lib/server/backtestCache";
import { exampleRegistry, type ExampleStrategy } from "./examples";

// 전략 시뮬레이션(docs/development/strategy-simulation.md §3.1) — 대상(예시 전략 등록부)과 공개 응답 허용 목록의 단일 정의.
// 목록·상세·실행·결과 저장의 모든 지점이 등록부로 대상 여부를 다시 확인한다.

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

/** 공개 응답에 싣는 전략 조건 — 허용 목록. 전략 ID·종목 코드 전체 목록(symbols)은 싣지 않는다. */
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
  assumptions: ExampleStrategy["assumptions"];
  row: {
    id: string; snapshotHash: string; dataAsOf: string | null; engineVersion: string | null;
    status: string; reason: string | null; result: string | null; computedAt: Date | null;
    refreshLeaseUntil: Date | null; lastAttemptAt: Date | null; lastError: string | null;
  };
};

const toItem = (example: ExampleStrategy, row: PublicStrategyRow["row"]): PublicStrategyRow => ({
  name: example.title, description: example.prompt, settings: example.settings, assumptions: example.assumptions, row,
});

/** 결과 행이 없는 예시는 pending 행을 만든 뒤, 예시 키별 결과 행을 돌려준다. */
async function ensureRows(examples: ExampleStrategy[]): Promise<Map<string, PublicStrategyRow["row"]>> {
  const ids = examples.map((e) => e.key);
  const found = await prisma.exampleSimulationResult.findMany({ where: { id: { in: ids } }, select: RESULT_ROW_SELECT });
  const rows = new Map(found.map((r) => [r.id, r]));
  const missing = examples.filter((e) => !rows.has(e.key));
  if (missing.length > 0) {
    await prisma.exampleSimulationResult.createMany({
      data: missing.map((e) => ({ id: e.key, snapshotHash: snapshotHash(snapshotFromSettings(e.settings)) })),
      skipDuplicates: true,
    });
    const made = await prisma.exampleSimulationResult.findMany({
      where: { id: { in: missing.map((e) => e.key) } },
      select: RESULT_ROW_SELECT,
    });
    for (const r of made) rows.set(r.id, r);
  }
  return rows;
}

/** publicId(예시 키)로 예시 전략과 원본 결과 행을 읽는다. 등록부에 없으면 null. */
export async function findPublicStrategy(publicId: string): Promise<PublicStrategyRow | null> {
  const example = exampleRegistry().get(publicId);
  if (!example) return null;
  const row = (await ensureRows([example])).get(example.key);
  return row ? toItem(example, row) : null;
}

/** 목록에 올릴 수 없는 예시: 현재 스냅샷으로 이미 '시뮬레이션 불가'로 판정된 예시. */
function isUnsimulatable(example: ExampleStrategy, row: PublicStrategyRow["row"] | undefined): boolean {
  const snapshot = snapshotFromSettings(example.settings);
  if (!snapshot) return true;
  return !!row && row.status === "unavailable" && row.snapshotHash === snapshotHash(snapshot);
}

/** 예시 이름순 한 페이지. 시뮬레이션할 수 없는 예시는 목록에서 뺀다. 다음 페이지는 21번째 항목으로 판단. */
export async function listPublicStrategies(
  { q, page }: { q?: string; page: number }
): Promise<{ items: PublicStrategyRow[]; hasNext: boolean }> {
  const needle = q?.toLocaleLowerCase("ko");
  const examples = [...exampleRegistry().values()]
    .filter((e) => !needle || e.title.toLocaleLowerCase("ko").includes(needle))
    .sort((a, b) => a.title.localeCompare(b.title, "ko") || (a.key < b.key ? -1 : 1));
  const rows = await ensureRows(examples);
  const eligible = examples.filter((e) => !isUnsimulatable(e, rows.get(e.key)));
  const skip = (Math.max(1, page) - 1) * PAGE_SIZE;
  const items = eligible.slice(skip, skip + PAGE_SIZE).flatMap((e) => {
    const row = rows.get(e.key);
    return row ? [toItem(e, row)] : [];
  });
  return { items, hasNext: eligible.length > skip + PAGE_SIZE };
}
