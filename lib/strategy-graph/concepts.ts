import { t } from "@/lib/i18n";
import { GraphBuilder, metaName, row, supportToStatus, unitText } from "./graphBuilder";
import type { GraphMeta, IndicatorMeta } from "./types";

// Ontology concept relations, kept separate from strategy-instance relations. Conditions that
// use the same indicator share one indicator node; classification nodes hang above it.

export function classPathOf(meta: GraphMeta, classId: string | null): string[] {
  const names: string[] = [];
  const seen = new Set<string>();
  let current = classId;
  while (current && !seen.has(current)) {
    seen.add(current);
    const cls = meta.classes.find((c) => c.id === current);
    if (!cls) break;
    names.unshift(cls.name);
    current = cls.parent;
  }
  return names;
}

export function supportNote(ind: IndicatorMeta): string | null {
  if (ind.dataPending) return t("데이터 준비 중인 지표입니다.");
  if (ind.supported === "UNSUPPORTED") return t("지원하지 않는 지표입니다.");
  if (ind.supported === "PARTIALLY_SUPPORTED") return t("일부 종목·기간은 데이터가 없을 수 있습니다.");
  return null;
}

/** Link a strategy-instance node to its (shared) indicator concept and classification chain. */
export function linkIndicator(b: GraphBuilder, instanceId: string, leafId: string | null): void {
  const meta = b.meta;
  if (!meta || !leafId) return;
  const ind = meta.indicators[leafId];
  if (!ind) return;

  const indId = `ind:${leafId}`;
  const status = supportToStatus(ind.supported, ind.dataPending);
  b.node(indId, "indicator", metaName(ind), status, `registry:${leafId}`, null, {
    role: t("지표 개념"),
    support: ind.supported,
    classPath: classPathOf(meta, ind.classId),
    statusNote: supportNote(ind),
    valueSource: "metadata",
    rows: unitText(ind.unit) ? [row(t("값의 단위"), unitText(ind.unit) as string)] : [],
  });
  b.edge("uses_indicator", instanceId, indId, t("사용 지표"));

  // Walk the classification chain upwards: indicator -> class -> parent class ...
  let child = indId;
  let classId = ind.classId;
  const seen = new Set<string>();
  while (classId && !seen.has(classId)) {
    seen.add(classId);
    const cls = meta.classes.find((c) => c.id === classId);
    if (!cls) break;
    const nodeId = `class:${cls.id}`;
    b.node(nodeId, "class", cls.name, "ok", `registry:${cls.id}`, null, {
      role: t("지표 분류"),
      statusNote: cls.description || null,
      valueSource: "metadata",
    });
    b.edge("is_a", child, nodeId, t("분류"));
    child = nodeId;
    classId = cls.parent;
  }
}
