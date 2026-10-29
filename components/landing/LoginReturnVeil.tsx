"use client";

import { useEffect, useState } from "react";
import { Spinner } from "phosphor-react";
import { completeLoginReturn, isLoginReturn } from "@/lib/auth/loginReturn";

// Google 로그인에서 돌아온 직후(주소에 토큰·코드가 실려 있는 동안)에는 서버가 아직 로그인 상태를 몰라
// 소개 페이지를 그린다. 상단 내비게이션이 세션을 교환하고 전략연구소로 보낼 때까지 "로그인 중" 화면으로 가린다.
// 교환이 실패하면 가림막을 걷는다 — 걷지 않으면 비로그인 상태인데 스피너만 끝없이 돈다.
export function LoginReturnVeil() {
  const [returning, setReturning] = useState(false);
  useEffect(() => {
    if (!isLoginReturn(window.location.hash, window.location.search)) return;
    let active = true;
    setReturning(true);
    void completeLoginReturn().then((user) => {
      if (active && !user) setReturning(false);
    });
    return () => {
      active = false;
    };
  }, []);
  if (!returning) return null;
  return (
    <div role="status" data-testid="login-return-veil" className="fixed inset-0 z-[70] flex flex-col items-center justify-center gap-3 bg-[var(--background)] text-sm font-bold text-gray-300">
      <Spinner size={28} className="animate-spin motion-reduce:animate-none" aria-hidden="true" data-testid="login-return-spinner" />
      로그인 중입니다…
    </div>
  );
}
