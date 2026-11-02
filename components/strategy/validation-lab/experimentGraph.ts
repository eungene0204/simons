import type { ReactNode } from "react";
import type { Edge, Node } from "@xyflow/react";
import { t } from "@/lib/i18n";

// 검증 연구소 캔버스(모니터)의 그래프 모델 — 아래 조정 칸에서 정한 실험(워크포워드·몬테카를로) 설정을
// "입력 → 처리 → 결과" 단계 노드로 비추고, 실행하면 결과 판까지 같은 캔버스에 붙인다. 노드 순서는 실험이
// 실제로 계산되는 순서 그대로다. 노드 자리는 옮길 수 있고, 조정 칸에 컨트롤이 있는 값은 노드에서 바로 고친다
// (RowEdit — 고친 값은 조정 칸과 같은 설정으로 들어가 양쪽이 함께 바뀐다).
// 순수 함수만 둔다 — 설계(입력)가 같으면 노드·엣지·좌표가 같다. 세로 위치는 측정 높이로 쌓는다(stackNodes).

export type ExperimentIcon = "data" | "split" | "optimize" | "test" | "aggregate" | "resample" | "paths" | "distribution" | "run";

/** ready=설정 완료, blocked=이 단계 설정 때문에 실행 불가, running=계산 중, done=결과 있음. */
export type ExperimentStatus = "ready" | "blocked" | "running" | "done";

/**
 * 노드에서 바로 고치는 칸 — key가 어떤 설정인지 알리고, 고친 값은 아래 조정 칸과 같은 경로로 들어간다.
 * number=직접 입력(범위 밖은 조정 칸 규칙대로 잘린다), select=조정 칸의 선택지 그대로, open=조정 칸의 설정 창을 연다.
 */
export type RowEdit =
  | { kind: "number"; key: string; value: number; min: number; max: number; suffix: string }
  | { kind: "select"; key: string; value: string; options: Array<{ value: string; label: string }> }
  | { kind: "open"; key: string };

export type ExperimentNodeData = {
  /** 노드를 누르면 이동할 조정 칸(설정) 구역 id. */
  section: string;
  /** 단계 번호 — 없으면 번호 없이 kicker만 적는다(실행 계획처럼 단계가 아닌 상태 노드). */
  index?: number;
  kicker: string;
  title: string;
  icon: ExperimentIcon;
  rows: Array<{ label: string; value: string; edit?: RowEdit }>;
  /** 행 아래에 붙이는 문장 — warn=실행을 막는 사유. */
  footnote?: { tone: "warn" | "muted"; lines: string[] };
  status: ExperimentStatus;
  /** 아래에 딸린 노드(창 배치·결과 판)로 내려가는 연결점을 단다. */
  hasDetail?: boolean;
  /** 번호 없는 상태 노드가 앞 단계에서 이어지는 연결점(왼쪽)을 단다. */
  hasIn?: boolean;
};

/** 워크포워드 창 하나 — 거래일 인덱스, 끝은 포함하지 않는다. */
export type WindowSpan = { window: number; isStart: number; isEnd: number; oosStart: number; oosEnd: number };

export type WindowOutcome = { window: number; isCagr: number | null; oosCagr: number | null };

/** 창 분할 단계 아래에 붙는 창 배치 노드 — 창마다 학습·검증 막대를 같은 시간축에 쌓는다. */
export type ScheduleNodeData = {
  section: string;
  spans: WindowSpan[];
  totalBars: number;
  dates: string[];
  anchor: boolean;
  trainBars: number;
  validationBars: number;
  outcomes?: WindowOutcome[];
};

/** 실행 결과 판 — 내용은 결과를 그리는 쪽이 slot 요소에 포털로 넣는다(상태·저장 버튼을 그쪽이 쥔다). */
export type ReportNodeData = {
  slot: (element: HTMLDivElement | null) => void;
  width: number;
  /** 위 결과 단계에서 내려오는 연결점의 가로 위치(노드 왼쪽 기준). */
  handleX: number;
  testId: string;
};

/** 실험 왼쪽 열의 참고 노드(검증 대상 전략·방법) — 내용은 그리는 쪽이 넣는다. */
export type ContextNodeData = {
  content: ReactNode;
  testId: string;
  /** 첫 단계로 이어지는 연결점을 단다. */
  hasOut: boolean;
};

