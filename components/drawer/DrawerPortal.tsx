"use client";

import { createPortal } from "react-dom";
import { useEffect, useState, useRef } from "react";
import WatchlistDrawer from "./WatchlistDrawer";
import VirtualAccountDrawer from "./VirtualAccountDrawer";
import { useDrawer } from "@/contexts/DrawerContext";
import { useRouter } from "next/navigation";

// Portal을 사용하여 drawer를 body에 직접 렌더링
// Context 리렌더링의 영향을 받지 않도록 분리
export default function DrawerPortal() {
  const { 
    drawerType,
    closeDrawer,
    setSelectedAccountId
  } = useDrawer();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [isAnimating, setIsAnimating] = useState(false);
  const [displayDrawerType, setDisplayDrawerType] = useState<string | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // 클라이언트 사이드에서만 Portal 렌더링
  useEffect(() => {
    setMounted(true);
  }, []);

  // drawerType 변경 시 애니메이션 처리
  useEffect(() => {
    if (drawerType) {
      // drawer가 열릴 때: 먼저 DOM에 추가하고, 다음 프레임에 애니메이션 시작
      setDisplayDrawerType(drawerType);
      setIsAnimating(true); // 먼저 닫힌 상태로 시작
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      // 다음 프레임에 열리는 애니메이션 시작
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setIsAnimating(false);
        });
      });
    } else {
      // drawer가 닫힐 때: 애니메이션 시작
      setIsAnimating(true);
      // 애니메이션 완료 후 DOM에서 제거 (300ms)
      timeoutRef.current = setTimeout(() => {
        setDisplayDrawerType(null);
        setIsAnimating(false);
        timeoutRef.current = null;
      }, 300);
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [drawerType]);

  const handleStockSelect = (symbol: string, name: string) => {
    // 주문 페이지로 이동 (드로어는 유지)
    router.push(`/order?symbol=${symbol}&name=${encodeURIComponent(name)}&watchlist=open`);
  };

  const handleAccountSelect = (accountId: string) => {
    // 가상계좌 선택 시 Context에 저장
    setSelectedAccountId(accountId);
  };

  if (!mounted) return null;

  // displayDrawerType이 null이면 아무것도 렌더링하지 않음
  if (!displayDrawerType) return null;

  // drawerType에 따라 하나의 drawer만 렌더링
  // isAnimating이 true면 닫히는 애니메이션 중
  return (
    <>
      {displayDrawerType === "watchlist" && createPortal(
        <WatchlistDrawer 
          isOpen={!isAnimating} 
          onClose={closeDrawer}
          onStockSelect={handleStockSelect}
        />,
        document.body
      )}
      {displayDrawerType === "virtualAccount" && createPortal(
        <VirtualAccountDrawer 
          isOpen={!isAnimating} 
          onClose={closeDrawer}
          onAccountSelect={handleAccountSelect}
        />,
        document.body
      )}
    </>
  );
}

