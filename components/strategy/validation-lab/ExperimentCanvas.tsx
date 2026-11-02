"use client";

import "@xyflow/react/dist/style.css";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type NodeChange,
  type NodeProps,
} from "@xyflow/react";
import {
  ChartBar,
  CheckCircle,
  Columns,
  Database,
  Flask,
  Path,
  Play,
  Shuffle,
  SlidersHorizontal,
  Target,
  Warning,
  type IconProps,
} from "phosphor-react";
import { t } from "@/lib/i18n";
import { stackNodes, type CanvasNode, type ExperimentGraph, type ExperimentIcon, type ExperimentNode, type ReportNode } from "./experimentGraph";
import WalkForwardScheduleNode from "./WalkForwardScheduleNode";

// 검증 연구소 모니터 — 전략 연구소 캔버스와 같은 점 격자·노드 언어로, 아래 조정 칸에서 정한 실험 설정과
// 실행 결과를 비춘다. 모니터라서 노드를 옮기거나 확대·이동하지 않는다: 캔버스 높이는 내용에 맞춰 늘고,
// 폭이 모자랄 때만 전체를 줄여 맞춘다. 값이 바뀐 단계는 잠깐 깜빡인다. 단계를 누르면 그 값을 정하는 조정 칸으로 간다.

const ICONS: Record<ExperimentIcon, ComponentType<IconProps>> = {
  data: Database,
  split: Columns,
  optimize: SlidersHorizontal,
  test: Flask,
  aggregate: Target,
  resample: Shuffle,
  paths: Path,
  distribution: ChartBar,
  run: Play,
};

const HANDLE_CLASS = "!h-2 !w-2 !rounded-full !border !border-[var(--lab-border-strong)] !bg-[var(--lab-panel)]";
const PAD = 24;
const MIN_HEIGHT = 240;

