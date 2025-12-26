"use client";

import { useState, useEffect, useRef, memo } from "react";
import Sidebar from "./Sidebar";
import DashboardHeader from "./DashboardHeader";
import { useDrawer } from "@/contexts/DrawerContext";

// 탑메뉴바를 memo로 감싸서 리렌더링 방지
const TopMenuBarContent = memo(function TopMenuBarContent() {
  const { drawerType, isWatchlistOpen, openWatchlist } = useDrawer();
  const [drawerWidthPx, setDrawerWidthPx] = useState(0);
  const topMenuBarRef = useRef<HTMLDivElement>(null);
  const [topMenuBarHeight, setTopMenuBarHeight] = useState(76);

  // 드로어 너비 계산 (20vw, 최소 300px, 최대 400px)
  useEffect(() => {
    const calculateDrawerWidth = () => {
      if (drawerType !== null) {
        const width = Math.min(Math.max(window.innerWidth * 0.2, 300), 400);
        setDrawerWidthPx(width);
      } else {
        setDrawerWidthPx(0);
      }
    };

    calculateDrawerWidth();
    
    if (drawerType !== null) {
      window.addEventListener("resize", calculateDrawerWidth);
      return () => window.removeEventListener("resize", calculateDrawerWidth);
    }
  }, [drawerType]);

  // CSS Custom Property로 높이 공유 (ResizeObserver 사용)
  useEffect(() => {
    const topMenuBar = topMenuBarRef.current;
    if (!topMenuBar) return;

    const updateHeight = () => {
      const height = topMenuBar.offsetHeight;
      if (height > 0) {
        document.documentElement.style.setProperty('--top-menu-bar-height', `${height}px`);
        setTopMenuBarHeight(height);
      }
    };

    // 초기 높이 설정
    updateHeight();

    // ResizeObserver로 높이 변경 감지
    const resizeObserver = new ResizeObserver(updateHeight);
    resizeObserver.observe(topMenuBar);

    // 리사이즈 이벤트도 함께 감지
    window.addEventListener('resize', updateHeight);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateHeight);
    };
  }, []);

  return (
    <div
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300 ease-in-out"
      style={{
        marginLeft: `${drawerWidthPx}px`,
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
      }}
    >
      <div 
        className="relative" 
        id="top-menu-bar"
        ref={topMenuBarRef}
      >
        <Sidebar 
          onWatchlistClick={openWatchlist} 
          isWatchlistOpen={isWatchlistOpen}
        />
        <DashboardHeader />
      </div>
    </div>
  );
});

export default function TopMenuBar() {
  return <TopMenuBarContent />;
}

