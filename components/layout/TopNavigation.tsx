"use client";

import { useMemo, memo, useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/firebase";
import {
  PENDING_STRATEGY_PROMPT_KEY,
  STRATEGY_CHAT_STATE_KEY,
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
  SignOut,
  X,
  Receipt,
} from "phosphor-react";
import QuickSearchModal from "./QuickSearchModal";
import SettingsModal from "./SettingsModal";
import {
  formatBacktestResetIn,
  formatUsageValue,
  getUsagePercent,
} from "./planUsageFormat";

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
    label: "전략모음",
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
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function formatPlanDate(value?: string | null) {
  if (!value) return "미등록";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return date.toLocaleDateString("ko-KR", {
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
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSearchModalOpen, isProfileMenuOpen]);

  const searchParamsString = searchParams.toString();
  useEffect(() => {
    setIsSearchModalOpen(false);
    setIsProfileMenuOpen(false);
  }, [pathname, searchParamsString]);

  const handleSearchClick = () => {
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
      setPlanError("플랜 정보를 불러오지 못했습니다.");
    } finally {
      setIsPlanLoading(false);
    }
  };

  const handleMenuClick = (
    item: (typeof menuItems)[0],
    e: React.MouseEvent
  ) => {
    if (authState === "anonymous" && item.id !== "analytics") {
      e.preventDefault();
      setIsLoginModalOpen(true);
      return;
    }

    // 전략연구소 메뉴 재진입 시에는 이전 백테스트 결과·대화를 유지한다(복원은
    // page.tsx의 세션 스냅샷 복원 로직이 담당). 새로 시작하려면 결과 화면의
    // 닫기 배지(전략연구소 초기 화면으로 이동)를 사용한다.

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
      <nav className="relative flex items-center gap-1 overflow-x-auto bg-black/40 px-6 py-3 backdrop-blur-xl scrollbar-hide">
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-3 mr-8 flex-shrink-0 group"
        >
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
          <span className="text-[15px] font-black tracking-tight text-white">널스탁</span>
          <span className="rounded-md bg-blue-500/15 px-2 py-0.5 text-[9px] font-black tracking-[0.14em] text-blue-300">
            OPEN BETA
          </span>
        </Link>

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
                  {item.label}
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
            className="group relative flex min-w-[180px] items-center rounded-xl border border-white/[0.1] bg-[#111116] px-2.5 py-1 text-left shadow-[0_8px_22px_rgba(0,0,0,0.22)] transition-all duration-200 hover:border-white/[0.18] hover:bg-[#17171d]"
            aria-label="검색 열기"
          >
            <MagnifyingGlass size={18} className="mr-2.5 flex-shrink-0 text-gray-500 group-hover:text-gray-300" />
            <span className="mr-2 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg bg-white/[0.07] text-xs font-black text-gray-400">
              /
            </span>
            <span className="min-w-0 flex-1 truncate text-xs font-bold tracking-tight text-gray-500 group-hover:text-gray-300">
              를 눌러 검색하세요
            </span>
          </button>
        </div>

        {/* User Profile */}
        {authState === "authenticated" ? (
          <button
            ref={profileButtonRef}
            type="button"
            aria-label={`${userProfile.name} 사용자 메뉴`}
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
            <span>{isStartingLogin ? "로그인 준비 중..." : "Google 로그인"}</span>
          </button>
        ) : (
          <div
            aria-hidden="true"
            className="h-[44px] w-[160px] flex-shrink-0 rounded-full border border-white/[0.08] bg-black/30"
          />
        )}
      </nav>

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
            <span>내 플랜</span>
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
            <span>설정</span>
          </button>
          <button
            type="button"
            onClick={handleLogout}
            disabled={isLoggingOut}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white disabled:cursor-wait disabled:opacity-60"
          >
            <SignOut size={16} weight="bold" className="text-gray-500" />
            <span>{isLoggingOut ? "로그아웃 중..." : "로그아웃"}</span>
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
                  내 플랜
                </h2>
              </div>
              <button
                type="button"
                aria-label="내 플랜 모달 닫기"
                onClick={() => setIsPlanModalOpen(false)}
                className="rounded-full border border-white/[0.08] p-2 text-gray-500 transition-colors hover:bg-white/[0.06] hover:text-white"
              >
                <X size={16} weight="bold" />
              </button>
            </div>

            {isPlanLoading ? (
              <div className="px-6 py-12 text-center text-sm font-bold text-gray-500">
                플랜 정보를 불러오는 중입니다.
              </div>
            ) : planError ? (
              <div className="px-6 py-12 text-center">
                <p className="text-sm font-black text-red-300">{planError}</p>
                <button
                  type="button"
                  onClick={() => void handlePlanClick()}
                  className="mt-5 rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-black text-gray-400 transition-colors hover:bg-white/[0.06]"
                >
                  다시 불러오기
                </button>
              </div>
            ) : planUsage ? (
              <div className="space-y-7 px-6 py-6">
                <section className="space-y-4">
                  {[
                    ["현재 플랜", planUsage.plan.name],
                    [
                      "플랜 시작 날짜",
                      formatPlanDate(planUsage.plan.planStartDate),
                    ],
                    [
                      "플랜 종료 날짜",
                      formatPlanDate(planUsage.plan.planEndDate),
                    ],
                    [
                      "계좌당 초기 모의 투자금",
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
                      label: "사용 중인 계좌",
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
                      label: "저장 가능 전략",
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
                      label: "백테스트 횟수",
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

      <QuickSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
      />

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
                로그인 후 이용할 수 있습니다
              </p>
              <p className="text-sm font-bold leading-relaxed text-gray-400">
                Google로 3초만에 시작하세요
              </p>
            </div>
            <div className="mt-6 flex flex-col items-center gap-3">
              <p className="text-xs font-black text-[#ff6b6b]">
                카드 등록 불필요
              </p>
              <button
                type="button"
                onClick={() => void handleGoogleLogin()}
                disabled={isStartingLogin || !isSupabaseConfigured()}
                className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white px-4 py-2 text-sm font-black text-black transition-colors duration-200 hover:bg-white/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <GoogleLogo size={18} weight="fill" />
                <span>{isStartingLogin ? "로그인 준비 중..." : "Google로 시작하기"}</span>
              </button>
              <button
                type="button"
                onClick={() => setIsLoginModalOpen(false)}
                className="text-sm font-black text-gray-400 transition-colors hover:text-white"
              >
                취소
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
