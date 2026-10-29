"use client";

import { useCallback, useEffect, useRef, useState, type ComponentProps, type ReactNode, type RefObject } from "react";
import { t } from "@/lib/i18n";
import ChatPanel, { CHAT_PANEL_MAX_RATIO, CHAT_PANEL_MIN } from "./ChatPanel";
import ConversationDrawer from "./ConversationDrawer";
import ExampleCardsDrawer from "./ExampleCardsDrawer";
import SideDrawer from "./SideDrawer";
import StrategyCanvas from "./StrategyCanvas";
import TopToolbar from "./TopToolbar";
import { useLabPanels, useMediaQuery } from "./panelState";

type StrategyLabLayoutProps = {
  toolbar: Omit<ComponentProps<typeof TopToolbar>, "zoom">;
  conversations: ComponentProps<typeof ConversationDrawer>;
  canvas: Omit<ComponentProps<typeof StrategyCanvas>, "onZoomChange">;
  chat: {
    scrollRef: RefObject<HTMLDivElement>;
    messages: ReactNode;
    /** 오른쪽 칸 — 칩으로 답하는 되묻기 카드. 있으면 채팅을 좌(대화)·우(선택지) 두 칸으로 나눈다. */
    aside?: ReactNode;
    /** 보여 줄 대화가 없다 — 메시지 영역 없이 머리줄과 입력창만 둔다. */
    empty?: boolean;
    footer?: ReactNode;
    actions?: ReactNode;
  };
  onPickExample: (prompt: string) => void;
  /** 레이아웃 밖에 겹쳐 그릴 요소(로그인 대화상자 등). */
  overlay?: ReactNode;
};

const LEFT_WIDTH = 280;
const DEFAULT_CHAT_HEIGHT = 320;

// 전략 연구소 5영역 — [A] 툴바 / [B] 대화 목록 서랍 / [C] 캔버스 / [D] 채팅 / [E] 전략 예시 서랍.
// 1024px 이하에서는 서랍을 기본으로 닫고 열면 옆 영역 위에 겹친다.
export default function StrategyLabLayout({ toolbar, conversations, canvas, chat, onPickExample, overlay }: StrategyLabLayoutProps) {
  const narrow = useMediaQuery("(max-width: 1024px)");
  const [panels, togglePanel] = useLabPanels(narrow);
  const [zoom, setZoom] = useState(1);
  const [leftTab, setLeftTab] = useState<"conversations" | "examples">("examples");
  const [chatHeight, setChatHeight] = useState(DEFAULT_CHAT_HEIGHT);

  // 창을 줄이면 채팅이 캔버스를 다 덮지 않게 상한을 다시 맞춘다.
  useEffect(() => {
    const clamp = () =>
      setChatHeight((h) => Math.max(CHAT_PANEL_MIN, Math.min(h, Math.round(window.innerHeight * CHAT_PANEL_MAX_RATIO))));
    clamp();
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, []);

  // 서랍·캔버스는 메모 컴포넌트다 — 페이지가 턴마다 새로 만드는 콜백을 최신 값 참조로 감싸 안정된 함수로
  // 내려야 예시 카드·노드가 대화 상태가 바뀔 때마다 다시 그려지지 않는다.
  const latest = useRef({ onPickExample, canvas, panels, narrow, togglePanel });
  latest.current = { onPickExample, canvas, panels, narrow, togglePanel };
  const pickExample = useCallback((prompt: string) => {
    const l = latest.current;
    l.onPickExample(prompt);
    if (!l.panels.chat) l.togglePanel("chat", true);
    if (l.narrow) l.togglePanel("conversations", false);
  }, []);
  const addBlock = useCallback((stage: Parameters<NonNullable<typeof canvas.onAddBlock>>[0], key: string) => {
    const l = latest.current;
    l.canvas.onAddBlock?.(stage, key);
    // 다음에 정할 조건을 채팅이 묻는다 — 채팅을 연다.
    if (!l.panels.chat) l.togglePanel("chat", true);
  }, []);
  const deleteItem = useCallback((id: string) => latest.current.canvas.onDeleteItem?.(id), []);
  const editItem = useCallback((itemId: string, changes: Record<string, number | string>) => {
    const l = latest.current;
    l.canvas.onEditItem?.(itemId, changes);
    if (!l.panels.chat) l.togglePanel("chat", true);
  }, []);

  return (
    <div
      className="flex flex-col overflow-hidden bg-[var(--lab-canvas)]"
      style={{ height: "calc(100dvh - var(--top-menu-bar-height, 76px))" }}
      data-testid="strategy-lab-background"
    >
      {/* 페이지 유일 h1 — 검색엔진이 본문 제목으로 읽는다(화면에는 툴바의 전략 이름이 보인다). */}
      <h1 className="sr-only" data-testid="strategy-lab-headline">
        {t("퀀트 전략을 입력하세요")}
      </h1>
      <TopToolbar {...toolbar} zoom={zoom} />
      <div className="relative flex min-h-0 flex-1">
        <SideDrawer
          side="left"
          open={panels.conversations}
          onToggle={() => togglePanel("conversations")}
          width={LEFT_WIDTH}
          overlay={narrow}
          title={t("대화 기록")}
          label={panels.conversations ? t("대화 기록 닫기") : t("대화 기록 열기")}
          testId="lab-left-drawer"
        >
          <div className="flex h-full flex-col">
            <div className="flex flex-shrink-0 justify-center gap-1 border-b border-[var(--lab-border)] px-3 pt-2" role="tablist" aria-label={t("왼쪽 패널")}>
              {([["examples", t("전략 예시")], ["conversations", t("대화 기록")]] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={leftTab === key}
                  onClick={() => setLeftTab(key)}
                  className={`-mb-px rounded-t-md border-b-2 px-3 py-1.5 text-xs font-black transition-colors ${
                    leftTab === key
                      ? "border-[var(--chat-accent)] text-white"
                      : "border-transparent text-[var(--text-label)] hover:text-white"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1">
              {leftTab === "conversations" ? (
              <ConversationDrawer
                {...conversations}
                onSelect={(id) => {
                  conversations.onSelect(id);
                  if (narrow) togglePanel("conversations", false);
                }}
              />
              ) : (
                <ExampleCardsDrawer onPick={pickExample} />
              )}
            </div>
          </div>
        </SideDrawer>
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="relative min-h-0 flex-1">
            <StrategyCanvas
              {...canvas}
              onDeleteItem={canvas.onDeleteItem ? deleteItem : undefined}
              onAddBlock={canvas.onAddBlock ? addBlock : undefined}
              onEditItem={canvas.onEditItem ? editItem : undefined}
              onZoomChange={setZoom}
            />
          </div>
          {/* 하단 줄 높이는 채팅 높이 하나로 정한다 — 예시 서랍의 내용 길이가 줄을 밀어 올리지 않게. */}
          <div
            className="relative flex flex-shrink-0 border-t border-[var(--lab-border)]"
            style={{ height: panels.chat ? chatHeight : undefined }}
          >
            <ChatPanel
              open={panels.chat}
              onToggle={() => togglePanel("chat")}
              height={chatHeight}
              onHeightChange={setChatHeight}
              scrollRef={chat.scrollRef}
              footer={chat.footer}
              actions={chat.actions}
              empty={chat.empty}
              aside={chat.aside}
            >
              {chat.messages}
            </ChatPanel>
          </div>
        </div>
      </div>
      {overlay}
    </div>
  );
}
