import { describe, expect, it } from "vitest";

import { confirmedInput, META } from "@/lib/strategy-graph/fixtures";
import { buildStrategyGraph } from "@/lib/strategy-graph/transform";
import { buildLabGraph, changedNodeIds, followStageDrag, itemsForStage, PIPELINE_ORDER, type LabNode } from "./labGraph";

const lab = () => buildLabGraph(buildStrategyGraph(confirmedInput("goldenCrossRsiAnd"), META));
const pipeline = (nodes: LabNode[]) => nodes.filter((n) => n.type === "pipeline");

describe("buildLabGraph — 고정 파이프라인 칸", () => {
  it("그래프가 없거나 칸이 없으면 빈 캔버스다", () => {
    expect(buildLabGraph(null)).toEqual({ nodes: [], edges: [] });
  });

  it("백테스트 노드는 그리지 않고, 같은 부모에서 갈라진 칸은 서로 다른 줄에 놓인다", () => {
    const { nodes, edges } = lab();
    const stages = pipeline(nodes).map((n) => n.data.stage);
    expect(stages).not.toContain("output");
    expect(edges.some((e) => e.source === "stage:output" || e.target === "stage:output")).toBe(false);
    // 노드 순서는 PIPELINE_ORDER의 부분 수열이다(그래프에 없는 칸은 건너뛴다).
    const order = stages.map((s) => PIPELINE_ORDER.indexOf(s));
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    const bySource = new Map<string, string[]>();
    for (const e of edges.filter((e) => e.id.startsWith("flow:"))) bySource.set(e.source, [...(bySource.get(e.source) ?? []), e.target]);
    for (const targets of bySource.values()) {
      const ys = targets.map((t) => nodes.find((n) => n.id === t)!.position.y);
      if (targets.length > 1) expect(new Set(ys).size).toBe(ys.length);
    }
  });

  it("흐름 엣지는 왼쪽에서 오른쪽으로만 이어져 순환이 생기지 않는다", () => {
    const { nodes, edges } = lab();
    const x = (id: string) => nodes.find((n) => n.id === id)!.position.x;
    const flow = edges.filter((e) => e.id.startsWith("flow:"));
    expect(flow.length).toBeGreaterThan(0);
    for (const e of flow) expect(x(e.target)).toBeGreaterThan(x(e.source));
    // 사용자가 포트를 끌어 연결을 바꿀 수 없다.
    expect(nodes.every((n) => n.connectable === false)).toBe(true);
  });

  it("매수 규칙의 조건은 칸의 하단 보조 포트에 매달리고, 결합 그룹은 칸의 결합 방식으로 접힌다", () => {
    const { nodes, edges } = lab();
    const entry = nodes.find((n) => n.id === "stage:entry");
    expect(entry?.type).toBe("pipeline");
    if (entry?.type !== "pipeline") return;
    expect(entry.data.itemCount).toBe(2);
    expect(entry.data.logic).toContain("AND");
    const children = edges.filter((e) => e.source === "stage:entry" && e.sourceHandle === "aux").map((e) => e.target);
    const labels = nodes.filter((n) => children.includes(n.id)).map((n) => n.data.label);
    expect(labels).toEqual(["20일선-60일선 골든크로스", "RSI(14) < 70"]);
  });

  it("항목 수는 칸 사이 흐름 선이 아니라 칸 아래 항목으로 이어지는 선에 표시한다", () => {
    const { edges } = lab();
    expect(edges.filter((e) => e.className === "lab-edge-flow").every((e) => e.label === undefined)).toBe(true);
    const aux = edges.filter((e) => e.source === "stage:entry" && e.sourceHandle === "aux");
    expect(aux.map((e) => e.label)).toEqual(["2개 항목", undefined]);
  });

  it("같은 그래프는 같은 노드·엣지·좌표를 만든다", () => {
    expect(lab()).toEqual(lab());
  });
});

describe("changedNodeIds — 짧게 강조할 노드", () => {
  it("첫 그래프는 모든 노드가 새 노드다", () => {
    const { nodes } = lab();
    expect(changedNodeIds([], nodes)).toEqual(nodes.map((n) => n.id));
  });

  it("내용이 같으면 강조하지 않고, 바뀐 노드만 고른다", () => {
    const { nodes } = lab();
    expect(changedNodeIds(nodes, lab().nodes)).toEqual([]);
    const next = nodes.map((n) => (n.id === "stage:entry" ? ({ ...n, data: { ...n.data, status: "pending" } } as LabNode) : n));
    expect(changedNodeIds(nodes, next)).toEqual(["stage:entry"]);
  });
});

describe("itemsForStage — 캔버스 지우기 후보", () => {
  const items = [
    { id: "universe" },
    { id: "fundamental.0" },
    { id: "entry.0" },
    { id: "exit.0" },
    { id: "hold_period" },
    { id: "max_positions" },
    { id: "rebalancing" },
    { id: "stop_loss" },
    { id: "take_profit" },
    { id: "backtest_period" },
  ];
  const ids = (stage: Parameters<typeof itemsForStage>[0]) => itemsForStage(stage, items).map((i) => i.id);

  it("칸에 속한 항목만 후보로 내고 짐작으로 하나를 고르지 않는다", () => {
    expect(ids("entry")).toEqual(["fundamental.0", "entry.0"]);
    expect(ids("exit")).toEqual(["exit.0", "hold_period"]);
    expect(ids("risk")).toEqual(["stop_loss", "take_profit"]);
    expect(ids("output")).toEqual(["backtest_period"]);
  });

  it("해석 결과에 항목이 없는 칸(순위 선정)은 후보가 없다", () => {
    expect(ids("ranking")).toEqual([]);
  });
});

describe("followStageDrag — 칸을 끌면 매달린 조건도 따라 움직인다", () => {
  it("칸 노드의 이동량만큼 같은 칸의 조건 노드만 옮긴다", () => {
    const { nodes } = lab();
    const parent = nodes.find((n) => n.type === "pipeline" && nodes.some((c) => c.type === "condition" && c.data.stage === n.data.stage))!;
    const children = nodes.filter((n) => n.type === "condition" && n.data.stage === parent.data.stage);
    const others = nodes.filter((n) => n.type === "condition" && n.data.stage !== parent.data.stage);
    const changes = followStageDrag(
      [{ id: parent.id, type: "position", position: { x: parent.position.x + 30, y: parent.position.y - 20 }, dragging: true }],
      nodes,
    );
    const moved = new Map(changes.flatMap((c) => (c.type === "position" && c.position ? [[c.id, c.position] as const] : [])));
    for (const child of children) expect(moved.get(child.id)).toEqual({ x: child.position.x + 30, y: child.position.y - 20 });
    for (const other of others) expect(moved.has(other.id)).toBe(false);
  });

  it("조건 노드를 끌거나 함께 끌리는 조건은 따로 옮기지 않는다", () => {
    const { nodes } = lab();
    const child = nodes.find((n) => n.type === "condition")!;
    const parent = nodes.find((n) => n.id === `stage:${child.data.stage}`)!;
    const own = [{ id: child.id, type: "position" as const, position: { x: 1, y: 1 } }];
    expect(followStageDrag(own, nodes)).toBe(own);
    const both = [{ id: parent.id, type: "position" as const, position: { x: parent.position.x + 5, y: parent.position.y } }, ...own];
    expect(followStageDrag(both, nodes).filter((c) => c.type === "position" && c.id === child.id)).toHaveLength(1);
  });
});
