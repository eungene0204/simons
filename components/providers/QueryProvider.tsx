"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { useRegionHref } from "@/lib/geo/useRegion";
import { stripRegionPrefix } from "@/lib/geo/region";

// 로그인하지 않고 열 수 있는 화면 — 인증 화면 자체가 여기 들어가야 한다.
// 빠지면 AuthSessionGuard가 비로그인 방문자를 홈으로 되돌려 페이지에 머물 수 없다.
const PUBLIC_PATHS = new Set(["/", "/login", "/register", "/guest"]);
// 하위 경로까지 공개인 화면 — 백테스트 가이드(`/guide`, `/guide/<slug>`)·연구노트(`/notes`, `/notes/<slug>`)는 검색 유입용 공개 글이다.
// 공개 가상계좌 열람(`/shared/virtual-account/<id>`)도 비로그인 읽기 전용 화면이다(소유자가 공개로 전환한 계좌만).
const PUBLIC_PATH_PREFIXES = ["/guide", "/notes", "/board", "/shared/virtual-account"];

function isPublicPath(pathname: string | null) {
  if (!pathname) return true;
  // 지역 프리픽스(/us)를 벗겨 판정한다 — /us·/us/login도 공개 경로다.
  const path = stripRegionPrefix(pathname);
  return (
    PUBLIC_PATHS.has(path) ||
    PUBLIC_PATH_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
  );
}

function AuthSessionGuard() {
  const pathname = usePathname();
  const router = useRouter();
  const regionHref = useRegionHref();

  useEffect(() => {
    if (isPublicPath(pathname)) return;

    let isMounted = true;

    const verifySession = async () => {
      try {
        const response = await fetch("/api/user", {
          cache: "no-store",
          credentials: "same-origin",
        });
        const data = (await response.json()) as { user?: unknown };

        if (!isMounted || data.user) return;

        router.replace(regionHref("/"));
        router.refresh();
      } catch {
        // Keep the current screen on transient network errors.
      }
    };

    void verifySession();

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void verifySession();
      }
    };

    window.addEventListener("focus", verifySession);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const intervalId = window.setInterval(verifySession, 60_000);

    return () => {
      isMounted = false;
      window.removeEventListener("focus", verifySession);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.clearInterval(intervalId);
    };
  }, [pathname, router, regionHref]);

  return null;
}

export default function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 2_000,
            gcTime: 60_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <AuthSessionGuard />
      {children}
    </QueryClientProvider>
  );
}
