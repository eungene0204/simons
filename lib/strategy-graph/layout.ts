import { t } from "@/lib/i18n";
import type { DetailRow, GraphNode, NodeKind, NodeStatus, SectionKey, StrategyGraph } from "./types";

// Trade-flow layout of the strategy graph, read left to right: the strategy -> where it picks
// stocks -> when it buys -> how it holds -> when it sells. The graph model is unchanged; this only
// decides how to draw it. Each stage is a column of sections (a pill header with its items stacked
// below); a resolved AND/OR group is folded into its section's header. A selected item's
// parameters and indicator hang below it as leaves. Deterministic: same graph + same open state ->
// same positions.

export interface OpenState {
  /** Instance ids (conditions/settings) whose parameter leaves + indicator are shown. */
  expanded: ReadonlySet<string>;
}

export type ItemKind = "node" | "pill" | "leaf";

export interface LayoutItem {
  key: string;
  kind: ItemKind;
  /** Graph node this item stands for (selection target); null for plain value leaves and edge pills. */
  nodeId: string | null;
  /** Graph node the item belongs to — used to dim/highlight with its owner. */
  owner: string;
  graphKind: NodeKind | null;
  lines: string[];
  sub: string | null;
  unresolved: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  depth: number;
  parentKey: string | null;
}

export interface LayoutEdge {
  key: string;
  from: string;
  to: string;
  d: string;
  arrow: boolean;
  /** Where the arrowhead sits and which way it points (drawn separately so it can animate). */
  end?: { x: number; y: number; dir: "down" | "right" };
}

export interface TreeLayout {
  items: Map<string, LayoutItem>;
  order: string[];
  edges: LayoutEdge[];
  width: number;
  height: number;
}

const TREE_EDGES = new Set(["has_section", "contains"]);
const COL_GAP = 64;
const ROW_GAP = 16;
const SECTION_GAP = 30;
const NODE_PAD_X = 22;
const LINE_H = 20;
const FONT = 14;
const STATUS_LABELS: Partial<Record<NodeStatus, string>> = {
  pending: "미정",
  not_applicable: "기준값 해당 없음",
  unsupported: "미지원",
  partial: "부분 지원",
  data_pending: "준비 중",
  check_needed: "확인 필요",
};

/** Which flow stage (column) each section belongs to: pick -> buy -> hold -> sell. */
const STAGES: SectionKey[][] = [["universe", "filters", "ranking"], ["entry"], ["allocation", "rebalance"], ["exit", "risk"]];

const charW = (ch: string): number => (/[ᄀ-ᇿ㄰-㆏가-힣一-鿿]/.test(ch) ? FONT : FONT * 0.68);
export const textWidth = (s: string): number => Array.from(s).reduce((sum, ch) => sum + charW(ch), 0);

