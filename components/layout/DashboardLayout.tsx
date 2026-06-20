"use client";

import {
  ReactNode,
  useState,
  useEffect,
  createContext,
  useContext,
  memo,
} from "react";
import { usePathname } from "next/navigation";

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

// 내부 컴포넌트 - memo로 감싸서 children이 변경되지 않으면 리렌더링 방지
const DashboardLayoutContent = memo(function DashboardLayoutContent({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedStockName, setSelectedStockName] = useState<string | null>(null);
  const [topMenuBarHeight, setTopMenuBarHeight] = useState(76);
  const dashboardFillClass = [
    "min-h-[calc(100vh-var(--top-menu-bar-height,76px))]",
    "[&>*]:min-h-[inherit]",
    "[&>*]:flex",
    "[&>*]:flex-col",
    "[&>*>*]:flex-1",
    "[&>*>*]:flex",
    "[&>*>*]:flex-col",
    "[&>*>*>:last-child]:flex-1",
  ].join(" ");

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
    const observer = new ResizeObserver(updateHeight);
    observer.observe(document.documentElement);
    return () => observer.disconnect();
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
      <div className="min-h-screen bg-[#050505] text-white flex flex-col relative">
        <main
          className="flex-1 overflow-y-auto overflow-x-hidden max-w-full"
          style={{
            paddingTop: `${topMenuBarHeight}px`,
          }}
        >
          <div className={`relative ${pathname === "/dashboard" ? dashboardFillClass : ""}`}>
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

export default function DashboardLayout({
  children,
}: {
  children: ReactNode;
  userName: string;
  subHeader?: ReactNode;
}) {
  return <DashboardLayoutContent>{children}</DashboardLayoutContent>;
}
