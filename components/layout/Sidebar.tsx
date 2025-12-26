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
    <nav className="bg-[#0f0f0f] flex items-center gap-1 px-4 py-2 overflow-x-auto">
      {/* Logo */}
      <Link
        href={
          drawerOpen ||
          isWatchlistOpen ||
          searchParams.get("watchlist") === "open"
            ? "/?watchlist=open"
            : "/"
        }
        className="flex items-center gap-2 mr-4 flex-shrink-0"
      >
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white font-bold text-sm">
          N
        </div>
        <p className="text-sm font-semibold text-white">널스탁</p>
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
              className={`relative flex items-center gap-2 px-3 py-2 rounded-lg transition-all duration-200 whitespace-nowrap ${
                isActive
                  ? "!bg-[#252525] !text-white font-semibold"
                  : "text-gray-400 hover:bg-gray-900"
              }`}
            >
              <IconComponent
                className={`w-5 h-5 ${isActive ? "text-white" : ""}`}
              />
              <span
                className={`text-sm ${
                  isActive ? "font-semibold" : "font-medium"
                }`}
              >
                {item.label}
              </span>
            </Link>
          );
        })}
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-2 ml-auto mr-2">
        <div
          onClick={handleSearchClick}
          className="relative flex items-center bg-[#1a1a1a] border border-gray-800 rounded-lg px-3 py-1.5 min-w-[200px] cursor-pointer hover:bg-[#252525] transition-colors"
        >
          <MagnifyingGlassIcon className="w-4 h-4 text-gray-400 mr-2 flex-shrink-0" />
          <span className="text-xs text-gray-400 bg-[#0f0f0f] border border-gray-700 rounded px-1.5 py-0.5 mr-2 flex-shrink-0">/</span>
          <span className="text-xs text-gray-500 flex-1">를 눌러 검색하세요</span>
        </div>
      </div>

      {/* Search Modal */}
      <StockSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
        onSelect={handleSearchSelect}
        singleSelect={true}
      />

      {/* Upgrade Button */}
      <button className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-600 flex items-center gap-1.5 flex-shrink-0">
        <span>⭐</span>
        <span>Upgrade</span>
      </button>
    </nav>
  );
}

// memo로 감싸서 props가 변경되지 않으면 리렌더링 방지
export default memo(SidebarComponent);
