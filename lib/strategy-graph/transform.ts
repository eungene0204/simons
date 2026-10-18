import { t } from "@/lib/i18n";
import { GraphBuilder } from "./graphBuilder";
import {
  buildAllocation,
  buildEntry,
  buildExit,
  buildFilters,
  buildRanking,
  buildRebalance,
  buildRisk,
  buildUniverse,
  type SectionCtx,
} from "./transformSections";
import type { GraphMeta, StrategyGraph, StrategyGraphInput } from "./types";

// Pure snapshot -> graph transform. It reads the input and metadata only (never mutates them),
// uses no randomness or clock, and derives every id from the path inside the snapshot, so the
// same input always yields the same graph. No network, no LLM.

export function buildStrategyGraph(input: StrategyGraphInput, meta: GraphMeta | null): StrategyGraph {
  const b = new GraphBuilder(meta);
  const notes: string[] = [];
  const base = {
    origin: input.origin,
    schema: input.schema,
    sourceRef: input.sourceRef,
    notices: input.notices ? [...input.notices] : [],
    metaState: meta ? ("ok" as const) : ("unavailable" as const),
  };

  const req = input.request;
  if (input.origin === "none" || !req) {
    return { ...base, nodes: [], edges: [], notes };
  }
  if (input.schema === "parsed") {
    notes.push(t("컴파일되지 않은 초안은 실행 요청이 없어 구조를 표시할 수 없습니다."));
    return { ...base, nodes: [], edges: [], notes };
  }

  const rootLabel = t(input.origin === "confirmed" ? "확정된 전략" : input.origin === "draft" ? "현재까지 이해한 전략" : "실행된 전략");
  b.node("strategy", "strategy", rootLabel, "ok", "snapshot", null, { role: rootLabel });

  const ctx: SectionCtx = {
    b,
    req,
    parsed: input.parsed ?? null,
    stated: input.origin === "draft" && input.explicitFields ? new Set(input.explicitFields) : null,
  };
  buildUniverse(ctx);
  buildFilters(ctx);
  buildRanking(ctx);
  buildEntry(ctx);
  buildExit(ctx);
  buildAllocation(ctx);
  buildRebalance(ctx);
  buildRisk(ctx);

  if (!meta) notes.push(t("지표 정보를 불러오지 못해 이름과 분류를 표시할 수 없습니다."));
  if (input.origin === "executed") {
    notes.push(t("실행에 쓰인 요청만 저장되어 있어 미정 항목과 조건별 원문 인용은 확인할 수 없습니다."));
  }
  // A combination the snapshot does not state (engine default) must be disclosed on the graph itself:
  // a folded section header would otherwise read like a value the user chose.
  for (const n of b.nodes()) {
    if (n.kind === "group" && n.details.valueSource === "engine_default" && n.details.statusNote) notes.push(n.details.statusNote);
  }
  return { ...base, nodes: b.nodes(), edges: b.edges(), notes };
}

/** True when the snapshot produced no strategy sections (e.g. an empty strategy). */
export function isEmptyGraph(graph: StrategyGraph): boolean {
  return !graph.nodes.some((n) => n.kind === "section");
}
