import { t } from "@/lib/i18n";
import type { NodeKind, NodeStatus, StrategyGraph } from "./types";

// Top-down tree layout of the strategy graph. The graph model is unchanged; this only decides how
// to draw it: section labels and edge labels become "pill" items on the edges, a condition's
// parameters and indicator become leaf items (only for expanded conditions), and classification
// nodes hang under the indicator leaf (only when opened). Deterministic: same graph + same open
// state -> same positions.

export interface OpenState {
  /** Instance ids (conditions/settings) whose parameter leaves + indicator are shown. */
  expanded: ReadonlySet<string>;
  /** Indicator ids whose classification chain is shown. */
  classes: ReadonlySet<string>;
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

const TREE_EDGES = new Set(["has_section", "contains", "combined_by"]);
const H_GAP = 28;
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

const charW = (ch: string): number => (/[ᄀ-ᇿ㄰-㆏가-힣一-鿿]/.test(ch) ? FONT : FONT * 0.6);
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

interface TNode {
  item: Omit<LayoutItem, "x" | "y" | "depth" | "parentKey">;
  children: TNode[];
  sub: number;
  /** Childless siblings under a section pill are stacked in one column instead of one wide row. */
  stack?: boolean;
}

function makeItem(
  key: string,
  kind: ItemKind,
  nodeId: string | null,
  owner: string,
  graphKind: NodeKind | null,
  rawLines: string[],
  sub: string | null,
  unresolved: boolean,
): TNode {
  const maxText = kind === "pill" ? 200 : kind === "leaf" ? 220 : 260;
  const lines = rawLines.flatMap((l) => wrap(l, maxText));
  const widest = Math.max(...lines.map(textWidth), sub ? textWidth(sub) * 0.8 : 0);
  const minW = kind === "pill" ? 56 : kind === "leaf" ? 84 : 120;
  const w = Math.max(minW, Math.ceil(widest + (kind === "pill" ? 28 : NODE_PAD_X * 2)));
  const h = kind === "pill" ? 32 : lines.length * LINE_H + (sub ? 16 : 0) + (kind === "leaf" ? 22 : 30);
  return { item: { key, kind, nodeId, owner, graphKind, lines, sub, unresolved, w, h }, children: [], sub: 0 };
}

export function layoutTree(graph: StrategyGraph, open: OpenState): TreeLayout {
  const nodeById = new Map(graph.nodes.map((n) => [n.id, n] as const));
  const kids = new Map<string, Array<{ id: string; label: string; kind: string }>>();
  const usesIndicator = new Map<string, string>();
  const parentClass = new Map<string, string>();
  for (const e of graph.edges) {
    if (TREE_EDGES.has(e.kind)) kids.set(e.source, [...(kids.get(e.source) ?? []), { id: e.target, label: e.label, kind: e.kind }]);
    else if (e.kind === "uses_indicator") usesIndicator.set(e.source, e.target);
    else if (e.kind === "is_a") parentClass.set(e.source, e.target);
  }

  const used = new Map<string, number>();
  const uniq = (base: string) => {
    const n = (used.get(base) ?? 0) + 1;
    used.set(base, n);
    return n === 1 ? base : `${base}~${n}`;
  };
  let conditionNo = 0;

  const pill = (label: string, owner: string, nodeId: string | null, child?: TNode): TNode => {
    const p = makeItem(uniq(`pill:${owner}:${label}`), "pill", nodeId, owner, nodeId ? nodeById.get(nodeId)?.kind ?? null : null, [label], null, false);
    if (child) p.children.push(child);
    return p;
  };

  const classChain = (indicatorId: string, owner: string): TNode[] => {
    const up = parentClass.get(indicatorId);
    if (!up || !open.classes.has(indicatorId)) return [];
    const walk = (id: string): TNode => {
      const n = nodeById.get(id)!;
      const leaf = makeItem(uniq(`leaf:${id}`), "leaf", id, owner, n.kind, [n.label], null, false);
      const next = parentClass.get(id);
      if (next && nodeById.has(next)) leaf.children.push(pill(t("분류"), owner, null, walk(next)));
      return leaf;
    };
    return [pill(t("분류"), owner, null, walk(up))];
  };

  const detailLeaves = (id: string): TNode[] => {
    const n = nodeById.get(id)!;
    const out: TNode[] = [];
    for (const r of n.details.rows) out.push(pill(r.label, id, null, makeItem(uniq(`leaf:${id}:${r.label}`), "leaf", null, id, null, [r.value], null, false)));
    const ind = usesIndicator.get(id);
    const indNode = ind ? nodeById.get(ind) : undefined;
    if (ind && indNode) {
      const leaf = makeItem(uniq(`leaf:${ind}@${id}`), "leaf", ind, id, "indicator", [indNode.label], null, false);
      leaf.children.push(...classChain(ind, id));
      out.push(pill(t("사용 지표"), id, null, leaf));
    }
    return out;
  };

  const childrenOf = (id: string): TNode[] =>
    (kids.get(id) ?? []).map((c) => {
      const child = nodeT(c.id);
      return c.kind === "combined_by" && c.label ? pill(c.label, c.id, null, child) : child;
    });

  const nodeT = (id: string, withChildren = true): TNode => {
    const n = nodeById.get(id)!;
    const lines = n.kind === "condition" ? [`${t("조건")} ${(conditionNo += 1)}`, n.label] : [n.label];
    const status = STATUS_LABELS[n.status];
    const node = makeItem(uniq(`node:${id}`), "node", id, id, n.kind, lines, status ? t(status) : null, ["pending", "check_needed", "unsupported", "data_pending"].includes(n.status));
    if (!withChildren) return node;
    node.children.push(...childrenOf(id));
    if (open.expanded.has(id)) node.children.push(...detailLeaves(id));
    return node;
  };

  if (!nodeById.has("strategy")) return { items: new Map(), order: [], edges: [], width: 0, height: 0 };
  const root = nodeT("strategy", false);
  // Section pills carry the section label between the strategy and its items.
  root.children = (kids.get("strategy") ?? []).map((s) => {
    const sec = pill(nodeById.get(s.id)!.label, s.id, s.id);
    sec.children.push(...childrenOf(s.id));
    sec.stack = sec.children.length >= 3 && sec.children.every((c) => c.children.length === 0);
    return sec;
  });


  // ── measure (subtree widths) ─────────────────────────────────────────────────────────────
  const measure = (n: TNode): number => {
    const childW = n.children.map(measure);
    if (n.stack) {
      n.sub = Math.max(n.item.w, ...childW);
      return n.sub;
    }
    const block = childW.reduce((a, b) => a + b, 0) + H_GAP * Math.max(0, n.children.length - 1);
    n.sub = Math.max(n.item.w, block);
    return n.sub;
  };
  // Bands: every section is its own top-down tree; bands are stacked vertically and joined to the
  // strategy by a trunk line on the left. This keeps the graph wide-but-short per band instead of
  // one very wide row of all sections.
  const items = new Map<string, LayoutItem>();
  const order: string[] = [];
  const edges: LayoutEdge[] = [];
  const gapBelow = (n: TNode) => (n.item.kind === "pill" ? 30 : 34 + Math.min(n.children.length - 1, 6) * 12);
  const STACK_GAP = 14;

  const place = (n: TNode, left: number, y: number, depth: number, parentKey: string | null): number => {
    const k = n.children.length;
    if (n.stack) {
      let cy = y + n.item.h + 30;
      for (const c of n.children) {
        place(c, left + (n.sub - c.sub) / 2, cy, depth + 1, n.item.key);
        cy += c.item.h + STACK_GAP;
      }
      items.set(n.item.key, { ...n.item, x: left + n.sub / 2 - n.item.w / 2, y, depth, parentKey });
      order.push(n.item.key);
      return left + n.sub / 2;
    }
    const block = n.children.reduce((a, c) => a + c.sub, 0) + H_GAP * Math.max(0, k - 1);
    let cursor = left + (n.sub - block) / 2;
    const childY = y + n.item.h + gapBelow(n);
    const centers = n.children.map((c) => {
      const cx = place(c, cursor, childY, depth + 1, n.item.key);
      cursor += c.sub + H_GAP;
      return cx;
    });
    const center = k === 0 ? left + n.sub / 2 : (centers[0] + centers[k - 1]) / 2;
    items.set(n.item.key, { ...n.item, x: center - n.item.w / 2, y, depth, parentKey });
    order.push(n.item.key);
    return center;
  };

  const TRUNK_X = 22;
  const BAND_LEFT = 44;
  const BAND_GAP = 40;
  items.set(root.item.key, { ...root.item, x: 0, y: 0, depth: 0, parentKey: null });
  order.push(root.item.key);
  const rootItem = items.get(root.item.key)!;
  let bandTop = rootItem.h + 36;
  for (const sec of root.children) {
    measure(sec);
    const before = order.length;
    place(sec, BAND_LEFT, bandTop, 1, root.item.key);
    let bandBottom = bandTop;
    for (const key of order.slice(before)) {
      const i = items.get(key)!;
      bandBottom = Math.max(bandBottom, i.y + i.h);
    }
    const pillItem = items.get(sec.item.key)!;
    const cy = pillItem.y + pillItem.h / 2;
    edges.push({ key: `${root.item.key}>${pillItem.key}`, from: root.item.key, to: pillItem.key, d: `M ${TRUNK_X} ${rootItem.h} V ${cy - 8} Q ${TRUNK_X} ${cy} ${TRUNK_X + 8} ${cy} H ${pillItem.x}`, arrow: true, end: { x: pillItem.x, y: cy, dir: "right" } });
    bandTop = bandBottom + BAND_GAP;
  }

  // ── edges inside each band (elbow connectors; farther targets run higher, like a staircase) ─
  const walk = (n: TNode) => {
    const p = items.get(n.item.key)!;
    const k = n.children.length;
    const bottom = p.y + p.h;
    if (n.stack) {
      for (const c of n.children) {
        const ci = items.get(c.item.key)!;
        const x = p.x + p.w / 2;
        edges.push({ key: `${p.key}>${ci.key}`, from: p.key, to: ci.key, d: `M ${x} ${bottom} V ${ci.y}`, arrow: false });
        walk(c);
      }
      return;
    }
    const rows = n.children.map((c, i) => {
      const ci = items.get(c.item.key)!;
      const sx = p.kind === "pill" || k === 1 ? p.x + p.w / 2 : p.x + (p.w * (i + 1)) / (k + 1);
      return { c, ci, sx, cx: ci.x + ci.w / 2, dx: ci.x + ci.w / 2 - sx };
    });
    const midY = new Map<string, number>();
    for (const side of [-1, 1]) {
      const same = rows.filter((r) => Math.sign(r.dx) === side).sort((a, b) => Math.abs(b.dx) - Math.abs(a.dx));
      same.forEach((r, rank) => midY.set(r.ci.key, bottom + 14 + rank * 12));
    }
    for (const r of rows) {
      edges.push({ key: `${p.key}>${r.ci.key}`, from: p.key, to: r.ci.key, d: elbowPath(r.sx, bottom, r.cx, r.ci.y, midY.get(r.ci.key) ?? bottom + 14), arrow: p.kind === "pill", end: p.kind === "pill" ? { x: r.cx, y: r.ci.y, dir: "down" } : undefined });
      walk(r.c);
    }
  };
  root.children.forEach(walk);

  let width = 0;
  let height = 0;
  items.forEach((i) => {
    width = Math.max(width, i.x + i.w);
    height = Math.max(height, i.y + i.h);
  });
  // Items can sit left of 0 when a parent is wider than its children block; shift everything right.
  let minX = 0;
  items.forEach((i) => (minX = Math.min(minX, i.x)));
  if (minX < 0) {
    items.forEach((i) => (i.x -= minX));
    width -= minX;
    edges.forEach((e) => {
      e.d = shiftPath(e.d, -minX);
      if (e.end) e.end = { ...e.end, x: e.end.x - minX };
    });
  }
  return { items, order, edges, width, height };
}

function shiftPath(d: string, dx: number): string {
  // Paths are built from absolute "M x,y", "H x", "Q cx,cy x,y" commands (V has no x).
  return d
    .replace(/M ([\d.-]+) ([\d.-]+)/, (_, x, y) => `M ${+x + dx} ${y}`)
    .replace(/H ([\d.-]+)/g, (_, x) => `H ${+x + dx}`)
    .replace(/Q ([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+)/g, (_, a, b, c, e) => `Q ${+a + dx} ${b} ${+c + dx} ${e}`)
    .replace(/V ([\d.-]+)/g, (_, y) => `V ${y}`);
}

/** Orthogonal connector with rounded corners: down, across at midY, down into the child. */
export function elbowPath(sx: number, sy: number, cx: number, cy: number, midY: number): string {
  const dx = cx - sx;
  if (Math.abs(dx) < 1) return `M ${sx} ${sy} V ${cy}`;
  const dir = Math.sign(dx);
  const r = Math.min(10, Math.abs(dx) / 2, Math.max(2, (cy - midY) / 2));
  return `M ${sx} ${sy} V ${midY - r} Q ${sx} ${midY} ${sx + dir * r} ${midY} H ${cx - dir * r} Q ${cx} ${midY} ${cx} ${midY + r} V ${cy}`;
}

/** Instance nodes that can show parameter leaves / an indicator. */
export function expandableIds(graph: StrategyGraph): string[] {
  const withIndicator = new Set(graph.edges.filter((e) => e.kind === "uses_indicator").map((e) => e.source));
  return graph.nodes
    .filter((n) => ["condition", "setting", "risk"].includes(n.kind) && (n.details.rows.length > 0 || withIndicator.has(n.id)))
    .map((n) => n.id);
}

/** Small strategies open every condition by default; large ones start collapsed (expand on select). */
export function defaultExpanded(graph: StrategyGraph, maxLeaves = 24): Set<string> {
  const withIndicator = new Set(graph.edges.filter((e) => e.kind === "uses_indicator").map((e) => e.source));
  const ids = expandableIds(graph).filter((id) => graph.nodes.find((n) => n.id === id)?.kind === "condition");
  const leaves = ids.reduce((sum, id) => sum + (graph.nodes.find((n) => n.id === id)?.details.rows.length ?? 0) + (withIndicator.has(id) ? 1 : 0), 0);
  return leaves <= maxLeaves ? new Set(ids) : new Set();
}
