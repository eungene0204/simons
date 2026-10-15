import type { ParsedSummary } from "@/lib/strategy-summary";

// ── Public indicator metadata (mirror of GET /api/strategy/graph-meta) ──────────────────────

export type SupportStatus = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "UNSUPPORTED";

export interface IndicatorMeta {
  name: string;
  nameEn: string;
  category: string;
  supported: SupportStatus;
  dataPending: boolean;
  partialData: boolean;
  unit: string | null;
  operators: string[];
  parameters: Record<string, { minimum: number | null; maximum: number | null; required: boolean }>;
  classId: string | null;
  alternatives: string[];
}

export interface GraphMeta {
  version: string;
  indicators: Record<string, IndicatorMeta>;
  /** "kind:field" (engine binding) -> canonical indicator id */
  bindings: Record<string, string>;
  classes: Array<{ id: string; name: string; parent: string | null; description: string }>;
  concepts: Array<{ id: string; name: string; supported: string; expandsTo: string | null; requires: string[] }>;
}

// ── Snapshot input ───────────────────────────────────────────────────────────────────────────

export type GraphOrigin = "draft" | "confirmed" | "executed" | "none";
export type GraphSchema = "parsed+request" | "parsed" | "request" | "none";

export interface EngineCondition {
  type?: string;
  id?: string;
  params?: Record<string, unknown>;
  weight?: number;
}

/** Loose view of the engine request (BacktestRequest dict). Only fields the graph reads. */
export interface EngineRequestLike {
  symbols?: string[];
  universe_id?: string | null;
  backtest_mode?: string | null;
  target_stocks?: Array<{ symbol: string; name?: string }> | null;
  sector?: string | string[] | null;
  etf_theme?: string | null;
  us_industry?: string | null;
  exclude_sectors?: string[] | null;
  listing_from?: string | null;
  listing_to?: string | null;
  entry?: { conditions?: EngineCondition[]; logic?: string | null } | null;
  exit?: { conditions?: EngineCondition[]; logic?: string | null } | null;
  risk?: Record<string, unknown> | null;
  period?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  options?: Record<string, unknown> | null;
}

/** Graph-only input wrapper. Does not change any existing strategy contract. */
export interface StrategyGraphInput {
  origin: GraphOrigin;
  schema: GraphSchema;
  /** Stable reference of the snapshot (e.g. "confirmed:<messageId>#1", "history:<id>"). */
  sourceRef: string;
  parsed?: ParsedSummary | null;
  request?: EngineRequestLike | null;
  /** Notices preserved in the same turn only (never re-derived). */
  notices?: string[];
  /**
   * Drafts only: the fields the user actually stated (backend provenance). Compiled requests carry
   * defaults for period, capital, holdings and rebalancing, so an unstated default must not be
   * drawn as if the user had said it.
   */
  explicitFields?: string[];
}

// ── Graph model ──────────────────────────────────────────────────────────────────────────────

export type SectionKey =
  | "universe"
  | "filters"
  | "ranking"
  | "entry"
  | "exit"
  | "allocation"
  | "rebalance"
  | "risk";

export type NodeKind =
  | "strategy"
  | "section"
  | "group"
  | "condition"
  | "risk"
  | "setting"
  | "indicator"
  | "class";

/**
 * ok: fully specified. pending: a value is required but missing. not_applicable: the
 * threshold is not needed (e.g. crossovers). unsupported / partial / data_pending: registry
 * support state. check_needed: meaning cannot be confirmed from the snapshot.
 */
export type NodeStatus =
  | "ok"
  | "pending"
  | "not_applicable"
  | "unsupported"
  | "partial"
  | "data_pending"
  | "check_needed";

export type EdgeKind = "has_section" | "contains" | "combined_by" | "uses_indicator" | "is_a";

/** Strategy-instance relations vs. ontology concept relations. */
export function edgeLayer(kind: EdgeKind): "strategy" | "ontology" {
  return kind === "is_a" ? "ontology" : "strategy";
}

export interface DetailRow {
  label: string;
  value: string;
}

export interface GraphNodeDetails {
  /** Role inside the strategy, e.g. "매수 규칙". */
  role: string | null;
  /** Human-readable condition expression. */
  expression: string | null;
  rows: DetailRow[];
  /** Registry support state of the used indicator (null if unknown). */
  support: SupportStatus | null;
  /** Classification path (root first) from the ontology metadata. */
  classPath: string[];
  /** Short explanation of non-ok statuses. */
  statusNote: string | null;
  /** Per-condition source quote. Always null today: no snapshot schema stores one. */
  quote: string | null;
  /** Where the displayed values came from. */
  valueSource: "request" | "parsed" | "metadata" | "engine_default" | null;
}

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  status: NodeStatus;
  /** Path inside the snapshot (a reference within this snapshot, not a permanent condition id). */
  sourceRef: string;
  section: SectionKey | null;
  details: GraphNodeDetails;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label: string;
}

export interface StrategyGraph {
  origin: GraphOrigin;
  schema: GraphSchema;
  sourceRef: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Interpretation notices kept with the same snapshot. */
  notices: string[];
  /** Things the transform could not confirm. */
  notes: string[];
  /** ok: indicator metadata applied; unavailable: structure only. */
  metaState: "ok" | "unavailable";
}
