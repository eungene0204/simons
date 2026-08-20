"use client";

import { useMemo, memo, useState, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/firebase";
import {
  PENDING_STRATEGY_PROMPT_KEY,
  STRATEGY_CHAT_STATE_KEY,
  requestStrategyLabChatView,
} from "@/components/strategy/strategyTemplateSession";
import {
  SquaresFour,
  Bank,
  MagnifyingGlass,
  ChartLineUp,
  Flask,
  SlidersHorizontal,
  CaretDown,
  GearSix,
  GoogleLogo,
  List,
  SignOut,
  X,
  Receipt,
} from "phosphor-react";
import {
  formatBacktestResetIn,
  formatUsageValue,
  getUsagePercent,
} from "./planUsageFormat";
import LanguageToggle from "@/lib/i18n/LanguageToggle";
import { getLocale, t } from "@/lib/i18n";

const QuickSearchModal = dynamic(() => import("./QuickSearchModal"), {
  ssr: false,
});
const SettingsModal = dynamic(() => import("./SettingsModal"), {
  ssr: false,
});

const menuItems = [
  {
    label: "전략연구소",
    href: "/analytics",
    id: "analytics",
    Icon: Flask,
  },
  {
    label: "모의투자",
    href: "/virtual-account",
    id: "virtual-account",
    Icon: ChartLineUp,
  },
  {
    label: "백테스트 기록",
    href: "/backtest",
    id: "backtest",
    Icon: SlidersHorizontal,
  },
  {
    label: "대시보드",
    href: "/dashboard",
    id: "dashboard",
    Icon: SquaresFour,
  },
  {
    label: "요금제",
    href: "/pricing",
    id: "pricing",
    Icon: Receipt,
  },
];

type UserProfile = {
  name: string;
  email?: string;
  avatarUrl?: string;
};

type CurrentUserResponse = {
  user?: {
    name?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
  } | null;
};

type LoginResponse = {
  error?: string;
  user?: {
    name?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
  } | null;
};

type AuthState = "loading" | "authenticated" | "anonymous";

type PlanUsageSummary = {
  plan: {
    planId: string;
    name: string;
    initialInvestmentAmount: number;
    planStartDate?: string | null;
    planEndDate?: string | null;
  };
  accounts: { used: number; limit: number };
  strategies: { used: number; limit: number | null; unlimited: boolean };
  backtests: { used: number; limit: number };
};

function formatWon(value: number) {
  return t("{0}원", Math.round(value).toLocaleString("ko-KR"));
}

function formatPlanDate(value?: string | null) {
  if (!value) return t("미등록");

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString(getLocale(), {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function isSpecificUserName(value: string) {
  return Boolean(value && value !== "사용자" && value !== "게스트");
}

function getInitials(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "U";
  const compact = trimmed.replace(/\s+/g, "");
  return compact.slice(0, Math.min(2, compact.length)).toUpperCase();
}

function TopNavigationComponent({ userName }: { userName?: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [planUsage, setPlanUsage] = useState<PlanUsageSummary | null>(null);
  const [isPlanLoading, setIsPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isStartingLogin, setIsStartingLogin] = useState(false);
  const [authState, setAuthState] = useState<AuthState>(
    isSpecificUserName(userName?.trim() || "") ? "authenticated" : "loading"
  );
  const [userProfile, setUserProfile] = useState<UserProfile>({
    name: userName?.trim() || "사용자",
  });
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isMounted = true;
    const providedName = userName?.trim() || "";
    const fallbackProfile = {
      name: providedName || "사용자",
    };

    const hydrateUserProfile = async () => {
      try {
        const response = await fetch("/api/user", {
          cache: "no-store",
          credentials: "same-origin",
        });
        const data = (await response.json()) as CurrentUserResponse;
        const currentUser = data.user;

        if (currentUser) {
          const serverName = currentUser.name?.trim();
          const serverEmail = currentUser.email?.trim();
          const serverAvatarUrl = currentUser.avatarUrl?.trim();

          if (isMounted) {
            setAuthState("authenticated");
            setUserProfile({
              name:
                serverName ||
                serverEmail?.split("@")[0] ||
                (isSpecificUserName(providedName) ? providedName : "") ||
                providedName ||
                "사용자",
              email: serverEmail,
              avatarUrl: serverAvatarUrl || undefined,
            });
          }
          return;
        }
      } catch {
        // Fall through to the local browser session fallback below.
      }

      if (!isSupabaseConfigured()) {
        if (isMounted) {
          setUserProfile(fallbackProfile);
          setAuthState("anonymous");
        }
        return;
      }

      try {
        const { data } = await getSupabaseBrowserClient().auth.getSession();
        if (!isMounted) return;

        const accessToken = data.session?.access_token;
        if (!accessToken) {
          setUserProfile(fallbackProfile);
          setAuthState("anonymous");
          return;
        }

        const loginResponse = await fetch("/api/login", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          credentials: "same-origin",
          body: JSON.stringify({ supabaseAccessToken: accessToken }),
        });
        const loginData = (await loginResponse.json()) as LoginResponse;

        if (!isMounted) return;

        if (!loginResponse.ok || !loginData.user) {
          setUserProfile(fallbackProfile);
          setAuthState("anonymous");
          return;
        }

        const hydratedName = loginData.user.name?.trim();
        const hydratedEmail = loginData.user.email?.trim();
        const hydratedAvatarUrl = loginData.user.avatarUrl?.trim();

        setAuthState("authenticated");
        setUserProfile({
          name:
            hydratedName ||
            hydratedEmail?.split("@")[0] ||
            (isSpecificUserName(providedName) ? providedName : "") ||
            providedName ||
            "사용자",
          email: hydratedEmail,
          avatarUrl: hydratedAvatarUrl || undefined,
        });
      } catch {
        if (isMounted) {
          setUserProfile(fallbackProfile);
          setAuthState("anonymous");
        }
      }
    };

    void hydrateUserProfile();

    return () => {
      isMounted = false;
    };
  }, [userName]);

  useEffect(() => {
    if (!isProfileMenuOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        profileButtonRef.current?.contains(target) ||
        profileMenuRef.current?.contains(target)
      ) {
        return;
      }

      setIsProfileMenuOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [isProfileMenuOpen]);

  // '/' 키보드 단축키 처리
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // '/' 키를 누르고, input이나 textarea에 포커스가 없을 때만 모달 열기
      if (e.key === "/" && !isSearchModalOpen) {
        const target = e.target as HTMLElement;
        const isInputFocused =
          target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable;
        
        if (!isInputFocused) {
          e.preventDefault();
          setIsSearchModalOpen(true);
        }
      }
      
      // ESC 키로 모달 닫기
      if (e.key === "Escape" && isSearchModalOpen) {
        setIsSearchModalOpen(false);
      }

      if (e.key === "Escape" && isProfileMenuOpen) {
        setIsProfileMenuOpen(false);
      }

      if (e.key === "Escape" && isMobileMenuOpen) {
        setIsMobileMenuOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSearchModalOpen, isProfileMenuOpen, isMobileMenuOpen]);

  useEffect(() => {
    if (!isMobileMenuOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isMobileMenuOpen]);

  const searchParamsString = searchParams.toString();
  useEffect(() => {
    setIsSearchModalOpen(false);
    setIsProfileMenuOpen(false);
    setIsMobileMenuOpen(false);
  }, [pathname, searchParamsString]);

  const handleSearchClick = () => {
    setIsMobileMenuOpen(false);
    setIsSearchModalOpen(true);
  };

  const handleGoogleLogin = async () => {
    if (isStartingLogin || !isSupabaseConfigured()) return;

    setIsStartingLogin(true);
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

      if (error) {
        throw error;
      }
    } finally {
      setIsLoginModalOpen(false);
      setIsStartingLogin(false);
    }
  };

  const handleLogout = async () => {
    if (isLoggingOut) return;

    setIsLoggingOut(true);
    setIsMobileMenuOpen(false);
    setIsProfileMenuOpen(false);
    setUserProfile({ name: "사용자" });
    setAuthState("anonymous");
    // 로그아웃 후 랜딩으로 이동할 때 이전 채팅 스냅샷이 복원되어 채팅 화면이
    // 다시 보이지 않도록 세션에 저장된 전략연구소 채팅 상태를 지운다.
    try {
      sessionStorage.removeItem(STRATEGY_CHAT_STATE_KEY);
      sessionStorage.removeItem(PENDING_STRATEGY_PROMPT_KEY);
    } catch {
      // sessionStorage 접근 불가 시 무시 — 정리는 best-effort.
    }
    try {
      await fetch("/api/logout", {
        method: "POST",
        credentials: "same-origin",
      });

      if (isSupabaseConfigured()) {
        await getSupabaseBrowserClient().auth.signOut().catch(() => undefined);
      }
    } finally {
      setIsLoggingOut(false);
      router.replace("/");
      router.refresh();
    }
  };

  const handlePlanClick = async () => {
    setIsProfileMenuOpen(false);
    setIsMobileMenuOpen(false);
    setIsPlanModalOpen(true);
    setIsPlanLoading(true);
    setPlanError(null);

    try {
      const response = await fetch("/api/user/plan", {
        cache: "no-store",
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("Failed to load plan");
      }

      const data = (await response.json()) as PlanUsageSummary;
      setPlanUsage(data);
    } catch {
      setPlanError(t("플랜 정보를 불러오지 못했습니다."));
    } finally {
      setIsPlanLoading(false);
    }
  };

  const handleMenuClick = (
    item: (typeof menuItems)[0],
    e: React.MouseEvent
  ) => {
    setIsMobileMenuOpen(false);

    if (authState === "anonymous" && item.id !== "analytics") {
      e.preventDefault();
      setIsLoginModalOpen(true);
      return;
    }

    // 전략연구소 메뉴 재진입 시에는 이전 대화를 유지한다(복원은 page.tsx의 세션
    // 스냅샷 복원 로직이 담당). 단, 백테스트 결과 화면이 떠 있으면 결과 화면이
    // 그대로 남아 메뉴를 눌러도 이동이 안 된 것처럼 보이므로 대화 화면으로 내린다.
    if (item.id === "analytics") {
      requestStrategyLabChatView();
    }

    e.preventDefault();
    router.push(item.href);
  };

  const activeMenuItemId = useMemo(() => {
    if (!pathname) return null;

    if (pathname === "/") {
      return "analytics";
    }

    if (pathname === "/dashboard") {
      return "dashboard";
    }

    let bestMatch: { id: string; href: string; pathLength: number } | null =
      null;

    for (const item of menuItems) {
      if (item.href === "/") {
        continue;
      }

      if (pathname === item.href || pathname.startsWith(item.href + "/")) {
        const pathLength = item.href.length;
        if (!bestMatch || pathLength > bestMatch.pathLength) {
          bestMatch = { id: item.id, href: item.href, pathLength };
        }
      }
    }

    if (bestMatch) {
      return bestMatch.id;
    }

    return null;
  }, [pathname]);


  return (
    <>
      <nav
        className="flex items-center justify-between bg-black/40 px-4 py-3 backdrop-blur-xl lg:hidden"
        aria-label={t("모바일 상단 내비게이션")}
      >
        <div className="flex min-w-0 items-center gap-2">
          <Link
            href="/"
            onClick={() => setIsMobileMenuOpen(false)}
            className="group flex min-w-0 items-center gap-2"
          >
            <svg
              aria-hidden="true"
              viewBox="510 215 400 330"
              className="h-[1.125rem] w-[1.375rem] flex-shrink-0 overflow-hidden"
            >
              <image href="/nullStock.png" width="1408" height="768" />
            </svg>
            <span className="truncate text-[15px] font-black tracking-tight text-white">
              {t("널스탁")}
            </span>
          </Link>
          <span className="rounded-md bg-blue-500/15 px-1.5 py-0.5 text-[8px] font-black tracking-[0.12em] text-blue-300">
            OPEN BETA
          </span>
        </div>

        <div className="flex flex-shrink-0 items-center gap-1">
          <LanguageToggle className="mr-1" />
          <button
            type="button"
            onClick={handleSearchClick}
            className="rounded-xl p-2.5 text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
            aria-label={t("검색 열기")}
          >
            <MagnifyingGlass size={20} weight="bold" />
          </button>
          <button
            type="button"
            onPointerUp={() => setIsMobileMenuOpen(true)}
            onClick={() => setIsMobileMenuOpen(true)}
            className="touch-manipulation rounded-xl p-2.5 text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
            aria-label={t("메뉴 열기")}
            aria-expanded={isMobileMenuOpen}
            aria-controls="mobile-navigation-drawer"
          >
            <List size={22} weight="bold" />
          </button>
        </div>
      </nav>

      <nav className="relative hidden items-center gap-1 overflow-x-auto bg-black/40 px-6 py-3 backdrop-blur-xl scrollbar-hide lg:flex">
        {/* Logo */}
        <div className="mr-8 flex flex-shrink-0 items-center gap-3">
          <Link href="/" className="group flex items-center gap-3">
            <svg
              aria-hidden="true"
              viewBox="510 215 400 330"
              className="h-[1.125rem] w-[1.375rem] overflow-hidden transition-transform duration-300 group-hover:scale-105"
              data-testid="nullstock-logo-mark"
            >
              <defs>
                <filter
                  id="nullstock-transparent-background"
                  x="-10%"
                  y="-10%"
                  width="120%"
                  height="120%"
                  colorInterpolationFilters="sRGB"
                >
                  <feColorMatrix
                    type="matrix"
                    values="
                      1 0 0 0 0
                      0 1 0 0 0
                      0 0 1 0 0
                      0.2126 0.7152 0.0722 0 -0.2
                    "
                  />
                  <feComponentTransfer>
                    <feFuncA type="linear" slope="2.2" intercept="0" />
                  </feComponentTransfer>
                </filter>
              </defs>
              <image
                href="/nullStock.png"
                width="1408"
                height="768"
                filter="url(#nullstock-transparent-background)"
              />
            </svg>
            <span className="text-[15px] font-black tracking-tight text-white">{t("널스탁")}</span>
          </Link>
          <span className="rounded-md bg-blue-500/15 px-2 py-0.5 text-[9px] font-black tracking-[0.14em] text-blue-300">
            OPEN BETA
          </span>
        </div>

        {/* Menu Items */}
        <div
          className="flex flex-1 items-center gap-1 xl:absolute xl:left-1/2 xl:flex-none xl:-translate-x-1/2"
          data-testid="top-navigation-menu"
        >
          {menuItems.map((item) => {
            const isActive = activeMenuItemId === item.id;
            const IconComponent = item.Icon;

            return (
              <Link
                key={item.id}
                href={item.href}
                onClick={(e) => handleMenuClick(item, e)}
                className={`relative flex items-center gap-2 px-4 py-2 rounded-xl transition-all duration-300 whitespace-nowrap group ${
                  isActive
                    ? "bg-white/10 text-white shadow-lg"
                    : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.02]"
                }`}
              >
                <IconComponent
                  size={18}
                  weight={isActive ? "fill" : "regular"}
                  className={`transition-colors ${isActive ? "text-blue-400" : "group-hover:text-blue-400"}`}
                />
                <span
                  className={`text-sm tracking-tight ${
                    isActive ? "font-black" : "font-bold"
                  }`}
                >
                  {t(item.label)}
                </span>
              </Link>
            );
          })}
        </div>

        {/* Search Bar */}
        <div className="flex items-center gap-2 ml-auto mr-4">
          <button
            type="button"
            onClick={handleSearchClick}
            className="group relative flex min-w-[180px] items-center rounded-xl border border-white/[0.1] bg-[#111116] px-2.5 py-1 text-left shadow-[0_8px_22px_rgba(0,0,0,0.22)] transition-all duration-200 hover:border-white/[0.18] hover:bg-[#17171d] xl:w-[160px] xl:min-w-0 min-[1320px]:w-auto min-[1320px]:min-w-[180px]"
            aria-label={t("검색 열기")}
            data-testid="desktop-search-trigger"
          >
            <MagnifyingGlass size={18} className="mr-2.5 flex-shrink-0 text-gray-500 group-hover:text-gray-300" />
            <span className="mr-2 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-white/[0.07] text-xs font-black text-gray-400">
              /
            </span>
            <span className="min-w-0 flex-1 truncate text-xs font-bold tracking-tight text-gray-500 group-hover:text-gray-300">
              {t("를 눌러 검색하세요")}
            </span>
          </button>
        </div>

        {/* Language toggle (KR / EN) — sits left of the profile */}
        <LanguageToggle className="mr-3" />

        {/* User Profile */}
        {authState === "authenticated" ? (
          <button
            ref={profileButtonRef}
            type="button"
            aria-label={t("{0} 사용자 메뉴", userProfile.name)}
            aria-expanded={isProfileMenuOpen}
            onClick={() => setIsProfileMenuOpen((open) => !open)}
            className="flex flex-shrink-0 items-center gap-3 rounded-full border border-white/[0.08] bg-black/40 py-1.5 pl-1.5 pr-3 text-white transition-colors duration-200 hover:border-white/[0.16] hover:bg-white/[0.04]"
          >
            <span className="flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border border-white/[0.12] bg-white/[0.08] text-xs font-black text-white">
              {userProfile.avatarUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={userProfile.avatarUrl}
                  alt=""
                  className="h-full w-full object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : (
                getInitials(userProfile.name)
              )}
            </span>
            <span className="max-w-[120px] truncate text-sm font-black tracking-tight text-white">
              {userProfile.name}
            </span>
            <CaretDown size={16} weight="bold" className="text-gray-400" />
          </button>
        ) : authState === "anonymous" ? (
          <button
            type="button"
            onClick={handleGoogleLogin}
            disabled={isStartingLogin || !isSupabaseConfigured()}
            className="flex flex-shrink-0 items-center gap-2 rounded-full border border-white/[0.08] bg-white px-4 py-2 text-sm font-black text-black transition-colors duration-200 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <GoogleLogo size={18} weight="fill" />
            <span>{isStartingLogin ? t("로그인 준비 중...") : t("Google 로그인")}</span>
          </button>
        ) : (
          <div
            aria-hidden="true"
            className="h-[44px] w-[160px] flex-shrink-0 rounded-full border border-white/[0.08] bg-black/30"
          />
        )}
      </nav>

      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-[70] lg:hidden" data-testid="mobile-navigation-drawer">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            onClick={() => setIsMobileMenuOpen(false)}
            aria-label={t("모바일 메뉴 닫기")}
          />
          <aside
            id="mobile-navigation-drawer"
            role="dialog"
            aria-modal="true"
            aria-label={t("모바일 메뉴")}
            className="absolute inset-y-0 right-0 flex w-[min(86vw,320px)] flex-col border-l border-white/[0.08] bg-[#050505] shadow-2xl shadow-black/60"
          >
            <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-4">
              <span className="text-sm font-black tracking-tight text-white">{t("메뉴")}</span>
              <button
                type="button"
                onClick={() => setIsMobileMenuOpen(false)}
                className="rounded-xl p-2 text-gray-400 transition-colors hover:bg-white/[0.06] hover:text-white"
                aria-label={t("메뉴 닫기")}
              >
                <X size={18} weight="bold" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-4">
              <div className="space-y-1">
                {menuItems.map((item) => {
                  const isActive = activeMenuItemId === item.id;
                  const IconComponent = item.Icon;

                  return (
                    <Link
                      key={item.id}
                      href={item.href}
                      onClick={(event) => handleMenuClick(item, event)}
                      className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 transition-colors ${
                        isActive
                          ? "bg-white/10 text-white"
                          : "text-gray-400 hover:bg-white/[0.04] hover:text-white"
                      }`}
                    >
                      <IconComponent
                        size={20}
                        weight={isActive ? "fill" : "regular"}
                        className={isActive ? "text-blue-400" : "text-gray-500"}
                      />
                      <span className="text-sm font-black">{t(item.label)}</span>
                    </Link>
                  );
                })}
              </div>

              <button
                type="button"
                onClick={handleSearchClick}
                className="mt-5 flex w-full items-center gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-3 text-left text-sm font-bold text-gray-400"
              >
                <MagnifyingGlass size={20} weight="bold" />
                <span>{t("검색")}</span>
              </button>
            </div>

            <div className="border-t border-white/[0.08] p-4">
              {authState === "authenticated" ? (
                <button
                  type="button"
                  aria-label={t("{0} 사용자 메뉴", userProfile.name)}
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    setIsProfileMenuOpen(true);
                  }}
                  className="flex w-full min-w-0 items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-white/[0.04]"
                >
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/[0.12] bg-white/[0.08] text-xs font-black text-white">
                    {getInitials(userProfile.name)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm font-black text-white">
                    {userProfile.name}
                  </span>
                  <CaretDown size={16} weight="bold" className="text-gray-500" />
                </button>
              ) : authState === "anonymous" ? (
                <button
                  type="button"
                  onClick={() => void handleGoogleLogin()}
                  disabled={isStartingLogin || !isSupabaseConfigured()}
                  className="flex w-full items-center justify-center gap-2 rounded-full bg-white px-4 py-2.5 text-sm font-black text-black disabled:opacity-60"
                >
                  <GoogleLogo size={18} weight="fill" />
                  <span>{isStartingLogin ? t("로그인 준비 중...") : t("Google 로그인")}</span>
                </button>
              ) : (
                <div className="h-10 animate-pulse rounded-full bg-white/[0.06]" />
              )}
            </div>
          </aside>
        </div>
      )}

      {authState === "authenticated" && isProfileMenuOpen && (
        <div
          ref={profileMenuRef}
          className="fixed right-6 top-[64px] z-[60] w-56 overflow-hidden rounded-2xl border border-white/[0.08] bg-[#050505] shadow-2xl shadow-black/40"
        >
          <div className="border-b border-white/[0.06] px-4 py-3">
            <p className="truncate text-sm font-black text-white">{userProfile.name}</p>
            {userProfile.email && (
              <p className="mt-0.5 truncate text-[11px] font-bold text-gray-500">
                {userProfile.email}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => void handlePlanClick()}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white"
          >
            <Bank size={16} weight="bold" className="text-gray-500" />
            <span>{t("내 플랜")}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setIsProfileMenuOpen(false);
              setIsSettingsModalOpen(true);
            }}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white"
          >
            <GearSix size={16} weight="bold" className="text-gray-500" />
            <span>{t("설정")}</span>
          </button>
          <button
            type="button"
            onClick={handleLogout}
            disabled={isLoggingOut}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white disabled:cursor-wait disabled:opacity-60"
          >
            <SignOut size={16} weight="bold" className="text-gray-500" />
            <span>{isLoggingOut ? t("로그아웃 중...") : t("로그아웃")}</span>
          </button>
        </div>
      )}

      {authState === "authenticated" && isPlanModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="plan-summary-modal-title"
        >
          <div className="w-full max-w-lg overflow-hidden rounded-3xl border border-white/[0.08] bg-[#050505] shadow-2xl shadow-black/60">
            <div className="flex items-start justify-between gap-4 border-b border-white/[0.08] px-6 py-5">
              <div>
                <h2
                  id="plan-summary-modal-title"
                  className="text-2xl font-black tracking-tight text-gray-400"
                >
                  {t("내 플랜")}
                </h2>
              </div>
              <button
                type="button"
                aria-label={t("내 플랜 모달 닫기")}
                onClick={() => setIsPlanModalOpen(false)}
                className="rounded-full border border-white/[0.08] p-2 text-gray-500 transition-colors hover:bg-white/[0.06] hover:text-white"
              >
                <X size={16} weight="bold" />
              </button>
            </div>

            {isPlanLoading ? (
              <div className="px-6 py-12 text-center text-sm font-bold text-gray-500">
                {t("플랜 정보를 불러오는 중입니다.")}
              </div>
            ) : planError ? (
              <div className="px-6 py-12 text-center">
                <p className="text-sm font-black text-red-300">{planError}</p>
                <button
                  type="button"
                  onClick={() => void handlePlanClick()}
                  className="mt-5 rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-black text-gray-400 transition-colors hover:bg-white/[0.06]"
                >
                  {t("다시 불러오기")}
                </button>
              </div>
            ) : planUsage ? (
              <div className="space-y-7 px-6 py-6">
                <section className="space-y-4">
                  {[
                    [t("현재 플랜"), planUsage.plan.name],
                    [
                      t("플랜 시작 날짜"),
                      formatPlanDate(planUsage.plan.planStartDate),
                    ],
                    [
                      t("플랜 종료 날짜"),
                      formatPlanDate(planUsage.plan.planEndDate),
                    ],
                    [
                      t("계좌당 초기 모의 투자금"),
                      formatWon(planUsage.plan.initialInvestmentAmount),
                    ],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-center justify-between gap-5"
                    >
                      <span className="text-sm font-bold text-gray-500">
                        {label}
                      </span>
                      <span className="min-w-0 truncate text-right text-base font-black text-gray-300">
                        {value}
                      </span>
                    </div>
                  ))}
                </section>

                <section className="space-y-5">
                  <p className="font-outfit text-sm font-black uppercase tracking-[0.18em] text-gray-500">
                    Usage
                  </p>
                  {[
                    {
                      label: t("사용 중인 계좌"),
                      value: formatUsageValue(
                        planUsage.accounts.used,
                        planUsage.accounts.limit
                      ),
                      percent: getUsagePercent(
                        planUsage.accounts.used,
                        planUsage.accounts.limit
                      ),
                      sublabel: null as string | null,
                    },
                    {
                      label: t("저장 가능 전략"),
                      value: formatUsageValue(
                        planUsage.strategies.used,
                        planUsage.strategies.limit,
                        planUsage.strategies.unlimited
                      ),
                      percent: getUsagePercent(
                        planUsage.strategies.used,
                        planUsage.strategies.limit,
                        planUsage.strategies.unlimited
                      ),
                      sublabel: null as string | null,
                    },
                    {
                      label: t("백테스트 횟수"),
                      value: formatUsageValue(
                        planUsage.backtests.used,
                        planUsage.backtests.limit
                      ),
                      percent: getUsagePercent(
                        planUsage.backtests.used,
                        planUsage.backtests.limit
                      ),
                      sublabel: formatBacktestResetIn(
                        planUsage.plan.planEndDate
                      ),
                    },
                  ].map((item) => (
                    <div key={item.label} className="space-y-2">
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-xs font-bold text-gray-500">
                          {item.label}
                        </span>
                        <span className="font-outfit text-sm font-bold tabular-nums text-gray-500">
                          {item.value}
                        </span>
                      </div>
                      <div
                        role="progressbar"
                        aria-label={item.label}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={item.percent}
                        className="h-2 overflow-hidden rounded-full bg-white/[0.16]"
                      >
                        <div
                          className="h-full rounded-full bg-[var(--accent-blue)]"
                          style={{ width: `${item.percent}%` }}
                        />
                      </div>
                      {item.sublabel ? (
                        <p className="text-right font-outfit text-xs font-bold text-gray-600">
                          {item.sublabel}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </section>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {authState === "authenticated" && isSettingsModalOpen && (
        <SettingsModal
          userEmail={userProfile.email ?? null}
          onClose={() => setIsSettingsModalOpen(false)}
          onLogout={() => {
            setIsSettingsModalOpen(false);
            void handleLogout();
          }}
          onAccountDeleted={() => {
            setIsSettingsModalOpen(false);
            void handleLogout();
          }}
        />
      )}

      {isSearchModalOpen && (
        <QuickSearchModal
          isOpen
          onClose={() => setIsSearchModalOpen(false)}
        />
      )}

      {isLoginModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="sidebar-login-modal-title"
        >
          <div className="w-full max-w-md rounded-3xl border border-white/[0.08] bg-[#0b0b0b] p-6 text-center shadow-2xl shadow-black/50">
            <div className="space-y-3">
              <p
                id="sidebar-login-modal-title"
                className="text-2xl font-black tracking-tight text-white"
              >
                {t("로그인 후 이용할 수 있습니다")}
              </p>
              <p className="text-sm font-bold leading-relaxed text-gray-400">
                {t("Google로 3초만에 시작하세요")}
              </p>
            </div>
            <div className="mt-6 flex flex-col items-center gap-3">
              <p className="text-xs font-black text-[#ff6b6b]">
                {t("카드 등록 불필요")}
              </p>
              <button
                type="button"
                onClick={() => void handleGoogleLogin()}
                disabled={isStartingLogin || !isSupabaseConfigured()}
                className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white px-4 py-2 text-sm font-black text-black transition-colors duration-200 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <GoogleLogo size={18} weight="fill" />
                <span>{isStartingLogin ? t("로그인 준비 중...") : t("Google로 시작하기")}</span>
              </button>
              <Link
                href="/login"
                onClick={() => setIsLoginModalOpen(false)}
                className="text-xs font-bold text-gray-400 transition-colors hover:text-white"
              >
                {t("이메일로 로그인")}
              </Link>
              <button
                type="button"
                onClick={() => setIsLoginModalOpen(false)}
                className="text-sm font-black text-gray-400 transition-colors hover:text-white"
              >
                {t("취소")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// memo로 감싸서 props가 변경되지 않으면 리렌더링 방지
export default memo(TopNavigationComponent);
