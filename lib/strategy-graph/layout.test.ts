import { describe, expect, it } from "vitest";

import { confirmedInput, META } from "./fixtures";
import { defaultExpanded, expandableIds, layoutTree, textWidth, type LayoutItem } from "./layout";
import { buildOutline } from "./textOutline";
import { buildStrategyGraph } from "./transform";

const big = buildStrategyGraph(confirmedInput("krComplex"), META);
const small = buildStrategyGraph(confirmedInput("goldenCrossRsiAnd"), META);
const closed = { expanded: new Set<string>() };
const graph = big;

const overlaps = (a: LayoutItem, b: LayoutItem) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const nodeIds = (l: ReturnType<typeof layoutTree>) => Array.from(l.items.values()).map((i) => i.nodeId).filter(Boolean);

describe("default expansion", () => {
  it("starts every strategy collapsed, small or large", () => {
    expect(defaultExpanded(small).size).toBe(0);
    expect(defaultExpanded(big).size).toBe(0);
  });
});

describe("tree layout", () => {
  it("keeps every strategy instance node, expanded or not (collapsing never loses a condition)", () => {
    const instances = big.nodes.filter((n) => !["indicator", "class", "section", "group"].includes(n.kind)).map((n) => n.id);
    for (const open of [closed, { expanded: new Set(expandableIds(big)) }]) {
      const ids = nodeIds(layoutTree(big, open));
      for (const id of instances) expect(ids).toContain(id);
    }
  });

  it("shows indicator leaves only for expanded items", () => {
    expect(nodeIds(layoutTree(big, closed)).some((id) => String(id).startsWith("ind:"))).toBe(false);
    const one = layoutTree(big, { expanded: new Set(["cond:exit/exit.0"]) });
    expect(nodeIds(one).filter((id) => String(id).startsWith("ind:"))).toEqual(["ind:technical.rsi"]);
    expect(nodeIds(one).some((id) => String(id).startsWith("class:"))).toBe(false);
  });

  it("turns parameters into one 'label: value' leaf each", () => {
    const l = layoutTree(small, { expanded: new Set(["cond:entry/entry.1"]) });
    const text = Array.from(l.items.values()).map((i) => i.lines.join(" "));
    expect(text).toEqual(expect.arrayContaining(["기간: 14일", "연산자: <", "기준값: 70", "사용 지표: RSI"]));
  });

  it("reads left to right as pick -> buy -> hold -> sell", () => {
    const x = (id: string) => Array.from(layoutTree(big, closed).items.values()).find((i) => i.nodeId === id)!.x;
    expect(x("strategy")).toBeLessThan(x("section:universe"));
    expect(x("section:universe")).toBeLessThan(x("section:entry"));
    expect(x("section:entry")).toBeLessThan(x("section:allocation"));
    expect(x("section:allocation")).toBeLessThan(x("section:exit"));
    expect(x("section:risk")).toBe(x("section:exit"));
  });

  it("is deterministic, overlap-free, and every edge joins two drawn items", () => {
    const open = { expanded: new Set(expandableIds(big)) };
    const a = layoutTree(big, open);
    const b = layoutTree(big, open);
    expect(JSON.stringify(Array.from(a.items))).toBe(JSON.stringify(Array.from(b.items)));
    const items = Array.from(a.items.values());
    for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) expect(overlaps(items[i], items[j])).toBe(false);
    for (const e of a.edges) {
      expect(a.items.has(e.from)).toBe(true);
      expect(a.items.has(e.to)).toBe(true);
    }
    expect(items.every((it) => it.x >= 0 && it.y >= 0)).toBe(true);
  });

  it("draws only real relations: siblings hang from their section header, sections chain by header", () => {
    const l = layoutTree(big, closed);
    const byNode = (id: string) => Array.from(l.items.values()).find((i) => i.nodeId === id)!;
    const universe = byNode("section:universe");
    // KOSPI and the sector are two settings of the same section, not a chain.
    expect(l.items.get(byNode("setting:universe/markets").key)!.parentKey).toBe(universe.key);
    expect(l.items.get(byNode("setting:universe/sector").key)!.parentKey).toBe(universe.key);
    // The next section is reached from the previous section header, never from one of its items.
    const into = l.edges.find((e) => e.to === byNode("section:filters").key)!;
    expect(into.from).toBe(universe.key);
  });

  it("connects every item: each one has an incoming edge except the strategy itself", () => {
    for (const g of [big, small]) {
      for (const open of [closed, { expanded: new Set(expandableIds(g)) }]) {
        const l = layoutTree(g, open);
        const incoming = new Set(l.edges.map((e) => e.to));
        const loose = Array.from(l.items.keys()).filter((k) => k !== "node:strategy" && !incoming.has(k));
        expect(loose).toEqual([]);
      }
    }
  });
});

describe("section headers", () => {
  it("keep their folded AND/OR label on one line and are tall enough for every line", () => {
    const l = layoutTree(big, closed);
    for (const i of l.items.values()) {
      if (i.kind !== "pill") continue;
      expect(i.lines).toHaveLength(1);
      expect(i.h).toBeGreaterThanOrEqual(i.lines.length * 20 + 12);
      expect(i.w).toBeGreaterThan(textWidth(i.lines[0]));
    }
  });
});

describe("simplified structure", () => {
  it("folds a resolved AND/OR group into the section label (no group node, no AND/OR pills)", () => {
    const l = layoutTree(big, closed);
    const labels = Array.from(l.items.values()).map((i) => i.lines.join(" "));
    expect(labels.some((x) => x.includes("AND") && x.includes("·"))).toBe(true);
    expect(labels).not.toContain("AND");
    expect(labels).not.toContain("OR");
    expect(nodeIds(l).some((id) => String(id).startsWith("group:"))).toBe(false);
  });
});

describe("text outline uses the same model", () => {
  it("lists every strategy-instance node exactly once", () => {
    const outline = buildOutline(graph);
    const ids = outline.flatMap((s) => s.items.map((i) => i.id));
    const expected = graph.nodes.filter((n) => !["strategy", "section", "indicator", "class"].includes(n.kind)).map((n) => n.id);
    expect(ids.sort()).toEqual(expected.sort());
    expect(outline.map((s) => s.id)).toEqual(graph.nodes.filter((n) => n.kind === "section").map((n) => n.id));
  });
  it("shows the indicator and classification path under a condition", () => {
    const item = buildOutline(graph).flatMap((s) => s.items).find((i) => i.id === "cond:exit/exit.0");
    expect(item?.indicator?.name).toBe("RSI");
    expect(item?.indicator?.path.length).toBeGreaterThan(0);
  });
});
