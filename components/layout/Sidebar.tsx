"use client";

import { useMemo, memo, useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useDrawer } from "@/contexts/DrawerContext";
import { getSupabaseBrowserClient, isSupabaseConfigured } from "@/lib/firebase";
import Image from "next/image";
import {
  SquaresFour,
  Bank,
  MagnifyingGlass,
  ChartLineUp,
  Clock,
  CaretDown,
  SignOut,
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

function isSpecificUserName(value: string) {
  return Boolean(value && value !== "사용자" && value !== "게스트");
}

function getInitials(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "U";
  const compact = trimmed.replace(/\s+/g, "");
  return compact.slice(0, Math.min(2, compact.length)).toUpperCase();
}

function SidebarComponent({ userName }: { userName?: string }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile>({
    name: userName?.trim() || "사용자",
  });
  const profileButtonRef = useRef<HTMLButtonElement>(null);
  const profileMenuRef = useRef<HTMLDivElement>(null);

  const { isVirtualAccountOpen, openVirtualAccount } = useDrawer();

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
        if (isMounted) setUserProfile(fallbackProfile);
        return;
      }

      try {
        const { data } = await getSupabaseBrowserClient().auth.getSession();
        if (!isMounted) return;

        const sessionUser = data.session?.user;
        const metadata = sessionUser?.user_metadata ?? {};
        const metadataName =
          typeof metadata.full_name === "string"
            ? metadata.full_name
            : typeof metadata.name === "string"
              ? metadata.name
              : "";
        const avatarUrl =
          typeof metadata.avatar_url === "string"
            ? metadata.avatar_url
            : typeof metadata.picture === "string"
              ? metadata.picture
              : undefined;

        setUserProfile({
          name:
            (isSpecificUserName(providedName) ? providedName : "") ||
            metadataName ||
            sessionUser?.email?.split("@")[0] ||
            providedName ||
            "사용자",
          email: sessionUser?.email,
          avatarUrl,
        });
      } catch {
        if (isMounted) {
          setUserProfile(fallbackProfile);
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

  const handleLogout = async () => {
    if (isLoggingOut) return;

    setIsLoggingOut(true);
    try {
      await fetch("/api/logout", {
        method: "POST",
        credentials: "same-origin",
      });

      if (isSupabaseConfigured()) {
        await getSupabaseBrowserClient().auth.signOut().catch(() => undefined);
      }
    } finally {
      setIsProfileMenuOpen(false);
      router.replace("/");
      router.refresh();
    }
  };

  const handleMenuClick = (
    item: (typeof menuItems)[0],
    e: React.MouseEvent
  ) => {
    if (item.id === "virtual-account") {
      e.preventDefault();
      openVirtualAccount();
    } else {
      const isVirtualAccountDrawerOpen =
        isVirtualAccountOpen || searchParams.get("virtualAccount") === "open";

      e.preventDefault();
      if (isVirtualAccountDrawerOpen) {
        const url = new URL(item.href, window.location.origin);
        url.searchParams.set("virtualAccount", "open");
        router.push(url.pathname + url.search);
      } else {
        router.push(item.href);
      }
    }
  };

  const virtualAccountParam = searchParams.get("virtualAccount");

  const activeMenuItemId = useMemo(() => {
    if (!pathname) return null;

    if (pathname === "/" || pathname === "/dashboard") {
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

    if (isVirtualAccountOpen || virtualAccountParam === "open") {
      return "virtual-account";
    }

    return null;
  }, [pathname, virtualAccountParam, isVirtualAccountOpen]);


  return (
    <>
      <nav className="bg-black/40 backdrop-blur-xl flex items-center gap-1 px-6 py-3 overflow-x-auto scrollbar-hide">
        {/* Logo */}
        <Link
          href="/"
          className="flex items-center gap-3 mr-8 flex-shrink-0 group"
        >
          <Image
            src="/nullStock.png"
            alt="NullStock Logo"
            width={72}
            height={42}
            className="rounded-full group-hover:scale-105 transition-transform duration-300"
          />
          <span className="text-sm font-black text-white tracking-tighter uppercase">널스탁</span>
        </Link>

        {/* Menu Items */}
        <div className="flex items-center gap-1 flex-1">
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
      </nav>

      {isProfileMenuOpen && (
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
            onClick={handleLogout}
            disabled={isLoggingOut}
            className="flex w-full items-center gap-2 px-4 py-3 text-left text-xs font-black text-gray-300 transition-colors duration-200 hover:bg-white/[0.04] hover:text-white disabled:cursor-wait disabled:opacity-60"
          >
            <SignOut size={16} weight="bold" className="text-gray-500" />
            <span>{isLoggingOut ? "로그아웃 중..." : "로그아웃"}</span>
          </button>
        </div>
      )}

      <QuickSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
      />
    </>
  );
}

// memo로 감싸서 props가 변경되지 않으면 리렌더링 방지
export default memo(SidebarComponent);
