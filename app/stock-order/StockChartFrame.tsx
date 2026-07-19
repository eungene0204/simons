import type { ReactNode } from "react";

export default function StockChartFrame({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex h-[420px] flex-col overflow-hidden sm:h-[480px] lg:h-[560px] ${className}`}
      data-testid="stock-chart-frame"
    >
      {children}
    </div>
  );
}
