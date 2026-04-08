"use client";

interface TradeExecution {
  price: number;
  quantity: number;
  type: "buy" | "sell";
  timestamp: Date;
}

interface TradeListProps {
  tradeStrength: number | null;
  recentTrades: TradeExecution[];
  formatPrice: (price: number) => string;
  formatQuantity: (quantity: number) => string;
}

export default function TradeList({
  tradeStrength,
  recentTrades,
  formatPrice,
  formatQuantity,
}: TradeListProps) {
  return (
    <div className="flex flex-col">
      <div className="px-3 pt-0 pb-2">
        <div className="text-sm text-gray-700 dark:text-gray-300">
          체결강도: <span className={`tabular-nums ${tradeStrength !== null && tradeStrength >= 100 ? "text-red-400" : "text-blue-400"}`}>
            {tradeStrength !== null ? `${tradeStrength.toFixed(2)}%` : "-"}
          </span>
        </div>
      </div>
      <div>
        {recentTrades.map((trade, index) => (
          <div
            key={`trade-${index}`}
            className="h-[18px] flex items-center px-3 text-sm tracking-tighter animate-slide-up"
          >
            <div className="flex items-center justify-between gap-2 w-full">
              <span className="tabular-nums text-white">
                {formatPrice(trade.price)}
              </span>
              <span
                className={`tabular-nums ${
                  trade.type === "buy"
                    ? "text-[var(--main-red)]"
                    : "text-[var(--main-blue)]"
                }`}
              >
                {formatQuantity(trade.quantity)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
