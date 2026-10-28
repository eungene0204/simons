import type { Edge, Node } from "@xyflow/react";
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

/** 전략 그래프 → 캔버스 노드·엣지. 그래프에 없는 칸은 그리지 않고, 끝에는 항상 백테스트 칸이 온다. */
export function buildLabGraph(graph: StrategyGraph | null): LabGraph {
  if (!graph || !graph.nodes.some((n) => n.kind === "section")) return { nodes: [], edges: [] };

  const nodes: LabNode[] = [];
  const edges: Edge[] = [];
  let column = 0;
  let previous: { id: string; itemCount: number } | null = null;

  for (const stage of PIPELINE_ORDER) {
    const family = STAGE_FAMILY[stage];
    const x = column * STAGE_GAP_X;
    let pipelineData: PipelineNodeData;
    const id = `stage:${stage}`;

    if (stage === "output") {
      pipelineData = { stage, family, label: t("백테스트"), itemCount: 0, logic: null, status: "ok" };
    } else {
      const section = graph.nodes.find((n) => n.kind === "section" && n.section === stage);
      if (!section) continue;
      const { leaves, logic } = sectionLeaves(graph, section.id);
      const leafStatuses = leaves.map((leaf) => labStatus(leaf.status));
      pipelineData = {
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
          position: { x: x + 10, y: CHILD_OFFSET_Y + index * CHILD_GAP_Y },
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
          selectable: false,
        });
      });
    }

    nodes.push({ id, type: "pipeline", position: { x, y: 0 }, data: pipelineData, connectable: false });
    if (previous) {
      edges.push({
        id: `flow:${previous.id}->${id}`,
        source: previous.id,
        sourceHandle: "out",
        target: id,
        targetHandle: "in",
        type: "default",
        label: previous.itemCount > 0 ? t("{0}개 항목", previous.itemCount) : undefined,
        className: "lab-edge-flow",
        selectable: false,
      });
    }
    previous = { id, itemCount: pipelineData.itemCount };
    column += 1;
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
