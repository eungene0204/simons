"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ArrowsIn, MagnifyingGlassMinus, MagnifyingGlassPlus } from "phosphor-react";
import { t } from "@/lib/i18n";
import { layoutTree, type LayoutItem, type OpenState } from "@/lib/strategy-graph/layout";
import type { StrategyGraph } from "@/lib/strategy-graph/types";
import { kindLabel } from "./graphLabels";

// Warm dark palette (docs/UI_GUIDELINES.md): flat cards on the page background, the strategy root
// in the single terracotta accent, soft cream hairlines for edges. Kind is told apart by position,
// label and shape, not by per-kind colour.
const NODE_FILL = "#1e1d1a";
const NODE_STROKE = "rgba(244,241,234,0.16)";
const NODE_TEXT = "#f4f1ea";
const LEAF_FILL = "rgba(244,241,234,0.03)";
const LEAF_TEXT = "#d8d4cb";
const PILL_FILL = "rgba(244,241,234,0.07)";
const PILL_STROKE = "rgba(244,241,234,0.16)";
const ROOT_FILL = "#e0805c";
const ROOT_TEXT = "#1c0f09";
const EDGE = "rgba(244,241,234,0.3)";
const SELECT = "#e0805c";

const MIN_SCALE = 0.3;
// Default size of the whole graph (nodes and text scale together); zoom buttons change it.
const DEFAULT_SCALE = 0.7;
const MAX_SCALE = 2;
const PAD = 16;
// First draw of a whole graph: one item per step (capped to a total), after the edge leading to it.
const BUILD_UP_MIN_ITEMS = 4;
const BUILD_UP_STEP_MS = 380;
const BUILD_UP_TOTAL_MS = 7000;
const BUILD_UP_EDGE_LEAD_MS = 320;
/** Keys of what has already been drawn; only what is not in here animates in. */
export interface GraphSeen {
  items: Set<string>;
  edges: Set<string>;
}
export const createGraphSeen = (): GraphSeen => ({ items: new Set(), edges: new Set() });

interface Props {
  seen?: GraphSeen;
  graph: StrategyGraph;
  selectedId: string | null;
  open: OpenState;
  onSelect: (id: string | null) => void;
}

