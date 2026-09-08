"use client";

import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

type Options = {
  open: boolean;
  onClose: () => void;
  containerRef: RefObject<HTMLElement>;
  /** 기본 true — 열려 있는 동안 body 스크롤을 잠근다. */
  lockScroll?: boolean;
};

// 모달·다이얼로그의 키보드 계약을 한곳에서 맡는다(2026-09-08 — 로그인·검색·설정 모달이 각각
// Esc·포커스 트랩·포커스 복귀·스크롤 잠금을 서로 다르게 빠뜨리고 있었다).
// - Esc → onClose
// - Tab/Shift+Tab이 컨테이너 밖으로 나가지 않는다(포커스 트랩)
// - 열릴 때 컨테이너 안에 포커스가 없으면 첫 포커스 가능 요소(없으면 컨테이너)로 옮긴다
// - 닫힐 때 열기 전에 포커스가 있던 요소로 되돌린다
// 겹쳐 열린 다이얼로그(설정 모달 위의 확인 대화 등)는 맨 위 하나만 키를 받는다 — 아래 것의
// 포커스 트랩이 위 것에서 포커스를 빼앗아 오지 않게.
const openDialogs: symbol[] = [];

export function useDialogBehavior({ open, onClose, containerRef, lockScroll = true }: Options) {
  // onClose는 렌더마다 새 함수인 경우가 많다 — ref로 받아 effect가 매 렌더 재실행되며
  // 포커스를 다시 옮기는 일을 막는다.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const dialogId = Symbol("dialog");
    openDialogs.push(dialogId);
    const isTopmost = () => openDialogs[openDialogs.length - 1] === dialogId;
    const container = containerRef.current;
    const previouslyFocused =
      typeof document !== "undefined" ? (document.activeElement as HTMLElement | null) : null;

    const focusables = (): HTMLElement[] =>
      container
        ? Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
            (el) => el.getAttribute("aria-hidden") !== "true",
          )
        : [];

    if (container && !container.contains(document.activeElement)) {
      const first = focusables()[0];
      (first ?? container).focus();
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTopmost()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !container) return;
      const items = focusables();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      const outside = !container.contains(active);
      if (event.shiftKey) {
        if (active === first || outside) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last || outside) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);

    let previousOverflow: string | null = null;
    if (lockScroll) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }

    return () => {
      const index = openDialogs.indexOf(dialogId);
      if (index >= 0) openDialogs.splice(index, 1);
      document.removeEventListener("keydown", handleKeyDown);
      if (previousOverflow !== null) document.body.style.overflow = previousOverflow;
      if (previouslyFocused && typeof previouslyFocused.focus === "function") {
        previouslyFocused.focus();
      }
    };
  }, [open, containerRef, lockScroll]);
}
