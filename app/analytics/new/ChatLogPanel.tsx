"use client";

import { useState } from "react";
import { ClockCounterClockwise, Trash, X } from "phosphor-react";
import { t } from "@/lib/i18n";
import type { ChatLogEntry } from "./chatLog";

type ChatLogPanelProps = {
  entries: ChatLogEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
};

// 왼쪽 대화 로그. 1280px 이상에서는 화면 왼쪽에 고정된 패널로(오른쪽은 진행률 패널 자리),
// 그 아래에서는 대화 위의 작은 버튼 → 서랍으로 열린다.
// 면은 진행률 패널과 같다 — 헤어라인 테두리 + 유리(.chat-glass), 채움 없음(UI §17).
function ChatLogList({
  entries,
  activeId,
  onSelect,
  onDelete,
}: ChatLogPanelProps) {
  return (
    <ul className="flex flex-col gap-0.5" data-testid="chat-log-list">
      {entries.map((entry) => {
        const isActive = entry.id === activeId;
        const title = entry.title || t("제목 없는 대화");
        return (
          <li key={entry.id} className="group relative flex items-center">
            <button
              type="button"
              aria-current={isActive ? "true" : undefined}
              onClick={() => onSelect(entry.id)}
              className={`flex min-w-0 flex-1 items-center gap-2 rounded-xl py-2 pl-2.5 pr-8 text-left text-xs font-bold transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)] ${
                isActive
                  ? "bg-white/10 text-white"
                  : "text-gray-300 hover:bg-white/[0.06] hover:text-white"
              }`}
              title={title}
            >
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 flex-shrink-0 rounded-full border ${
                  isActive ? "border-white bg-white" : "border-white/30"
                }`}
              />
              <span className="truncate">{title}</span>
            </button>
            <button
              type="button"
              aria-label={t("{0} 대화 삭제", title)}
              onClick={() => onDelete(entry.id)}
              className="absolute right-1.5 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-md text-[var(--text-label)] opacity-0 transition-opacity duration-200 hover:text-white focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)] group-hover:opacity-100"
            >
              <Trash size={13} weight="bold" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function ChatLogPanel(props: ChatLogPanelProps) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const { entries } = props;
  const select = (id: string) => {
    setIsDrawerOpen(false);
    props.onSelect(id);
  };

  return (
    <>
      <aside
        aria-label={t("대화 기록")}
        className="z-20 hidden flex-col rounded-2xl border border-[var(--chat-hairline)] p-4 chat-glass xl:fixed xl:bottom-4 xl:left-4 xl:top-[calc(var(--top-menu-bar-height,76px)+5rem)] xl:flex xl:w-40 2xl:w-56"
        data-testid="chat-log-panel"
      >
        <div className="flex flex-shrink-0 items-end justify-between gap-3">
          <h2 className="text-xs font-black text-white">{t("대화 기록")}</h2>
          <span className="font-outfit text-[11px] font-black tabular-nums text-[var(--text-label)]">
            {entries.length}
          </span>
        </div>
        <div className="custom-scrollbar mt-3 min-h-0 flex-1 overflow-y-auto">
          <ChatLogList {...props} onSelect={select} />
        </div>
      </aside>

      <div className="relative z-20 flex w-full max-w-4xl xl:hidden">
        <button
          type="button"
          onClick={() => setIsDrawerOpen(true)}
          aria-label={t("대화 기록 열기")}
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/[0.14] bg-white/[0.05] px-2.5 py-1.5 text-[11px] font-bold text-gray-200 transition-colors duration-200 hover:bg-white/[0.09] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent-ring)]"
          data-testid="chat-log-drawer-trigger"
        >
          <ClockCounterClockwise size={14} weight="bold" />
          <span>{t("대화 기록")}</span>
          <span className="font-outfit tabular-nums text-[var(--text-label)]">{entries.length}</span>
        </button>
      </div>

      {isDrawerOpen && (
        <div className="fixed inset-0 z-[70] xl:hidden" data-testid="chat-log-drawer">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            onClick={() => setIsDrawerOpen(false)}
            aria-label={t("대화 기록 닫기")}
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label={t("대화 기록")}
            className="absolute inset-y-0 left-0 flex w-[min(86vw,320px)] flex-col bg-[#050505] shadow-2xl shadow-black/60"
          >
            <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-4">
              <span className="text-sm font-black tracking-tight text-white">{t("대화 기록")}</span>
              <button
                type="button"
                onClick={() => setIsDrawerOpen(false)}
                className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                aria-label={t("대화 기록 닫기")}
              >
                <X size={18} weight="bold" />
              </button>
            </div>
            <div className="custom-scrollbar flex-1 overflow-y-auto px-3 py-4">
              <ChatLogList {...props} onSelect={select} />
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
