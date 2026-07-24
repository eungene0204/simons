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
          
          {/* Advanced background ambience
              — blur(150px) 필터는 모바일 GPU에서 매우 비싸 드로어/애니메이션 프레임을
              지연시킨다. 동일한 글로우를 radial-gradient로 그려 필터 연산을 제거한다
              (중심 좌표·색·투명도·펄스 동일, 블러 확산 범위만큼 박스를 키움). */}
          <div className="fixed top-0 left-0 w-full h-full pointer-events-none overflow-hidden -z-10">
            <div
              className="absolute top-[-25%] left-[-20%] w-[70%] h-[70%] animate-pulse"
              style={{
                animationDuration: '8s',
                background:
                  'radial-gradient(closest-side, rgba(37,99,235,0.10) 0%, rgba(37,99,235,0.09) 30%, rgba(37,99,235,0.055) 55%, rgba(37,99,235,0.02) 78%, transparent 100%)',
              }}
            />
            <div
              className="absolute bottom-[-25%] right-[-20%] w-[70%] h-[70%] animate-pulse"
              style={{
                animationDuration: '10s',
                background:
                  'radial-gradient(closest-side, rgba(79,70,229,0.10) 0%, rgba(79,70,229,0.09) 30%, rgba(79,70,229,0.055) 55%, rgba(79,70,229,0.02) 78%, transparent 100%)',
              }}
            />
            <div
              className="absolute top-[12%] right-[2%] w-[46%] h-[46%]"
              style={{
                background:
                  'radial-gradient(closest-side, rgba(147,51,234,0.05) 0%, rgba(147,51,234,0.045) 30%, rgba(147,51,234,0.028) 55%, rgba(147,51,234,0.01) 78%, transparent 100%)',
              }}
            />
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
