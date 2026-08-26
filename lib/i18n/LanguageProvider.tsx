"use client";

import { type ReactNode } from "react";
import { setLanguage, type Language } from "./index";

/**
 * 요청 언어(레이아웃이 지역 헤더에서 읽음)를 SSR과 클라이언트 모두에 고정한다.
 * 렌더 중 setLanguage를 호출하는 이유: 자식 클라이언트 컴포넌트가 `t()`를 렌더 중에 부르므로
 * 그 전에 모듈 언어가 맞춰져 있어야 서버 HTML과 클라이언트 하이드레이션이 일치한다.
 * 언어 전환 UI는 없다 — 언어는 지역(`/` = 한국어, `/us` = 영어)이 결정한다.
 */
export function LanguageProvider({
  initialLanguage,
  children,
}: {
  initialLanguage: Language;
  children: ReactNode;
}) {
  setLanguage(initialLanguage);
  return <>{children}</>;
}
