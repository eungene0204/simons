import { prisma } from "@/lib/prisma";
import { fetchBackend } from "@/lib/server/backend";
import {
  findPublicStrategy,
  snapshotFromSettings,
  snapshotHash,
  type PublicStrategyRow,
} from "./access";

// 예시 원본 결과(§3.8) — 조회는 저장된 결과만 읽고, 낡았으면 백그라운드 갱신을 예약할 뿐 기다리지 않는다.

export type Baseline = {
  today: string; requestedStart: string; requestedEnd: string; endDate: string;
  dataAsOf: string; stale: boolean; engineVersion: string;
};
export type OriginalView = Record<string, unknown> & {
  status: "pending" | "refreshing" | "ready" | "no_trades" | "unavailable" | "failed";
};

const BASELINE_TTL_MS = 5 * 60_000;
const LEASE_MS = 4 * 60_000;       // 한 실행의 최대 점유(FastAPI 제한 180초 + 여유)
const BUSY_RETRY_MS = 60_000;
const FAILURE_BACKOFF_MS = 15 * 60_000;
const DONE = ["ready", "no_trades", "unavailable"];

let baselineCache: { value: Baseline; at: number } | null = null;

export function resetBaselineCache() {
  baselineCache = null;
}

/** 현재 데이터 기준일·엔진 버전. 백엔드가 응답하지 못하면 마지막으로 안 값, 없으면 null. */
export async function getBaseline(): Promise<Baseline | null> {
  if (baselineCache && Date.now() - baselineCache.at < BASELINE_TTL_MS) return baselineCache.value;
  try {
    const res = await fetchBackend("/internal/public-simulation/baseline", { cache: "no-store", timeoutMs: 10_000 });
    if (res.ok) {
      baselineCache = { value: (await res.json()) as Baseline, at: Date.now() };
    }
  } catch {
    // 아래에서 마지막 값으로 대체한다.
  }
  return baselineCache?.value ?? null;
}

