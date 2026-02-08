"use client";

import { useMemo, memo, useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useDrawer } from "@/contexts/DrawerContext";
import {
  Squares2X2Icon,
  StarIcon,
  BanknotesIcon,
  MagnifyingGlassIcon,
  PresentationChartLineIcon,
  UsersIcon,
  SparklesIcon,
} from "@heroicons/react/24/outline";
import {
  Squares2X2Icon as Squares2X2IconSolid,
  StarIcon as StarIconSolid,
  BanknotesIcon as BanknotesIconSolid,
  PresentationChartLineIcon as PresentationChartLineIconSolid,
  UsersIcon as UsersIconSolid,
} from "@heroicons/react/24/solid";
import StockSearchModal from "@/components/stock/StockSearchModal";

const menuItems = [
  {
    label: "대시보드",
    href: "/",
    id: "dashboard",
    Icon: Squares2X2Icon,
    IconSolid: Squares2X2IconSolid,
  },
  {
    label: "가상계좌",
    href: "/virtual-account",
    id: "virtual-account",
    Icon: BanknotesIcon,
    IconSolid: BanknotesIconSolid,
  },
  {
    label: "관심종목",
    href: "/watchlist",
    id: "watchlist",
    Icon: StarIcon,
    IconSolid: StarIconSolid,
  },
  {
    label: "전략연구소",
    href: "/analytics",
    id: "analytics",
    Icon: PresentationChartLineIcon,
    IconSolid: PresentationChartLineIconSolid,
  },
  {
    label: "커뮤니티",
    href: "/community",
    id: "community",
    Icon: UsersIcon,
    IconSolid: UsersIconSolid,
  },
];

interface SidebarProps {
  onWatchlistClick?: () => void;
  isWatchlistOpen?: boolean;
}

