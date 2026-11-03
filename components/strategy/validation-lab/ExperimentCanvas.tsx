"use client";

import "@xyflow/react/dist/style.css";
import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import {
  Background,
  BackgroundVariant,
  Handle,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  useStore,
  type NodeChange,
  type NodeProps,
  type XYPosition,
} from "@xyflow/react";
import {
  ChartBar,
  CheckCircle,
  Columns,
  CornersOut,
  Database,
  Flask,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
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
  EXPERIMENT_NODE_W,
  stackNodes,
  type CanvasNode,
  type ContextNode,
  type ExperimentGraph,
  type ExperimentIcon,
  type ExperimentNode,
  type ReportNode,
  type RowEdit,
} from "./experimentGraph";
import NodeSizer, { useNodeScale } from "./NodeSizer";
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
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 2;
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
  const { width, zoom } = useNodeScale(id, EXPERIMENT_NODE_W);
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
      className={`relative cursor-pointer overflow-hidden rounded-2xl border bg-[var(--lab-node)] ${border} ${data.status === "running" ? "lab-node-running" : ""} ${pulse ? "lab-node-pulse" : ""}`}
      style={{ width }}
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
      <NodeSizer minWidth={EXPERIMENT_NODE_W * 0.75} />
      {(data.index !== undefined || data.hasIn) && <Handle type="target" id="in" position={Position.Left} className={HANDLE_CLASS} isConnectable={false} />}
      {data.index !== undefined && <Handle type="source" id="out" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
      {data.hasDetail && <Handle type="source" id="detail" position={Position.Bottom} className={HANDLE_CLASS} isConnectable={false} />}
      <div style={{ zoom }}>
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
    </div>
  );
});

// 결과 판 — 내용은 결과를 가진 쪽이 slot 요소에 포털로 넣는다. 표·버튼을 쓰는 판이라 글자 선택을 살린다.
const ReportPanelNode = memo(function ReportPanelNode({ id, data }: NodeProps<ReportNode>) {
  const { width, zoom } = useNodeScale(id, data.width);
  return (
    <div
      className="nodrag nopan cursor-default overflow-hidden rounded-2xl border border-[var(--lab-border-strong)] bg-[var(--lab-node)]"
      style={{ width, userSelect: "text" }}
      data-testid={data.testId}
    >
      <NodeSizer minWidth={data.width * 0.5} />
      <Handle type="target" id="in" position={Position.Top} style={{ left: data.handleX * zoom }} className={HANDLE_CLASS} isConnectable={false} />
      <div ref={data.slot} style={{ zoom }} />
    </div>
  );
});

