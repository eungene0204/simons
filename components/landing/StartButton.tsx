"use client";

import type { ReactNode } from "react";
import { requestLoginModal } from "@/lib/auth/loginEvents";

// 소개 페이지의 '무료로 시작하기' — 비로그인 방문자에게 Google 로그인 모달을 보여 준다.
// 로그인하면 `/`로 돌아오고, 로그인한 사용자에게 `/`는 전략연구소를 그대로 연다(app/page.tsx).
// 링크(`href`)는 모달을 열 수 없을 때(스크립트 실패·내비게이션 없음)의 대체 경로이자 새 탭 열기용이다.
export function StartButton({ href, className, children }: { href: string; className: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className={className}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        if (requestLoginModal()) event.preventDefault();
      }}
    >
      {children}
    </a>
  );
}
