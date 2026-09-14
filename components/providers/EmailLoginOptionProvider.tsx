"use client";

import { createContext, useContext, type ReactNode } from "react";

// 이메일 로그인·가입은 테스트용 한시 기능이다(킬 스위치 EMAIL_SIGNUP_ENABLED=off).
// 서버 env는 클라이언트 번들이 읽을 수 없으므로 루트 레이아웃(서버)이 판정값을
// 이 컨텍스트로 내려 주고, 로그인 선택 모달들은 이 값으로 "이메일로 시작하기"
// 진입점을 숨긴다. 기본값 true = 프로바이더 없는 테스트·스토리에서는 종전 UI.
const EmailLoginOptionContext = createContext<boolean>(true);

export function EmailLoginOptionProvider({
  enabled,
  children,
}: {
  enabled: boolean;
  children: ReactNode;
}) {
  return (
    <EmailLoginOptionContext.Provider value={enabled}>
      {children}
    </EmailLoginOptionContext.Provider>
  );
}

export function useEmailLoginEnabled(): boolean {
  return useContext(EmailLoginOptionContext);
}