// 참고 노드(검증 대상 전략·방법) — 실험 왼쪽 열에 놓고, 첫 노드는 첫 단계로 잇는다.
const ContextPanelNode = memo(function ContextPanelNode({ id, data }: NodeProps<ContextNode>) {
  const { width, zoom } = useNodeScale(id, CONTEXT_NODE_W);
  return (
    <div
      className="overflow-hidden rounded-2xl border border-[var(--lab-border-strong)] bg-[var(--lab-node)]"
      style={{ width }}
      data-testid={data.testId}
    >
      <NodeSizer minWidth={CONTEXT_NODE_W * 0.6} />
      {data.hasOut && <Handle type="source" id="out" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
      <div className="p-4" style={{ zoom }}>
        {data.content}
      </div>
    </div>
  );
});

const ZOOM_BUTTON_CLASS =
  "flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-label)] hover:bg-white/[0.08] hover:text-white disabled:opacity-40";

// 확대·축소 — 누르면 자동 맞춤을 멈추고(빈 곳을 끌어 이동), '화면에 맞춤'으로 돌아간다. ⌘/Ctrl+스크롤·핀치로도 확대한다.
function ZoomControls({ manual, onZoom, onFit }: { manual: boolean; onZoom: (direction: 1 | -1) => void; onFit: () => void }) {
  const zoom = useStore((s) => s.transform[2]);
  return (
    <Panel position="top-right" className="!m-2 flex items-center gap-0.5 rounded-lg border border-[var(--lab-border-strong)] bg-[var(--lab-panel)] p-0.5">
      <button type="button" className={ZOOM_BUTTON_CLASS} onClick={() => onZoom(-1)} disabled={zoom <= MIN_ZOOM + 1e-3} aria-label={t("축소")} title={t("축소")}>
        <MagnifyingGlassMinus size={15} weight="bold" />
      </button>
      <span className="w-10 text-center font-mono text-[10px] font-bold tabular-nums text-[var(--text-label)]" data-testid="experiment-zoom-level">
        {Math.round(zoom * 100)}%
      </span>
      <button type="button" className={ZOOM_BUTTON_CLASS} onClick={() => onZoom(1)} disabled={zoom >= MAX_ZOOM - 1e-3} aria-label={t("확대")} title={t("확대")}>
        <MagnifyingGlassPlus size={15} weight="bold" />
      </button>
      <button type="button" className={ZOOM_BUTTON_CLASS} onClick={onFit} disabled={!manual} aria-label={t("화면에 맞춤")} title={t("화면에 맞춤")}>
        <CornersOut size={15} weight="bold" />
      </button>
    </Panel>
  );
}

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
  // 끌거나 크기를 바꾸는 중 — 이 동안에는 화면 맞춤을 멈춘다.
  const [interacting, setInteracting] = useState(false);
  // 사용자가 확대·축소·이동한 뒤 — '화면에 맞춤'을 누를 때까지 자동 맞춤을 하지 않는다.
  const [manual, setManual] = useState(false);
  const graphRef = useRef(graph);
  graphRef.current = graph;
  // 사용자가 옮긴 노드의 자리와 바꾼 크기 — 자동 배치(stackNodes)보다 우선한다.
  const moved = useRef(new Map<string, XYPosition>());
  const resized = useRef(new Map<string, number>());

  // 그래프가 정한 자리에서 측정 높이로 다시 쌓은 뒤, 옮긴 노드만 옮긴 자리에, 크기를 바꾼 노드는 그 폭으로 둔다.
  // 높이는 손잡이가 정해도 버린다 — 내용이 폭에 비례해 커지므로 높이는 내용을 따른다. 잰 크기는 이어받는다.
  const relayout = useCallback((prev: CanvasNode[]) => {
    const measured = new Map(prev.map((n) => [n.id, n.measured]));
    const { nodes: base, stack } = graphRef.current;
    return stackNodes(
      base.map((n) => ({ ...n, measured: measured.get(n.id) })),
      stack,
    ).map((n) => {
      const position = moved.current.get(n.id);
      const width = resized.current.get(n.id);
      return { ...n, ...(position && { position }), ...(width && { width }) };
    });
  }, []);

  // 설정이 바뀌면 노드 내용을 갈아 끼운다.
  useEffect(() => {
    setNodes(relayout);
  }, [graph, setNodes, relayout]);

  // 노드를 끌거나 크기를 바꾸면 기억하고, 크기가 (다시) 재지면 세로로 다시 쌓는다.
  const handleNodesChange = useCallback(
    (changes: NodeChange<CanvasNode>[]) => {
      for (const change of changes) {
        if (change.type === "position" && change.position) moved.current.set(change.id, change.position);
        if (change.type === "dimensions" && change.resizing !== undefined) {
          if (change.setAttributes && change.dimensions) resized.current.set(change.id, change.dimensions.width);
          setInteracting(change.resizing);
        }
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
  // 끌거나 크기를 바꾸는 동안에는 맞춤을 멈춘다 — 노드가 가장자리를 넘을 때마다 화면이 줄어들면 손끝에서 노드가 미끄러진다.
  const lastBounds = useRef(measuredBounds);
  if (!interacting) lastBounds.current = measuredBounds;
  const bounds = lastBounds.current;

  const zoom = bounds && width > 0 ? Math.min(1, (width - PAD * 2) / bounds.width) : 1;
  const height = bounds ? Math.ceil(bounds.height * zoom + PAD * 2) : MIN_HEIGHT;

  useEffect(() => {
    if (manual || !bounds || width <= 0) return;
    void flow.setViewport({
      x: Math.max(PAD, (width - bounds.width * zoom) / 2) - bounds.left * zoom,
      y: PAD - bounds.top * zoom,
      zoom,
    });
  }, [flow, bounds, width, zoom, manual]);

  const handleZoom = useCallback(
    (direction: 1 | -1) => {
      setManual(true);
      void (direction > 0 ? flow.zoomIn({ duration: 150 }) : flow.zoomOut({ duration: 150 }));
    },
    [flow],
  );

  return (
    <div ref={wrapRef} style={{ height }} data-testid="experiment-monitor">
      <EditContext.Provider value={editState}>
      <ReactFlow
        nodes={nodes}
        edges={graph.edges}
        nodeTypes={NODE_TYPES}
        onNodesChange={handleNodesChange}
        onNodeDragStart={() => setInteracting(true)}
        onNodeDragStop={() => setInteracting(false)}
        onNodeClick={(_e, node) => {
          const n = node as CanvasNode;
          if (n.type === "report" || n.type === "context") return;
          if (onEdit && n.type === "experiment" && n.data.rows.some((row) => row.edit)) setEditingId(n.id);
          else onFocusSection(n.data.section);
        }}
        onPaneClick={() => setEditingId(null)}
        // 사용자 조작(핀치·⌘+스크롤·빈 곳 끌기)만 수동으로 바꾼다 — 자동 맞춤의 setViewport는 event가 없다.
        onMoveStart={(event) => {
          if (event) setManual(true);
        }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={manual}
        panOnScroll={false}
        zoomOnScroll={false}
        zoomOnPinch
        zoomOnDoubleClick={false}
        preventScrolling={false}
        deleteKeyCode={null}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        proOptions={{ hideAttribution: true }}
        className="lab-flow"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.4} color="var(--lab-dot)" />
        <ZoomControls manual={manual} onZoom={handleZoom} onFit={() => setManual(false)} />
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
