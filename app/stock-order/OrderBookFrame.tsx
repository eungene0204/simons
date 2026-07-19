import type { ReactNode } from "react";

export default function OrderBookFrame({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`h-[420px] overflow-hidden sm:h-[480px] lg:h-[560px] ${className}`}
      data-testid="order-book-frame"
    >
      {children}
    </div>
  );
}
