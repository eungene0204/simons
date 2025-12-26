"use client";

import { ReactNode, useState, useEffect, createContext, useContext, memo } from "react";
import { useDrawer } from "@/contexts/DrawerContext";

// 주문 페이지 컨텍스트
interface OrderContextType {
  selectedSymbol: string | null;
  selectedStockName: string | null;
  setOrderStock: (symbol: string, name: string) => void;
  clearOrderStock: () => void;
}

const OrderContext = createContext<OrderContextType | undefined>(undefined);

export function useOrder() {
  const context = useContext(OrderContext);
  if (!context) {
    throw new Error("useOrder must be used within DashboardLayout");
  }
  return context;
}

// 내부 컴포넌트 - memo로 감싸서 children이나 userName이 변경되지 않으면 리렌더링 방지
const DashboardLayoutContent = memo(function DashboardLayoutContent({
  children,
  userName,
}: {
  children: ReactNode;
  userName: string;
}) {
  const { drawerType } = useDrawer();
  const [drawerWidthPx, setDrawerWidthPx] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedStockName, setSelectedStockName] = useState<string | null>(null);
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

  const setOrderStock = (symbol: string, name: string) => {
    setSelectedSymbol(symbol);
    setSelectedStockName(name);
  };

  const clearOrderStock = () => {
    setSelectedSymbol(null);
    setSelectedStockName(null);
  };

  // 탑메뉴바 높이를 CSS 변수에서 읽어오기
  useEffect(() => {
    const updateHeight = () => {
      const height = parseFloat(
        getComputedStyle(document.documentElement)
          .getPropertyValue('--top-menu-bar-height')
          .trim()
      ) || 76;
        setTopMenuBarHeight(height);
    };

    updateHeight();
    const interval = setInterval(updateHeight, 100);
    return () => clearInterval(interval);
  }, []);

  return (
    <OrderContext.Provider
      value={{
        selectedSymbol,
        selectedStockName,
        setOrderStock,
        clearOrderStock,
      }}
    >
      <div className="min-h-screen bg-[#0f0f0f] flex flex-col relative">
        <main 
          className="flex-1 overflow-y-auto overflow-x-hidden animate-fade-in max-w-full transition-all duration-300 ease-in-out"
          style={{
            marginLeft: `${drawerWidthPx}px`,
            paddingTop: `${topMenuBarHeight}px`,
          }}
        >
          {children}
        </main>
      </div>
    </OrderContext.Provider>
  );
});

// DrawerProvider는 app/layout.tsx에서 전역으로 제공됨
export default function DashboardLayout({
  children,
  userName,
}: {
  children: ReactNode;
  userName: string;
}) {
  return (
    <DashboardLayoutContent userName={userName}>
      {children}
    </DashboardLayoutContent>
  );
}