export type ExperimentNode = Node<ExperimentNodeData, "experiment">;
export type ScheduleNode = Node<ScheduleNodeData, "schedule">;
export type ReportNode = Node<ReportNodeData, "report">;
export type ContextNode = Node<ContextNodeData, "context">;
export type CanvasNode = ExperimentNode | ScheduleNode | ReportNode | ContextNode;
/** stack: 노드 id → 그 노드를 내려놓을 기준 노드 id들(그 중 가장 아래 끝 밑으로 간다). */
export type ExperimentGraph = { nodes: CanvasNode[]; edges: Edge[]; stack: Record<string, string[]> };

export const EXPERIMENT_NODE_W = 212;
export const EXPERIMENT_GAP_X = 248;
/** 창 배치 노드는 창 분할~검증 단계 밑을 가로지른다 — 결과 단계 밑은 결과 판으로 내려가는 선 자리로 비운다. */
export const SCHEDULE_NODE_W = EXPERIMENT_GAP_X * 2 + EXPERIMENT_NODE_W;
export const STACK_GAP_Y = 44;
export const CONTEXT_NODE_W = 280;

const stepCenterX = (index: number) => index * EXPERIMENT_GAP_X + EXPERIMENT_NODE_W / 2;

/**
 * stack에 적힌 노드를 기준 노드들의 측정 높이 기준 가장 아래 끝에서 STACK_GAP_Y만큼 밑으로 내린다.
 * 노드 배열 순서대로 처리하므로 기준 노드가 먼저 나와야 한다. 기준 중 하나라도 아직 측정 전이면 그대로 둔다.
 * 위치가 그대로인 노드는 같은 객체를 돌려준다.
 */
export function stackNodes<T extends Node>(nodes: T[], stack: Record<string, string[]>): T[] {
  const placed = new Map<string, T>();
  return nodes.map((node) => {
    let next = node;
    const anchors = stack[node.id];
    if (anchors && anchors.length > 0) {
      let bottom = -Infinity;
      let ready = true;
      for (const id of anchors) {
        const anchor = placed.get(id);
        const h = anchor?.measured?.height;
        if (!anchor) continue;
        if (h == null) {
          ready = false;
          break;
        }
        bottom = Math.max(bottom, anchor.position.y + h);
      }
      if (ready && Number.isFinite(bottom)) {
        const y = bottom + STACK_GAP_Y;
        if (y !== node.position.y) next = { ...node, position: { ...node.position, y } };
      }
    }
    placed.set(next.id, next);
    return next;
  });
}

/**
 * 학습·검증 거래일 수로 창을 배치한다 — 백엔드 `WalkForwardAnalyzer._split_windows`의 명시 bars 규칙과 같다.
 * 롤링: 학습 창이 검증 길이만큼 함께 밀린다. 확장: 학습 시작은 첫날에 고정되고 끝만 늘어난다.
 * 검증 길이를 다 채우지 못하는 마지막 조각 창은 만들지 않는다.
 */
export function buildWindowSchedule(totalBars: number, trainBars: number, validationBars: number, anchor: boolean): WindowSpan[] {
  if (trainBars <= 0 || validationBars <= 0 || trainBars + validationBars > totalBars) return [];
  const out: WindowSpan[] = [];
  for (let k = 0; ; k += 1) {
    const isEnd = trainBars + k * validationBars;
    const oosEnd = isEnd + validationBars;
    if (oosEnd > totalBars) break;
    out.push({ window: k + 1, isStart: anchor ? 0 : k * validationBars, isEnd, oosStart: isEnd, oosEnd });
  }
  return out;
}

/** 날짜 문자열 정렬 목록에서 date 이상이 처음 나오는 인덱스. */
function lowerBound(dates: string[], date: string): number {
  let lo = 0;
  let hi = dates.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] < date) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * 결과 창의 기간 문자열("YYYY-MM-DD ~ YYYY-MM-DD")을 거래일 인덱스로 되돌린다 — 결과가 있을 때 배치도는
 * 지금 폼 설정이 아니라 그 결과를 실제로 만든 창을 그린다(저장 결과를 불러오면 폼과 다를 수 있다).
 * 기간을 읽을 수 없는 창이 하나라도 있으면 null.
 */
export function scheduleFromPeriods(
  dates: string[],
  windows: Array<{ window: number; isPeriod: string; oosPeriod: string }>,
): WindowSpan[] | null {
  if (dates.length < 2 || windows.length === 0) return null;
  const parse = (period: string) => {
    const [start, end] = period.split("~").map((part) => part.trim());
    return start && end ? { start: lowerBound(dates, start), end: lowerBound(dates, end) + 1 } : null;
  };
  const out: WindowSpan[] = [];
  for (const w of windows) {
    const is = parse(w.isPeriod);
    const oos = parse(w.oosPeriod);
    if (!is || !oos) return null;
    out.push({ window: w.window, isStart: is.start, isEnd: Math.min(is.end, dates.length), oosStart: oos.start, oosEnd: Math.min(oos.end, dates.length) });
  }
  return out;
}

