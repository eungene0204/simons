type CoachJsonPayload = Record<string, unknown>;

const COACH_CACHE_MAX = 200;

const jsonCache = new Map<string, CoachJsonPayload>();
const jsonInFlight = new Map<string, Promise<CoachJsonPayload>>();
const streamCache = new Map<string, string>();
const streamInFlight = new Map<string, Promise<string>>();

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(",")}]`;
  }

  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}

export async function coachCacheKey(body: unknown): Promise<string> {
  const data = new TextEncoder().encode(stableStringify(body));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function remember<K, V>(cache: Map<K, V>, key: K, value: V) {
  if (cache.has(key)) cache.delete(key);
  cache.set(key, value);
  if (cache.size > COACH_CACHE_MAX) {
    const oldestKey = cache.keys().next().value;
    if (oldestKey) cache.delete(oldestKey);
  }
}

export function getCachedCoachJson(key: string) {
  return jsonCache.get(key);
}

export function rememberCoachJson(key: string, payload: CoachJsonPayload) {
  remember(jsonCache, key, payload);
}

export function getCoachJsonInFlight(key: string) {
  return jsonInFlight.get(key);
}

export function setCoachJsonInFlight(key: string, pending: Promise<CoachJsonPayload>) {
  jsonInFlight.set(
    key,
    pending.finally(() => {
      jsonInFlight.delete(key);
    })
  );
  return jsonInFlight.get(key)!;
}

export function getCachedCoachStream(key: string) {
  return streamCache.get(key);
}

export function rememberCoachStream(key: string, payload: string) {
  remember(streamCache, key, payload);
}

export function getCoachStreamInFlight(key: string) {
  return streamInFlight.get(key);
}

export function setCoachStreamInFlight(key: string, pending: Promise<string>) {
  streamInFlight.set(
    key,
    pending.finally(() => {
      streamInFlight.delete(key);
    })
  );
  return streamInFlight.get(key)!;
}

export function __resetCoachCacheForTests() {
  jsonCache.clear();
  jsonInFlight.clear();
  streamCache.clear();
  streamInFlight.clear();
}
