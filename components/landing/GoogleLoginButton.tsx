"use client";

import clsx from "clsx";
import { ArrowRight, GoogleLogo } from "phosphor-react";
import { useRouter } from "next/navigation";
import { startTransition, useEffect, useMemo, useState } from "react";
import {
  getSupabaseBrowserClient,
  isSupabaseConfigured,
} from "@/lib/firebase";

type GoogleLoginButtonProps = {
  className?: string;
  label?: string;
};

async function exchangeSupabaseToken(supabaseAccessToken: string) {
  const response = await fetch("/api/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ supabaseAccessToken }),
  });

  const data = (await response.json()) as { error?: string };

  if (!response.ok) {
    throw new Error(data.error || "Google 로그인에 실패했습니다.");
  }
}

export default function GoogleLoginButton({
  className,
  label = "Google로 시작하기",
}: GoogleLoginButtonProps) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRedirectLoading, setIsRedirectLoading] = useState(true);
  const isConfigured = useMemo(() => isSupabaseConfigured(), []);
  const isLoading = isSubmitting || isRedirectLoading;

  useEffect(() => {
    if (!isConfigured) {
      setIsRedirectLoading(false);
      return;
    }

    let isMounted = true;

    const hydrateRedirectSession = async () => {
      try {
        const supabase = getSupabaseBrowserClient();
        const {
          data: { session },
        } = await supabase.auth.getSession();

        if (!session?.access_token) {
          return;
        }

        await exchangeSupabaseToken(session.access_token);
        await supabase.auth.signOut().catch(() => undefined);

        if (!isMounted) {
          return;
        }

        startTransition(() => {
          router.push("/analytics");
          router.refresh();
        });
      } catch (redirectError) {
        if (isMounted) {
          setError(
            redirectError instanceof Error
              ? redirectError.message
              : "Google 로그인 처리 중 오류가 발생했습니다."
          );
        }
      } finally {
        if (isMounted) {
          setIsRedirectLoading(false);
        }
      }
    };

    void hydrateRedirectSession();

    return () => {
      isMounted = false;
    };
  }, [isConfigured, router]);

  const handleGoogleLogin = async () => {
    if (!isConfigured) {
      setError("Supabase 설정이 완료되지 않았습니다.");
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      const supabase = getSupabaseBrowserClient();
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: window.location.origin,
          queryParams: {
            access_type: "offline",
            prompt: "select_account",
          },
        },
      });

      if (oauthError) {
        throw oauthError;
      }
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? loginError.message
          : "Google 로그인 중 오류가 발생했습니다."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full">
      <button
        type="button"
        onClick={handleGoogleLogin}
        disabled={isLoading}
        className={clsx(
          "group inline-flex w-full items-center justify-center gap-3 rounded-full border border-white/10 bg-white px-5 py-3 text-sm font-semibold text-black transition hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto",
          className
        )}
        aria-describedby={error ? "google-login-error" : undefined}
      >
        <GoogleLogo className="h-5 w-5" weight="fill" />
        <span>{isLoading ? "로그인 준비 중..." : label}</span>
        <ArrowRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
      </button>
      {!isConfigured ? (
        <p className="mt-3 text-sm text-amber-300">
          Supabase 환경 변수가 설정되면 Google 로그인을 사용할 수 있습니다.
        </p>
      ) : null}
      {error ? (
        <p id="google-login-error" className="mt-3 text-sm text-red-300">
          {error}
        </p>
      ) : null}
    </div>
  );
}