function SidebarComponent({
  onWatchlistClick,
  isWatchlistOpen,
}: SidebarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);
  
  // Context에서 drawer 상태 직접 가져오기
  const {
    isWatchlistOpen: drawerOpen,
    openWatchlist,
    isVirtualAccountOpen,
    openVirtualAccount,
  } = useDrawer();

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
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSearchModalOpen]);

  const handleSearchClick = () => {
    setIsSearchModalOpen(true);
  };

  const handleSearchSelect = (symbols: Array<{ symbol: string; name: string }>) => {
    if (symbols.length > 0) {
      const { symbol, name } = symbols[0];
      router.push(`/order?symbol=${symbol}&name=${encodeURIComponent(name)}`);
    }
  };

  const handleMenuClick = (
    item: (typeof menuItems)[0],
    e: React.MouseEvent
  ) => {
    if (item.id === "watchlist") {
      e.preventDefault();
      // Context의 openWatchlist 사용
      if (onWatchlistClick) {
        onWatchlistClick();
      } else {
        openWatchlist();
      }
    } else if (item.id === "virtual-account") {
      e.preventDefault();
      // 가상계좌 drawer 열기
      openVirtualAccount();
    } else {
      // 다른 메뉴를 클릭할 때 drawer가 열려있으면 파라미터 유지
      // drawer 상태는 절대 변경하지 않음
      const isWatchlistDrawerOpen =
        drawerOpen ||
        isWatchlistOpen ||
        searchParams.get("watchlist") === "open";
      const isVirtualAccountDrawerOpen =
        isVirtualAccountOpen || searchParams.get("virtualAccount") === "open";

      if (isWatchlistDrawerOpen) {
        e.preventDefault();
        const url = new URL(item.href, window.location.origin);
        url.searchParams.set("watchlist", "open");
        router.push(url.pathname + url.search);
      } else if (isVirtualAccountDrawerOpen) {
        e.preventDefault();
        const url = new URL(item.href, window.location.origin);
        url.searchParams.set("virtualAccount", "open");
        router.push(url.pathname + url.search);
      } else {
        // drawer가 열려있지 않을 때도 명시적으로 pathname 업데이트
        e.preventDefault();
        router.push(item.href);
      }
    }
  };

  // Find the active menu item - only one should be active at a time
  // useMemo로 메모이제이션하여 pathname, searchParams, drawer 상태 변경 시에만 재계산
  // searchParams는 객체이므로 toString()으로 변환하여 dependency로 사용
  const watchlistParam = searchParams.get("watchlist");
  const virtualAccountParam = searchParams.get("virtualAccount");

  const activeMenuItemId = useMemo(() => {
    if (!pathname) return null;

    // 1. 먼저 pathname 기반으로 정확히 일치하는 메뉴 확인 (최우선)
    // Root path는 정확히 일치해야 함
    if (pathname === "/") {
      return "dashboard";
    }

    // 다른 경로들은 정확히 일치하거나 하위 경로인지 확인
    let bestMatch: { id: string; href: string; pathLength: number } | null =
      null;

    for (const item of menuItems) {
      // Root path는 이미 처리했으므로 스킵
      if (item.href === "/") {
        continue;
      }

      // 정확히 일치하거나 하위 경로인지 확인
      // 예: pathname이 "/watchlist"이고 item.href가 "/watchlist"이면 매칭
      // 예: pathname이 "/virtual-account/123"이고 item.href가 "/virtual-account"이면 매칭
      if (pathname === item.href || pathname.startsWith(item.href + "/")) {
        const pathLength = item.href.length;
        // 가장 긴 매칭 경로 선택 (가장 구체적인 매칭)
        if (!bestMatch || pathLength > bestMatch.pathLength) {
          bestMatch = { id: item.id, href: item.href, pathLength };
        }
      }
    }

    // 2. pathname과 일치하는 메뉴가 있으면 해당 메뉴 활성화 (최우선)
    // drawer 상태와 관계없이 경로 기반 매칭이 우선
    if (bestMatch) {
      return bestMatch.id;
    }

    // 3. pathname과 일치하는 메뉴가 없을 때만 drawer 상태 확인
    // (예: /order 같은 특정 페이지에 있을 때)
    const isWatchlistDrawerOpen =
      drawerOpen || isWatchlistOpen || watchlistParam === "open";
    const isVirtualAccountDrawerOpen =
      isVirtualAccountOpen || virtualAccountParam === "open";

    if (isWatchlistDrawerOpen) {
      return "watchlist";
    }
    if (isVirtualAccountDrawerOpen) {
      return "virtual-account";
    }

    return null;
  }, [
    pathname,
    watchlistParam,
    virtualAccountParam,
    drawerOpen,
    isWatchlistOpen,
    isVirtualAccountOpen,
  ]);

  // 디버깅: pathname과 activeMenuItemId 확인 (개발 중에만)
  if (process.env.NODE_ENV === "development") {
    console.log(
      "Sidebar - pathname:",
      pathname,
      "activeMenuItemId:",
      activeMenuItemId,
      "drawerOpen:",
      drawerOpen,
      "watchlistParam:",
      watchlistParam,
      "virtualAccountParam:",
      virtualAccountParam
    );
  }

  return (
    <nav className="bg-black/40 backdrop-blur-xl border-b border-white/5 flex items-center gap-1 px-6 py-3 overflow-x-auto scrollbar-hide">
      {/* Logo */}
      <Link
        href={
          drawerOpen ||
          isWatchlistOpen ||
          searchParams.get("watchlist") === "open"
            ? "/?watchlist=open"
            : "/"
        }
        className="flex items-center gap-3 mr-8 flex-shrink-0 group"
      >
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-black text-lg shadow-[0_0_15px_rgba(59,130,246,0.3)] group-hover:scale-105 transition-transform duration-300">
          N
        </div>
        <p className="text-sm font-black text-white tracking-tighter font-outfit uppercase">널스탁</p>
      </Link>

      {/* Menu Items */}
      <div className="flex items-center gap-1 flex-1">
        {menuItems.map((item) => {
          const isActive = activeMenuItemId === item.id;
          const IconComponent = isActive ? item.IconSolid : item.Icon;

          return (
            <Link
              key={item.id}
              href={item.href}
              onClick={(e) => handleMenuClick(item, e)}
              className={`relative flex items-center gap-2 px-4 py-2 rounded-xl transition-all duration-300 whitespace-nowrap group ${
                isActive
                  ? "bg-white/10 text-white shadow-lg border border-white/5"
                  : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.02]"
              }`}
            >
              <IconComponent
                className={`w-4.5 h-4.5 transition-colors ${isActive ? "text-blue-400" : "group-hover:text-blue-400"}`}
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
          <MagnifyingGlassIcon className="w-4 h-4 text-gray-500 group-hover:text-gray-300 mr-2 flex-shrink-0" />
          <span className="text-[10px] text-gray-500 font-bold bg-black/40 border border-white/10 rounded px-1.5 py-0.5 mr-2 flex-shrink-0">/</span>
          <span className="text-xs text-gray-500 group-hover:text-gray-400 font-bold flex-1">Quick Search</span>
        </div>
      </div>

      {/* Upgrade Button */}
      <button className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl text-xs font-black hover:shadow-[0_0_15px_rgba(59,130,246,0.4)] transition-all flex items-center gap-2 flex-shrink-0">
        <SparklesIcon className="w-4 h-4" />
        <span>PRO</span>
      </button>
    </nav>
  );
}

// memo로 감싸서 props가 변경되지 않으면 리렌더링 방지
export default memo(SidebarComponent);
