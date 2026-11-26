"use client";

// 처음 들어온 링크의 UTM을 쿠키에 한 번만 남긴다(first-touch) — 가입 API가 읽어 User에 옮긴다.
// 이미 쿠키가 있으면 덮지 않는다. 렌더 결과는 없다.

import { useEffect } from "react";
import { SIGNUP_UTM_COOKIE, SIGNUP_UTM_MAX_AGE_SEC, serializeSignupUtm, utmFromSearchParams } from "@/lib/signupUtm";

export default function SignupUtmCapture() {
  useEffect(() => {
    try {
      if (document.cookie.split("; ").some((c) => c.startsWith(`${SIGNUP_UTM_COOKIE}=`))) return;
      const utm = utmFromSearchParams(new URLSearchParams(window.location.search));
      if (!utm) return;
      const secure = window.location.protocol === "https:" ? "; Secure" : "";
      document.cookie = `${SIGNUP_UTM_COOKIE}=${encodeURIComponent(serializeSignupUtm(utm))}; Max-Age=${SIGNUP_UTM_MAX_AGE_SEC}; Path=/; SameSite=Lax${secure}`;
    } catch {
      // 쿠키 차단 환경 — 유입 경로 없이 가입된다(direct로 집계).
    }
  }, []);
  return null;
}
