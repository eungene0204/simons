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

  it("손절·익절 노드는 위험 관리 칸과 매도 칸 두 곳에 이어지고, 위험 관리 칸과 매도 칸끼리는 잇지 않는다", () => {
    const g = lab();
    const into = (target: string) => g.edges.filter((e) => e.target === target);
    // 칸끼리 흐름 선 없음.
    expect(g.edges.some((e) => e.id.startsWith("flow:") && e.target === "stage:risk")).toBe(false);
    for (const leaf of ["item:setting:risk/stop_loss", "item:setting:risk/take_profit"]) {
      expect(into(leaf).map((e) => `${e.source}:${e.sourceHandle}->${e.targetHandle}`).sort()).toEqual(["stage:exit:out->side", "stage:risk:aux->top"]);
      const node = g.nodes.find((n) => n.id === leaf);
      expect(node?.type === "condition" && node.data.sellTrigger).toBe(true);
    }
    // 위험 관리 칸은 매도 칸 오른쪽, 같은 줄이다(선이 매도 칸의 조건 노드를 가로지르지 않게).
    const pos = (id: string) => g.nodes.find((n) => n.id === id)!.position;
    expect(pos("stage:risk").y).toBe(pos("stage:exit").y);
    expect(pos("stage:risk").x).toBeGreaterThan(pos("stage:exit").x);

    // 매도 칸이 없으면 위험 관리 칸은 매수 칸에 흐름 선으로 잇고, 매도 선은 없다.
    const noExit = buildLabGraph(buildStrategyGraph(confirmedInput("riskRoles"), META));
    expect(noExit.nodes.some((n) => n.id === "stage:exit")).toBe(false);
    expect(noExit.edges.filter((e) => e.id.startsWith("flow:") && e.target === "stage:risk").map((e) => e.source)).toEqual(["stage:entry"]);
    expect(noExit.edges.some((e) => e.id.startsWith("sell:"))).toBe(false);
  });

  it("팔지 않는 위험 관리 설정은 매도 칸에 잇지 않는다", () => {
    const input = confirmedInput("goldenCrossRsiAnd");
    const request = { ...input.request, risk: { ...input.request!.risk, stop_cooldown_days: 5 } };
    const g = buildLabGraph(buildStrategyGraph({ ...input, request }, META));
    expect(g.nodes.some((n) => n.id === "item:setting:risk/cooldown")).toBe(true);
    expect(g.edges.some((e) => e.target === "item:setting:risk/cooldown" && e.source === "stage:exit")).toBe(false);
  });

  it("매수·매도 조건 없이 종목을 바꾸는 리밸런싱이면 리밸런싱에서 매수·매도 칸을 풀어 그리고 손절은 매도에 잇는다", () => {
    // 실측(2026-10-28): 'PBR·ROE 필터 + 분기 리밸런싱 + 손절 -12%'는 매수·매도를 리밸런싱이 하는데
    // 캔버스에 매수·매도 칸이 없어 손절이 종목 선정 필터에 매달려 보였다.
    const withMethod = (method: string) => {
      // 재무 필터만 남긴다(매수 신호 없음) — 사용자 전략과 같은 모양.
      const input = confirmedInput("filterRankingEntry");
      const entry = { ...input.request!.entry, conditions: input.request!.entry!.conditions!.filter((c) => c.type === "filter") };
      const request = { ...input.request, entry, risk: { ...input.request!.risk, stop_loss_pct: 12, rebalance_method: method } };
      return buildLabGraph(buildStrategyGraph({ ...input, parsed: { ...input.parsed!, entry_signals: [] }, request }, META));
    };
    const flow = (g: ReturnType<typeof lab>) => g.edges.filter((e) => e.id.startsWith("flow:")).map((e) => `${e.source}->${e.target}`);
    const node = (g: ReturnType<typeof lab>, id: string) => g.nodes.find((n) => n.id === id);

    const swap = withMethod("reconstitute");
    expect(flow(swap)).toEqual(
      expect.arrayContaining(["stage:allocation->stage:rebalance", "stage:rebalance->stage:entry", "stage:rebalance->stage:exit"]),
    );
    // 손절은 위험 관리 칸에 매달리고 매도 칸에도 이어진다.
    expect(swap.edges.filter((e) => e.target === "item:setting:risk/stop_loss").map((e) => e.source).sort()).toEqual(["stage:exit", "stage:risk"]);
    expect(flow(swap).some((f) => f.endsWith("->stage:allocation") && f.startsWith("stage:entry"))).toBe(false);
    // 풀어 그린 칸은 전략 항목이 아니라 리밸런싱의 동작이다 — 편집·삭제는 리밸런싱으로 간다.
    expect(node(swap, "stage:entry")?.data.derivedFrom).toBe("rebalance");
    expect(node(swap, "item:derived:exit/rebalance")?.data.derivedFrom).toBe("rebalance");
    expect(node(swap, "item:derived:exit/rebalance")?.data.label).toBe("조건에서 빠진 종목 매도");
    // 종목 교체 항목은 매수·매도 칸에도 이어진다.
    expect(swap.edges.filter((e) => e.source === "item:setting:rebalance/reconstitute" && e.sourceHandle === "trade").map((e) => e.target).sort()).toEqual([
      "stage:entry",
      "stage:exit",
    ]);
    expect(node(swap, "item:setting:rebalance/reconstitute")?.data).toMatchObject({ swapTrade: true });
    // 손절은 매도 칸과 같은 줄이다.
    expect(node(swap, "stage:risk")!.position.y).toBe(node(swap, "stage:exit")!.position.y);

    // 비중만 조정하는 리밸런싱은 종목을 사고팔지 않으므로 매수·매도 칸을 지어내지 않는다.
    const weights = withMethod("weights_only");
    expect(weights.edges.some((e) => e.id.startsWith("swap:"))).toBe(false);
    expect(weights.nodes.some((n) => n.id === "stage:entry" || n.id === "stage:exit")).toBe(false);
    // 매수·매도 조건이 실제로 있으면 그 칸을 그대로 쓴다(풀어 그리지 않는다).
    expect(lab().nodes.some((n) => n.data.derivedFrom)).toBe(false);
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
