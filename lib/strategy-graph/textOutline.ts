import type { DetailRow, GraphNode, NodeStatus, StrategyGraph } from "./types";

// Text view model. It walks the SAME graph the canvas renders (strategy-instance edges only), so
// the two views cannot disagree. Indicator concepts appear as a line under the condition that
// uses them; classification nodes appear as that line's path.

export interface OutlineItem {
  id: string;
  label: string;
  status: NodeStatus;
  depth: number;
  rows: DetailRow[];
  note: string | null;
  /** Indicator concept used by this item (name + classification path), if any. */
  indicator: { name: string; path: string[] } | null;
}

export interface OutlineSection {
  id: string;
  label: string;
  items: OutlineItem[];
}

const TREE_EDGES = new Set(["has_section", "contains", "combined_by"]);

export function buildOutline(graph: StrategyGraph): OutlineSection[] {
  const byId = new Map(graph.nodes.map((n) => [n.id, n] as const));
  const children = new Map<string, string[]>();
  const indicatorOf = new Map<string, string>();
  for (const e of graph.edges) {
    if (TREE_EDGES.has(e.kind)) {
      children.set(e.source, [...(children.get(e.source) ?? []), e.target]);
    } else if (e.kind === "uses_indicator") {
      indicatorOf.set(e.source, e.target);
    }
  }

  const sections: OutlineSection[] = [];
  for (const id of children.get("strategy") ?? []) {
    const section = byId.get(id) as GraphNode;
    const items: OutlineItem[] = [];
    const walk = (nodeId: string, depth: number) => {
      for (const childId of children.get(nodeId) ?? []) {
        const n = byId.get(childId) as GraphNode;
        const ind = indicatorOf.get(childId);
        const indNode = ind ? byId.get(ind) : undefined;
        items.push({
          id: n.id,
          label: n.label,
          status: n.status,
          depth,
          rows: n.details.rows,
          note: n.details.statusNote,
          indicator: indNode ? { name: indNode.label, path: indNode.details.classPath } : null,
        });
        walk(childId, depth + 1);
      }
    };
    walk(id, 0);
    sections.push({ id: section.id, label: section.label, items });
  }
  return sections;
}