function parseStored(result: string | null): Record<string, unknown> | null {
  try {
    const parsed = result ? JSON.parse(result) : null;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

/** 확정 데이터·엔진 버전·'오늘' 기준 3년 창 중 하나라도 바뀌었으면 낡은 결과다. 불가 판정(unavailable)은 창과 무관. */
export function isStale(row: PublicStrategyRow["row"], stored: Record<string, unknown>, baseline: Baseline | null): boolean {
  if (!baseline || row.status === "unavailable") return !!baseline && row.engineVersion !== baseline.engineVersion;
  const window = stored.window as { requestedStart?: string } | undefined;
  return (
    row.dataAsOf !== baseline.dataAsOf ||
    row.engineVersion !== baseline.engineVersion ||
    window?.requestedStart !== baseline.requestedStart
  );
}

/** 화면에 보일 원본 상태. 스냅샷이 바뀐 옛 결과는 새 조건과 나란히 보이지 않게 pending으로 둔다. */
export function presentOriginal(item: PublicStrategyRow, baseline: Baseline | null): OriginalView {
  const { row } = item;
  const hash = snapshotHash(snapshotFromSettings(item.settings));
  const stored = parseStored(row.result);
  if (row.snapshotHash !== hash || !stored || !DONE.includes(row.status)) {
    if (row.status === "failed" && row.snapshotHash === hash) {
      return { status: "failed", reason: row.reason ?? row.lastError ?? "ENGINE_ERROR" };
    }
    return { status: "pending" };
  }
  return { ...stored, status: isStale(row, stored, baseline) ? "refreshing" : (row.status as OriginalView["status"]) };
}

function needsRefresh(item: PublicStrategyRow, baseline: Baseline | null, now: number): boolean {
  const { row } = item;
  if (row.refreshLeaseUntil && row.refreshLeaseUntil.getTime() > now) return false;
  const hash = snapshotHash(snapshotFromSettings(item.settings));
  const stored = parseStored(row.result);
  if (row.snapshotHash !== hash || !stored || !DONE.includes(row.status)) return true;
  return isStale(row, stored, baseline);
}

const inFlight = new Set<string>();
let chain: Promise<void> = Promise.resolve();

/** 갱신을 순차 큐(동시 1건)에 넣는다. 같은 publicId는 한 번만. */
export function scheduleRefresh(publicId: string): void {
  if (inFlight.has(publicId)) return;
  inFlight.add(publicId);
  chain = chain
    .then(() => refreshOne(publicId))
    .catch((error) => console.error("[public-simulation] refresh failed", error))
    .finally(() => inFlight.delete(publicId));
}

export function whenRefreshesSettled(): Promise<void> {
  return chain;
}

/** 조회 시 호출 — 낡았거나 없으면 갱신을 예약한다(리스가 살아 있으면 건너뜀). */
export function ensureFresh(item: PublicStrategyRow, baseline: Baseline | null): void {
  if (needsRefresh(item, baseline, Date.now())) scheduleRefresh(item.row.id);
}

export async function refreshOne(publicId: string): Promise<void> {
  const now = new Date();
  // 리스를 조건부 갱신(CAS)으로 잡은 프로세스 하나만 실행한다.
  const leased = await prisma.exampleSimulationResult.updateMany({
    where: {
      id: publicId,
      OR: [{ refreshLeaseUntil: null }, { refreshLeaseUntil: { lt: now } }],
    },
    data: { refreshLeaseUntil: new Date(now.getTime() + LEASE_MS), lastAttemptAt: now },
  });
  if (leased.count !== 1) return;

  const item = await findPublicStrategy(publicId);
  if (!item) return;
  const snapshot = snapshotFromSettings(item.settings);
  const hash = snapshotHash(snapshot);
  const baseline = await getBaseline();

  // 예시 실행 설정은 배포 단위로 고정이라 실행 도중 바뀌지 않는다 — 결과 행만 갱신한다.
  const write = (data: Record<string, unknown>) =>
    prisma.exampleSimulationResult.updateMany({
      where: { id: publicId },
      data: { lastAttemptAt: new Date(), ...data },
    });
  const fail = (code: string, backoffMs: number) =>
    write({
      lastError: code,
      refreshLeaseUntil: new Date(Date.now() + backoffMs),
      // 이전 결과가 있으면 그대로 두고(갱신 실패로 표시), 없을 때만 failed로 둔다.
      ...(item.row.result && item.row.snapshotHash === hash ? {} : { status: "failed", reason: code, result: null }),
    });

  if (!snapshot) {
    await write({
      snapshotHash: hash, status: "unavailable", reason: "NO_EXECUTABLE_SNAPSHOT", lastError: null,
      result: JSON.stringify({ status: "unavailable", reason: "NO_EXECUTABLE_SNAPSHOT", detail: [] }),
      dataAsOf: baseline?.dataAsOf ?? null, engineVersion: baseline?.engineVersion ?? null,
      computedAt: new Date(), refreshLeaseUntil: null,
    });
    return;
  }

  let res: Response;
  try {
    res = await fetchBackend("/internal/public-simulation/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot }),
      cache: "no-store",
      timeoutMs: 195_000,
    });
  } catch {
    await fail("BACKEND_UNREACHABLE", FAILURE_BACKOFF_MS);
    return;
  }
  const body = await res.json().catch(() => null);
  if (res.status === 429) {
    await fail("BUSY", BUSY_RETRY_MS);
    return;
  }
  if (!res.ok || !body || typeof body.status !== "string") {
    await fail(typeof body?.code === "string" ? body.code : "ENGINE_ERROR", FAILURE_BACKOFF_MS);
    return;
  }

  const { appliedOverrides: _a, ...stored } = body;
  await write({
    snapshotHash: hash,
    status: body.status,
    reason: body.status === "unavailable" ? String(body.reason ?? "") : null,
    result: JSON.stringify(stored),
    dataAsOf: body.dataAsOf ?? baseline?.dataAsOf ?? null,
    engineVersion: body.engineVersion ?? baseline?.engineVersion ?? null,
    computedAt: body.computedAt ? new Date(body.computedAt) : new Date(),
    lastError: null,
    refreshLeaseUntil: null,
  });
}
