"use client";

import Link from "next/link";
import { useState } from "react";
import { GoogleLogo } from "phosphor-react";
import NullstockLogoMark from "@/components/layout/NullstockLogoMark";
import { t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import { useAnalytics } from "@/lib/hooks/useAnalytics";
import { useGoogleLogin } from "@/lib/hooks/useGoogleLogin";
import {
  AUTH_ERROR_CLASS,
  AUTH_INPUT_CLASS,
  AUTH_LABEL_CLASS,
  AUTH_LINK_CLASS,
  AUTH_PRIMARY_BUTTON_CLASS,
  AUTH_GOOGLE_BUTTON_CLASS,
} from "@/components/ui/authStyles";

// 이메일 로그인 — /api/login의 이메일·비밀번호 경로를 사용한다. Google 로그인도 같은 페이지에서 시작한다.
// 앱은 다크 전용이다 — `dark:` 조건부 색을 쓰지 않는다(기기 색상 설정이 라이트면 흰 배경에
// 흰 글자가 되던 결함, 2026-09-08).
export default function LoginForm() {
  const regionHref = useRegionHref();
  const analytics = useAnalytics();
  const google = useGoogleLogin();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!email || !password) {
      setError(t("이메일과 비밀번호를 입력해주세요."));
      return;
    }

    setLoading(true);
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.error || t("로그인에 실패했습니다."));
        setLoading(false);
        return;
      }
      // 쿠키 발급됨 — 전체 리로드로 인증 상태를 반영한다.
      // GA 이벤트는 리다이렉트 직전에 보낸다 — gtag는 beacon 전송이라 페이지 이탈에도 살아남는다.
      analytics.login("email");
      window.location.href = regionHref("/");
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-[100dvh] items-center justify-center p-8 pt-[calc(var(--top-menu-bar-height,76px)+2rem)]">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <NullstockLogoMark
            className="h-8 w-10"
            filterId="nullstock-logo-login"
          />
          <div>
            <p className="text-sm font-bold text-[var(--text-label)]">{t("널스탁")}</p>
            <h1 className="text-xl font-black text-white">{t("로그인")}</h1>
          </div>
        </div>

        {google.available && (
          <>
            <button
              type="button"
              onClick={() => void google.start()}
              disabled={google.isStarting}
              className={AUTH_GOOGLE_BUTTON_CLASS}
            >
              <GoogleLogo size={18} weight="fill" />
              <span>{google.isStarting ? t("로그인 준비 중...") : t("Google로 시작하기")}</span>
            </button>
            <div className="my-6 flex items-center gap-3" aria-hidden="true">
              <span className="h-px flex-1 bg-white/[0.08]" />
              <span className="text-xs font-bold text-[var(--text-label)]">{t("또는 이메일로")}</span>
              <span className="h-px flex-1 bg-white/[0.08]" />
            </div>
          </>
        )}

        {error && (
          <div role="alert" className={AUTH_ERROR_CLASS}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className={AUTH_LABEL_CLASS}>
              {t("이메일")}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={AUTH_INPUT_CLASS}
              required
            />
          </div>
          <div>
            <label htmlFor="password" className={AUTH_LABEL_CLASS}>
              {t("비밀번호")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={AUTH_INPUT_CLASS}
              required
            />
          </div>

          <button type="submit" disabled={loading} className={AUTH_PRIMARY_BUTTON_CLASS}>
            {loading ? t("처리 중...") : t("로그인")}
          </button>

          <p className="text-center text-sm font-bold text-gray-400">
            {t("계정이 없으신가요?")}{" "}
            <Link href={regionHref("/register")} className={AUTH_LINK_CLASS}>
              {t("이메일로 가입")}
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
