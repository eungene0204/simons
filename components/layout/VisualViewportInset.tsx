"use client";

import { useEffect } from "react";

// 모바일 소프트 키보드가 차지한 높이를 `--kb-inset`(px)으로 문서에 기록한다.
// `position: fixed; bottom` 요소(대화 입력 바·되묻기 카드)는 이 값과 `env(safe-area-inset-bottom)`을
// 더한 `.dock-bottom`으로 키보드·홈 인디케이터 위에 머문다(2026-09-08 — 입력 바가 키보드 뒤로
// 숨어 사용자가 보이지 않는 채 입력하던 결함).
export default function VisualViewportInset() {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const root = document.documentElement;
    const update = () => {
      const inset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      root.style.setProperty("--kb-inset", `${Math.round(inset)}px`);
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => {
      viewport.removeEventListener("resize", update);
      viewport.removeEventListener("scroll", update);
      root.style.removeProperty("--kb-inset");
    };
  }, []);
  return null;
}