export type WalkForwardDesign = {
  periodLabel: string;
  totalBars: number;
  trainBars: number;
  validationBars: number;
  anchor: boolean;
  windows: number;
  methodLabel: string;
  targetMetricLabel: string;
  /** 최적화 대상 파라미터 — range는 조정 칸 표기 그대로("1.8%p~22.5%p · STEP 2.5%p"). */
  parameters: Array<{ id: string; label: string; range: string; excluded: boolean }>;
  /** 있으면 노드에서 설정을 고칠 수 있다 — 결과가 있거나 실행 중이면 null(조정 칸도 잠긴다). */
  edit?: {
    windowBarsMin: number;
    windowBarsMax: number;
    trainRatioMin: number;
    trainRatioMax: number;
    method: "grid" | "bayesian";
    trials: number;
    trialOptions: number[];
  } | null;
  /** 실행을 막는 설정이 어느 단계에 있는가(없으면 null). */
  blockedAt: "split" | "optimize" | null;
  running: boolean;
  /** 실행 계획(총 백테스트·예상 시간·실행 불가 사유). 결과가 있으면 그리지 않는다. */
  plan?: { totalBacktests: number; estimateLabel: string; blockedReason: string | null; suggestions: string[]; note: string | null };
  /** 있으면 창 분할 단계 밑에 창 배치 노드를 붙인다. */
  schedule?: { spans: WindowSpan[]; dates: string[]; outcomes?: WindowOutcome[] };
  /** 있고 결과가 있으면 결과 단계 밑에 결과 판을 붙인다. */
  reportSlot?: ReportNodeData["slot"];
  result: {
    /** null = 학습 평균 CAGR ≤ 0이라 해석 불가. */
    wfe: number | null;
    wfeTierText: string | null;
    avgOosCagr: number | null;
    windowsDone: number;
  } | null;
};

export type MonteCarloDesign = {
  sourceLabel: string;
  sourceDetail: string;
  methodLabel: string;
  iterations: number;
  seed: number;
  running: boolean;
  /** 있으면 노드에서 방식·반복 횟수를 고칠 수 있다. 선택지는 조정 칸의 버튼과 같다. */
  edit?: { methodValue: string; methodOptions: Array<{ value: string; label: string }>; iterationOptions: number[] } | null;
  /** 있으면 결과 단계 밑에 결과 판(실행 전 안내 포함)을 붙인다. */
  reportSlot?: ReportNodeData["slot"];
  result: {
    cagrMedian: number;
    cagrP05: number;
    mddMedian: number;
    probPositive: number;
  } | null;
};

/** 노드에서 고친 워크포워드 설정 — 조정 칸의 같은 컨트롤이 하는 일을 그대로 한다. */
export type WalkForwardEdit =
  | { field: "anchor"; value: boolean }
  | { field: "windowBars"; value: number }
  | { field: "trainRatioPct"; value: number }
  | { field: "method"; method: "grid" | "bayesian"; trials?: number }
  | { field: "parameter"; id: string };

const PARAM_KEY = "wf.param:";
const BAYESIAN_VALUE = "bayesian:";

/** RowEdit의 key·값을 워크포워드 설정 변경으로 되돌린다. 워크포워드 칸이 아니면 null. */
export function parseWalkForwardEdit(key: string, value: string | number | null): WalkForwardEdit | null {
  if (key === "wf.anchor") return { field: "anchor", value: value === "anchored" };
  if (key === "wf.windowBars" && typeof value === "number") return { field: "windowBars", value };
  if (key === "wf.trainRatioPct" && typeof value === "number") return { field: "trainRatioPct", value };
  if (key === "wf.method" && typeof value === "string") {
    if (value === "grid") return { field: "method", method: "grid" };
    const trials = Number(value.slice(BAYESIAN_VALUE.length));
    return value.startsWith(BAYESIAN_VALUE) && trials > 0 ? { field: "method", method: "bayesian", trials } : null;
  }
  if (key.startsWith(PARAM_KEY)) return { field: "parameter", id: key.slice(PARAM_KEY.length) };
  return null;
}

