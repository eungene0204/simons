"use client";

import { useMemo, useState } from "react";
import { MagnifyingGlass, Plus, Trash } from "phosphor-react";
import { t } from "@/lib/i18n";
import type { ChatLogEntry } from "@/lib/strategy/chatLogEntry";

type ConversationDrawerProps = {
  entries: ChatLogEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
};

function formatUpdatedAt(ms: number): string {
  const date = new Date(ms);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  return sameDay
    ? date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// 좌측 서랍 — 지난 전략 대화(계정별 서버 로그). 검색은 화면에 보이는 제목 문자열의 부분 일치만 한다
// (사용자가 입력한 검색어로 목록을 거르는 UI 필터이지 전략 의미 해석이 아니다).
export default function ConversationDrawer({ entries, activeId, onSelect, onDelete, onNew }: ConversationDrawerProps) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? entries.filter((e) => (e.title || "").toLowerCase().includes(q)) : entries;
  }, [entries, query]);

  return (
    <div className="flex h-full flex-col" data-testid="lab-conversations">
      <div className="space-y-2 border-b border-[var(--lab-border)] p-3">
        <button
          type="button"
          onClick={onNew}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--lab-border-strong)] px-3 py-1.5 text-xs font-black text-white hover:bg-white/[0.06]"
        >
          <Plus size={12} weight="bold" />
          {t("새 전략")}
        </button>
        <label className="flex items-center gap-2 rounded-lg border border-[var(--lab-border)] px-2.5 py-1.5 focus-within:border-[var(--lab-border-focus)]">
          <MagnifyingGlass size={12} className="flex-shrink-0 text-[var(--text-label)]" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("대화 검색")}
            aria-label={t("대화 검색")}
            className="min-w-0 flex-1 bg-transparent text-xs font-bold text-white outline-none placeholder:text-[var(--text-placeholder)]"
          />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="px-2 py-3 text-xs font-bold text-[var(--text-label)]">
            {entries.length === 0 ? t("저장된 대화가 없습니다.") : t("검색 결과가 없습니다.")}
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5" data-testid="chat-log-list">
            {filtered.map((entry) => {
              const isActive = entry.id === activeId;
              const title = entry.title || t("제목 없는 대화");
              return (
                <li key={entry.id} className="group relative">
                  <button
                    type="button"
                    aria-current={isActive ? "true" : undefined}
                    onClick={() => onSelect(entry.id)}
                    aria-label={title}
                    title={title}
                    className={`flex w-full flex-col gap-0.5 rounded-lg py-2 pl-2.5 pr-8 text-left transition-colors ${
                      isActive ? "bg-white/[0.12] text-white" : "text-gray-300 hover:bg-white/[0.06] hover:text-white"
                    }`}
                  >
                    <span className="truncate text-xs font-bold">{title}</span>
                    <span className="text-[11px] font-bold text-[var(--text-label)]">{formatUpdatedAt(entry.updatedAt)}</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(entry.id)}
                    aria-label={t("{0} 대화 삭제", title)}
                    title={t("{0} 대화 삭제", title)}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-md p-1 text-[var(--text-label)] opacity-0 transition-opacity hover:text-white focus-visible:opacity-100 group-hover:opacity-100"
                  >
                    <Trash size={12} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
