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
      <div className="min-h-screen bg-[#0f0f0f] text-white flex flex-col relative">
        {/* Real-time Ticker Tape */}
        <div 
          className="fixed top-[var(--top-menu-bar-height)] left-0 right-0 h-9 bg-black/40 backdrop-blur-xl border-b border-white/5 z-40 flex items-center overflow-hidden"
          style={{ marginLeft: `${drawerWidthPx}px` }}
        >
          <div className="animate-marquee flex gap-12 whitespace-nowrap text-[11px] font-bold tracking-tight">
             <div className="flex gap-12 py-2">
               <span className="flex items-center gap-2">KOSPI <span className="text-red-400 tabular-nums">2,580.42 ▲ 12.3</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.48%</span></span>
               <span className="flex items-center gap-2">KOSDAQ <span className="text-blue-400 tabular-nums">840.12 ▼ 3.1</span> <span className="text-[9px] bg-blue-400/10 px-1 rounded text-blue-500">0.37%</span></span>
               <span className="flex items-center gap-2">NASDAQ <span className="text-red-400 tabular-nums">16,248.52 ▲ 45.2</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.28%</span></span>
               <span className="flex items-center gap-2">S&P 500 <span className="text-red-400 tabular-nums">5,123.34 ▲ 8.7</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.17%</span></span>
               <span className="flex items-center gap-2 text-gray-400">USD/KRW <span className="text-white tabular-nums">1,342.50</span></span>
               <span className="flex items-center gap-2">BTC/USDT <span className="text-red-400 tabular-nums">98,240 ▲ 1.4%</span></span>
             </div>
             {/* Duplicate for seamless loop */}
             <div className="flex gap-12 py-2">
               <span className="flex items-center gap-2">KOSPI <span className="text-red-400 tabular-nums">2,580.42 ▲ 12.3</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.48%</span></span>
               <span className="flex items-center gap-2">KOSDAQ <span className="text-blue-400 tabular-nums">840.12 ▼ 3.1</span> <span className="text-[9px] bg-blue-400/10 px-1 rounded text-blue-500">0.37%</span></span>
               <span className="flex items-center gap-2">NASDAQ <span className="text-red-400 tabular-nums">16,248.52 ▲ 45.2</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.28%</span></span>
               <span className="flex items-center gap-2">S&P 500 <span className="text-red-400 tabular-nums">5,123.34 ▲ 8.7</span> <span className="text-[9px] bg-red-400/10 px-1 rounded text-red-500">0.17%</span></span>
               <span className="flex items-center gap-2 text-gray-400">USD/KRW <span className="text-white tabular-nums">1,342.50</span></span>
               <span className="flex items-center gap-2">BTC/USDT <span className="text-red-400 tabular-nums">98,240 ▲ 1.4%</span></span>
             </div>
          </div>
        </div>

        <main 
          className="flex-1 overflow-y-auto overflow-x-hidden animate-fade-in max-w-full transition-all duration-300 ease-in-out"
          style={{
            marginLeft: `${drawerWidthPx}px`,
            paddingTop: `calc(${topMenuBarHeight}px + 32px)`, // Adjust for ticker tape
          }}
        >
          <div className="relative z-10">
            {children}
          </div>
          
          {/* Advanced background ambience */}
          <div className="fixed top-0 left-0 w-full h-full pointer-events-none overflow-hidden -z-10">
            <div className="absolute top-[-15%] left-[-10%] w-[50%] h-[50%] bg-blue-600/10 blur-[150px] rounded-full animate-pulse" style={{ animationDuration: '8s' }} />
            <div className="absolute bottom-[-15%] right-[-10%] w-[50%] h-[50%] bg-indigo-600/10 blur-[150px] rounded-full animate-pulse" style={{ animationDuration: '10s' }} />
            <div className="absolute top-[20%] right-[10%] w-[30%] h-[30%] bg-purple-600/5 blur-[120px] rounded-full" />
          </div>
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
