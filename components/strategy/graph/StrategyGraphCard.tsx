"use client";

import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Graph, ListBullets } from "phosphor-react";
import { t } from "@/lib/i18n";
import { isEmptyGraph, buildStrategyGraph } from "@/lib/strategy-graph/transform";
import { useGraphMeta } from "@/lib/strategy-graph/useGraphMeta";
import type { StrategyGraph, StrategyGraphInput } from "@/lib/strategy-graph/types";
import StrategyGraphText from "./StrategyGraphText";
import StrategyGraphView, { type GraphSeen } from "./StrategyGraphView";
import { defaultExpanded, expandableIds } from "@/lib/strategy-graph/layout";

interface CardProps {
  input: StrategyGraphInput;
  /** Card title, e.g. "확정된 전략". */
  title: string;
  /** Shown instead of the graph when the entry point has no snapshot. */
  noSnapshotMessage?: string;
  testId?: string;
  /** What a previous card of the same conversation already drew — only the rest animates. */
  seen?: GraphSeen;
  /** Shown right under the title row, above the graph (e.g. the confirmed-summary chips). */
  summary?: ReactNode;
}

type View = "graph" | "text";

function Workspace({ graph, seen, view }: { graph: StrategyGraph; seen?: GraphSeen; view: View }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => defaultExpanded(graph));
  const open = useMemo(() => ({ expanded }), [expanded]);
  const expandable = useMemo(() => new Set(expandableIds(graph)), [graph]);

  const toggle = (set: ReadonlySet<string>, id: string, force?: boolean) => {
    const next = new Set(set);
    if (force === true || (force === undefined && !next.has(id))) next.add(id);
    else next.delete(id);
    return next;
  };
  const select = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      // Progressive disclosure: selecting an item opens only its own parameters and indicator.
      if (id && expandable.has(id)) setExpanded((prev) => toggle(prev, id, true));
    },
    [expandable],
  );

  return (
    <div className="flex flex-col gap-3">
      {view === "text" ? (
        <StrategyGraphText graph={graph} />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="min-w-0 flex-1">
            <StrategyGraphView
              graph={graph}
              selectedId={selectedId}
              open={open}
              onSelect={select}
              seen={seen}
            />
          </div>
        </div>
      )}

      {graph.notes.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs font-bold text-[var(--text-label)]" data-testid="graph-notes">
          {graph.notes.map((n) => <li key={n}>{n}</li>)}
        </ul>
      )}
      {graph.notices.length > 0 && (
        <details className="rounded-lg border border-[var(--chat-hairline)] px-3 py-2 text-xs font-bold text-gray-300">
          <summary className="cursor-pointer text-[var(--text-label)]">{t("해석 안내")} ({graph.notices.length})</summary>
          <ul className="mt-1.5 flex flex-col gap-1">{graph.notices.map((n, i) => <li key={i} className="whitespace-pre-line">{t(n)}</li>)}</ul>
        </details>
      )}
    </div>
  );
}

const segment = (on: boolean) =>
  `inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-bold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50 ${on ? "bg-white/[0.12] text-white" : "text-gray-400 hover:text-gray-200"}`;

/**
 * Read-only strategy graph card. The caller passes ONE frozen snapshot; this component never
 * reads mutable strategy state, never calls the confirm/compile API, and never calls an LLM.
 * Retrying only re-requests the public metadata and/or rebuilds the graph from the same input.
 */
export default function StrategyGraphCard({ input, title, noSnapshotMessage, testId = "strategy-graph-card", seen, summary }: CardProps) {
  const metaState = useGraphMeta();
  const [view, setView] = useState<View>("graph");
  // Widen only the graph: the card keeps its left edge (everything else stays where it is) and
  // grows to the right, up to the space that is left in the window.
  const sectionRef = useRef<HTMLElement>(null);
  const [wide, setWide] = useState<number | null>(null);
  useLayoutEffect(() => {
    const measure = () => {
      const el = sectionRef.current;
      if (!el || typeof window === "undefined") return;
      const left = el.getBoundingClientRect().left;
      setWide(Math.max(0, Math.min(MAX_WIDE, Math.floor(window.innerWidth - left - 16))));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  const [attempt, setAttempt] = useState(0);

  const built = useMemo(() => {
    if (metaState.status === "loading") return null;
    try {
      return { graph: buildStrategyGraph(input, metaState.meta) };
    } catch {
      return { error: true as const };
    }
    // attempt forces a rebuild from the same snapshot on retry
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [input, metaState.status, metaState.meta, attempt]);

  const noSnapshot = input.origin === "none";
  const graph = built && "graph" in built ? built.graph : null;

  return (
    <section ref={sectionRef} aria-label={title} data-testid={testId} className="w-full" style={wide ? { width: wide, maxWidth: "none" } : undefined}>
      <header className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        <h3 className="text-sm font-black text-white">{title}</h3>
        {graph && !noSnapshot && !isEmptyGraph(graph) && (
          <div role="group" aria-label={t("보기 방식")} className="inline-flex rounded-lg border border-[var(--chat-hairline)] p-0.5">
            <button type="button" aria-pressed={view === "graph"} onClick={() => setView("graph")} className={segment(view === "graph")}>
              <Graph size={14} />{t("그래프")}
            </button>
            <button type="button" aria-pressed={view === "text"} onClick={() => setView("text")} className={segment(view === "text")}>
              <ListBullets size={14} />{t("텍스트로 보기")}
            </button>
          </div>
        )}
      </header>
      {summary && <div className="mb-3">{summary}</div>}

      {noSnapshot ? (
        <p className="text-sm font-bold text-gray-300" data-testid="graph-no-snapshot">
          {noSnapshotMessage ?? t("이 실행의 전략 스냅샷이 저장되어 있지 않습니다.")}
        </p>
      ) : metaState.status === "loading" ? (
        <p className="text-sm font-bold text-[var(--text-label)]" role="status" data-testid="graph-loading">{t("전략 구조를 준비하는 중입니다.")}</p>
      ) : built && "error" in built ? (
        <div role="alert" className="flex items-center gap-3 text-sm font-bold text-gray-200" data-testid="graph-build-error">
          <span className="flex-1">{t("전략 그래프를 만들지 못했습니다.")}</span>
          <button type="button" onClick={() => setAttempt((n) => n + 1)} className={retryButton}>{t("다시 시도")}</button>
        </div>
      ) : graph && isEmptyGraph(graph) ? (
        <p className="text-sm font-bold text-gray-300" data-testid="graph-empty">{t("표시할 전략 항목이 없습니다.")}</p>
      ) : graph ? (
        <div className="flex flex-col gap-3">
          {metaState.status === "error" && (
            <div role="alert" className="flex items-center gap-3 rounded-lg bg-white/[0.05] px-3 py-2 text-xs font-bold text-gray-200" data-testid="graph-meta-error">
              <span className="flex-1">{t("지표 정보를 불러오지 못해 이름과 분류 없이 구조만 표시합니다.")}</span>
              <button type="button" onClick={metaState.retry} className={retryButton}>{t("다시 시도")}</button>
            </div>
          )}
          <Workspace graph={graph} seen={seen} view={view} />
        </div>
      ) : null}

    </section>
  );
}

const MAX_WIDE = 1600;


const retryButton =
  "rounded-lg border border-[var(--chat-hairline)] px-3 py-1 text-xs font-bold text-gray-100 hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50";