const bars = (n: number) => t("{0}거래일", n.toLocaleString());
const pct = (ratio: number) => `${(ratio * 100).toFixed(1)}%`;

/** 창 배치의 첫 검증 시작일 ~ 마지막 검증 종료일. 날짜를 짚을 수 없으면 null. */
function validationPeriodLabel(schedule: WalkForwardDesign["schedule"]): string | null {
  if (!schedule || schedule.spans.length === 0) return null;
  const start = schedule.dates[schedule.spans[0].oosStart];
  const end = schedule.dates[schedule.spans[schedule.spans.length - 1].oosEnd - 1];
  return start && end ? `${start} ~ ${end}` : null;
}

function layout(steps: Array<Omit<ExperimentNodeData, "index">>, edgeLabels: Array<string | null>): ExperimentGraph {
  const nodes: ExperimentNode[] = steps.map((step, index) => ({
    id: step.section,
    type: "experiment",
    position: { x: index * EXPERIMENT_GAP_X, y: 0 },
    data: { ...step, index },
  }));
  const edges: Edge[] = nodes.slice(1).map((node, i) => ({
    id: `${nodes[i].id}->${node.id}`,
    source: nodes[i].id,
    target: node.id,
    sourceHandle: "out",
    targetHandle: "in",
    type: "smoothstep",
    animated: steps[i + 1].status === "running",
    ...(edgeLabels[i] ? { label: edgeLabels[i] as string } : {}),
  }));
  return { nodes, edges, stack: {} };
}

/** 단계 노드 아래로 내려가는 보조 점선. */
const detailEdge = (source: string, target: string): Edge => ({
  id: `${source}->${target}`,
  source,
  target,
  sourceHandle: "detail",
  targetHandle: "in",
  type: "straight",
  className: "lab-edge-aux",
});

const reportNode = (id: string, slot: ReportNodeData["slot"], width: number, resultStepIndex: number, testId: string): ReportNode => ({
  id,
  type: "report",
  position: { x: 0, y: 0 },
  data: { slot, width, handleX: stepCenterX(resultStepIndex), testId },
});

