import compiled from "./__fixtures__/compiled.json";
import metaJson from "./__fixtures__/meta.json";
import type { ParsedSummary } from "@/lib/strategy-summary";
import type { EngineRequestLike, GraphMeta, StrategyGraphInput } from "./types";

// Fixtures are real outputs of backend ParsedStrategy -> to_backtest_request (no LLM, no mock
// schema), plus a trimmed real slice of the public indicator metadata.

type CompiledCase = { parsed: ParsedSummary; request: EngineRequestLike };
const cases = compiled as unknown as Record<string, CompiledCase>;

export const META = metaJson as unknown as GraphMeta;
export type FixtureName = keyof typeof compiled;

export function confirmedInput(name: FixtureName, ref = `confirmed:test#${String(name)}`): StrategyGraphInput {
  const c = cases[name as string];
  return { origin: "confirmed", schema: "parsed+request", sourceRef: ref, parsed: c.parsed, request: c.request, notices: [] };
}

/** The request as persisted in BacktestHistory.result.executedRequest. */
export function executedInput(name: FixtureName, ref = `history:test#${String(name)}`): StrategyGraphInput {
  const c = cases[name as string];
  const keys = ["symbols", "universe_id", "backtest_mode", "target_stocks", "sector", "etf_theme", "listing_from", "listing_to", "entry", "exit", "risk", "period", "startDate", "endDate", "options"];
  const picked: Record<string, unknown> = {};
  for (const k of keys) if ((c.request as Record<string, unknown>)[k] !== undefined) picked[k] = (c.request as Record<string, unknown>)[k];
  return { origin: "executed", schema: "request", sourceRef: ref, request: picked as EngineRequestLike };
}
