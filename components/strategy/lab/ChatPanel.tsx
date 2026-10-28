"use client";

import { useRef, type PointerEvent as ReactPointerEvent, type ReactNode, type RefObject } from "react";
import { CaretDown, CaretUp, ChatCircleText } from "phosphor-react";
import { t } from "@/lib/i18n";

type ChatPanelProps = {
  open: boolean;
  onToggle: () => void;
  height: number;
  onHeightChange: (height: number) => void;
  /** 대화 스크롤 영역(자동 스크롤이 이 요소를 기준으로 움직인다). */
  scrollRef: RefObject<HTMLDivElement>;
  /** 대화 메시지. */
  children: ReactNode;
  /** 입력창·고정 되묻기 카드 등 스크롤 밖 하단 영역. */
  footer?: ReactNode;
  /** 머리줄 오른쪽 컨트롤(대화 종료 등). */
  actions?: ReactNode;
  /** true면 메시지 영역을 그리지 않고 입력창을 패널 하단에 붙인다. 높이는 항상 고정 높이다. */
  empty?: boolean;
  /** 오른쪽 선택지 칸. 있으면 본문을 좌(대화·입력)·우(선택지) 두 칸으로 나눈다. */
  aside?: ReactNode;
};

export const CHAT_PANEL_MIN = 180;
export const CHAT_PANEL_MAX_RATIO = 0.75;

// 하단 채팅 패널 — 윗변을 끌어 높이를 바꾸고, "채팅 숨기기"로 머리줄만 남긴다.
export default function ChatPanel({ open, onToggle, height, onHeightChange, scrollRef, children, footer, actions, empty, aside }: ChatPanelProps) {
  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!open) return;
    dragRef.current = { startY: e.clientY, startHeight: height };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const max = Math.round(window.innerHeight * CHAT_PANEL_MAX_RATIO);
    onHeightChange(Math.min(max, Math.max(CHAT_PANEL_MIN, drag.startHeight + (drag.startY - e.clientY))));
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };

  return (
    <section
      className={`relative flex min-w-0 flex-1 flex-col bg-[var(--lab-panel)] ${open ? "h-full" : ""}`}
      aria-label={t("채팅")}
      data-testid="lab-chat-panel"
    >
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label={t("채팅 높이 조절")}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        className={`absolute inset-x-0 -top-1 z-10 h-2 ${open ? "cursor-row-resize" : ""}`}
      />
      <div className="flex h-9 flex-shrink-0 items-center justify-between gap-2 border-b border-[var(--lab-border)] px-3">
        <span className="flex items-center gap-1.5 text-xs font-black text-white">
          <ChatCircleText size={13} weight="bold" />
          {t("채팅")}
        </span>
        <div className="flex items-center gap-2">
          {open && actions}
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={open}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold text-[var(--text-label)] hover:text-white"
          >
            {open ? <CaretDown size={11} /> : <CaretUp size={11} />}
            {open ? t("채팅 숨기기") : t("채팅 보기")}
          </button>
        </div>
      </div>
      {open && (
        <div className="flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            {!empty && (
              <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-3" data-testid="lab-chat-scroll">
                {children}
              </div>
            )}
            {footer && (
              // 대화와 입력창은 경계선 없이 한 창으로 잇는다 — 창을 나누는 것은 옵션칩 오른쪽 칸뿐이다.
              <div className={`flex-shrink-0 px-3 pb-3 ${empty ? "min-h-0 flex-1 pt-3" : "pt-1"}`}>{footer}</div>
            )}
          </div>
          {aside && (
            <div
              className="flex min-h-0 w-[min(46%,560px)] flex-shrink-0 flex-col overflow-y-auto border-l border-[var(--lab-border)] [&>*]:flex-1"
              data-testid="lab-chat-aside"
            >
              {aside}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
