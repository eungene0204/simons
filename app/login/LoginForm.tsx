"use client";

import Link from "next/link";
import { useState } from "react";
import NullstockLogoMark from "@/components/layout/NullstockLogoMark";
import { t } from "@/lib/i18n";

// 이메일 로그인 — /api/login의 이메일·비밀번호 경로를 사용한다.
// (Google 로그인은 상단 내비게이션/로그인 모달에서 제공)
export default function LoginForm() {
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
      window.location.href = "/";
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
      setLoading(false);
    }
  };

  const inputClass =
    "w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-100";

  return (
    <main className="min-h-screen flex items-center justify-center p-8 pt-[calc(var(--top-menu-bar-height,76px)+2rem)]">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <NullstockLogoMark
            className="h-8 w-10"
            filterId="nullstock-logo-login"
          />
          <div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{t("널스탁")}</p>
            <h1 className="text-xl font-semibold">{t("이메일로 로그인")}</h1>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium mb-1">
              {t("이메일")}
            </label>
            <input
              id="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputClass}
              required
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1">
              {t("비밀번호")}
            </label>
            <input
              id="password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-gray-900 text-white py-2.5 font-medium hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? t("처리 중...") : t("로그인")}
          </button>

          <p className="text-center text-sm text-gray-600 dark:text-gray-400">
            {t("계정이 없으신가요?")}{" "}
            <Link href="/register" className="text-blue-500 hover:underline">
              {t("이메일로 가입")}
            </Link>
          </p>
        </form>
      </div>
    </main>
  );
}