export function buildWalkForwardGraph(d: WalkForwardDesign): ExperimentGraph {
  const done = d.result !== null;
  const stepStatus = (blockedHere: boolean): ExperimentStatus =>
    done ? "done" : d.running ? "running" : blockedHere ? "blocked" : "ready";
  const withReport = done && d.reportSlot !== undefined;
  const validationPeriod = validationPeriodLabel(d.schedule);
  const e = d.edit ?? null;
  const windowBars = d.trainBars + d.validationBars;
  const trainRatioPct = Math.round((d.trainBars / Math.max(windowBars, 1)) * 100);
  const graph = layout(
    [
      {
        section: "wf-data",
        kicker: t("입력"),
        title: t("표본 기간"),
        icon: "data",
        rows: [
          { label: t("기간"), value: d.periodLabel },
          { label: t("관측치"), value: bars(d.totalBars) },
        ],
        status: done ? "done" : "ready",
      },
      {
        section: "wf-split",
        kicker: t("설계"),
        title: t("창 분할"),
        icon: "split",
        rows: [
          {
            label: t("방식"),
            value: d.anchor ? t("확장") : t("롤링"),
            ...(e && {
              edit: {
                kind: "select" as const,
                key: "wf.anchor",
                value: d.anchor ? "anchored" : "rolling",
                options: [
                  { value: "rolling", label: t("롤링") },
                  { value: "anchored", label: t("확장") },
                ],
              },
            }),
          },
          {
            label: t("구간 길이"),
            value: bars(windowBars),
            ...(e && {
              edit: { kind: "number" as const, key: "wf.windowBars", value: windowBars, min: e.windowBarsMin, max: e.windowBarsMax, suffix: t("거래일") },
            }),
          },
          {
            label: t("학습 비중"),
            value: `${trainRatioPct}%`,
            ...(e && {
              edit: { kind: "number" as const, key: "wf.trainRatioPct", value: trainRatioPct, min: e.trainRatioMin, max: e.trainRatioMax, suffix: "%" },
            }),
          },
          { label: t("학습 · 검증"), value: `${bars(d.trainBars)} · ${bars(d.validationBars)}` },
          { label: t("창 수"), value: t("{0}개", d.windows) },
        ],
        status: stepStatus(d.blockedAt === "split"),
        hasDetail: d.schedule !== undefined,
      },
      {
        section: "wf-optimize",
        kicker: t("학습 구간"),
        title: t("파라미터 탐색"),
        icon: "optimize",
        rows: [
          {
            label: t("방법"),
            value: d.methodLabel,
            ...(e && {
              edit: {
                kind: "select" as const,
                key: "wf.method",
                value: e.method === "grid" ? "grid" : `${BAYESIAN_VALUE}${e.trials}`,
                options: [
                  { value: "grid", label: t("그리드 탐색") },
                  ...e.trialOptions.map((n) => ({ value: `${BAYESIAN_VALUE}${n}`, label: t("베이지안 {0}회", n) })),
                ],
              },
            }),
          },
          { label: t("목표"), value: d.targetMetricLabel },
          ...(d.parameters.length === 0
            ? [{ label: t("대상"), value: t("없음") }]
            : d.parameters.map((p) => ({
                label: p.label,
                value: p.excluded ? t("제외됨") : p.range,
                ...(e && { edit: { kind: "open" as const, key: `${PARAM_KEY}${p.id}` } }),
              }))),
        ],
        status: stepStatus(d.blockedAt === "optimize"),
      },
      {
        section: "wf-test",
        kicker: t("검증 구간"),
        title: t("처음 보는 구간에 적용"),
        icon: "test",
        rows: [
          ...(validationPeriod ? [{ label: t("기간"), value: validationPeriod }] : []),
          ...(done
            ? [
                { label: t("완료 창"), value: t("{0}개", d.result!.windowsDone) },
                { label: t("검증 평균 CAGR"), value: d.result!.avgOosCagr == null ? "—" : `${d.result!.avgOosCagr.toFixed(1)}%` },
              ]
            : []),
        ],
        status: stepStatus(false),
      },
      {
        section: "wf-result",
        kicker: t("결과"),
        title: t("워크포워드 효율(WFE)"),
        icon: "aggregate",
        rows: done
          ? [
              { label: "WFE", value: d.result!.wfe == null ? t("해석 불가") : pct(d.result!.wfe) },
              ...(d.result!.wfeTierText ? [{ label: t("해석"), value: d.result!.wfeTierText }] : []),
            ]
          : [{ label: t("계산"), value: t("검증 CAGR ÷ 학습 CAGR") }],
        status: done ? "done" : d.running ? "running" : "ready",
        hasDetail: withReport,
      },
    ],
    [null, t("창 ×{0}", d.windows), t("최적값"), null],
  );
  const steps = graph.nodes.map((n) => n.id);
  const nodes: CanvasNode[] = [...graph.nodes];
  const edges = [...graph.edges];
  const stack: Record<string, string[]> = {};
  const below: string[] = [...steps];

  if (d.plan && !done) {
    const p = d.plan;
    nodes.push({
      id: "wf-plan",
      type: "experiment",
      // 결과 단계 바로 오른쪽 — 파이프라인의 맨 끝에 이어 붙는다.
      position: { x: steps.length * EXPERIMENT_GAP_X, y: 0 },
      data: {
        section: "wf-optimize",
        hasIn: true,
        kicker: t("실행"),
        title: t("실행 계획"),
        icon: "run",
        rows: [
          { label: t("총 백테스트"), value: t("{0}회", p.totalBacktests.toLocaleString()) },
          { label: t("예상 시간"), value: p.blockedReason ? t("실행 불가") : p.estimateLabel },
        ],
        ...(p.blockedReason
          ? { footnote: { tone: "warn" as const, lines: [p.blockedReason, ...p.suggestions] } }
          : p.note
            ? { footnote: { tone: "muted" as const, lines: [p.note] } }
            : {}),
        status: d.running ? "running" : p.blockedReason ? "blocked" : "ready",
      },
    });
    edges.push({
      id: "wf-result->wf-plan",
      source: "wf-result",
      target: "wf-plan",
      sourceHandle: "out",
      targetHandle: "in",
      type: "smoothstep",
      animated: d.running,
    });
  }
  if (d.schedule) {
    nodes.push({
      id: "wf-schedule",
      type: "schedule",
      position: { x: EXPERIMENT_GAP_X, y: 0 },
      data: {
        section: "wf-split",
        spans: d.schedule.spans,
        totalBars: d.totalBars,
        dates: d.schedule.dates,
        anchor: d.anchor,
        trainBars: d.trainBars,
        validationBars: d.validationBars,
        outcomes: d.schedule.outcomes,
      },
    });
    edges.push(detailEdge("wf-split", "wf-schedule"));
    stack["wf-schedule"] = steps;
    below.push("wf-schedule");
  }
  if (withReport) {
    nodes.push(reportNode("wf-report", d.reportSlot!, EXPERIMENT_GAP_X * 4 + EXPERIMENT_NODE_W, 4, "walk-forward-report-node"));
    edges.push(detailEdge("wf-result", "wf-report"));
    stack["wf-report"] = below;
  }
  return { nodes, edges, stack };
}

