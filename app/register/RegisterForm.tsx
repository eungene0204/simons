"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { t } from "@/lib/i18n";

// 이메일 가입 — 2단계 플로우.
// 1) 정보 입력 + 약관 동의 → 인증번호 발송(/api/register/request-code)
// 2) 메일로 받은 6자리 인증번호 확인 → 계정 생성(/api/register) → 자동 로그인
// verificationRequired=false(테스트 기간, EMAIL_SIGNUP_VERIFICATION=off)면 1단계에서 바로 가입한다.
export default function RegisterForm({
  verificationRequired = true,
}: {
  verificationRequired?: boolean;
}) {
  const [step, setStep] = useState<"form" | "verify">("form");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [code, setCode] = useState("");
  const [resendLeft, setResendLeft] = useState(0);
  const [agreed, setAgreed] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  useEffect(() => {
    if (resendLeft <= 0) return;
    const timer = setInterval(() => {
      setResendLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendLeft]);

  const requestCode = async (): Promise<boolean> => {
    const response = await fetch("/api/register/request-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: formData.email.trim() }),
    });
    const data = await response.json();
    if (!response.ok) {
      setError(data.error || t("인증 메일 발송에 실패했습니다."));
      return false;
    }
    setNotice(t("인증번호를 발송했습니다. 메일함을 확인해주세요."));
    setResendLeft(60);
    return true;
  };

  // 계정 생성 요청 — 인증번호 단계가 꺼져 있으면 code 없이 보낸다(서버도 검사하지 않음).
  const submitRegistration = async (): Promise<void> => {
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: formData.name.trim(),
        email: formData.email.trim(),
        password: formData.password,
        ...(verificationRequired ? { code } : {}),
        termsAgreed: agreed,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      setError(data.error || t("회원가입에 실패했습니다."));
      setLoading(false);
      return;
    }
    // 가입 성공 = 자동 로그인(쿠키 발급됨). 전체 리로드로 인증 상태를 반영한다.
    window.location.href = "/";
  };

  const handleRequestCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");

    if (!formData.name.trim() || !formData.email || !formData.password) {
      setError(t("모든 필드를 입력해주세요."));
      return;
    }
    if (formData.password !== formData.confirmPassword) {
      setError(t("비밀번호가 일치하지 않습니다."));
      return;
    }
    if (
      formData.password.length < 8 ||
      !/[A-Za-z]/.test(formData.password) ||
      !/\d/.test(formData.password)
    ) {
      setError(t("비밀번호는 8자 이상이며 영문과 숫자를 모두 포함해야 합니다."));
      return;
    }
    if (!agreed) {
      setError(t("만 14세 이상 확인과 약관 동의가 필요합니다."));
      return;
    }

    setLoading(true);
    try {
      if (!verificationRequired) {
        await submitRegistration();
        return;
      }
      const sent = await requestCode();
      if (sent) {
        setCode("");
        setStep("verify");
      }
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
      setLoading(false);
      return;
    }
    if (verificationRequired) {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError("");
    setNotice("");
    setLoading(true);
    try {
      await requestCode();
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setNotice("");

    if (!/^\d{6}$/.test(code)) {
      setError(t("인증번호 6자리를 입력해주세요."));
      return;
    }

    setLoading(true);
    try {
      await submitRegistration();
    } catch {
      setError(t("서버 오류가 발생했습니다. 다시 시도해주세요."));
      setLoading(false);
    }
  };

  const inputClass =
    "w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-100";

  return (
    <main className="min-h-screen grid grid-cols-1 lg:grid-cols-2 overflow-x-hidden max-w-full pt-[var(--top-menu-bar-height,76px)]">
      <section className="flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <div className="h-10 w-10 rounded bg-gray-900 dark:bg-gray-100" />
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t("널스탁")}</p>
              <h1 className="text-xl font-semibold">{t("이메일로 가입")}</h1>
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}
          {notice && !error && (
            <div className="mb-4 p-3 rounded-md bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
              <p className="text-sm text-blue-600 dark:text-blue-400">{notice}</p>
            </div>
          )}

          {step === "form" ? (
            <form onSubmit={handleRequestCode} className="space-y-4">
              <div>
                <label htmlFor="name" className="block text-sm font-medium mb-1">
                  {t("이름")}
                </label>
                <input
                  id="name"
                  type="text"
                  placeholder={t("홍길동")}
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className={inputClass}
                  maxLength={50}
                  required
                />
              </div>
              <div>
                <label htmlFor="email" className="block text-sm font-medium mb-1">
                  {t("이메일")}
                </label>
                <input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
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
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className={inputClass}
                  required
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {t("8자 이상, 영문과 숫자를 모두 포함해주세요.")}
                </p>
              </div>
              <div>
                <label htmlFor="confirm" className="block text-sm font-medium mb-1">
                  {t("비밀번호 확인")}
                </label>
                <input
                  id="confirm"
                  type="password"
                  placeholder="••••••••"
                  value={formData.confirmPassword}
                  onChange={(e) =>
                    setFormData({ ...formData, confirmPassword: e.target.value })
                  }
                  className={inputClass}
                  required
                />
              </div>

              <label className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
                <input
                  type="checkbox"
                  checked={agreed}
                  onChange={(e) => setAgreed(e.target.checked)}
                  className="mt-0.5"
                  required
                />
                <span>
                  {t("만 14세 이상이며 아래에 동의합니다.")}{" "}
                  <Link href="/?legal=terms" className="text-blue-500 hover:underline" target="_blank">
                    {t("이용약관")}
                  </Link>
                  {" · "}
                  <Link href="/?legal=privacy" className="text-blue-500 hover:underline" target="_blank">
                    {t("개인정보처리방침")}
                  </Link>
                </span>
              </label>

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-md bg-gray-900 text-white py-2.5 font-medium hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading
                  ? t("처리 중...")
                  : verificationRequired
                    ? t("인증번호 받기")
                    : t("가입 완료")}
              </button>

              <p className="text-center text-sm text-gray-600 dark:text-gray-400">
                {t("이미 계정이 있으신가요?")}{" "}
                <Link href="/login" className="text-blue-500 hover:underline">
                  {t("로그인")}
                </Link>
              </p>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {t("{0} 주소로 발송된 인증번호 6자리를 입력해주세요.", formData.email.trim())}
              </p>
              <div>
                <label htmlFor="code" className="block text-sm font-medium mb-1">
                  {t("인증번호")}
                </label>
                <input
                  id="code"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  className={`${inputClass} tracking-[0.5em] text-center text-lg`}
                  required
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-md bg-gray-900 text-white py-2.5 font-medium hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? t("처리 중...") : t("가입 완료")}
              </button>

              <div className="flex items-center justify-between text-sm">
                <button
                  type="button"
                  onClick={() => {
                    setStep("form");
                    setError("");
                    setNotice("");
                  }}
                  className="text-gray-600 dark:text-gray-400 hover:underline"
                >
                  {t("정보 수정")}
                </button>
                <button
                  type="button"
                  onClick={() => void handleResend()}
                  disabled={loading || resendLeft > 0}
                  className="text-blue-500 hover:underline disabled:cursor-not-allowed disabled:text-gray-400 disabled:no-underline"
                >
                  {resendLeft > 0
                    ? t("{0}초 후 다시 받기", resendLeft)
                    : t("인증번호 다시 받기")}
                </button>
              </div>
            </form>
          )}
        </div>
      </section>

      <aside className="hidden lg:block relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600" />
        <div className="relative h-full w-full p-12 flex flex-col justify-between text-white">
          <div>
            <p className="text-sm font-medium opacity-90">{t("널스탁")}</p>
            <h2 className="mt-2 text-3xl font-bold leading-tight">
              {t("투자 전략 연구·시뮬레이션 플랫폼")}
            </h2>
            <p className="mt-4 max-w-md opacity-90">
              {t("나만의 전략을 설계하고, 과거 데이터로 검증하고, 시뮬레이션으로 연구하세요.")}
            </p>
          </div>
          <div className="text-xs opacity-90">
            <p>{t("© 널스탁")}</p>
          </div>
        </div>
      </aside>
    </main>
  );
}
