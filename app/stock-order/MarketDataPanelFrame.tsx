import type { ReactNode } from "react";

export default function MarketDataPanelFrame({ children }: { children: ReactNode }) {
  return (
    <div
      className="flex h-[420px] flex-col overflow-hidden sm:h-[480px] lg:h-[560px]"
      data-testid="market-data-panel-frame"
    >
      {children}
    </div>
  );
}
