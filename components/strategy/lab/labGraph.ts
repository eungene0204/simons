import type { Edge, Node, NodeChange } from "@xyflow/react";
import { t } from "@/lib/i18n";
import type { GraphNode, NodeStatus, SectionKey, StrategyGraph } from "@/lib/strategy-graph/types";

// 전략 연구소 캔버스의 그래프 모델 — 전략 그래프(lib/strategy-graph, 스냅샷→그래프 순수 변환)를
// 고정 파이프라인 칸으로 배치한다. 칸 순서는 엔진 요청 구조 그대로라 사용자가 연결을 바꿀 수
// 없다(순환이 구조적으로 생기지 않는다). 칸 안의 조건은 칸 노드의 하단 보조 포트에 매달린다.
// 순수 함수만 둔다 — 입력(그래프)이 같으면 노드·엣지·좌표가 같다.

export type PipelineStage = SectionKey | "output";

/** 칸 순서 = 엔진이 전략을 실행하는 순서(종목 범위 → 선정 → 매매 → 배분 → 위험 → 백테스트). */
export const PIPELINE_ORDER: readonly PipelineStage[] = [
  "universe",
  "filters",
  "ranking",
  "entry",
  "exit",
  "allocation",
  "rebalance",
  "risk",
  "output",
];

/** 칸의 종류 — 아이콘을 고르는 축(색이 아니라 아이콘으로 구분한다, UI 가이드라인 §2 강조색 단일화). */
export type StageFamily = "universe" | "filter" | "signal" | "sizing" | "risk" | "output";

export const STAGE_FAMILY: Record<PipelineStage, StageFamily> = {
  universe: "universe",
  filters: "filter",
  ranking: "filter",
  entry: "signal",
  exit: "signal",
  allocation: "sizing",
  rebalance: "sizing",
  risk: "risk",
  output: "output",
};

export type LabNodeStatus = "ok" | "pending" | "unsupported" | "check";

export type PipelineNodeData = {
  stage: PipelineStage;
  family: StageFamily;
  label: string;
  /** 칸에 매달린 조건 수. */
  itemCount: number;
  /** 칸 결합 방식(모두 충족·하나라도 충족) — 스냅샷에 있을 때만. */
  logic: string | null;
  status: LabNodeStatus;
};

export type ConditionNodeData = {
  stage: PipelineStage;
  family: StageFamily;
  label: string;
  status: LabNodeStatus;
  graphNode: GraphNode;
};

export type LabNode = Node<PipelineNodeData, "pipeline"> | Node<ConditionNodeData, "condition">;

export type LabGraph = { nodes: LabNode[]; edges: Edge[] };

export const STAGE_GAP_X = 260;
export const CHILD_OFFSET_Y = 150;
export const CHILD_GAP_Y = 64;

const LEAF_KINDS = new Set(["condition", "risk", "setting"]);

function labStatus(status: NodeStatus): LabNodeStatus {
  if (status === "ok" || status === "not_applicable") return "ok";
  if (status === "pending") return "pending";
  if (status === "unsupported") return "unsupported";
  return "check";
}

const STATUS_RANK: Record<LabNodeStatus, number> = { ok: 0, check: 1, pending: 2, unsupported: 3 };

function worst(statuses: LabNodeStatus[]): LabNodeStatus {
  return statuses.reduce<LabNodeStatus>((acc, s) => (STATUS_RANK[s] > STATUS_RANK[acc] ? s : acc), "ok");
}

/** 칸 노드 밑의 잎(조건·위험·설정)을 그래프 순서대로 모은다 — 결합 그룹은 칸의 logic으로 접는다. */
function sectionLeaves(graph: StrategyGraph, sectionId: string): { leaves: GraphNode[]; logic: string | null } {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const children = (id: string) =>
    graph.edges
      .filter((e) => e.source === id && (e.kind === "contains" || e.kind === "combined_by"))
      .map((e) => byId.get(e.target))
      .filter((n): n is GraphNode => !!n);
  const leaves: GraphNode[] = [];
  let logic: string | null = null;
  const walk = (id: string) => {
    for (const child of children(id)) {
      if (child.kind === "group") {
        logic ??= child.label;
        walk(child.id);
      } else if (LEAF_KINDS.has(child.kind)) {
        leaves.push(child);
      }
    }
  };
  walk(sectionId);
  return { leaves, logic };
}

