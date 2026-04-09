"use client";

import { useMemo, memo, useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { useDrawer } from "@/contexts/DrawerContext";
import Image from "next/image";
import {
  SquaresFour,
  Bank,
  MagnifyingGlass,
  ChartLineUp,
  Sparkle,
  Clock,
} from "phosphor-react";
import QuickSearchModal from "./QuickSearchModal";

const menuItems = [
  {
    label: "대시보드",
    href: "/",
    id: "dashboard",
    Icon: SquaresFour,
  },
  {
    label: "가상계좌",
    href: "/virtual-account",
    id: "virtual-account",
    Icon: Bank,
  },
  {
    label: "전략연구소",
    href: "/analytics",
    id: "analytics",
    Icon: ChartLineUp,
  },
  {
    label: "백테스트",
    href: "/backtest",
    id: "backtest",
    Icon: Clock,
  },
];

function SidebarComponent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const [isSearchModalOpen, setIsSearchModalOpen] = useState(false);

  const { isVirtualAccountOpen, openVirtualAccount } = useDrawer();

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
            <span className="text-xs text-gray-500 group-hover:text-gray-400 font-bold flex-1">Quick Search</span>
          </div>
        </div>

        {/* Upgrade Button */}
        <button className="px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-xl text-xs font-black hover:shadow-[0_0_15px_rgba(59,130,246,0.4)] transition-all flex items-center gap-2 flex-shrink-0">
          <Sparkle size={16} weight="fill" />
          <span>PRO</span>
        </button>
      </nav>

      <QuickSearchModal
        isOpen={isSearchModalOpen}
        onClose={() => setIsSearchModalOpen(false)}
      />
    </>
  );
}

// memo로 감싸서 props가 변경되지 않으면 리렌더링 방지
export default memo(SidebarComponent);
