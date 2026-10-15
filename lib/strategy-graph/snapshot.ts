import type { ParsedSummary } from "@/lib/strategy-summary";
import type { EngineRequestLike, StrategyGraphInput } from "./types";

// Snapshot selection rules. Each helper accepts ONLY the data that belongs to its entry point,
// so a caller cannot silently substitute the current (mutable) strategy for a frozen one.

function isEngineRequest(value: unknown): value is EngineRequestLike {
  const v = value as EngineRequestLike | null;
  return !!v && typeof v === "object" && !!v.entry && !!v.exit && !!v.risk;
}

export function emptyInput(origin: "executed" | "confirmed" | "draft", sourceRef: string): StrategyGraphInput {
  return { origin: "none", schema: "none", sourceRef: `${origin}:${sourceRef}` };
}

/** Confirmed strategy: the parsed + backtest_request pair returned by the same confirm response. */
export function fromConfirmed(args: {
  sourceRef: string;
  parsed: ParsedSummary | null | undefined;
  request: unknown;
  notices?: string[] | null;
}): StrategyGraphInput {
  if (!args.parsed || !isEngineRequest(args.request)) return emptyInput("confirmed", args.sourceRef);
  return {
    origin: "confirmed",
    schema: "parsed+request",
    sourceRef: args.sourceRef,
    parsed: args.parsed,
    request: args.request,
    notices: args.notices ? [...args.notices] : [],
  };
}

/**
 * Draft of the current turn: the turn's parsed result with the engine request produced for the same
 * turn. Not confirmed — shown as "understood so far". Without both, there is no graph.
 */
export function fromDraft(args: {
  sourceRef: string;
  parsed: ParsedSummary | null | undefined;
  request: unknown;
  notices?: string[] | null;
  explicitFields?: readonly string[] | null;
}): StrategyGraphInput {
  if (!args.parsed || !isEngineRequest(args.request)) return emptyInput("draft", args.sourceRef);
  return {
    origin: "draft",
    schema: "parsed+request",
    sourceRef: args.sourceRef,
    parsed: args.parsed,
    request: args.request,
    notices: args.notices ? [...args.notices] : [],
    ...(args.explicitFields ? { explicitFields: [...args.explicitFields] } : {}),
  };
}

/** Executed strategy: the request that produced the result (never the current edit request). */
export function fromExecuted(args: { sourceRef: string; request: unknown }): StrategyGraphInput {
  if (!isEngineRequest(args.request)) return emptyInput("executed", args.sourceRef);
  return {
    origin: "executed",
    schema: "request",
    sourceRef: args.sourceRef,
    request: args.request,
  };
}

/**
 * Saved result: only result.executedRequest counts. The Strategy row `settings` is the CURRENT
 * strategy and may differ from what ran, so it is intentionally not an accepted argument.
 */
export function fromSavedHistory(args: {
  historyId: string;
  result: { executedRequest?: unknown } | null | undefined;
}): StrategyGraphInput {
  return fromExecuted({
    sourceRef: `history:${args.historyId}`,
    request: args.result?.executedRequest,
  });
}
