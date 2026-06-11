"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

const PUBLIC_PATHS = new Set(["/", "/login", "/register"]);

function isPublicPath(pathname: string | null) {
  if (!pathname) return true;
  return PUBLIC_PATHS.has(pathname);
}

function AuthSessionGuard() {
  const pathname = usePathname();
  const router = useRouter();

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

        router.replace("/");
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
  }, [pathname, router]);

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
