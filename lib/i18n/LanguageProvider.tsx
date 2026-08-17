"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import {
  DEFAULT_LANGUAGE,
  persistLanguage,
  setLanguage,
  type Language,
} from "./index";

type LanguageContextValue = {
  language: Language;
  /** 언어를 영속하고 페이지를 새로고침해 전체 화면을 새 언어로 다시 그린다. */
  switchLanguage: (language: Language) => void;
};

const LanguageContext = createContext<LanguageContextValue>({
  language: DEFAULT_LANGUAGE,
  switchLanguage: () => undefined,
});

/**
 * 요청 언어(레이아웃이 쿠키에서 읽음)를 SSR과 클라이언트 모두에 고정한다.
 * 렌더 중 setLanguage를 호출하는 이유: 자식 클라이언트 컴포넌트가 `t()`를 렌더 중에 부르므로
 * 그 전에 모듈 언어가 맞춰져 있어야 서버 HTML과 클라이언트 하이드레이션이 일치한다.
 */
export function LanguageProvider({
  initialLanguage,
  children,
}: {
  initialLanguage: Language;
  children: ReactNode;
}) {
  setLanguage(initialLanguage);

  const switchLanguage = useCallback(
    (next: Language) => {
      if (next === initialLanguage) return;
      persistLanguage(next);
      // 새로고침으로 반영한다: 모듈 상수·useMemo·세션 캐시에 남은 옛 언어 문자열이 새 언어와
      // 섞여 보이는 상태를 구조적으로 없애기 위해서다(전략연구소 대화는 sessionStorage 스냅샷에서
      // 복원된다).
      if (typeof window !== "undefined") window.location.reload();
    },
    [initialLanguage]
  );

  const value = useMemo(
    () => ({ language: initialLanguage, switchLanguage }),
    [initialLanguage, switchLanguage]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
