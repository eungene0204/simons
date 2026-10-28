"use client";

import "@xyflow/react/dist/style.css";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  Background,
  BackgroundVariant,
  Panel,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type NodeChange,
  type NodeMouseHandler,
} from "@xyflow/react";
import {
  ArrowCounterClockwise,
  ArrowsOutSimple,
  ChatCircleText,
  MagnifyingGlassMinus,
  MagnifyingGlassPlus,
  Plus,
  Trash,
  X,
} from "phosphor-react";
import { t } from "@/lib/i18n";
import type { SectionKey, StrategyGraph } from "@/lib/strategy-graph/types";
import { SECTION_LABELS } from "@/lib/strategy-graph/transformSections";
import BlockTray from "./BlockTray";
import { visibleRows } from "@/lib/strategy-graph/layout";
import {
  buildLabGraph,
  changedNodeIds,
  followStageDrag,
  itemsForStage,
  PIPELINE_ORDER,
  type ConditionNodeData,
  type LabNode,
  type PipelineNodeData,
  type PipelineStage,
} from "./labGraph";
import { LAB_NODE_TYPES, type RunDecoration } from "./StrategyNode";

export type LabRunState = "idle" | "running" | "done" | "error";

export type CanvasItem = { id: string; label: string; value: string };
export type CanvasBlockOption = { key: string; label: string };
/** 상세 패널에서 바꿀 수 있는 값 하나 — 숫자 칸 또는 정해진 선택지. */
export type EditableField =
  | { key: string; label: string; kind: "number"; value: number; min?: number; max?: number; integer: boolean }
  | { key: string; label: string; kind: "choice"; value: string; options: Array<{ value: string; label: string }> };
/** 칸에 속한 전략 항목 하나와 그 편집 칸. */
export type EditableItem = { id: string; label: string; value: string; fields: EditableField[] };

type StrategyCanvasProps = {
  graph: StrategyGraph | null;
  /** 그래프를 준비하는 중(초안 컴파일 대기). */
  loading: boolean;
  /** 지표 메타데이터를 못 받았다 — 구조만 그리고 그 요청만 다시 시도할 수 있다. */
  metaError: boolean;
  onRetryMeta: () => void;
  runState: LabRunState;
  /** 지금 전략의 항목(지우기 후보의 원천). */
  items: readonly CanvasItem[];
  /** 항목 지우기 — 대화 흐름(다시 정하기)으로 처리된다. 응답 대기 중이면 undefined. */
  onDeleteItem?: (id: string) => void;
  /** 블록 트레이에 칸별로 보여 줄 블록. */
  blockOptions: (stage: SectionKey) => CanvasBlockOption[];
  /** 블록을 올리면 그 즉시 전략에 포함한다(빠진 값은 채팅이 묻는다). 응답 대기 중이면 undefined. */
  onAddBlock?: (stage: SectionKey, key: string) => void;
  /** 더블클릭한 노드의 편집 칸(상세 패널) — 조건 노드는 그 조건(sourceRef)만, 칸 노드(null)는 칸 전체. */
  editableItems: (stage: PipelineStage, sourceRef: string | null) => EditableItem[];
  /** 상세 패널에서 바꾼 값을 그 즉시 전략에 반영한다. 응답 대기 중이면 undefined. */
  onEditItem?: (itemId: string, changes: Record<string, number | string>) => void;
  onZoomChange: (zoom: number) => void;
};

const PULSE_MS = 1400;

type Dialog =
  | { kind: "delete"; stage: PipelineStage; label: string }
  | { kind: "confirmDelete"; item: CanvasItem }
  | { kind: "details"; node: LabNode }
  | null;

/** 편집·삭제가 향하는 칸 — 다른 칸에서 풀어 그린 칸(리밸런싱의 매수·매도)은 그 칸의 항목을 고친다. */
function editStage(node: LabNode): PipelineStage {
  return node.data.derivedFrom ?? node.data.stage;
}

function stageLabel(nodes: readonly LabNode[], stage: PipelineStage): string {
  return nodes.find((n) => n.type === "pipeline" && n.data.stage === stage)?.data.label ?? stage;
}

