import type { GraphMeta } from "./types";

// Public indicator metadata for the strategy graph. Only the success result is cached, so a
// failed lookup can be retried without re-running anything else (no confirm call, no LLM).
let cached: Promise<GraphMeta> | null = null;

export const GRAPH_META_URL = "/api/strategy/graph-meta";

function isGraphMeta(value: unknown): value is GraphMeta {
  const v = value as GraphMeta | null;
  return (
    !!v &&
    typeof v === "object" &&
    typeof v.version === "string" &&
    !!v.indicators &&
    !!v.bindings &&
    Array.isArray(v.classes) &&
    Array.isArray(v.concepts)
  );
}

async function request(): Promise<GraphMeta> {
  const res = await fetch(GRAPH_META_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`graph-meta ${res.status}`);
  const body = await res.json();
  if (!isGraphMeta(body)) throw new Error("graph-meta malformed");
  return body;
}

export function loadGraphMeta(): Promise<GraphMeta> {
  if (!cached) {
    const pending = request();
    cached = pending;
    pending.catch(() => {
      if (cached === pending) cached = null;
    });
  }
  return cached;
}

export function resetGraphMetaForTests(): void {
  cached = null;
}