const ExperimentStepNode = memo(function ExperimentStepNode({ data }: NodeProps<ExperimentNode>) {
  const Icon = ICONS[data.icon];
  // 조정 칸에서 값이 바뀌면 그 단계만 잠깐 깜빡인다(첫 표시는 제외).
  const signature = `${data.rows.map((row) => row.value).join("|")}#${data.footnote?.lines.join("|") ?? ""}`;
  const shownSignature = useRef(signature);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (shownSignature.current === signature) return;
    shownSignature.current = signature;
    setPulse(true);
  }, [signature]);

  const border = data.status === "blocked" ? "border-[var(--error-red-line)]" : "border-[var(--lab-border-strong)]";
  return (
    <div
      className={`relative w-[212px] cursor-pointer rounded-2xl border bg-[var(--lab-node)] ${border} ${data.status === "running" ? "lab-node-running" : ""} ${pulse ? "lab-node-pulse" : ""}`}
      data-testid={`experiment-node-${data.section}${data.index === undefined ? "-status" : ""}`}
      data-status={data.status}
      onAnimationEnd={(event) => {
        if (event.animationName === "labNodePulse") setPulse(false);
      }}
    >
      {data.index !== undefined && <Handle type="target" id="in" position={Position.Left} className={HANDLE_CLASS} isConnectable={false} />}
      {data.index !== undefined && <Handle type="source" id="out" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
      {data.hasDetail && <Handle type="source" id="detail" position={Position.Bottom} className={HANDLE_CLASS} isConnectable={false} />}
      <div className="flex items-center gap-2.5 border-b border-[var(--lab-border)] px-3 py-2.5">
        <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-[var(--lab-panel)]">
          <Icon size={17} weight="duotone" className="text-white" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-mono text-[10px] font-bold tracking-wider text-[var(--text-label)]">
            {data.index === undefined ? data.kicker : `${String(data.index + 1).padStart(2, "0")} · ${data.kicker}`}
          </span>
          <span className="block truncate text-xs font-black text-white">{data.title}</span>
        </span>
        {data.status === "done" && <CheckCircle size={15} weight="fill" className="flex-shrink-0 text-[var(--success-green)]" aria-label={t("완료")} />}
        {data.status === "blocked" && <Warning size={15} weight="fill" className="flex-shrink-0 text-[var(--error-red)]" aria-label={t("실행 불가")} />}
      </div>
      <dl className="space-y-1 px-3 py-2.5">
        {data.rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3 text-[11px]">
            <dt className="flex-shrink-0 font-bold text-[var(--text-label)]">{row.label}</dt>
            <dd className="min-w-0 break-words text-right font-bold tabular-nums text-white">{row.value}</dd>
          </div>
        ))}
      </dl>
      {data.footnote && (
        <ul
          className={`space-y-1 border-t border-[var(--lab-border)] px-3 py-2.5 text-[10px] font-bold leading-4 ${
            data.footnote.tone === "warn" ? "text-amber-300" : "text-[var(--text-label)]"
          }`}
        >
          {data.footnote.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
});

// 결과 판 — 내용은 결과를 가진 쪽이 slot 요소에 포털로 넣는다. 표·버튼을 쓰는 판이라 글자 선택을 살린다.
const ReportPanelNode = memo(function ReportPanelNode({ data }: NodeProps<ReportNode>) {
  return (
    <div
      className="nodrag nopan cursor-default rounded-2xl border border-[var(--lab-border-strong)] bg-[var(--lab-node)]"
      style={{ width: data.width, userSelect: "text" }}
      data-testid={data.testId}
    >
      <Handle type="target" id="in" position={Position.Top} style={{ left: data.handleX }} className={HANDLE_CLASS} isConnectable={false} />
      <div ref={data.slot} />
    </div>
  );
});

const NODE_TYPES = { experiment: ExperimentStepNode, schedule: WalkForwardScheduleNode, report: ReportPanelNode };

type ExperimentCanvasProps = {
  graph: ExperimentGraph;
  onFocusSection: (section: string) => void;
};

function CanvasInner({ graph, onFocusSection }: ExperimentCanvasProps) {
  const flow = useReactFlow();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(graph.nodes);
  const stackRef = useRef(graph.stack);
  stackRef.current = graph.stack;

  // 설정이 바뀌면 노드 내용을 갈아 끼우되, 이미 잰 크기는 이어받아 바로 다시 쌓는다.
  useEffect(() => {
    setNodes((prev) => {
      const measured = new Map(prev.map((n) => [n.id, n.measured]));
      return stackNodes(
        graph.nodes.map((n) => ({ ...n, measured: measured.get(n.id) })),
        graph.stack,
      );
    });
  }, [graph, setNodes]);

  // 노드 크기가 (다시) 재지면 세로로 다시 쌓는다.
  const handleNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      onNodesChange(changes);
      if (changes.some((change) => change.type === "dimensions")) setNodes((prev) => stackNodes(prev, stackRef.current));
    },
    [onNodesChange, setNodes],
  );

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => setWidth(entries[0]?.contentRect.width ?? 0));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const bounds = useMemo(() => {
    if (nodes.length === 0) return null;
    let right = 0;
    let bottom = 0;
    for (const node of nodes) {
      const w = node.measured?.width;
      const h = node.measured?.height;
      if (w == null || h == null) return null;
      right = Math.max(right, node.position.x + w);
      bottom = Math.max(bottom, node.position.y + h);
    }
    return { width: right, height: bottom };
  }, [nodes]);

  const zoom = bounds && width > 0 ? Math.min(1, (width - PAD * 2) / bounds.width) : 1;
  const height = bounds ? Math.ceil(bounds.height * zoom + PAD * 2) : MIN_HEIGHT;

  useEffect(() => {
    if (!bounds || width <= 0) return;
    void flow.setViewport({ x: Math.max(PAD, (width - bounds.width * zoom) / 2), y: PAD, zoom });
  }, [flow, bounds, width, zoom]);

  return (
    <div ref={wrapRef} style={{ height }} data-testid="experiment-monitor">
      <ReactFlow
        nodes={nodes}
        edges={graph.edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={handleNodesChange}
        onNodeClick={(_e, node) => {
          const n = node as CanvasNode;
          if (n.type !== "report") onFocusSection(n.data.section);
        }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        deleteKeyCode={null}
        minZoom={0.2}
        maxZoom={1}
        proOptions={{ hideAttribution: true }}
        className="lab-flow"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.4} color="var(--lab-dot)" />
      </ReactFlow>
    </div>
  );
}

function ExperimentCanvas(props: ExperimentCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

export default memo(ExperimentCanvas);