function wrap(text: string, maxW: number): string[] {
  const lines: string[] = [];
  let line = "";
  let w = 0;
  for (const ch of Array.from(text)) {
    const cw = charW(ch);
    if (w + cw > maxW && line) {
      lines.push(line);
      line = "";
      w = 0;
    }
    line += ch;
    w += cw;
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
}

type Draft = Omit<LayoutItem, "x" | "y" | "depth" | "parentKey">;

function makeItem(
  key: string,
  kind: ItemKind,
  nodeId: string | null,
  owner: string,
  graphKind: NodeKind | null,
  rawLines: string[],
  sub: string | null,
  unresolved: boolean,
): Draft {
  const maxText = kind === "pill" ? 400 : kind === "leaf" ? 220 : 260;
  const lines = rawLines.flatMap((l) => wrap(l, maxText));
  const widest = Math.max(...lines.map(textWidth), sub ? textWidth(sub) * 0.8 : 0);
  const minW = kind === "pill" ? 56 : kind === "leaf" ? 84 : 120;
  const w = Math.max(minW, Math.ceil(widest + (kind === "pill" ? 44 : NODE_PAD_X * 2)));
  const h = kind === "pill" ? Math.max(32, lines.length * LINE_H + 12) : lines.length * LINE_H + (sub ? 16 : 0) + (kind === "leaf" ? 22 : 30);
  return { key, kind, nodeId, owner, graphKind, lines, sub, unresolved, w, h };
}

export function layoutTree(graph: StrategyGraph, open: OpenState): TreeLayout {
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n] as const));
  const kids = new Map<string, string[]>();
  const usesIndicator = new Map<string, string>();
  for (const e of graph.edges) {
    if (TREE_EDGES.has(e.kind) || e.kind === "combined_by") kids.set(e.source, [...(kids.get(e.source) ?? []), e.target]);
    else if (e.kind === "uses_indicator") usesIndicator.set(e.source, e.target);
  }
  if (!nodeById.has("strategy")) return { items: new Map(), order: [], edges: [], width: 0, height: 0 };

  const used = new Map<string, number>();
  const uniq = (base: string) => {
    const n = (used.get(base) ?? 0) + 1;
    used.set(base, n);
    return n === 1 ? base : `${base}~${n}`;
  };

  const nodeDraft = (id: string): Draft => {
    const n = nodeById.get(id)!;
    const status = STATUS_LABELS[n.status];
    return makeItem(uniq(`node:${id}`), "node", id, id, n.kind, [n.label], status ? t(status) : null, ["pending", "check_needed", "unsupported", "data_pending"].includes(n.status));
  };

  /** Parameters and the used indicator of an opened item, as small leaves hanging below it. */
  const detailDrafts = (id: string): Draft[] => {
    const n = nodeById.get(id)!;
    const out = visibleRows(n).map((r) => makeItem(uniq(`leaf:${id}:${r.label}`), "leaf", null, id, null, [`${r.label}: ${r.value}`], null, false));
    const ind = usesIndicator.get(id);
    const indNode = ind ? nodeById.get(ind) : undefined;
    if (ind && indNode) {
      out.push(makeItem(uniq(`leaf:${ind}@${id}`), "leaf", ind, id, "indicator", [`${t("사용 지표")}: ${indNode.label}`], null, false));
      indNode.details.rows.forEach((r) => out.push(makeItem(uniq(`leaf:${ind}:${r.label}@${id}`), "leaf", null, id, null, [`${r.label}: ${r.value}`], null, false)));
    }
    return out;
  };

  // A stage column = its sections. Each section is a header pill; its items hang from the header
  // as a tree (a trunk with one branch per item), so items of one section are siblings, never a
  // chain. Only real relations are drawn: header -> header (stage order) and parent -> child.
  interface Entry {
    d: Draft;
    depth: number;
    parent: number;
  }
  interface Block {
    header: Draft;
    entries: Entry[];
  }
  const sectionOf = (key: SectionKey) => nodeById.get(`section:${key}`);
  const blockOf = (key: SectionKey): Block | null => {
    const sec = sectionOf(key);
    if (!sec) return null;
    const members = (kids.get(sec.id) ?? []).map((id) => nodeById.get(id)!);
    // A resolved AND/OR group is folded into the header; an unresolved one stays a node.
    const group = members.find((n) => n.kind === "group" && n.status === "ok") ?? null;
    const shown = group ? `${sec.label} · ${group.label}` : sec.label;
    const header = makeItem(uniq(`pill:${sec.id}:${sec.label}`), "pill", sec.id, sec.id, "section", [shown], null, false);
    const ids = members.flatMap((n) => (group && n.id === group.id ? kids.get(group.id) ?? [] : [n.id]));
    const entries: Entry[] = [];
    // Nested items (e.g. the components of a composite ranking) and an opened item's details hang
    // from their own parent.
    const add = (id: string, depth: number, parent: number) => {
      const at = entries.push({ d: nodeDraft(id), depth, parent }) - 1;
      if (open.expanded.has(id)) detailDrafts(id).forEach((leaf) => entries.push({ d: leaf, depth: depth + 1, parent: at }));
      (kids.get(id) ?? []).forEach((c) => add(c, depth + 1, at));
    };
    ids.forEach((id) => add(id, 1, -1));
    return { header, entries };
  };

  const items = new Map<string, LayoutItem>();
  const order: string[] = [];
  const edges: LayoutEdge[] = [];
  const put = (d: Draft, x: number, y: number, depth: number, parentKey: string | null) => {
    items.set(d.key, { ...d, x, y, depth, parentKey });
    order.push(d.key);
  };
  const INDENT = 28;
  const TRUNK = 16;
  /** Branch from a parent's trunk (below its left part) into the child's left edge. */
  const branch = (parent: LayoutItem, child: LayoutItem) => {
    const tx = parent.x + TRUNK;
    const cy = child.y + child.h / 2;
    edges.push({ key: `${parent.key}>${child.key}`, from: parent.key, to: child.key, d: `M ${tx} ${parent.y + parent.h} V ${cy - 6} Q ${tx} ${cy} ${tx + 6} ${cy} H ${child.x}`, arrow: false });
  };

  const ROW_CENTER = 40;
  const SIDE = 20;
  const root = nodeDraft("strategy");
  put(root, 0, ROW_CENTER - root.h / 2, 0, null);
  let prevHead: LayoutItem = items.get(root.key)!;
  let left = root.w + COL_GAP;

  STAGES.forEach((stage, col) => {
    const blocks = stage.map(blockOf).filter((b): b is Block => b !== null);
    if (blocks.length === 0) return;
    const colW = Math.max(...blocks.flatMap((b) => [b.header.w, ...b.entries.map((e) => e.depth * INDENT + e.d.w)]));
    let y = 0;
    let prevSection: LayoutItem | null = null;
    blocks.forEach((b, bi) => {
      // The first header of every column sits on the flow line; later sections start below.
      const hy = bi === 0 ? ROW_CENTER - b.header.h / 2 : y;
      put(b.header, left, hy, col + 1, null);
      const head = items.get(b.header.key)!;
      const cy = head.y + head.h / 2;
      if (bi === 0) {
        edges.push({ key: `${prevHead.key}>${head.key}`, from: prevHead.key, to: head.key, d: `M ${prevHead.x + prevHead.w} ${prevHead.y + prevHead.h / 2} H ${head.x}`, arrow: true, end: { x: head.x, y: cy, dir: "right" } });
        prevHead = head;
      } else if (prevSection) {
        // Stage order inside a column: previous section header -> this one, routed along the
        // left side so it never crosses the items hanging below the previous header.
        const from = prevSection;
        edges.push({ key: `${from.key}>${head.key}`, from: from.key, to: head.key, d: `M ${from.x} ${from.y + from.h / 2} H ${left - SIDE} V ${cy} H ${head.x}`, arrow: true, end: { x: head.x, y: cy, dir: "right" } });
      }
      prevSection = head;
      const placed: LayoutItem[] = [];
      y = head.y + head.h + 18;
      for (const e of b.entries) {
        const parent = e.parent < 0 ? head : placed[e.parent];
        put(e.d, left + e.depth * INDENT, y, col + 1 + e.depth, parent.key);
        const it = items.get(e.d.key)!;
        branch(parent, it);
        placed.push(it);
        y += it.h + ROW_GAP;
      }
      y += SECTION_GAP;
    });
    left += colW + COL_GAP;
  });

  let width = 0;
  let height = 0;
  items.forEach((i) => {
    width = Math.max(width, i.x + i.w);
    height = Math.max(height, i.y + i.h);
  });
  return { items, order, edges, width, height };
}

/**
 * Rows that tell something the node label does not already say (e.g. "업종: 반도체" under
 * "업종: 반도체"). Conditions keep every row: their label is a summary and the rows spell it out.
 */
export function visibleRows(n: GraphNode): DetailRow[] {
  if (n.kind === "condition") return n.details.rows;
  return n.details.rows.filter((r) => !n.label.includes(r.value));
}

/** Instance nodes that can show parameter leaves / an indicator. */
export function expandableIds(graph: StrategyGraph): string[] {
  const withIndicator = new Set(graph.edges.filter((e) => e.kind === "uses_indicator").map((e) => e.source));
  return graph.nodes
    .filter((n) => ["condition", "setting", "risk"].includes(n.kind) && (visibleRows(n).length > 0 || withIndicator.has(n.id)))
    .map((n) => n.id);
}

/** Every item starts collapsed: the first view shows only the strategy's flow (expand on select). */
export function defaultExpanded(_graph: StrategyGraph): Set<string> {
  return new Set();
}
