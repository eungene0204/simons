import { getLanguage, t } from "@/lib/i18n";
import type {
  DetailRow,
  EdgeKind,
  GraphEdge,
  GraphMeta,
  GraphNode,
  GraphNodeDetails,
  NodeKind,
  NodeStatus,
  SectionKey,
  SupportStatus,
} from "./types";

export function emptyDetails(partial: Partial<GraphNodeDetails> = {}): GraphNodeDetails {
  return {
    role: null,
    expression: null,
    rows: [],
    support: null,
    classPath: [],
    statusNote: null,
    quote: null,
    valueSource: null,
    ...partial,
  };
}

/** Collects nodes/edges with deterministic ids. The same node id is only stored once. */
export class GraphBuilder {
  private readonly nodeMap = new Map<string, GraphNode>();
  private readonly edgeMap = new Map<string, GraphEdge>();

  constructor(readonly meta: GraphMeta | null) {}

  node(
    id: string,
    kind: NodeKind,
    label: string,
    status: NodeStatus,
    sourceRef: string,
    section: SectionKey | null,
    details: Partial<GraphNodeDetails> = {},
  ): string {
    if (!this.nodeMap.has(id)) {
      this.nodeMap.set(id, { id, kind, label, status, sourceRef, section, details: emptyDetails(details) });
    }
    return id;
  }

  edge(kind: EdgeKind, source: string, target: string, label = ""): void {
    const id = `${kind}:${source}>${target}`;
    if (!this.edgeMap.has(id)) this.edgeMap.set(id, { id, source, target, kind, label });
  }

  has(id: string): boolean {
    return this.nodeMap.has(id);
  }

  nodes(): GraphNode[] {
    return Array.from(this.nodeMap.values());
  }

  edges(): GraphEdge[] {
    return Array.from(this.edgeMap.values());
  }
}

export function supportToStatus(
  support: SupportStatus,
  dataPending: boolean,
): NodeStatus {
  if (dataPending) return "data_pending";
  if (support === "UNSUPPORTED") return "unsupported";
  if (support === "PARTIALLY_SUPPORTED") return "partial";
  return "ok";
}

export const row = (label: string, value: string | number): DetailRow => ({ label, value: String(value) });

/** Indicator display name in the UI language (the registry carries both). */
export const metaName = (ind: { name: string; nameEn: string }): string =>
  getLanguage() === "en" ? ind.nameEn : ind.name;

/** Display text of a registry value unit (never the raw identifier). */
export function unitText(unit: string | null | undefined): string | null {
  switch (unit) {
    case "percent":
      return "%";
    case "ratio":
      return t("배");
    case "억원":
      return t("억원");
    case "point":
      return t("포인트");
    case "event":
      return t("사건");
    default:
      return null;
  }
}
