import type { ReactNode } from "react";

// 논문식 그림 틀 — "그림 N" 번호, 제목, 그림, 아래 설명(캡션). 연구 노트의 모든 도표가 같은 틀을 쓴다.
export default function LabFigure({
  number,
  title,
  caption,
  legend,
  children,
  testId,
}: {
  number: string;
  title: string;
  caption: ReactNode;
  legend?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <figure className="rounded-2xl border border-[var(--lab-border)] bg-[var(--lab-panel)]" data-testid={testId}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-2 border-b border-[var(--lab-border)] px-4 py-3">
        <p className="text-sm font-black text-white">
          <span className="mr-2 font-mono text-[11px] font-bold tracking-wider text-[var(--text-label)]">{number}</span>
          {title}
        </p>
        {legend && <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-bold text-[var(--text-label)]">{legend}</div>}
      </div>
      <div className="overflow-x-auto px-2 py-3 sm:px-4">{children}</div>
      <figcaption className="border-t border-[var(--lab-border)] px-4 py-3 text-xs font-bold leading-5 text-[var(--text-label)]">{caption}</figcaption>
    </figure>
  );
}

export function LegendSwatch({ color, label, line, dashed }: { color: string; label: string; line?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1.5">
      {line ? (
        <svg width="18" height="8" aria-hidden="true">
          <line x1="1" y1="4" x2="17" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dashed ? "4 3" : undefined} />
        </svg>
      ) : (
        <span className="h-2.5 w-2.5 rounded-sm" style={{ background: color }} />
      )}
      {label}
    </span>
  );
}
