import { BoardError } from "@/lib/board/rules";
import { limit } from "@/lib/board/server";
import { fetchBackend } from "@/lib/server/backend";
import { NotPublicError, findPublicStrategy, sha256, snapshotFromSettings, snapshotHash } from "./access";
import { getBaseline, presentOriginal } from "./originals";

// 방문자 수정 시뮬레이션(§3.7~3.8) — 원본 설정·원본 결과 행은 읽기만 하고, 결과는 서버 메모리에만 잠시 둔다.

export class BaselineChangedError extends Error {
  // REFRESHING: 원본이 새 기준일·새 '오늘' 창으로 갱신 중 / CHANGED: 클라이언트가 가진 원본이 낡음
  constructor(public reason: "REFRESHING" | "CHANGED" = "CHANGED") {
    super("BASELINE_CHANGED");
  }
}
export class InvalidParameterError extends Error {
  constructor(public errors: unknown) {
    super("INVALID_PARAMETER");
  }
}
export class RateLimitedError extends Error {
  constructor(public retryAfterSeconds: number) {
    super("RATE_LIMITED");
  }
}
export class SimulationFailedError extends Error {
  constructor(public code: string, public status = 500, public retryAfterSeconds?: number) {
    super(code);
  }
}

export type Override = { path: string; value: number };

const CACHE_MAX = 500;
const CACHE_TTL_MS = 30 * 60_000;
const IDENTITY_LIMIT = 20;
const GLOBAL_LIMIT = 60;
const RATE_WINDOW_SECONDS = 600;

const cache = new Map<string, { at: number; value: Record<string, unknown> }>();
const inFlight = new Map<string, Promise<Record<string, unknown>>>();

export function resetModifiedCache() {
  cache.clear();
  inFlight.clear();
}

function cacheGet(key: string) {
  const hit = cache.get(key);
  if (!hit) return undefined;
  if (Date.now() - hit.at > CACHE_TTL_MS) {
    cache.delete(key);
    return undefined;
  }
  cache.delete(key); // LRU: 다시 넣어 최신으로 옮긴다
  cache.set(key, hit);
  return hit.value;
}

function cacheSet(key: string, value: Record<string, unknown>) {
  cache.set(key, { at: Date.now(), value });
  while (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value as string);
}

async function enforceRateLimit(identity: string) {
  try {
    await limit(`sim-run:${identity}`, IDENTITY_LIMIT, RATE_WINDOW_SECONDS);
    await limit("sim-run:all", GLOBAL_LIMIT, RATE_WINDOW_SECONDS);
  } catch (error) {
    if (error instanceof BoardError && error.status === 429) throw new RateLimitedError(60);
    throw error;
  }
}

async function callBackend(snapshot: unknown, overrides: Override[]): Promise<Record<string, unknown>> {
  let res: Response;
  try {
    res = await fetchBackend("/internal/public-simulation/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ snapshot, overrides }),
      cache: "no-store",
      timeoutMs: 195_000,
    });
  } catch {
    throw new SimulationFailedError("BACKEND_UNREACHABLE", 502);
  }
  const body = await res.json().catch(() => null);
  if (res.status === 400) throw new InvalidParameterError(body?.errors ?? []);
  if (res.status === 429) throw new SimulationFailedError("BUSY", 429, body?.retryAfterSeconds ?? 30);
  if (res.status === 504) throw new SimulationFailedError("TIMEOUT", 504);
  if (!res.ok || !body || typeof body.status !== "string") {
    throw new SimulationFailedError(typeof body?.code === "string" ? body.code : "ENGINE_ERROR", 500);
  }
  return body;
}

/**
 * 수정 시뮬레이션. 호출마다 공개 조건을 먼저 확인하므로 캐시 히트도 비공개 전환 뒤에는 나가지 않는다.
 * 같은 키의 진행 중 요청은 하나로 합친다.
 */
export async function runModified(input: {
  publicId: string; overrides: Override[]; baseSnapshotHash: string; dataAsOf: string; identity: string;
}): Promise<Record<string, unknown>> {
  const ensurePublic = async () => {
    const found = await findPublicStrategy(input.publicId);
    if (!found) throw new NotPublicError();
    return found;
  };
  const item = await ensurePublic();
  const snapshot = snapshotFromSettings(item.settings);
  if (!snapshot) throw new SimulationFailedError("NO_EXECUTABLE_SNAPSHOT", 422);

  const baseline = await getBaseline();
  if (!baseline) throw new SimulationFailedError("BASELINE_UNAVAILABLE", 503);
  const original = presentOriginal(item, baseline);
  // 원본과 수정본은 같은 창·같은 데이터여야 한다 — 원본이 낡은 동안(갱신 중)에는 수정 계산을 하지 않는다.
  if (original.status === "refreshing" || original.status === "pending") throw new BaselineChangedError("REFRESHING");
  if (
    !["ready", "no_trades"].includes(original.status) ||
    snapshotHash(snapshot) !== input.baseSnapshotHash ||
    input.dataAsOf !== item.row.dataAsOf
  ) {
    throw new BaselineChangedError("CHANGED");
  }

  // 모든 값이 원본과 같으면 계산하지 않고 저장된 원본 결과를 돌려준다.
  const params = (original.editableParams as { path: string; original: number }[] | undefined) ?? [];
  const changed = input.overrides.filter((o) => params.find((p) => p.path === o.path)?.original !== o.value);
  if (input.overrides.length > 0 && changed.length === 0) return { ...original, appliedOverrides: [] };

  const overrides = [...input.overrides].sort((a, b) => (a.path < b.path ? -1 : 1));
  const key = sha256({
    kind: "modified", snapshot: input.baseSnapshotHash, overrides, dataAsOf: baseline.dataAsOf,
    start: baseline.requestedStart, end: baseline.endDate, engineVersion: baseline.engineVersion,
  });
  const cached = cacheGet(key);
  if (cached) return cached;

  await enforceRateLimit(input.identity);

  let pending = inFlight.get(key);
  if (!pending) {
    pending = callBackend(snapshot, overrides).finally(() => inFlight.delete(key));
    inFlight.set(key, pending);
  }
  const result = await pending;
  // 계산 도중 비공개 전환·설정 변경이 있었다면 결과를 내보내지도 캐시하지도 않는다.
  const after = await ensurePublic();
  if (after.settings !== item.settings) throw new NotPublicError();
  cacheSet(key, result);
  return result;
}
