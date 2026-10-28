"use client";

import type { ReactNode } from "react";
import { SidebarSimple } from "phosphor-react";

type SideDrawerProps = {
  side: "left" | "right";
  open: boolean;
  onToggle: () => void;
  /** 열린 폭(px). */
  width: number;
  /** 좁은 화면 — 옆 영역을 밀지 않고 위에 겹쳐 연다. */
  overlay: boolean;
  /** 서랍 영역 이름(보조 기술용). */
  title: string;
  /** 경계 탭(열기/닫기) 버튼 이름. */
  label: string;
  testId: string;
  children: ReactNode;
};

// 좌·우 서랍 공통 틀 — 닫히면 폭이 0으로 미끄러지고(220ms ease-out), 토글 버튼(사이드바 아이콘)으로 다시 연다.
// 열려 있으면 버튼은 서랍 머리줄 오른쪽 끝(탭 메뉴 줄)에, 닫히면 서랍이 있던 가장자리에 남는다.
// 내용은 닫혀도 마운트를 유지한다(검색어·스크롤 위치를 잃지 않게). 닫힌 내용은 invisible로 탭 이동에서 뺀다.
export default function SideDrawer({ side, open, onToggle, width, overlay, title, label, testId, children }: SideDrawerProps) {
  const isLeft = side === "left";
  return (
    <div
      className={`${overlay ? "absolute inset-y-0 z-30" : "relative"} ${isLeft ? "left-0" : "right-0"} flex-shrink-0 transition-[width] duration-[220ms] ease-out motion-reduce:transition-none`}
      style={{ width: open ? width : 0 }}
      data-testid={testId}
      data-open={open ? "true" : "false"}
    >
      <aside
        aria-label={title}
        aria-hidden={!open}
        className={`h-full w-full overflow-hidden bg-[var(--lab-panel)] ${isLeft ? "border-r" : "border-l"} ${
          open ? "border-[var(--lab-border)]" : "invisible border-transparent"
        }`}
      >
        <div className="h-full" style={{ width }}>
          {children}
        </div>
      </aside>
      <button
        type="button"
        onClick={onToggle}
        aria-label={label}
        aria-expanded={open}
        title={label}
        className={`absolute z-10 flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-label)] hover:bg-white/10 hover:text-white ${
          open ? `top-1.5 ${isLeft ? "right-2" : "left-2"}` : `top-3 ${isLeft ? "left-2" : "right-2"}`
        }`}
      >
        <SidebarSimple size={18} weight="regular" />
      </button>
    </div>
  );
}