function CanvasInner({ graph, loading, metaError, onRetryMeta, runState, items, onDeleteItem, blockOptions, onAddBlock, editableItems, onEditItem, onZoomChange }: StrategyCanvasProps) {
  const flow = useReactFlow();
  const base = useMemo(() => buildLabGraph(graph), [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState<LabNode>(base.nodes);
  const movedRef = useRef(new Map<string, { x: number; y: number }>());
  const previousRef = useRef<LabNode[]>([]);
  const historyRef = useRef<Array<Map<string, { x: number; y: number }>>>([]);
  const [pulseIds, setPulseIds] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<Dialog>(null);
  const [trayOpen, setTrayOpen] = useState(false);
  const [trayStage, setTrayStage] = useState<SectionKey>("entry");
  // 블록을 올린 뒤 바뀐 그래프는 화면에 맞춰 다시 본다(새 칸이 화면 밖에 생길 수 있다).
  const fitOnNextGraphRef = useRef(false);

  // 그래프가 바뀌면 노드를 다시 만들되 사용자가 옮긴 자리는 지킨다. 바뀐 노드만 짧게 강조한다.
  useEffect(() => {
    const next = base.nodes.map((n) => {
      const moved = movedRef.current.get(n.id);
      return (moved ? { ...n, position: moved } : n) as LabNode;
    });
    const changed = changedNodeIds(previousRef.current, base.nodes);
    const hadGraph = previousRef.current.length > 0;
    previousRef.current = base.nodes;
    setNodes(next);
    if ((!hadGraph || fitOnNextGraphRef.current) && next.length > 0) {
      fitOnNextGraphRef.current = false;
      // 칸이 적을 때 최대 배율(2배)로 확대되지 않게 1배에서 멈춘다. 자동 맞춤은 애니메이션 없이 한 번에
      // 자리 잡는다 — 그래프가 나타날 때 확대되며 보이는 움직임을 없앤다(사용자 지시). 버튼 맞춤만 부드럽게 움직인다.
      window.requestAnimationFrame(() => void flow.fitView({ padding: 0.25, duration: 0, maxZoom: 1 }));
    }
    if (changed.length === 0) return;
    setPulseIds(new Set(changed));
    const timer = window.setTimeout(() => setPulseIds(new Set()), PULSE_MS);
    return () => window.clearTimeout(timer);
  }, [base, setNodes, flow]);

  const pipelineOrder = useMemo(
    () => base.nodes.filter((n) => n.type === "pipeline").map((n) => n.id),
    [base],
  );

  const decorated = useMemo(
    () =>
      nodes.map((n) => {
        const stageIndex = pipelineOrder.indexOf(n.id);
        const extra: RunDecoration = {
          runState,
          pulse: pulseIds.has(n.id),
          ...(stageIndex >= 0 ? { runIndex: stageIndex } : {}),
          ...(n.type === "pipeline"
            ? {
                onAdd: () => {
                  if (n.data.stage === "output") return;
                  setTrayStage(n.data.stage as SectionKey);
                  setTrayOpen(true);
                },
              }
            : {}),
        };
        return { ...n, data: { ...n.data, ...extra } } as LabNode;
      }),
    [nodes, pipelineOrder, runState, pulseIds],
  );

  const pickBlock = (stage: SectionKey, key: string) => {
    if (!onAddBlock) return;
    setTrayOpen(false);
    fitOnNextGraphRef.current = true;
    onAddBlock(stage, key);
  };

  const snapshotPositions = () => new Map(nodes.map((n) => [n.id, { ...n.position }]));

  const onNodeDragStart = useCallback(() => {
    historyRef.current = [...historyRef.current.slice(-49), snapshotPositions()];
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reads the latest nodes on each drag
  }, [nodes]);

  const onNodeDragStop: NodeMouseHandler = useCallback((_e, node) => {
    movedRef.current.set(node.id, { ...node.position });
  }, []);

  // 칸을 끌면 매달린 조건도 함께 옮기고, 그 자리도 그래프가 바뀔 때 지킨다.
  const handleNodesChange = useCallback(
    (changes: NodeChange<LabNode>[]) => {
      const withChildren = followStageDrag(changes, nodes);
      for (const c of withChildren.slice(changes.length)) {
        if (c.type === "position" && c.position) movedRef.current.set(c.id, { ...c.position });
      }
      onNodesChange(withChildren);
    },
    [nodes, onNodesChange],
  );

  const undo = () => {
    const last = historyRef.current.pop();
    if (!last) return;
    for (const [id, pos] of last) movedRef.current.set(id, pos);
    setNodes((prev) => prev.map((n) => (last.has(n.id) ? { ...n, position: last.get(n.id)! } : n)));
  };

  const openDeleteFor = (node: LabNode) => {
    // 조건 노드는 가리키는 전략 항목이 하나로 정해지면 고르는 단계 없이 바로 확인만 받는다.
    if (node.type === "condition") {
      const [only, ...rest] = editableItems(editStage(node), (node.data as ConditionNodeData).graphNode.sourceRef);
      if (only && rest.length === 0) {
        setDialog({ kind: "confirmDelete", item: { id: only.id, label: only.label, value: only.value } });
        return;
      }
    }
    setDialog({ kind: "delete", stage: editStage(node), label: stageLabel(nodes, editStage(node)) });
  };

  // React Flow 기본 삭제는 화면 상태에서만 노드를 지운다 — 전략과 어긋나므로 끄고(deleteKeyCode=null),
  // Delete/Backspace는 "어느 항목을 지울지" 고르는 대화상자로 보낸다.
  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "Delete" && e.key !== "Backspace") return;
    if ((e.target as HTMLElement).closest("input, textarea, [contenteditable]")) return;
    const selected = nodes.find((n) => n.selected);
    if (!selected) return;
    e.preventDefault();
    openDeleteFor(selected);
  };

  const zoomReport = useCallback(
    (_e: unknown, viewport: { zoom: number }) => onZoomChange(viewport.zoom),
    [onZoomChange],
  );

  const isEmpty = base.nodes.length === 0;
  const addableStages = PIPELINE_ORDER.filter((s): s is SectionKey => s !== "output");

  return (
    <div className="relative h-full w-full" onKeyDown={handleKeyDown} data-testid="lab-canvas" data-origin={graph?.origin ?? "none"}>
      <ReactFlow
        nodes={decorated}
        edges={base.edges}
        nodeTypes={LAB_NODE_TYPES}
        onNodesChange={handleNodesChange}
        onNodeDragStart={onNodeDragStart}
        onNodeDragStop={onNodeDragStop}
        onNodeDoubleClick={(_e, node) => setDialog({ kind: "details", node: node as LabNode })}
        onMove={zoomReport}
        onInit={(instance) => onZoomChange(instance.getZoom())}
        nodesConnectable={false}
        deleteKeyCode={null}
        zoomOnDoubleClick={false}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        className="lab-flow"
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.4} color="var(--lab-dot)" />

        {/* 우측 상단 세로 툴바 */}
        <Panel position="top-right" className="!m-3">
          <div className="relative flex flex-col gap-1 rounded-xl border border-[var(--lab-border)] bg-[var(--lab-panel)] p-1">
            <button
              type="button"
              onClick={() => setTrayOpen((v) => !v)}
              aria-label={t("블록 추가")}
              title={t("블록 추가")}
              aria-expanded={trayOpen}
              data-block-tray-toggle=""
              className="lab-icon-button"
            >
              <Plus size={16} weight="bold" />
            </button>
          </div>
        </Panel>

        {/* 좌하단 컨트롤 바 */}
        <Panel position="bottom-left" className="!m-3">
          <div className="flex items-center gap-1 rounded-xl border border-[var(--lab-border)] bg-[var(--lab-panel)] p-1" data-testid="lab-canvas-controls">
            <button type="button" className="lab-icon-button" onClick={() => void flow.fitView({ padding: 0.25, duration: 200 })} aria-label={t("화면 맞춤")} title={t("화면 맞춤")}>
              <ArrowsOutSimple size={16} />
            </button>
            <button type="button" className="lab-icon-button" onClick={() => void flow.zoomIn({ duration: 150 })} aria-label={t("확대")} title={t("확대")}>
              <MagnifyingGlassPlus size={16} />
            </button>
            <button type="button" className="lab-icon-button" onClick={() => void flow.zoomOut({ duration: 150 })} aria-label={t("축소")} title={t("축소")}>
              <MagnifyingGlassMinus size={16} />
            </button>
            <button type="button" className="lab-icon-button" onClick={undo} aria-label={t("배치 되돌리기")} title={t("배치 되돌리기")}>
              <ArrowCounterClockwise size={16} />
            </button>
          </div>
        </Panel>
      </ReactFlow>

      <BlockTray
        open={trayOpen}
        stages={addableStages}
        stage={trayStage}
        onStageChange={setTrayStage}
        options={blockOptions}
        onPick={pickBlock}
        disabled={!onAddBlock}
        onClose={() => setTrayOpen(false)}
      />

      {metaError && !isEmpty && (
        <div
          className="absolute left-3 top-3 flex items-center gap-2 rounded-xl border border-[var(--lab-border)] bg-[var(--lab-panel)] px-3 py-2"
          role="status"
          data-testid="graph-meta-error"
        >
          <p className="text-[11px] font-bold text-[var(--text-label)]">{t("지표 정보를 불러오지 못해 이름과 분류를 표시할 수 없습니다.")}</p>
          <button type="button" onClick={onRetryMeta} className="rounded-md border border-[var(--lab-border-strong)] px-2 py-0.5 text-[11px] font-black text-white">
            {t("다시 시도")}
          </button>
        </div>
      )}

      {isEmpty && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center p-4">
          <div className="max-w-sm rounded-2xl border border-[var(--lab-border)] bg-[var(--lab-panel)] px-6 py-5 text-center" data-testid="lab-canvas-empty">
            <ChatCircleText size={28} className="mx-auto text-[var(--text-label)]" />
            <p className="mt-3 text-sm font-black text-white">
              {loading ? t("전략 구조를 준비하는 중입니다.") : t("아래 채팅창에 전략을 설명해 보세요")}
            </p>
          </div>
        </div>
      )}

      {dialog?.kind === "delete" && (
        <DeleteDialog
          label={dialog.label}
          candidates={itemsForStage(dialog.stage, items)}
          onDelete={onDeleteItem}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "confirmDelete" && (
        <ConfirmDeleteDialog
          item={dialog.item}
          onConfirm={
            onDeleteItem
              ? () => {
                  onDeleteItem(dialog.item.id);
                  setDialog(null);
                }
              : undefined
          }
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "details" && (
        <DetailsDialog
          node={dialog.node}
          editItems={editableItems(
            editStage(dialog.node),
            dialog.node.type === "condition" ? (dialog.node.data as ConditionNodeData).graphNode.sourceRef : null,
          )}
          onEdit={
            onEditItem
              ? (itemId, changes) => {
                  setDialog(null);
                  onEditItem(itemId, changes);
                }
              : undefined
          }
          onClose={() => setDialog(null)}
          onDelete={() => openDeleteFor(dialog.node)}
        />
      )}
    </div>
  );
}

