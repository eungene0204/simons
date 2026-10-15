import { describe, expect, it } from "vitest";

import { confirmedInput, META } from "./fixtures";
import { defaultExpanded, expandableIds, layoutTree, type LayoutItem } from "./layout";
import { buildOutline } from "./textOutline";
import { buildStrategyGraph } from "./transform";

const big = buildStrategyGraph(confirmedInput("krComplex"), META);
const small = buildStrategyGraph(confirmedInput("goldenCrossRsiAnd"), META);
const closed = { expanded: new Set<string>(), classes: new Set<string>() };
const graph = big;

const overlaps = (a: LayoutItem, b: LayoutItem) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const nodeIds = (l: ReturnType<typeof layoutTree>) => Array.from(l.items.values()).map((i) => i.nodeId).filter(Boolean);

describe("default expansion", () => {
  it("opens every condition of a small strategy and keeps a large one collapsed", () => {
    expect(defaultExpanded(small).size).toBeGreaterThan(0);
    expect(defaultExpanded(big).size).toBe(0);
  });
});

describe("tree layout", () => {
  it("keeps every strategy instance node, expanded or not (collapsing never loses a condition)", () => {
    const instances = big.nodes.filter((n) => !["indicator", "class", "section"].includes(n.kind)).map((n) => n.id);
    for (const open of [closed, { expanded: new Set(expandableIds(big)), classes: new Set<string>() }]) {
      const ids = nodeIds(layoutTree(big, open));
      for (const id of instances) expect(ids).toContain(id);
    }
  });

  it("shows indicator leaves only for expanded items and classification only when opened", () => {
    expect(nodeIds(layoutTree(big, closed)).some((id) => String(id).startsWith("ind:"))).toBe(false);
    const cond = "cond:exit/exit.0";
    const one = layoutTree(big, { expanded: new Set([cond]), classes: new Set() });
    expect(nodeIds(one).filter((id) => String(id).startsWith("ind:"))).toEqual(["ind:technical.rsi"]);
    expect(nodeIds(one).some((id) => String(id).startsWith("class:"))).toBe(false);
    const withClasses = layoutTree(big, { expanded: new Set([cond]), classes: new Set(["ind:technical.rsi"]) });
    expect(nodeIds(withClasses).some((id) => String(id).startsWith("class:"))).toBe(true);
  });

  it("turns parameters into labelled leaves like the reference design", () => {
    const l = layoutTree(small, { expanded: new Set(["cond:entry/entry.1"]), classes: new Set() });
    const text = Array.from(l.items.values()).map((i) => i.lines.join(" "));
    expect(text).toEqual(expect.arrayContaining(["RSI", "14일", "<", "70", "기간", "연산자", "기준값", "사용 지표"]));
  });

  it("is deterministic, overlap-free, and places children below their parents", () => {
    const open = { expanded: new Set(expandableIds(big)), classes: new Set(["ind:technical.rsi"]) };
    const a = layoutTree(big, open);
    const b = layoutTree(big, open);
    expect(JSON.stringify(Array.from(a.items))).toBe(JSON.stringify(Array.from(b.items)));
    const items = Array.from(a.items.values());
    for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) expect(overlaps(items[i], items[j])).toBe(false);
    for (const it of items) if (it.parentKey) expect(it.y).toBeGreaterThan(a.items.get(it.parentKey)!.y);
    expect(a.edges).toHaveLength(items.length - 1);
    expect(items.every((it) => it.x >= 0)).toBe(true);
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
