"use client";

import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

// Drawer 컨텍스트 - 전역 상태 관리
export type DrawerType = "watchlist" | "virtualAccount" | null;

interface DrawerContextType {
  drawerType: DrawerType;
  isWatchlistOpen: boolean; // 하위 호환성을 위해 유지
  openWatchlist: () => void;
  closeWatchlist: () => void;
  isVirtualAccountOpen: boolean; // 하위 호환성을 위해 유지
  openVirtualAccount: () => void;
  closeVirtualAccount: () => void;
  closeDrawer: () => void; // 공유 drawer 닫기
  selectedAccountId: string | null;
  setSelectedAccountId: (id: string | null) => void;
}

const DrawerContext = createContext<DrawerContextType | undefined>(undefined);

export function useDrawer() {
  const context = useContext(DrawerContext);
  if (!context) {
    throw new Error("useDrawer must be used within DrawerProvider");
  }
  return context;
}

export function DrawerProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [drawerType, setDrawerType] = useState<DrawerType>(null);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const isInitialized = useRef(false);
  // drawer 상태가 한 번 열리면 사용자가 명시적으로 닫을 때까지 유지
  const drawerWasOpened = useRef(false);
  
  // 하위 호환성을 위한 computed 값
  const isWatchlistOpen = drawerType === "watchlist";
  const isVirtualAccountOpen = drawerType === "virtualAccount";

  // 공유 Drawer 닫기 함수
  const closeDrawer = useCallback(() => {
    setDrawerType(null);
    drawerWasOpened.current = false;
    setSelectedAccountId(null);
    // URL에서 모든 drawer 파라미터 제거
    const currentUrl = new URL(window.location.href);
    currentUrl.searchParams.delete("watchlist");
    currentUrl.searchParams.delete("virtualAccount");
    const newUrl = currentUrl.pathname + (currentUrl.search ? currentUrl.search : "");
    router.replace(newUrl, { scroll: false });
  }, [router]);

  // Drawer 열기/닫기 함수 - useCallback으로 메모이제이션하여 리렌더링 방지
  const openWatchlist = useCallback(() => {
    // drawer가 이미 열려있으면 컨텐츠만 변경
    if (drawerType !== null) {
      setDrawerType("watchlist");
      drawerWasOpened.current = true;
      // URL 파라미터 업데이트
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.delete("virtualAccount");
      currentUrl.searchParams.set("watchlist", "open");
      router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
    } else {
      setDrawerType("watchlist");
      drawerWasOpened.current = true;
      // URL에 watchlist=open 파라미터 추가
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.set("watchlist", "open");
      router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
    }
  }, [router, drawerType]);

  const closeWatchlist = useCallback(() => {
    closeDrawer();
  }, [closeDrawer]);

  // 가상계좌 Drawer 열기/닫기 함수
  const openVirtualAccount = useCallback(() => {
    // drawer가 이미 열려있으면 컨텐츠만 변경
    if (drawerType !== null) {
      setDrawerType("virtualAccount");
      drawerWasOpened.current = true;
      // URL 파라미터 업데이트
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.delete("watchlist");
      currentUrl.searchParams.set("virtualAccount", "open");
      router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
    } else {
      setDrawerType("virtualAccount");
      drawerWasOpened.current = true;
      // URL에 virtualAccount=open 파라미터 추가
      const currentUrl = new URL(window.location.href);
      currentUrl.searchParams.set("virtualAccount", "open");
      router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
    }
  }, [router, drawerType]);

  const closeVirtualAccount = useCallback(() => {
    closeDrawer();
  }, [closeDrawer]);

  const handleSetSelectedAccountId = useCallback((id: string | null) => {
    setSelectedAccountId(id);
  }, []);

  // 초기 로드 시 drawer는 항상 닫힌 상태로 시작
  useEffect(() => {
    if (!isInitialized.current) {
      // 초기 로드 시 URL에 drawer 파라미터가 있어도 무시하고 닫힌 상태로 시작
      // 사용자가 명시적으로 메뉴를 클릭했을 때만 열림
      setDrawerType(null);
      drawerWasOpened.current = false;
      
      // URL에 drawer 파라미터가 있으면 제거하여 깨끗한 상태로 시작
      const watchlistParam = searchParams.get("watchlist");
      const virtualAccountParam = searchParams.get("virtualAccount");
      if (watchlistParam === "open" || virtualAccountParam === "open") {
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.delete("watchlist");
        currentUrl.searchParams.delete("virtualAccount");
        const newUrl = currentUrl.pathname + (currentUrl.search ? currentUrl.search : "");
        router.replace(newUrl, { scroll: false });
      }
      
      isInitialized.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // 초기 로드 시에만 실행

  // drawer가 열려있을 때 다른 페이지로 이동해도 drawer 파라미터 유지
  // pathname이 변경될 때만 실행 (drawer 상태는 절대 변경하지 않음)
  useEffect(() => {
    // drawer가 열려있고 초기화가 완료된 경우에만 실행
    // drawer 상태는 절대 변경하지 않음 - 오직 URL 파라미터만 업데이트
    if (drawerType !== null && isInitialized.current && drawerWasOpened.current) {
      // pathname이 변경되었을 때만 URL 파라미터 확인 및 추가
      // 약간의 지연을 두어 불필요한 리렌더링 방지
      const timer = setTimeout(() => {
        const currentWatchlistParam = new URLSearchParams(window.location.search).get("watchlist");
        const currentVirtualAccountParam = new URLSearchParams(window.location.search).get("virtualAccount");
        
        if (drawerType === "watchlist" && currentWatchlistParam !== "open") {
          // URL 파라미터만 업데이트, drawer 상태는 절대 변경하지 않음
          const currentUrl = new URL(window.location.href);
          currentUrl.searchParams.delete("virtualAccount");
          currentUrl.searchParams.set("watchlist", "open");
          router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
        } else if (drawerType === "virtualAccount" && currentVirtualAccountParam !== "open") {
          const currentUrl = new URL(window.location.href);
          currentUrl.searchParams.delete("watchlist");
          currentUrl.searchParams.set("virtualAccount", "open");
          router.replace(currentUrl.pathname + currentUrl.search, { scroll: false });
        }
      }, 0);
      return () => clearTimeout(timer);
    }
    // drawer가 닫혀있을 때는 아무것도 하지 않음 (상태 유지)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, drawerType]); // pathname과 drawerType 변경 시에만 실행

  // Context value를 메모이제이션하여 불필요한 리렌더링 방지
  const contextValue = useMemo(
    () => ({
      drawerType,
      isWatchlistOpen,
      openWatchlist,
      closeWatchlist,
      isVirtualAccountOpen,
      openVirtualAccount,
      closeVirtualAccount,
      closeDrawer,
      selectedAccountId,
      setSelectedAccountId: handleSetSelectedAccountId,
    }),
    [drawerType, isWatchlistOpen, openWatchlist, closeWatchlist, isVirtualAccountOpen, openVirtualAccount, closeVirtualAccount, closeDrawer, selectedAccountId, handleSetSelectedAccountId]
  );

  return (
    <DrawerContext.Provider value={contextValue}>
      {children}
    </DrawerContext.Provider>
  );
}

