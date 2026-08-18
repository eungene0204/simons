"use client";

import { StockListItem } from "@/types/stock";
import { useStockPrices } from "@/lib/hooks/useStockPrices";
import { t } from "@/lib/i18n";

interface StockListCardProps {
  stock: StockListItem;
  onClick: (symbol: string, name: string) => void;
}

export default function StockListCard({ stock, onClick }: StockListCardProps) {
  const { data } = useStockPrices([stock.symbol], {
    enabled: !!stock.symbol,
    refetchInterval: 3000,
  });
  const quote = data?.[stock.symbol];
  const currentPrice = quote?.price ?? 0;
  const previousClose = quote?.previousClose ?? currentPrice;
  const change = currentPrice - previousClose;
  const changePercent = quote?.changePercent ?? 0;
  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  return (
    <button
      onClick={() => onClick(stock.symbol, stock.name)}
      className="w-full p-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-500 dark:hover:border-blue-500 hover:shadow-md transition-all text-left"
    >
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {stock.name}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {stock.symbol} · {stock.market}
            {stock.sector && ` · ${stock.sector}`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {currentPrice > 0 ? t("{0} 원", formatPrice(currentPrice)) : "-"}
          </p>
          <p
            className={`text-xs font-medium ${
              change >= 0
                ? "text-red-600 dark:text-red-400"
                : "text-blue-600 dark:text-blue-400"
            }`}
          >
            {currentPrice > 0 ? (
              <>
                {change >= 0 ? "+" : ""}
                {formatPrice(change)} ({changePercent >= 0 ? "+" : ""}
                {changePercent.toFixed(2)}%)
              </>
            ) : (
              "-"
            )}
          </p>
        </div>
      </div>
    </button>
  );
}