// 칸 배치 — 매수까지는 한 줄로 이어지고, 그 뒤 청산 · 배분(비중→리밸런싱) · 위험 관리가 나란히 갈라져
// 백테스트에서 다시 합쳐진다(n8n의 분기·병합 모양). 갈래는 서로 독립이라 순서를 주장하지 않는다.
// 없는 칸은 건너뛰고 가까운 앞 칸에 잇는다. 선은 앞→뒤로만 가서 순환이 생기지 않는다.
const STAGE_PARENT: Partial<Record<PipelineStage, PipelineStage>> = {
  filters: "universe",
  ranking: "filters",
  entry: "ranking",
  exit: "entry",
  allocation: "entry",
  rebalance: "allocation",
  risk: "entry",
};

/** 같은 갈래(줄)에 놓이는 칸 — 줄 번호가 작을수록 위. */
const STAGE_LANE: Record<PipelineStage, number> = {
  universe: 0,
  filters: 0,
  ranking: 0,
  entry: 0,
  exit: 0,
  allocation: 1,
  rebalance: 1,
  risk: 2,
  output: 1, // 실제 줄은 갈래들의 가운데로 정한다(laneOf)
};

const LANE_MIN_HEIGHT = 190;

/** 전략 그래프 → 캔버스 노드·엣지. 그래프에 없는 칸은 그리지 않는다. 백테스트 칸은 그리지 않는다(2026-10-28 — 보여줄 필요 없음). */
export function buildLabGraph(graph: StrategyGraph | null): LabGraph {
  if (!graph || !graph.nodes.some((n) => n.kind === "section")) return { nodes: [], edges: [] };

  type Present = { stage: PipelineStage; section?: GraphNode; leaves: GraphNode[]; logic: string | null };
  const present = new Map<PipelineStage, Present>();
  for (const stage of PIPELINE_ORDER) {
    if (stage === "output") continue;
    const section = graph.nodes.find((n) => n.kind === "section" && n.section === stage);
    if (!section) continue;
    present.set(stage, { stage, section, ...sectionLeaves(graph, section.id) });
  }

  const parentOf = (stage: PipelineStage): PipelineStage | null => {
    let p = STAGE_PARENT[stage];
    while (p && !present.has(p)) p = STAGE_PARENT[p];
    return p ?? null;
  };
  const depth = new Map<PipelineStage, number>();
  const depthOf = (stage: PipelineStage): number => {
    if (stage === "output") return 0;
    const cached = depth.get(stage);
    if (cached !== undefined) return cached;
    const p = parentOf(stage);
    const d = p ? depthOf(p) + 1 : 0;
    depth.set(stage, d);
    return d;
  };
  const stages = PIPELINE_ORDER.filter((s) => present.has(s));
  const bodyStages = stages.filter((s) => s !== "output");

  // 줄 높이 = 그 줄 칸들에 매달린 조건 중 가장 긴 것 — 아래 줄과 겹치지 않게 위에서부터 쌓는다.
  const bodyLanes = [...new Set(bodyStages.map((s) => STAGE_LANE[s]))].sort((a, b) => a - b);
  const laneOf = (stage: PipelineStage) => STAGE_LANE[stage];
  const usedLanes = bodyLanes;
  const laneTop = new Map<number, number>();
  let cursor = 0;
  for (const lane of usedLanes) {
    laneTop.set(lane, cursor);
    const tallest = Math.max(
      0,
      ...stages.filter((s) => laneOf(s) === lane).map((s) => (present.get(s)!.leaves.length > 0 ? CHILD_OFFSET_Y + present.get(s)!.leaves.length * CHILD_GAP_Y : 0)),
    );
    cursor += Math.max(LANE_MIN_HEIGHT, tallest);
  }

  const nodes: LabNode[] = [];
  const edges: Edge[] = [];

  for (const stage of stages) {
    const { section, leaves, logic } = present.get(stage)!;
    const family = STAGE_FAMILY[stage];
    const x = depthOf(stage) * STAGE_GAP_X;
    const y = laneTop.get(laneOf(stage)) ?? 0;
    const id = `stage:${stage}`;

    if (!section) continue;
    const leafStatuses = leaves.map((leaf) => labStatus(leaf.status));
    const pipelineData: PipelineNodeData = {
      stage,
      family,
      label: section.label,
      itemCount: leaves.length,
      logic,
      status: worst([labStatus(section.status), ...leafStatuses]),
    };
    leaves.forEach((leaf, index) => {
      const childId = `item:${leaf.id}`;
      nodes.push({
        id: childId,
        type: "condition",
        position: { x: x + 10, y: y + CHILD_OFFSET_Y + index * CHILD_GAP_Y },
        data: { stage, family, label: leaf.label, status: leafStatuses[index], graphNode: leaf },
        connectable: false,
      });
      edges.push({
        id: `sub:${id}->${childId}`,
        source: id,
        sourceHandle: "aux",
        target: childId,
        targetHandle: "top",
        type: "smoothstep",
        className: "lab-edge-aux",
        // 항목 수는 칸 아래 항목으로 이어지는 선에 단다 — 칸 사이 흐름 선에 달면 항목이 다음 칸으로 넘어가는 것처럼 읽힌다.
        label: index === 0 ? t("{0}개 항목", leaves.length) : undefined,
        selectable: false,
      });
    });

    nodes.push({ id, type: "pipeline", position: { x, y }, data: pipelineData, connectable: false });
  }

  // 흐름 선: 칸 → 부모 칸.
  const link = (from: PipelineStage, to: PipelineStage) =>
    edges.push({
      id: `flow:stage:${from}->stage:${to}`,
      source: `stage:${from}`,
      sourceHandle: "out",
      target: `stage:${to}`,
      targetHandle: "in",
      type: "default",
      className: "lab-edge-flow",
      selectable: false,
    });
  for (const stage of bodyStages) {
    const p = parentOf(stage);
    if (p) link(p, stage);
  }
  return { nodes, edges };
}

