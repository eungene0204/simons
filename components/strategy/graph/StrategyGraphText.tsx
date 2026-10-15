"use client";

import { t } from "@/lib/i18n";
import { buildOutline } from "@/lib/strategy-graph/textOutline";
import type { StrategyGraph } from "@/lib/strategy-graph/types";
import { statusLabel } from "./graphLabels";

// Text view of the same graph model the canvas renders (see lib/strategy-graph/textOutline.ts).
export default function StrategyGraphText({ graph }: { graph: StrategyGraph }) {
  const outline = buildOutline(graph);
  return (
    <div className="flex flex-col gap-3" data-testid="strategy-graph-text">
      {outline.map((section) => (
        <section key={section.id} aria-label={section.label}>
          <h4 className="text-xs font-black uppercase tracking-widest text-[var(--text-label)]">{section.label}</h4>
          <ul className="mt-1.5 flex flex-col gap-1.5">
            {section.items.map((item) => {
              const status = statusLabel(item.status);
              return (
                <li key={item.id} style={{ marginLeft: item.depth * 14 }} className="rounded-lg bg-white/[0.04] px-2.5 py-1.5 text-xs font-bold text-gray-100" data-outline-id={item.id}>
                  <span>{item.label}</span>
                  {status && <span className="ml-1.5 rounded bg-white/[0.1] px-1.5 py-0.5 text-[10px] text-[var(--text-label)]">{status}</span>}
                  {item.rows.length > 0 && (
                    <span className="mt-0.5 block font-medium text-[var(--text-label)]">
                      {item.rows.map((r) => `${r.label}: ${r.value}`).join(" · ")}
                    </span>
                  )}
                  {item.note && <span className="mt-0.5 block font-medium text-gray-300">{item.note}</span>}
                  {item.indicator && (
                    <span className="mt-0.5 block font-medium text-[var(--text-label)]">
                      {t("사용 지표")}: {item.indicator.name}
                      {item.indicator.path.length > 0 ? ` (${item.indicator.path.join(" › ")})` : ""}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
