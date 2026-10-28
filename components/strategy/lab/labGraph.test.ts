import { describe, expect, it } from "vitest";

import { confirmedInput, META } from "@/lib/strategy-graph/fixtures";
import { buildStrategyGraph } from "@/lib/strategy-graph/transform";
import { buildLabGraph, changedNodeIds, itemsForStage, PIPELINE_ORDER, STAGE_GAP_X, type LabNode } from "./labGraph";

const lab = () => buildLabGraph(buildStrategyGraph(confirmedInput("goldenCrossRsiAnd"), META));
const pipeline = (nodes: LabNode[]) => nodes.filter((n) => n.type === "pipeline");

describe("buildLabGraph — 고정 파이프라인 칸", () => {
  it("그래프가 없거나 칸이 없으면 빈 캔버스다", () => {
    expect(buildLabGraph(null)).toEqual({ nodes: [], edges: [] });
  });

  it("칸을 엔진 실행 순서로 한 줄에 놓고 끝에는 항상 백테스트 칸이 온다", () => {
    const { nodes } = lab();
    const stages = pipeline(nodes).map((n) => n.data.stage);
    expect(stages[stages.length - 1]).toBe("output");
    // 순서는 PIPELINE_ORDER의 부분 수열이다(그래프에 없는 칸은 건너뛴다).
    const order = stages.map((s) => PIPELINE_ORDER.indexOf(s));
    expect([...order].sort((a, b) => a - b)).toEqual(order);
    pipeline(nodes).forEach((n, i) => expect(n.position).toEqual({ x: i * STAGE_GAP_X, y: 0 }));
  });

  it("칸 사이 흐름 엣지는 앞 칸에서 뒤 칸으로만 이어져 순환이 생기지 않는다", () => {
    const { nodes, edges } = lab();
    const ids = pipeline(nodes).map((n) => n.id);
    const flow = edges.filter((e) => e.id.startsWith("flow:"));
    expect(flow).toHaveLength(ids.length - 1);
    for (const e of flow) expect(ids.indexOf(e.target)).toBe(ids.indexOf(e.source) + 1);
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