export default function StrategyGraphView({ graph, selectedId, open, onSelect, seen }: Props) {
  const ownSeen = useRef<GraphSeen>(createGraphSeen());
  const drawn = seen ?? ownSeen.current;
  const layout = useMemo(() => layoutTree(graph, open), [graph, open]);
  const hostRef = useRef<HTMLDivElement>(null);
  const refs = useRef(new Map<string, SVGGElement>());
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const layoutWidth = useRef(layout.width);
  layoutWidth.current = layout.width;
  // Starts fitted to the available width (as if "화면에 맞추기" had been pressed) and follows the
  // width of the card until the user zooms by hand. Opening an item never re-fits the view.
  const auto = useRef(true);
  const fit = useCallback((floor = MIN_SCALE) => {
    const host = hostRef.current;
    if (!host || host.clientWidth === 0) return;
    const next = (host.clientWidth - PAD * 2) / Math.max(1, layoutWidth.current);
    setScale(Math.max(floor, Math.min(1, next)));
    host.scrollTo?.({ left: 0, top: 0 });
  }, []);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    if (auto.current) fit();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => auto.current && fit());
    observer.observe(host);
    return () => observer.disconnect();
  }, [fit]);

  const zoom = (change: (s: number) => number) => {
    auto.current = false;
    setScale(change);
  };
  // Nothing scrolls the view on selection.
  // Direct relations of the selection (graph edges), used to dim everything else.
  const related = useMemo(() => {
    if (!selectedId) return null;
    const ids = new Set([selectedId]);
    for (const e of graph.edges) {
      if (e.source === selectedId) ids.add(e.target);
      if (e.target === selectedId) ids.add(e.source);
    }
    return ids;
  }, [graph.edges, selectedId]);

  // Decided during render (before the effect below records the keys): new items/edges animate in,
  // everything that was already drawn just stays put or glides to its new place.
  // Fixed per layout: a re-render for another reason (e.g. the fit-to-width scale right after
  // mounting) must not turn everything "already drawn" before the animation has played.
  const fresh = useMemo(
    () => ({
      items: new Set(layout.order.filter((k) => !drawn.items.has(k))),
      edges: new Set(layout.edges.map((e) => e.key).filter((k) => !drawn.edges.has(k))),
    }),
    [layout, drawn],
  );
  const isNewItem = (key: string) => fresh.items.has(key);
  const isNewEdge = (key: string) => fresh.edges.has(key);
  // A graph drawn for the first time (many new items) builds up one item at a time in flow order,
  // each item appearing right after the edge that leads to it. Small additions keep the quick stagger.
  const freshOrder = layout.order.filter(isNewItem);
  const buildUp = freshOrder.length >= BUILD_UP_MIN_ITEMS;
  const buildStep = Math.min(BUILD_UP_STEP_MS, BUILD_UP_TOTAL_MS / Math.max(1, freshOrder.length));
  const rankOf = (key: string) => Math.max(0, freshOrder.indexOf(key));
  const edgeDelayMs = (key: string, depth: number) =>
    buildUp ? 150 + rankOf(key) * buildStep : 180 + Math.min(depth, 8) * 70;
  const itemDelayMs = (key: string, depth: number) =>
    buildUp ? 150 + rankOf(key) * buildStep + BUILD_UP_EDGE_LEAD_MS : 120 + Math.min(depth, 8) * 70;
  useEffect(() => {
    layout.order.forEach((k) => drawn.items.add(k));
    layout.edges.forEach((e) => drawn.edges.add(e.key));
  }, [layout, drawn]);

  // A click anywhere other than a node (or the zoom toolbar) clears the selection.
  useEffect(() => {
    if (!selectedId) return;
    const clear = (event: MouseEvent) => {
      const target = event.target;
      if (target instanceof Element && target.closest("[data-node-id], [data-graph-toolbar]")) return;
      onSelect(null);
    };
    document.addEventListener("click", clear);
    return () => document.removeEventListener("click", clear);
  }, [selectedId, onSelect]);

  const isDim = (i: LayoutItem) => related != null && !related.has(i.owner) && !(i.nodeId && related.has(i.nodeId));
  const focusable = (i: LayoutItem) => i.nodeId != null;
  const tabStopKey = useMemo(() => {
    const sel = selectedId ? layout.order.find((k) => layout.items.get(k)?.nodeId === selectedId) : undefined;
    return sel ?? layout.order.find((k) => layout.items.get(k)?.nodeId === "strategy");
  }, [layout, selectedId]);

  const focusKey = (key: string | undefined) => key && refs.current.get(key)?.focus();
  const move = (item: LayoutItem, dir: string) => {
    const all = layout.order.map((k) => layout.items.get(k)!).filter(focusable);
    if (dir === "ArrowDown") return focusKey(all.find((i) => i.parentKey === item.key || layout.items.get(i.parentKey ?? "")?.parentKey === item.key)?.key);
    if (dir === "ArrowUp") {
      let p = item.parentKey ? layout.items.get(item.parentKey) : undefined;
      while (p && !focusable(p)) p = p.parentKey ? layout.items.get(p.parentKey) : undefined;
      return focusKey(p?.key);
    }
    const row = all.filter((i) => i.depth === item.depth).sort((a, b) => a.x - b.x);
    const at = row.findIndex((i) => i.key === item.key);
    focusKey(row[at + (dir === "ArrowRight" ? 1 : -1)]?.key);
  };

  const onKey = (event: React.KeyboardEvent, item: LayoutItem) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(item.nodeId === selectedId ? null : item.nodeId);
    } else if (event.key === "Escape" && selectedId) {
      event.stopPropagation();
      onSelect(null);
    } else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
      move(item, event.key);
    }
  };

  // No left padding: the graph starts at the same left edge as the card title and toolbar.
  const w = Math.ceil(layout.width * scale) + PAD;
  const h = Math.ceil(layout.height * scale) + PAD * 2;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <style>{ANIMATION_CSS}</style>
      <div data-graph-toolbar className="flex items-center gap-1.5">
        <button type="button" aria-label={t("축소")} onClick={() => zoom((s) => Math.max(MIN_SCALE, +(s - 0.15).toFixed(2)))} className={toolButton}>
          <MagnifyingGlassMinus size={16} />
        </button>
        <button type="button" aria-label={t("확대")} onClick={() => zoom((s) => Math.min(MAX_SCALE, +(s + 0.15).toFixed(2)))} className={toolButton}>
          <MagnifyingGlassPlus size={16} />
        </button>
        <button type="button" onClick={() => { auto.current = true; fit(); }} className={`${toolButton} gap-1 px-2.5 text-xs font-bold`}>
          <ArrowsIn size={14} />
          {t("화면에 맞추기")}
        </button>
        <span className="ml-auto text-xs font-bold tabular-nums text-[var(--text-label)]" aria-live="polite">
          {Math.round(scale * 100)}%
        </span>
      </div>
      <div ref={hostRef} data-testid="strategy-graph-canvas" className="relative overflow-x-auto">
        <svg width={w} height={h} role="group" aria-label={t("전략 구조 그래프")} className="block">
          <g transform={`translate(0 ${PAD}) scale(${scale})`}>
            {layout.edges.map((e) => {
              const to = layout.items.get(e.to)!;
              const from = layout.items.get(e.from)!;
              const dim = related != null && isDim(to) && isDim(from);
              // Keyed by the edge, not its route: an existing edge morphs to its new route (CSS `d`
              // transition where supported), only a brand-new edge draws itself.
              const fresh = isNewEdge(e.key);
              const edgeDelay = edgeDelayMs(e.to, to.depth);
              const delay = `${fresh ? edgeDelay : 0}ms`;
              return (
                <g key={e.key} opacity={dim ? 0.2 : 1} style={{ transition: "opacity 250ms" }}>
                  <path
                    d={e.d}
                    pathLength={1}
                    className={`sg-edge${fresh ? " sg-draw" : ""}`}
                    style={{ animationDelay: delay, d: `path("${e.d}")` } as CSSProperties}
                    fill="none"
                    stroke={EDGE}
                    strokeWidth={1.6}
                    opacity={0.85}
                  />
                  {e.arrow && e.end && (
                    <g className="sg-edge" style={{ transform: `translate(${e.end.x}px, ${e.end.y}px)` }}>
                      <polyline
                        className={fresh ? "sg-fade" : undefined}
                        style={{ animationDelay: `${fresh ? edgeDelay + 420 : 0}ms` }}
                        points={e.end.dir === "down" ? "-5 -7 0 0 5 -7" : "-7 -5 0 0 -7 5"}
                        fill="none"
                        stroke={EDGE}
                        strokeWidth={1.4}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </g>
                  )}
                </g>
              );
            })}
            {layout.order.map((key) => {
              const i = layout.items.get(key)!;
              const selectable = i.nodeId != null;
              const selected = selectable && i.nodeId === selectedId;
              const isPill = i.kind === "pill";
              const isLeaf = i.kind === "leaf";
              const isRoot = i.nodeId === "strategy";
              const rx = isPill ? i.h / 2 : isLeaf ? 10 : 12;
              const label = i.lines.join(" ");
              return (
                <g
                  key={key}
                  ref={(el) => {
                    if (el) refs.current.set(key, el);
                    else refs.current.delete(key);
                  }}
                  opacity={isDim(i) ? 0.3 : 1}
                  // Position is a CSS transform so existing nodes glide when the layout changes.
                  style={{ transform: `translate(${i.x}px, ${i.y}px)`, transition: "transform 450ms cubic-bezier(0.22, 1, 0.36, 1), opacity 250ms" }}
                  data-item-key={key}
                  // 이번 배치에서 새로 그려진 항목 표시 — 하단 고정 카드가 뜰 때 페이지가 이 항목들이 보이게 스크롤한다.
                  data-fresh={isNewItem(key) ? "true" : undefined}
                  {...(selectable
                    ? {
                        role: "button",
                        tabIndex: key === tabStopKey ? 0 : -1,
                        "aria-pressed": selected,
                        "aria-label": [i.graphKind ? kindLabel(i.graphKind) : "", label, i.sub].filter(Boolean).join(", "),
                        "data-node-id": i.nodeId,
                        "data-kind": i.graphKind === "section" ? "section" : i.graphKind,
                        onClick: () => onSelect(selected ? null : i.nodeId),
                        onKeyDown: (ev: React.KeyboardEvent) => onKey(ev, i),
                        className: "sg-item cursor-pointer outline-none [&:focus-visible_rect]:stroke-[var(--chat-accent)] [&:focus-visible_rect]:stroke-[3px]",
                      }
                    : { "aria-hidden": true, className: "sg-item" })}
                >
                  <g className={isNewItem(key) ? "sg-enter" : undefined} style={{ animationDelay: `${itemDelayMs(key, i.depth)}ms` }}>
                  <rect
                    x={0}
                    y={0}
                    width={i.w}
                    height={i.h}
                    rx={rx}
                    fill={isRoot ? ROOT_FILL : isPill ? PILL_FILL : isLeaf ? LEAF_FILL : NODE_FILL}
                    stroke={selected ? SELECT : isRoot ? "none" : isPill ? PILL_STROKE : NODE_STROKE}
                    strokeWidth={selected ? 2.5 : 1.2}
                    strokeDasharray={i.unresolved ? "5 4" : undefined}
                  />
                  <foreignObject x={6} y={2} width={i.w - 12} height={i.h - 4}>
                    <div
                      className="flex h-full flex-col items-center justify-center text-center leading-tight"
                      style={{ color: isRoot ? ROOT_TEXT : isLeaf ? LEAF_TEXT : NODE_TEXT, fontSize: isPill ? 13 : 14, fontWeight: isRoot ? 800 : 700 }}
                    >
                      {i.lines.map((l, n) => (
                        <span key={n} style={{ lineHeight: "20px" }}>{l}</span>
                      ))}
                      {i.sub && <span style={{ fontSize: 11, opacity: 0.8, lineHeight: "14px" }}>{i.sub}</span>}
                    </div>
                  </foreignObject>
                  </g>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}

// Nodes pop in (fade + small rise), edges draw themselves, existing nodes glide (CSS transform).
// All of it is switched off for users who prefer reduced motion.
const ANIMATION_CSS = `
.sg-enter{animation:sg-pop 520ms cubic-bezier(0.22,1,0.36,1) both}
@keyframes sg-pop{from{opacity:0;transform:translateY(10px) scale(0.94)}to{opacity:1;transform:none}}
.sg-enter{transform-box:fill-box;transform-origin:center}
.sg-edge{transition:d 450ms cubic-bezier(0.22,1,0.36,1),transform 450ms cubic-bezier(0.22,1,0.36,1)}
.sg-fade{animation:sg-fade 300ms ease-out both}
@keyframes sg-fade{from{opacity:0}to{opacity:1}}
.sg-draw{stroke-dasharray:1;animation:sg-draw 650ms ease-out both}
@keyframes sg-draw{from{stroke-dashoffset:1;opacity:0.15}to{stroke-dashoffset:0;opacity:0.85}}
@media (prefers-reduced-motion: reduce){.sg-enter,.sg-draw,.sg-fade{animation:none}.sg-item,.sg-edge{transition:none !important}}
`;

const toolButton =
  "inline-flex h-8 min-w-8 items-center justify-center rounded-lg border border-[var(--chat-hairline)] px-1.5 text-gray-200 transition-colors hover:bg-white/[0.06] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50";
