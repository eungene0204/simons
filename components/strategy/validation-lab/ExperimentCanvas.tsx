"use client";

import "@xyflow/react/dist/style.css";
import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
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
  type XYPosition,
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
import {
  CONTEXT_NODE_W,
  stackNodes,
  type CanvasNode,
  type ContextNode,
  type ExperimentGraph,
  type ExperimentIcon,
  type ExperimentNode,
  type ReportNode,
  type RowEdit,
} from "./experimentGraph";
import WalkForwardScheduleNode from "./WalkForwardScheduleNode";

// 검증 연구소 모니터 — 전략 연구소 캔버스와 같은 점 격자·노드 언어로, 아래 조정 칸에서 정한 실험 설정과
// 실행 결과를 비춘다. 노드는 끌어서 옮길 수 있고(옮긴 자리는 설정이 바뀌어도 유지), 화면 확대·이동은 없다:
// 캔버스 높이는 내용에 맞춰 늘고, 폭이 모자랄 때만 전체를 줄여 맞춘다. 값이 바뀐 단계는 잠깐 깜빡인다.
// 고칠 값이 있는 단계를 누르면 그 자리에서 입력 칸이 열리고, 없는 단계를 누르면 그 값을 정하는 조정 칸으로 간다.

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
const INPUT_CLASS =
  "nodrag nopan rounded-md border border-[var(--lab-border-strong)] bg-[var(--lab-panel)] px-1.5 py-0.5 text-right text-[11px] font-bold tabular-nums text-white focus:border-sky-400/60 focus:outline-none";

type EditState = {
  editingId: string | null;
  setEditingId: (id: string | null) => void;
  onEdit?: (key: string, value: string | number | null) => void;
};
const EditContext = createContext<EditState>({ editingId: null, setEditingId: () => {} });

