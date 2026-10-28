"use client";

import { useEffect, useRef, useState } from "react";
import { CheckCircle, Play, ShareNetwork, Stop, Warning } from "phosphor-react";
import { t } from "@/lib/i18n";
import type { LabRunState } from "./StrategyCanvas";

type TopToolbarProps = {
  name: string;
  onRename: (name: string) => void;
  /** 전략 상태 한 줄("작성 중"·"실행 준비됨"). */
  statusLabel: string;
  runState: LabRunState;
  /** 실행할 수 없는 이유 — null이면 실행 가능. */
  runDisabledReason: string | null;
  onRun: () => void;
  onStop: () => void;
  zoom: number;
};

export default function TopToolbar({ name, onRename, statusLabel, runState, runDisabledReason, onRun, onStop, zoom }: TopToolbarProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(name);
  }, [name, editing]);
  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next && next !== name) onRename(next);
  };

  const running = runState === "running";
  const disabled = !running && runDisabledReason !== null;

  return (
    <header
      className="flex h-12 flex-shrink-0 items-center gap-3 border-b border-[var(--lab-border)] bg-[var(--lab-panel)] px-3"
      data-testid="lab-toolbar"
    >
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit();
              if (e.key === "Escape") setEditing(false);
            }}
            maxLength={60}
            aria-label={t("전략 이름")}
            className="min-w-0 max-w-xs rounded-md border border-[var(--lab-border-focus)] bg-transparent px-2 py-1 text-sm font-black text-white outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            title={t("이름 바꾸기")}
            className="min-w-0 truncate rounded-md px-2 py-1 text-sm font-black text-white hover:bg-white/[0.06]"
            data-testid="lab-strategy-name"
          >
            {name}
          </button>
        )}
        <span className="hidden flex-shrink-0 rounded-md bg-white/[0.06] px-2 py-0.5 text-[11px] font-bold text-gray-400 sm:inline">
          {statusLabel}
        </span>
      </div>

      <div className="flex flex-shrink-0 items-center gap-2">
        {runState === "done" && (
          <span className="hidden items-center gap-1 text-[11px] font-bold text-[var(--text-label)] md:flex">
            <CheckCircle size={13} weight="fill" className="text-[var(--success-green)]" />
            {t("실행 완료")}
          </span>
        )}
        {runState === "error" && (
          <span className="hidden items-center gap-1 text-[11px] font-bold text-[var(--error-red)] md:flex">
            <Warning size={13} weight="fill" />
            {t("실행 실패")}
          </span>
        )}
        <span className="hidden w-12 text-right text-[11px] font-bold tabular-nums text-[var(--text-label)] md:inline" aria-label={t("캔버스 확대 비율")}>
          {Math.round(zoom * 100)}%
        </span>
        {/* TODO(strategy-lab): 공유 기능 — 자리만 둔다. */}
        <button type="button" disabled className="lab-icon-button" aria-label={t("공유 (준비 중)")} title={t("공유 (준비 중)")}>
          <ShareNetwork size={16} />
        </button>
        <span title={disabled ? runDisabledReason ?? undefined : undefined} className="inline-flex">
          <button
            type="button"
            onClick={running ? onStop : onRun}
            disabled={disabled}
            aria-describedby={disabled ? "lab-run-disabled-reason" : undefined}
            data-testid="lab-run-button"
            className="flex items-center gap-2 rounded-lg bg-[var(--chat-accent)] px-3.5 py-1.5 text-xs font-black text-[var(--chat-accent-ink)] transition-colors hover:brightness-110 active:translate-y-[1px] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
          >
            {running ? (
              <>
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--chat-accent-ink)] border-t-transparent motion-reduce:animate-none" aria-hidden="true" />
                {t("실행 중")}
                <Stop size={11} weight="fill" aria-label={t("중지")} />
              </>
            ) : (
              <>
                <Play size={12} weight="fill" />
                {t("백테스트 실행")}
              </>
            )}
          </button>
        </span>
        {disabled && (
          <span id="lab-run-disabled-reason" className="sr-only">
            {runDisabledReason}
          </span>
        )}
      </div>
    </header>
  );
}
