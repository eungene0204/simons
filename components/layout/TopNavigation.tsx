"use client";

import { useMemo, memo, useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/firebase";
import {
  SquaresFour,
  Bank,
  MagnifyingGlass,
  ChartLineUp,
  Clock,
  CaretDown,
  GoogleLogo,
  SignOut,
  X,
} from "phosphor-react";
import QuickSearchModal from "./QuickSearchModal";

const menuItems = [
  {
    label: "전략연구소",
    href: "/analytics",
    id: "analytics",
    Icon: ChartLineUp,
  },
  {
    label: "가상계좌",
    href: "/virtual-account",
    id: "virtual-account",
    Icon: Bank,
  },
  {
    label: "백테스트",
    href: "/backtest",
    id: "backtest",
    Icon: Clock,
  },
  {
    label: "대시보드",
    href: "/dashboard",
    id: "dashboard",
    Icon: SquaresFour,
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

type AssetSummary = {
  availableCash: number;
  activeAccountValue: number;
  totalAssets: number;
  totalProfitLoss: number;
};

function formatWon(value: number) {
  return `${Math.round(value).toLocaleString("ko-KR")}원`;
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
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [assetSummary, setAssetSummary] = useState<AssetSummary | null>(null);
  const [isAssetLoading, setIsAssetLoading] = useState(false);
  const [assetError, setAssetError] = useState<string | null>(null);
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

  const handleAssetsClick = async () => {
    setIsProfileMenuOpen(false);
    setIsAssetModalOpen(true);
    setIsAssetLoading(true);
    setAssetError(null);

    try {
      const response = await fetch("/api/user/assets", {
        cache: "no-store",
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("Failed to load assets");
      }

      const data = (await response.json()) as AssetSummary;
      setAssetSummary(data);
    } catch {
      setAssetError("자산 정보를 불러오지 못했습니다.");
    } finally {
      setIsAssetLoading(false);
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
          <div
            onClick={handleSearchClick}
            className="relative flex items-center bg-white/5 border border-white/5 rounded-xl px-4 py-1.5 min-w-[220px] cursor-pointer hover:bg-white/10 transition-all group"
          >
            <MagnifyingGlass size={16} className="text-gray-500 group-hover:text-gray-300 mr-2 flex-shrink-0" />
            <span className="text-[10px] text-gray-500 font-bold bg-black/40 border border-white/10 rounded px-1.5 py-0.5 mr-2 flex-shrink-0">/</span>
            <span className="text-xs text-gray-500 group-hover:text-gray-400 font-bold flex-1">빠른 검색</span>
          </div>
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
            onClick={() => void handleAssetsClick()}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white"
          >
            <Bank size={16} weight="bold" className="text-gray-500" />
            <span>자산</span>
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

      {authState === "authenticated" && isAssetModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="asset-summary-modal-title"
        >
          <div className="w-full max-w-lg overflow-hidden rounded-3xl border border-white/[0.08] bg-[#050505] shadow-2xl shadow-black/60">
            <div className="flex items-start justify-between gap-4 border-b border-white/[0.08] px-6 py-5">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.24em] text-blue-300/70">
                  Asset Wallet
                </p>
                <h2
                  id="asset-summary-modal-title"
                  className="mt-2 text-2xl font-black tracking-tight text-white"
                >
                  자산
                </h2>
              </div>
              <button
                type="button"
                aria-label="자산 모달 닫기"
                onClick={() => setIsAssetModalOpen(false)}
                className="rounded-full border border-white/[0.08] p-2 text-gray-500 transition-colors hover:bg-white/[0.06] hover:text-white"
              >
                <X size={16} weight="bold" />
              </button>
            </div>

            {isAssetLoading ? (
              <div className="px-6 py-12 text-center text-sm font-bold text-gray-500">
                자산 정보를 불러오는 중입니다.
              </div>
            ) : assetError ? (
              <div className="px-6 py-12 text-center">
                <p className="text-sm font-black text-red-300">{assetError}</p>
                <button
                  type="button"
                  onClick={() => void handleAssetsClick()}
                  className="mt-5 rounded-xl border border-white/[0.1] px-4 py-2 text-xs font-black text-white transition-colors hover:bg-white/[0.06]"
                >
                  다시 불러오기
                </button>
              </div>
            ) : assetSummary ? (
              <div className="grid grid-cols-1 divide-y divide-white/[0.08]">
                <div className="px-6 py-5">
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                    총 자산
                  </p>
                  <p className="mt-2 text-3xl font-black text-white">
                    {formatWon(assetSummary.totalAssets)}
                  </p>
                </div>
                <div className="grid grid-cols-1 divide-y divide-white/[0.08] sm:grid-cols-2 sm:divide-x sm:divide-y-0">
                  <div className="px-6 py-5">
                    <p className="text-xs font-black uppercase tracking-[0.18em] text-gray-500">
                      사용 가능 자산
                    </p>
                    <p className="mt-2 text-xl font-black text-emerald-300">
                      {formatWon(assetSummary.availableCash)}
                    </p>
                  </div>
                  <div className="px-6 py-5">
                    <p className="text-xs font-black uppercase tracking-[0.18em] text-gray-500">
                      가상계좌 운용 중 자산
                    </p>
                    <p className="mt-2 text-xl font-black text-blue-200">
                      {formatWon(assetSummary.activeAccountValue)}
                    </p>
                  </div>
                </div>
                <div className="px-6 py-5">
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-gray-500">
                    총 수익/손실
                  </p>
                  <p
                    className={`mt-2 text-2xl font-black ${
                      assetSummary.totalProfitLoss > 0
                        ? "text-emerald-300"
                        : assetSummary.totalProfitLoss < 0
                          ? "text-red-300"
                          : "text-gray-300"
                    }`}
                  >
                    {assetSummary.totalProfitLoss > 0 ? "+" : ""}
                    {formatWon(assetSummary.totalProfitLoss)}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        </div>
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