/**
 * 참고 노드를 첫 단계 왼쪽 열에 위에서부터 쌓는다 — 첫 노드(검증 대상 전략)는 첫 단계로 점선을 잇는다.
 * 단계 노드의 좌표는 그대로 두고 열만 음수 x에 더한다(캔버스가 왼쪽 끝까지 맞춘다).
 */
export function attachContextNodes(graph: ExperimentGraph, items: Array<{ id: string; content: ReactNode; testId: string }>): ExperimentGraph {
  if (items.length === 0 || graph.nodes.length === 0) return graph;
  const first = graph.nodes[0].id;
  const x = -(CONTEXT_NODE_W + EXPERIMENT_GAP_X - EXPERIMENT_NODE_W);
  const nodes: ContextNode[] = items.map((item, index) => ({
    id: item.id,
    type: "context",
    position: { x, y: 0 },
    data: { content: item.content, testId: item.testId, hasOut: index === 0 },
  }));
  const stack = { ...graph.stack };
  nodes.slice(1).forEach((node, index) => {
    stack[node.id] = [nodes[index].id];
  });
  return {
    nodes: [...nodes, ...graph.nodes],
    edges: [
      { id: `${nodes[0].id}->${first}`, source: nodes[0].id, target: first, sourceHandle: "out", targetHandle: "in", type: "smoothstep", className: "lab-edge-aux" },
      ...graph.edges,
    ],
    stack,
  };
}

export function buildMonteCarloGraph(d: MonteCarloDesign): ExperimentGraph {
  const done = d.result !== null;
  const status: ExperimentStatus = done ? "done" : d.running ? "running" : "ready";
  const graph = layout(
    [
      {
        section: "mc-data",
        kicker: t("입력"),
        title: t("원본 표본"),
        icon: "data",
        rows: [
          { label: t("단위"), value: d.sourceLabel },
          { label: t("표본"), value: d.sourceDetail },
        ],
        status: done ? "done" : "ready",
      },
      {
        section: "mc-resample",
        kicker: t("설계"),
        title: t("재표본 방식"),
        icon: "resample",
        rows: [
          {
            label: t("방식"),
            value: d.methodLabel,
            ...(d.edit && { edit: { kind: "select" as const, key: "mc.method", value: d.edit.methodValue, options: d.edit.methodOptions } }),
          },
        ],
        status,
      },
      {
        section: "mc-paths",
        kicker: t("처리"),
        title: t("가상 시나리오"),
        icon: "paths",
        rows: [
          {
            label: t("반복"),
            value: t("{0}회", d.iterations.toLocaleString()),
            ...(d.edit && {
              edit: {
                kind: "select" as const,
                key: "mc.iterations",
                value: String(d.iterations),
                options: d.edit.iterationOptions.map((n) => ({ value: String(n), label: t("{0}회", n.toLocaleString()) })),
              },
            }),
          },
          { label: "seed", value: String(d.seed) },
        ],
        status,
      },
      {
        section: "mc-result",
        kicker: t("결과"),
        title: t("성과 분포"),
        icon: "distribution",
        rows: done
          ? [
              { label: t("CAGR 중앙값"), value: pct(d.result!.cagrMedian) },
              { label: t("CAGR 하위 5%"), value: pct(d.result!.cagrP05) },
              { label: t("MDD 중앙값"), value: pct(d.result!.mddMedian) },
              { label: t("양수 CAGR 확률"), value: pct(d.result!.probPositive) },
            ]
          : [{ label: t("집계"), value: t("CAGR · MDD · 샤프 분포") }],
        status,
        hasDetail: d.reportSlot !== undefined,
      },
    ],
    [null, t("×{0}", d.iterations.toLocaleString()), null],
  );
  if (!d.reportSlot) return graph;
  return {
    nodes: [...graph.nodes, reportNode("mc-report", d.reportSlot, EXPERIMENT_GAP_X * 3 + EXPERIMENT_NODE_W, 3, "monte-carlo-report-node")],
    edges: [...graph.edges, detailEdge("mc-result", "mc-report")],
    stack: { "mc-report": graph.nodes.map((n) => n.id) },
  };
}
