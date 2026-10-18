"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ArrowsIn, MagnifyingGlassMinus, MagnifyingGlassPlus } from "phosphor-react";
import { t } from "@/lib/i18n";
import { layoutTree, type LayoutItem, type OpenState } from "@/lib/strategy-graph/layout";
import type { StrategyGraph } from "@/lib/strategy-graph/types";
import { kindLabel } from "./graphLabels";

// One calm blue family for every node (kind is told apart by position, label and shape, not by
// per-kind colour); edge labels sit on the edges as pills.
const NODE_FILL = "#0e2748";
const NODE_STROKE = "#24457a";
const NODE_TEXT = "#bcd7ff";
const PILL_FILL = "#08172b";
const PILL_STROKE = "#1d3a66";
const EDGE = "#9aa3b2";
const SELECT = "#e8f1ff";

const MIN_SCALE = 0.3;
// Default size of the whole graph (nodes and text scale together); zoom buttons change it.
const DEFAULT_SCALE = 0.7;
const MAX_SCALE = 2;
const PAD = 16;

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
  const isNewItem = (key: string) => !drawn.items.has(key);
  const isNewEdge = (key: string) => !drawn.edges.has(key);
  useEffect(() => {
    layout.order.forEach((k) => drawn.items.add(k));
    layout.edges.forEach((e) => drawn.edges.add(e.key));
  }, [layout, drawn]);

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
      <div className="flex items-center gap-1.5">
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
              const delay = `${fresh ? 180 + Math.min(to.depth, 8) * 70 : 0}ms`;
              return (
                <g key={e.key} opacity={dim ? 0.2 : 1} style={{ transition: "opacity 250ms" }}>
                  <path
                    d={e.d}
                    pathLength={1}
                    className={`sg-edge${fresh ? " sg-draw" : ""}`}
                    style={{ animationDelay: delay, d: `path("${e.d}")` } as CSSProperties}
                    fill="none"
                    stroke={EDGE}
                    strokeWidth={1.4}
                    opacity={0.85}
                  />
                  {e.arrow && e.end && (
                    <g className="sg-edge" style={{ transform: `translate(${e.end.x}px, ${e.end.y}px)` }}>
                      <polyline
                        className={fresh ? "sg-fade" : undefined}
                        style={{ animationDelay: `${fresh ? 180 + Math.min(to.depth, 8) * 70 + 420 : 0}ms` }}
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
              const rx = isPill ? i.h / 2 : i.kind === "leaf" ? 14 : 22;
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
                  <g className={isNewItem(key) ? "sg-enter" : undefined} style={{ animationDelay: `${120 + Math.min(i.depth, 8) * 70}ms` }}>
                  <rect
                    x={0}
                    y={0}
                    width={i.w}
                    height={i.h}
                    rx={rx}
                    fill={isPill ? PILL_FILL : NODE_FILL}
                    stroke={selected ? SELECT : isPill ? PILL_STROKE : NODE_STROKE}
                    strokeWidth={selected ? 2.5 : 1.2}
                    strokeDasharray={i.unresolved ? "5 4" : undefined}
                  />
                  <foreignObject x={6} y={2} width={i.w - 12} height={i.h - 4}>
                    <div
                      className="flex h-full flex-col items-center justify-center text-center leading-tight"
                      style={{ color: NODE_TEXT, fontSize: isPill ? 13 : 14, fontWeight: 700 }}
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
