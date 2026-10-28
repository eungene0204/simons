"use client";

import { memo, type ComponentType, type CSSProperties } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import {
  ChartLineUp,
  ChartPie,
  ArrowsClockwise,
  CheckCircle,
  Funnel,
  Globe,
  Lightning,
  Plus,
  ShieldCheck,
  Warning,
  type IconProps,
} from "phosphor-react";
import { t } from "@/lib/i18n";
import type { ConditionNodeData, LabNodeStatus, PipelineNodeData, StageFamily } from "./labGraph";

// n8n 스타일 노드 — 칸 노드는 둥근 정사각형 + 가운데 아이콘 + 아래 이름, 좌/우 흐름 포트와 하단 보조
// 포트를 가진다. 조건 노드는 보조 포트에 매달리는 알약 모양이다. 종류 구분은 아이콘이 하고 색은
// 상태에만 쓴다(강조색=사용자 응답이 필요한 지점·진행 상태, UI 가이드라인 §2).

export const FAMILY_ICON: Record<StageFamily, ComponentType<IconProps>> = {
  universe: Globe,
  filter: Funnel,
  signal: Lightning,
  sizing: ChartPie,
  risk: ShieldCheck,
  output: ChartLineUp,
};

// 같은 종류 안에서 칸을 구분해야 할 때만 칸 단위로 덮어쓴다(자금 배분=파이, 리밸런싱=순환 화살표).
const STAGE_ICON: Partial<Record<PipelineNodeData["stage"], ComponentType<IconProps>>> = {
  rebalance: ArrowsClockwise,
};

/** 캔버스가 실행 상태를 노드에 내려 줄 때 쓰는 추가 필드(그래프 모델 밖, 표시 전용). */
export type RunDecoration = {
  runState?: "idle" | "running" | "done" | "error";
  /** 실행 중 순서대로 켜지는 연출의 순번. */
  runIndex?: number;
  pulse?: boolean;
  onAdd?: () => void;
};

const HANDLE_CLASS = "!h-2.5 !w-2.5 !rounded-full !border !border-[var(--lab-border-strong)] !bg-[var(--lab-panel)]";

function StatusBadge({ status, runState }: { status: LabNodeStatus; runState?: RunDecoration["runState"] }) {
  if (status === "pending" || status === "unsupported") {
    return (
      <span
        className="absolute -bottom-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--lab-panel)]"
        title={t(status === "pending" ? "값이 정해지지 않았습니다" : "지원하지 않는 조건입니다")}
      >
        <Warning size={16} weight="fill" className={status === "pending" ? "text-[var(--chat-accent)]" : "text-[var(--error-red)]"} />
      </span>
    );
  }
  if (runState === "done") {
    return (
      <span className="absolute -bottom-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--lab-panel)]" title={t("실행 완료")}>
        <CheckCircle size={16} weight="fill" className="text-[var(--success-green)]" />
      </span>
    );
  }
  return null;
}

function nodeStateClass(selected: boolean, d: RunDecoration): string {
  return [
    selected ? "border-[var(--lab-border-focus)]" : "border-[var(--lab-border-strong)]",
    d.pulse ? "lab-node-pulse" : "",
    d.runState === "running" ? "lab-node-running" : "",
  ].join(" ");
}

type PipelineNodeType = Node<PipelineNodeData & RunDecoration, "pipeline">;
type ConditionNodeType = Node<ConditionNodeData & RunDecoration, "condition">;

export const PipelineNode = memo(function PipelineNode({ data, selected }: NodeProps<PipelineNodeType>) {
  const Icon = STAGE_ICON[data.stage] ?? FAMILY_ICON[data.family];
  const isOutput = data.stage === "output";
  const failed = isOutput && data.runState === "error";
  return (
    <div className="group flex w-[120px] flex-col items-center gap-2" data-testid={`lab-node-${data.stage}`}>
      <div
        className={`relative flex h-[88px] w-[88px] items-center justify-center rounded-2xl border bg-[var(--lab-node)] transition-colors ${nodeStateClass(!!selected, data)} ${failed ? "!border-[var(--error-red)]" : ""}`}
        style={data.runIndex !== undefined ? ({ "--lab-run-delay": `${data.runIndex * 180}ms` } as CSSProperties) : undefined}
      >
        <Handle type="target" id="in" position={Position.Left} className={HANDLE_CLASS} isConnectable={false} />
        <Icon size={32} weight="duotone" className="text-white" />
        {!isOutput && <Handle type="source" id="out" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
        {!isOutput && <Handle type="source" id="aux" position={Position.Bottom} className={`${HANDLE_CLASS} !rounded-sm`} isConnectable={false} />}
        {failed ? (
          <span className="absolute -bottom-1.5 -right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--lab-panel)]" title={t("백테스트 실패")}>
            <Warning size={16} weight="fill" className="text-[var(--error-red)]" />
          </span>
        ) : (
          <StatusBadge status={data.status} runState={data.runState} />
        )}
        {!isOutput && data.onAdd && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              data.onAdd?.();
            }}
            aria-label={t("{0}에 조건 추가", data.label)}
            title={t("{0}에 조건 추가", data.label)}
            className="nodrag absolute -bottom-9 left-1/2 flex h-6 w-6 -translate-x-1/2 items-center justify-center rounded-md border border-[var(--lab-border-strong)] bg-[var(--lab-panel)] text-[var(--text-label)] opacity-0 transition-opacity hover:text-white focus-visible:opacity-100 group-hover:opacity-100"
          >
            <Plus size={12} weight="bold" />
          </button>
        )}
      </div>
      <div className="text-center leading-tight">
        <p className="text-xs font-black text-white">{data.label}</p>
        {data.logic && <p className="mt-0.5 text-[11px] font-bold text-[var(--text-label)]">{data.logic}</p>}
      </div>
    </div>
  );
});

export const ConditionNode = memo(function ConditionNode({ data, selected }: NodeProps<ConditionNodeType>) {
  const Icon = FAMILY_ICON[data.family];
  return (
    <div
      className={`relative flex w-[200px] items-center gap-2 rounded-full border bg-[var(--lab-node)] py-2 pl-2 pr-3 ${nodeStateClass(!!selected, data)}`}
      data-testid="lab-condition-node"
      title={data.label}
    >
      <Handle type="target" id="top" position={Position.Top} className={HANDLE_CLASS} isConnectable={false} />
      {data.sellTrigger && <Handle type="target" id="side" position={Position.Left} className={HANDLE_CLASS} isConnectable={false} />}
      {data.swapTrade && <Handle type="source" id="trade" position={Position.Right} className={HANDLE_CLASS} isConnectable={false} />}
      <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[var(--lab-panel)]">
        <Icon size={14} weight="bold" className="text-[var(--text-label)]" />
      </span>
      <span className="min-w-0 flex-1 truncate text-xs font-bold text-white">{data.label}</span>
      <StatusBadge status={data.status} runState={data.runState} />
    </div>
  );
});

export const LAB_NODE_TYPES = { pipeline: PipelineNode, condition: ConditionNode };
