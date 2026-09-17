"use client";

import { useEffect, useState } from "react";
import NullstockLogoMark from "@/components/layout/NullstockLogoMark";
import { t } from "@/lib/i18n";
import { useRegionHref } from "@/lib/geo/useRegion";
import { useAnalytics } from "@/lib/hooks/useAnalytics";
import {
  AUTH_ERROR_CLASS,
  AUTH_INPUT_CLASS,
  AUTH_LABEL_CLASS,
  AUTH_PRIMARY_BUTTON_CLASS,
} from "@/components/ui/authStyles";

// 게스트(테스터) 입장 폼 — /api/guest/login을 사용한다.
// 입장 링크(`/guest#<입장 코드>`)로 들어오면 코드를 주소창에서 곧바로 지우고 자동으로 입장한다.
// 코드는 프래그먼트라 서버·접속 로그에 실리지 않으며, POST 본문으로만 보낸다.
// 앱은 다크 전용이다 — `dark:` 조건부 색을 쓰지 않는다(app/login/LoginForm.tsx와 같은 규칙).
export default function GuestLoginForm() {
  const regionHref = useRegionHref();
  const analytics = useAnalytics();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [guestId, setGuestId] = useState("");
  const [password, setPassword] = useState("");
  const [checkingInvite, setCheckingInvite] = useState(false);

  const enter = async (body: { invite: string } | { guestId: string; password: string }) => {
    setError("");
    setLoading(true);
    try {
      const response = await fetch("/api/guest/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.error || t("로그인에 실패했습니다."));
        setLoading(false);
        setCheckingInvite(false);
        return;
      }
      // 쿠키 발급됨 — 전체 리로드로 인증 상태를 반영한다.
      analytics.login("guest");
      window.location.href = regionHref("/");
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
      setLoading(false);
      setCheckingInvite(false);
    }
  };

  useEffect(() => {
    const code = window.location.hash.slice(1);
    if (!code) return;
    // 비밀값이 방문 기록·복사된 주소에 남지 않게 먼저 지운다.
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    setCheckingInvite(true);
    void enter({ invite: code });
    // 마운트 1회 — 지운 뒤에는 hash가 비어 재실행돼도 아무것도 하지 않는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!guestId.trim() || !password) {
      setError(t("아이디와 비밀번호를 입력해주세요."));
      return;
    }

    await enter({ guestId: guestId.trim(), password });
  };

  return (
    <main className="flex min-h-[100dvh] items-center justify-center p-8 pt-[calc(var(--top-menu-bar-height,76px)+2rem)]">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <NullstockLogoMark className="h-8 w-10" filterId="nullstock-logo-guest" />
          <div>
            <p className="text-sm font-bold text-[var(--text-label)]">{t("널스탁")}</p>
            <h1 className="text-xl font-black text-white">{t("특별 계정")}</h1>
          </div>
        </div>

        <p className="mb-6 text-sm font-bold text-gray-400">
          {checkingInvite
            ? t("입장 링크를 확인하는 중입니다...")
            : t("발급받은 아이디와 비밀번호로 입장합니다.")}
        </p>

        {error && (
          <div role="alert" className={AUTH_ERROR_CLASS}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" hidden={checkingInvite}>
          <div>
            <label htmlFor="guestId" className={AUTH_LABEL_CLASS}>
              {t("아이디")}
            </label>
            <input
              id="guestId"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="guest_1234"
              value={guestId}
              onChange={(e) => setGuestId(e.target.value)}
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
              placeholder="•••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={AUTH_INPUT_CLASS}
              required
            />
          </div>

          <button type="submit" disabled={loading} className={AUTH_PRIMARY_BUTTON_CLASS}>
            {loading ? t("처리 중...") : t("입장")}
          </button>
        </form>
      </div>
    </main>
  );
}