function DialogFrame({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-[rgba(20,20,19,0.6)] p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={`flex max-h-full w-full flex-col overflow-hidden rounded-2xl border border-[var(--lab-border)] bg-[var(--lab-panel)] ${wide ? "max-w-4xl" : "max-w-md"}`}
      >
        <div className="flex items-center justify-between border-b border-[var(--lab-border)] px-4 py-3">
          <p className="text-sm font-black text-white">{title}</p>
          <button type="button" onClick={onClose} className="lab-icon-button" aria-label={t("닫기")}>
            <X size={14} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ConfirmDeleteDialog({ item, onConfirm, onClose }: { item: CanvasItem; onConfirm?: () => void; onClose: () => void }) {
  return (
    <DialogFrame title={t("지우기")} onClose={onClose}>
      <div className="space-y-3 p-4" role="alertdialog" aria-label={t("지우기")}>
        <p className="text-sm font-black text-white">{t("'{0}'를 지울까요?", `${item.label} ${item.value}`.trim())}</p>
        <p className="text-[11px] font-bold leading-relaxed text-[var(--text-label)]">
          {onConfirm ? t("지운 항목은 채팅에서 다시 정하도록 안내합니다.") : t("응답이 끝난 뒤에 지울 수 있습니다.")}
        </p>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-lg border border-[var(--lab-border-strong)] px-3 py-1.5 text-xs font-black text-gray-300 hover:text-white">
            {t("취소")}
          </button>
          <button
            type="button"
            autoFocus
            disabled={!onConfirm}
            onClick={onConfirm}
            className="flex items-center gap-1 rounded-lg border border-[var(--error-red-line)] !outline-none px-3 py-1.5 text-xs font-black text-[var(--error-red)] hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash size={12} />
            {t("확인")}
          </button>
        </div>
      </div>
    </DialogFrame>
  );
}

function DeleteDialog({
  label,
  candidates,
  onDelete,
  onClose,
}: {
  label: string;
  candidates: CanvasItem[];
  onDelete?: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <DialogFrame title={t("{0}에서 지울 항목", label)} onClose={onClose}>
      <div className="space-y-2 p-4">
        {candidates.length === 0 ? (
          <p className="text-xs font-bold leading-relaxed text-[var(--text-label)]">
            {t("이 단계는 캔버스에서 지울 수 있는 항목이 없습니다. 채팅으로 바꿀 내용을 알려 주세요.")}
          </p>
        ) : (
          <>
            <p className="text-xs font-bold leading-relaxed text-[var(--text-label)]">
              {t("지운 항목은 채팅에서 다시 정하도록 안내합니다.")}
            </p>
            <ul className="space-y-1">
              {candidates.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 rounded-xl border border-[var(--lab-border)] px-3 py-2">
                  <span className="min-w-0 text-xs font-bold text-white">
                    <span className="text-[var(--text-label)]">{item.label}</span> {item.value}
                  </span>
                  <button
                    type="button"
                    disabled={!onDelete}
                    onClick={() => {
                      onDelete?.(item.id);
                      onClose();
                    }}
                    className="flex flex-shrink-0 items-center gap-1 rounded-lg border border-[var(--error-red-line)] px-2 py-1 text-[11px] font-black text-[var(--error-red)] hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Trash size={11} />
                    {t("지우기")}
                  </button>
                </li>
              ))}
            </ul>
            {!onDelete && (
              <p className="text-[11px] font-bold text-[var(--text-label)]">{t("응답이 끝난 뒤에 지울 수 있습니다.")}</p>
            )}
          </>
        )}
      </div>
    </DialogFrame>
  );
}