/** 행 하나의 입력 칸 — 숫자는 Enter·포커스 이탈에서 확정하고, 선택지는 고르는 즉시 확정한다. */
function RowEditor({ edit, label, display, autoFocus, onCommit }: {
  edit: RowEdit;
  label: string;
  display: string;
  autoFocus: boolean;
  onCommit: (value: string | number | null) => void;
}) {
  const [draft, setDraft] = useState(edit.kind === "number" ? String(edit.value) : "");
  const editValue = edit.kind === "number" ? edit.value : null;
  useEffect(() => {
    if (editValue !== null) setDraft(String(editValue));
  }, [editValue]);

  if (edit.kind === "select") {
    return (
      <select
        aria-label={label}
        autoFocus={autoFocus}
        value={edit.value}
        onChange={(event) => onCommit(event.target.value)}
        className={`${INPUT_CLASS} max-w-[120px]`}
      >
        {edit.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  if (edit.kind === "open") {
    return (
      <button
        type="button"
        aria-label={label}
        autoFocus={autoFocus}
        onClick={(event) => {
          event.stopPropagation();
          onCommit(null);
        }}
        className={`${INPUT_CLASS} cursor-pointer break-words hover:bg-white/[0.06]`}
      >
        {display}
      </button>
    );
  }
  const commit = () => {
    const next = Number(draft);
    if (draft.trim() !== "" && Number.isFinite(next) && next !== edit.value) onCommit(next);
    else setDraft(String(edit.value));
  };
  return (
    <span className="flex items-center gap-1">
      <input
        aria-label={label}
        autoFocus={autoFocus}
        type="number"
        inputMode="numeric"
        min={edit.min}
        max={edit.max}
        title={`${edit.min.toLocaleString()}~${edit.max.toLocaleString()}${edit.suffix}`}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") commit();
        }}
        className={`${INPUT_CLASS} w-16`}
      />
      <span className="text-[10px] font-bold text-[var(--text-label)]">{edit.suffix}</span>
    </span>
  );
}

const ExperimentStepNode = memo(function ExperimentStepNode({ id, data }: NodeProps<ExperimentNode>) {
  const Icon = ICONS[data.icon];
  const { editingId, setEditingId, onEdit } = useContext(EditContext);
  const editing = editingId === id && onEdit !== undefined && data.rows.some((row) => row.edit);
  const firstEditable = data.rows.findIndex((row) => row.edit);
  // 조정 칸에서 값이 바뀌면 그 단계만 잠깐 깜빡인다(첫 표시는 제외).
  const signature = `${data.rows.map((row) => row.value).join("|")}#${data.footnote?.lines.join("|") ?? ""}`;
  const shownSignature = useRef(signature);
  const [pulse, setPulse] = useState(false);
  useEffect(() => {
    if (shownSignature.current === signature) return;
    shownSignature.current = signature;
    setPulse(true);
  }, [signature]);

  const border = editing
    ? "border-sky-400/60"
    : data.status === "blocked"
      ? "border-[var(--error-red-line)]"
      : "border-[var(--lab-border-strong)]";
  return (
    <div
      className={`relative w-[212px] cursor-pointer rounded-2xl border bg-[var(--lab-node)] ${border} ${data.status === "running" ? "lab-node-running" : ""} ${pulse ? "lab-node-pulse" : ""}`}
      data-testid={`experiment-node-${data.section}${data.index === undefined ? "-status" : ""}`}
      data-status={data.status}
      data-editing={editing || undefined}
      onKeyDown={(event) => {
        if (editing && event.key === "Escape") setEditingId(null);
      }}
      onAnimationEnd={(event) => {
        if (event.animationName === "labNodePulse") setPulse(false);
      }}
    >
      {(data.index !== undefined || data.hasIn) && <Handle type="target" id="in" position={Position.Left} className={HANDLE_CLASS} isConnectable={false} />}
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
        {data.rows.map((row, i) => (
          <div key={row.label} className={`flex justify-between gap-3 text-[11px] ${editing && row.edit ? "items-center" : "items-baseline"}`}>
            <dt className="flex-shrink-0 font-bold text-[var(--text-label)]">{row.label}</dt>
            <dd className="min-w-0 break-words text-right font-bold tabular-nums text-white">
              {editing && row.edit ? (
                <RowEditor
                  edit={row.edit}
                  label={row.label}
                  display={row.value}
                  autoFocus={i === firstEditable}
                  onCommit={(value) => onEdit!(row.edit!.key, value)}
                />
              ) : (
                row.value
              )}
            </dd>
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

// 참고 노드(검증 대상 전략·방법) — 실험 왼쪽 열에 놓고, 첫 노드는 첫 단계로 잇는다.
const ContextPanelNode = memo(function ContextPanelNode({ data }: NodeProps<ContextNode>) {
  return (
    <div
      className="rounded-2xl border border-[var(--lab-border-strong)] bg-[var(--lab-node)] p-4"
      style={{ width: CONTEXT_NODE_W }}
      data-testid={data.testId}
    >
      {data.hasOut && <Handle type="source" id="out" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
      {data.content}
    </div>
  );
});

const NODE_TYPES = { experiment: ExperimentStepNode, schedule: WalkForwardScheduleNode, report: ReportPanelNode, context: ContextPanelNode };

type ExperimentCanvasProps = {
  graph: ExperimentGraph;
  onFocusSection: (section: string) => void;
  /** 노드에서 고친 값(RowEdit의 key와 새 값, open이면 null). 없으면 노드를 눌러도 입력 칸이 열리지 않는다. */
  onEdit?: (key: string, value: string | number | null) => void;
};

function CanvasInner({ graph, onFocusSection, onEdit }: ExperimentCanvasProps) {
  const flow = useReactFlow();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [nodes, setNodes, onNodesChange] = useNodesState<CanvasNode>(graph.nodes);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const graphRef = useRef(graph);
  graphRef.current = graph;
  // 사용자가 옮긴 노드의 자리 — 자동 배치(stackNodes)보다 우선한다.
  const moved = useRef(new Map<string, XYPosition>());

  // 그래프가 정한 자리에서 측정 높이로 다시 쌓은 뒤, 옮긴 노드만 옮긴 자리에 둔다. 잰 크기는 이어받는다.
  const relayout = useCallback((prev: CanvasNode[]) => {
    const measured = new Map(prev.map((n) => [n.id, n.measured]));
    const { nodes: base, stack } = graphRef.current;
    return stackNodes(
      base.map((n) => ({ ...n, measured: measured.get(n.id) })),
      stack,
    ).map((n) => {
      const position = moved.current.get(n.id);
      return position ? { ...n, position } : n;
    });
  }, []);

  // 설정이 바뀌면 노드 내용을 갈아 끼운다.
  useEffect(() => {
    setNodes(relayout);
  }, [graph, setNodes, relayout]);

  // 노드를 끌면 자리를 기억하고, 크기가 (다시) 재지면 세로로 다시 쌓는다.
  const handleNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      for (const change of changes) {
        if (change.type === "position" && change.position) moved.current.set(change.id, change.position);
      }
      onNodesChange(changes);
      if (changes.some((change) => change.type === "dimensions")) setNodes(relayout);
    },
    [onNodesChange, setNodes, relayout],
  );
  const editState = useMemo(() => ({ editingId, setEditingId, onEdit }), [editingId, onEdit]);

  useEffect(() => {
    const element = wrapRef.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) => setWidth(entries[0]?.contentRect.width ?? 0));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const measuredBounds = useMemo(() => {
    if (nodes.length === 0) return null;
    let left = Infinity;
    let top = Infinity;
    let right = -Infinity;
    let bottom = -Infinity;
    for (const node of nodes) {
      const w = node.measured?.width;
      const h = node.measured?.height;
      if (w == null || h == null) return null;
      left = Math.min(left, node.position.x);
      top = Math.min(top, node.position.y);
      right = Math.max(right, node.position.x + w);
      bottom = Math.max(bottom, node.position.y + h);
    }
    return { left, top, width: right - left, height: bottom - top };
  }, [nodes]);
  // 끄는 동안에는 맞춤을 멈춘다 — 노드가 가장자리를 넘을 때마다 화면이 줄어들면 손끝에서 노드가 미끄러진다.
  const lastBounds = useRef(measuredBounds);
  if (!dragging) lastBounds.current = measuredBounds;
  const bounds = lastBounds.current;

  const zoom = bounds && width > 0 ? Math.min(1, (width - PAD * 2) / bounds.width) : 1;
  const height = bounds ? Math.ceil(bounds.height * zoom + PAD * 2) : MIN_HEIGHT;

  useEffect(() => {
    if (!bounds || width <= 0) return;
    void flow.setViewport({
      x: Math.max(PAD, (width - bounds.width * zoom) / 2) - bounds.left * zoom,
      y: PAD - bounds.top * zoom,
      zoom,
    });
  }, [flow, bounds, width, zoom]);

  return (
    <div ref={wrapRef} style={{ height }} data-testid="experiment-monitor">
      <EditContext.Provider value={editState}>
      <ReactFlow
        nodes={nodes}
        edges={graph.edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={handleNodesChange}
        onNodeDragStart={() => setDragging(true)}
        onNodeDragStop={() => setDragging(false)}
        onNodeClick={(_e, node) => {
          const n = node as CanvasNode;
          if (n.type === "report" || n.type === "context") return;
          if (onEdit && n.type === "experiment" && n.data.rows.some((row) => row.edit)) setEditingId(n.id);
          else onFocusSection(n.data.section);
        }}
        onPaneClick={() => setEditingId(null)}
        nodesDraggable
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
      </EditContext.Provider>
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
