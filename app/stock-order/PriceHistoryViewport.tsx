import type { ReactNode } from "react";

export default function PriceHistoryViewport({ children }: { children: ReactNode }) {
  return (
    <div
      className="min-h-0 flex-1 overflow-x-auto lg:overflow-x-hidden"
      data-testid="price-history-scroll"
    >
      <div
        className="flex h-full min-w-[696px] flex-col lg:min-w-0"
        data-testid="price-history-table"
      >
        {children}
      </div>
    </div>
  );
}
