"use client";

import { useEffect, useRef, memo } from "react";
import TopNavigation from "./TopNavigation";

// 탑메뉴바를 memo로 감싸서 리렌더링 방지
const TopMenuBarContent = memo(function TopMenuBarContent({
  subHeader,
  userName,
}: {
  subHeader?: React.ReactNode;
  userName?: string;
}) {
  const topMenuBarRef = useRef<HTMLDivElement>(null);

  // CSS Custom Property로 높이 공유 (ResizeObserver 사용)
  useEffect(() => {
    const topMenuBar = topMenuBarRef.current;
    if (!topMenuBar) return;

    const updateHeight = () => {
      const height = topMenuBar.offsetHeight;
      if (height > 0) {
        document.documentElement.style.setProperty('--top-menu-bar-height', `${height}px`);
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
      className="fixed top-0 left-0 right-0 z-50 border-b border-white/5"
      style={{
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
        <TopNavigation userName={userName} />
        {subHeader}
      </div>
    </div>
  );
});

export default function TopMenuBar({
  subHeader,
  userName,
}: {
  subHeader?: React.ReactNode;
  userName?: string;
}) {
  return <TopMenuBarContent subHeader={subHeader} userName={userName} />;
}