// n8n 설정 패널처럼 입력 · 설정 · 출력 3단. 노드별 입력/출력 데이터(남은 종목 수 등)는 아직 백엔드가
// 단계별로 내주지 않는다 — 지어내지 않고 비어 있음을 그대로 표시한다.
// TODO(strategy-lab): 백테스트 결과에 단계별 통과 종목 수가 실리면 입력/출력 칸에 연결한다.
function DetailsDialog({
  node,
  editItems,
  onEdit,
  onClose,
  onDelete,
}: {
  node: LabNode;
  editItems: EditableItem[];
  onEdit?: (itemId: string, changes: Record<string, number | string>) => void;
  onClose: () => void;
  onDelete: () => void;
}) {
  const graphNode = node.type === "condition" ? (node.data as ConditionNodeData).graphNode : null;
  const rows = graphNode ? visibleRows(graphNode) : [];
  const pipelineData = node.type === "pipeline" ? (node.data as PipelineNodeData) : null;
  return (
    <DialogFrame title={node.data.label} onClose={onClose}>
      <div className="min-h-0 flex-1 overflow-auto">
        <section className="p-4">
          <p className="text-[11px] font-black text-[var(--text-label)]">{t("설정")}</p>
          {graphNode ? (
            <dl className="mt-2 space-y-1.5">
              {graphNode.details.role && <Row label={t("역할")} value={graphNode.details.role} />}
              {graphNode.details.expression && <Row label={t("조건")} value={graphNode.details.expression} />}
              {rows.map((row) => (
                <Row key={row.label} label={row.label} value={row.value} />
              ))}
              {graphNode.details.statusNote && (
                <p className="pt-1 text-[11px] font-bold leading-relaxed text-[var(--chat-accent)]">{graphNode.details.statusNote}</p>
              )}
            </dl>
          ) : (
            <dl className="mt-2 space-y-1.5">
              <Row label={t("항목 수")} value={String(pipelineData?.itemCount ?? 0)} />
              {pipelineData?.logic && <Row label={t("결합 방식")} value={pipelineData.logic} />}
            </dl>
          )}
          {editItems.length > 0 ? (
            <div className="mt-3 space-y-2" data-testid="lab-item-editors">
              <p className="text-[11px] font-black text-[var(--text-label)]">{t("값 바꾸기")}</p>
              {editItems.map((item) => (
                <ItemEditor key={item.id} item={item} onApply={onEdit ? (changes) => onEdit(item.id, changes) : undefined} />
              ))}
            </div>
          ) : (
            <p className="mt-3 text-[11px] font-bold leading-relaxed text-[var(--text-label)]">
              {t("값을 바꾸려면 채팅으로 알려 주세요.")}
            </p>
          )}
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              onClick={onDelete}
              className="flex items-center gap-1 rounded-lg border border-[var(--lab-border-strong)] px-2 py-1 text-[11px] font-black text-gray-300 hover:text-white"
            >
              <Trash size={11} />
              {t("지우기")}
            </button>
          </div>
        </section>
      </div>
    </DialogFrame>
  );
}

