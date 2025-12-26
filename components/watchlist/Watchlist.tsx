"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpIcon,
  ArrowDownIcon,
  StarIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import { StarIcon as StarIconSolid } from "@heroicons/react/24/solid";
import StockSearchModal from "@/components/stock/StockSearchModal";
import { getWatchlistSymbols, addMultipleToWatchlist, removeFromWatchlist } from "@/lib/watchlist";

interface WatchlistItem {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  volume: number;
}

export default function Watchlist() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const router = useRouter();

  const fetchWatchlist = async (isInitial = false) => {
    try {
      if (isInitial) {
        setLoading(true);
      }
      
      // Get symbols from localStorage
      const watchlistSymbols = getWatchlistSymbols();
      const symbols = watchlistSymbols.map((item) => item.symbol);
      
      // If no symbols in localStorage, use empty array (will show default mock data)
      const symbolsParam = symbols.length > 0 ? JSON.stringify(symbols) : null;
      const url = symbolsParam 
        ? `/api/watchlist?symbols=${encodeURIComponent(symbolsParam)}`
        : "/api/watchlist";
      
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setItems(data.items || []);
      }
    } catch (error) {
      console.error("Failed to fetch watchlist:", error);
    } finally {
      if (isInitial) {
        setLoading(false);
      }
    }
  };

  const handleAddToWatchlist = (items: Array<{ symbol: string; name: string }>) => {
    const addedCount = addMultipleToWatchlist(items);
    if (addedCount > 0) {
      fetchWatchlist(false);
      setIsSearchOpen(false);
    }
  };

  const handleRemoveFromWatchlist = (symbol: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent row click
    if (removeFromWatchlist(symbol)) {
      fetchWatchlist(false);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchWatchlist(true);

    // Set up real-time updates every 3 seconds
    const interval = setInterval(() => {
      fetchWatchlist(false);
    }, 3000);

    // Cleanup interval on unmount
    return () => clearInterval(interval);
  }, []);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatVolume = (volume: number) => {
    return new Intl.NumberFormat("ko-KR").format(volume);
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="animate-pulse space-y-3">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/4"></div>
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="h-12 bg-gray-200 dark:bg-gray-700 rounded"
              ></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="bg-white dark:bg-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <StarIconSolid className="w-5 h-5 text-yellow-500" />
            <h1 className="text-lg sm:text-xl font-bold text-gray-900 dark:text-white">
              관심종목
            </h1>
          </div>
          <button
            onClick={() => setIsSearchOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-600 transition-colors text-sm font-semibold"
          >
            <MagnifyingGlassIcon className="w-4 h-4" />
            종목 검색
          </button>
        </div>

      {/* Watchlist Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 px-2 text-xs font-semibold text-gray-600 dark:text-gray-400">
                종목
              </th>
              <th className="text-right py-2 px-2 text-xs font-semibold text-gray-600 dark:text-gray-400">
                현재가
              </th>
              <th className="text-right py-2 px-2 text-xs font-semibold text-gray-600 dark:text-gray-400">
                등락률
              </th>
              <th className="text-right py-2 px-2 text-xs font-semibold text-gray-600 dark:text-gray-400">
                등락액
              </th>
              <th className="text-right py-2 px-2 text-xs font-semibold text-gray-600 dark:text-gray-400">
                거래량(주)
              </th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="text-center py-8 text-sm text-gray-500 dark:text-gray-400"
                >
                  관심종목이 없습니다.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.symbol}
                  onClick={() => router.push(`/stock/${item.symbol}`)}
                  className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors cursor-pointer"
                >
                  {/* 종목 (로고 + 이름) */}
                  <td className="py-2.5 px-2">
                    <div className="flex items-center gap-2">
                      {/* Company Logo Placeholder */}
                      <div className="w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
                        {item.logo ? (
                          <img
                            src={item.logo}
                            alt={item.name}
                            className="w-8 h-8 rounded-full object-cover"
                          />
                        ) : (
                          <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                            {item.name.charAt(0)}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">
                          {item.name}
                        </span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {item.symbol}
                        </span>
                      </div>
                      <button
                        onClick={(e) => handleRemoveFromWatchlist(item.symbol, e)}
                        className="ml-auto p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
                        title="관심종목에서 제거"
                      >
                        <XMarkIcon className="w-4 h-4 text-gray-500 dark:text-gray-400" />
                      </button>
                    </div>
                  </td>

                  {/* 현재가 */}
                  <td className="text-right py-2.5 px-2">
                    <span
                      className={`text-sm font-semibold ${
                        item.changePercent >= 0
                          ? "text-red-600 dark:text-red-400"
                          : item.changePercent < 0
                          ? "text-blue-500 dark:text-blue-400"
                          : "text-gray-900 dark:text-white"
                      }`}
                    >
                      {formatPrice(item.currentPrice)}
                    </span>
                  </td>

                  {/* 등락률 */}
                  <td className="text-right py-2.5 px-2">
                    <div className="flex items-center justify-end gap-0.5">
                      {item.changePercent > 0 ? (
                        <ArrowUpIcon className="w-3 h-3 text-red-600 dark:text-red-400" />
                      ) : item.changePercent < 0 ? (
                        <ArrowDownIcon className="w-3 h-3 text-blue-500 dark:text-blue-400" />
                      ) : null}
                      <span
                        className={`text-sm font-semibold ${
                          item.changePercent > 0
                            ? "text-red-600 dark:text-red-400"
                            : item.changePercent < 0
                            ? "text-blue-500 dark:text-blue-400"
                            : "text-gray-900 dark:text-white"
                        }`}
                      >
                        {item.changePercent >= 0 ? "+" : ""}
                        {item.changePercent.toFixed(2)}%
                      </span>
                    </div>
                  </td>

                  {/* 등락액 */}
                  <td className="text-right py-2.5 px-2">
                    <span
                      className={`text-sm font-semibold ${
                        item.change >= 0
                          ? "text-red-600 dark:text-red-400"
                          : item.change < 0
                          ? "text-blue-500 dark:text-blue-400"
                          : "text-gray-900 dark:text-white"
                      }`}
                    >
                      {item.change >= 0 ? "+" : ""}
                      {formatPrice(item.change)}
                    </span>
                  </td>

                  {/* 거래량 */}
                  <td className="text-right py-2.5 px-2">
                    <span className="text-xs text-gray-600 dark:text-gray-400">
                      {formatVolume(item.volume)}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      </div>

      {/* Stock Search Modal */}
      <StockSearchModal
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelect={handleAddToWatchlist}
      />
    </>
  );
}