/** 노드 내용이 바뀐 것을 가리는 서명 — 새로 생기거나 바뀐 노드만 짧게 강조한다. */
export function nodeSignature(node: LabNode): string {
  const d = node.data;
  return node.type === "pipeline"
    ? `${d.label}|${(d as PipelineNodeData).itemCount}|${(d as PipelineNodeData).logic}|${d.status}`
    : `${d.label}|${d.status}`;
}

/** 이전 그래프 대비 새로 생기거나 내용이 바뀐 노드 id. 첫 그래프(이전 없음)는 전부 새 노드다. */
export function changedNodeIds(previous: readonly LabNode[], next: readonly LabNode[]): string[] {
  const before = new Map(previous.map((n) => [n.id, nodeSignature(n)]));
  return next.filter((n) => before.get(n.id) !== nodeSignature(n)).map((n) => n.id);
}

/**
 * 칸 노드를 끌면 그 칸에 매달린 조건 노드도 같은 만큼 따라 움직인다. 칸 노드의 위치 변경마다
 * 자식 조건의 위치 변경을 덧붙인다 — 자식이 이미 함께 끌리는 중(다중 선택)이면 두 번 옮기지 않는다.
 */
export function followStageDrag(changes: NodeChange<LabNode>[], nodes: readonly LabNode[]): NodeChange<LabNode>[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const moving = new Set(changes.filter((c) => c.type === "position").map((c) => (c as { id: string }).id));
  const extra: NodeChange<LabNode>[] = [];
  for (const change of changes) {
    if (change.type !== "position" || !change.position) continue;
    const parent = byId.get(change.id);
    if (parent?.type !== "pipeline") continue;
    const dx = change.position.x - parent.position.x;
    const dy = change.position.y - parent.position.y;
    if (dx === 0 && dy === 0) continue;
    for (const child of nodes) {
      if (child.type !== "condition" || child.data.stage !== parent.data.stage || moving.has(child.id)) continue;
      extra.push({
        id: child.id,
        type: "position",
        position: { x: child.position.x + dx, y: child.position.y + dy },
        dragging: change.dragging,
      });
    }
  }
  return extra.length > 0 ? [...changes, ...extra] : changes;
}

// ── 캔버스 삭제 → 전략 항목 ─────────────────────────────────────────────────────────────────
// 캔버스의 조건은 엔진 요청(컴파일 결과) 기준이고, 지우기는 해석 결과(parsed)의 항목 단위다.
// 둘은 1:1이 아니다(재무 필터가 매수 조건으로 컴파일되는 등) — 그래서 칸 단위로 후보 항목을
// 보여 주고 사용자가 고르게 한다. 짐작으로 한 항목을 골라 지우지 않는다.

const STAGE_ITEM_IDS: Record<PipelineStage, (id: string) => boolean> = {
  universe: (id) => id === "universe",
  filters: (id) => id.startsWith("fundamental."),
  ranking: () => false,
  entry: (id) => id.startsWith("entry.") || id.startsWith("fundamental."),
  exit: (id) => id.startsWith("exit.") || id === "hold_period",
  allocation: (id) => id === "max_positions",
  rebalance: (id) => id === "rebalancing" || id === "rebalance_method",
  risk: (id) => id === "stop_loss" || id === "take_profit" || id === "trailing_stop",
  output: (id) => id === "backtest_period" || id === "initial_capital",
};

/** 칸에서 지울 수 있는 전략 항목 후보(순서 보존). */
export function itemsForStage<T extends { id: string }>(stage: PipelineStage, items: readonly T[]): T[] {
  return items.filter((item) => STAGE_ITEM_IDS[stage](item.id));
}