function fieldValid(field: EditableField, raw: string): boolean {
  if (field.kind === "choice") return raw !== "";
  if (raw.trim() === "") return false;
  const value = Number(raw);
  if (!Number.isFinite(value)) return false;
  if (field.integer && !Number.isInteger(value)) return false;
  if (field.min !== undefined && value < field.min) return false;
  if (field.max !== undefined && value > field.max) return false;
  return true;
}

// 전략 항목 하나의 값 편집 — 바꾼 칸만 모아 적용한다. 범위를 벗어난 숫자는 적용할 수 없다.
function ItemEditor({ item, onApply }: { item: EditableItem; onApply?: (changes: Record<string, number | string>) => void }) {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(item.fields.map((f) => [f.key, String(f.value)])),
  );
  const changed = item.fields.filter((f) => draft[f.key] !== String(f.value));
  const valid = item.fields.every((f) => fieldValid(f, draft[f.key] ?? ""));
  const apply = () => {
    if (!onApply || changed.length === 0 || !valid) return;
    onApply(Object.fromEntries(changed.map((f) => [f.key, f.kind === "number" ? Number(draft[f.key]) : draft[f.key]])));
  };
  return (
    <div className="rounded-lg border border-[var(--lab-border)] p-2.5" data-testid="lab-item-editor">
      <p className="text-xs font-black text-white">
        {item.label} <span className="font-bold text-[var(--text-label)]">{item.value}</span>
      </p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        {item.fields.map((field) => (
          <label key={field.key} className="flex flex-col gap-1 text-[11px] font-bold text-[var(--text-label)]">
            {field.label}
            {field.kind === "number" ? (
              <input
                type="number"
                inputMode="decimal"
                step={field.integer ? 1 : "any"}
                min={field.min}
                max={field.max}
                value={draft[field.key] ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, [field.key]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") apply();
                }}
                aria-invalid={!fieldValid(field, draft[field.key] ?? "")}
                className="w-24 rounded-md border border-[var(--lab-border-strong)] bg-[var(--lab-canvas)] px-2 py-1 text-xs font-bold text-white aria-[invalid=true]:border-[var(--error-red)] focus:border-[var(--lab-border-focus)] focus:outline-none"
              />
            ) : (
              <select
                value={draft[field.key] ?? ""}
                onChange={(e) => setDraft((d) => ({ ...d, [field.key]: e.target.value }))}
                className="rounded-md border border-[var(--lab-border-strong)] bg-[var(--lab-canvas)] px-2 py-1 text-xs font-bold text-white focus:border-[var(--lab-border-focus)] focus:outline-none"
              >
                {field.value === "" && <option value="">{t("선택")}</option>}
                {field.options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            )}
          </label>
        ))}
        <button
          type="button"
          onClick={apply}
          disabled={!onApply || changed.length === 0 || !valid}
          className="rounded-md bg-[var(--chat-accent)] px-2.5 py-1 text-[11px] font-black text-[var(--chat-accent-ink)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t("적용")}
        </button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-xs">
      <dt className="w-20 flex-shrink-0 font-bold text-[var(--text-label)]">{label}</dt>
      <dd className="min-w-0 font-bold text-white">{value}</dd>
    </div>
  );
}

function StrategyCanvas(props: StrategyCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}

export default memo(StrategyCanvas);
