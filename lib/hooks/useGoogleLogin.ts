"use client";

import { useState } from "react";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/firebase";

// Google 로그인 시작 — Supabase OAuth 리다이렉트를 연다. 상단 로그인 모달과 /login 페이지가
// 같은 시작 절차를 공유한다(이메일 페이지에만 Google 버튼이 없어 되돌아갈 길이 없던 결함, 2026-09-08).
export function useGoogleLogin() {
  const [isStarting, setIsStarting] = useState(false);
  const available = isSupabaseConfigured();

  const start = async () => {
    if (isStarting || !available) return;
    setIsStarting(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
          queryParams: {
            access_type: "offline",
            prompt: "select_account",
          },
        },
      });
      if (error) throw error;
    } finally {
      setIsStarting(false);
    }
  };

  return { start, isStarting, available };
}
