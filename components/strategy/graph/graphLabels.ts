import { t } from "@/lib/i18n";
import type { GraphNode, NodeKind, NodeStatus } from "@/lib/strategy-graph/types";

// Neutral, text-first labels. Kinds are told apart by shape/icon/label, not by decorative colour.

export const KIND_LABELS: Record<NodeKind, string> = {
  strategy: "전략",
  section: "구분",
  group: "결합",
  condition: "조건",
  risk: "위험 관리",
  setting: "설정",
  indicator: "지표 개념",
  class: "지표 분류",
};

export const STATUS_LABELS: Record<NodeStatus, string | null> = {
  ok: null,
  pending: "미정",
  not_applicable: "기준값 해당 없음",
  unsupported: "미지원",
  partial: "부분 지원",
  data_pending: "준비 중",
  check_needed: "확인 필요",
};

export const kindLabel = (kind: NodeKind): string => t(KIND_LABELS[kind]);

export function statusLabel(status: NodeStatus): string | null {
  const label = STATUS_LABELS[status];
  return label ? t(label) : null;
}

/** Dashed outline for states that need attention (not a colour). */
export const isUnresolved = (status: NodeStatus): boolean =>
  status === "pending" || status === "check_needed" || status === "unsupported" || status === "data_pending";
