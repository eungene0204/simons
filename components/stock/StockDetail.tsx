"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeftIcon,
  ArrowUpIcon,
  ArrowDownIcon,
} from "@heroicons/react/24/outline";
import CandlestickChart, { OHLCV } from "@/components/stock/CandlestickChart";

interface StockDetail {
  symbol: string;
  name: string;
  logo?: string;
  currentPrice: number;
  changePercent: number;
  change: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  marketCap: number;
  previousClose: number;
  pe: number;
  pbr: number;
  description: string;
  sector: string;
  industry: string;
  timeSeries?: Array<{ date: string; value: number }>;
  candleData?: Array<{
    date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
}

type ChartPeriod = "day" | "week" | "month";

export default function StockDetail({ symbol }: { symbol: string }) {
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const fetchDetail = async () => {
    try {
      setLoading(true);
      const response = await fetch(`/api/stock/${symbol}/detail`);
      if (response.ok) {
        const data = await response.json();
        setDetail(data);
      }
    } catch (error) {
      console.error("Failed to fetch stock detail:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatVolume = (volume: number) => {
    return new Intl.NumberFormat("ko-KR").format(volume);
  };

  const formatMarketCap = (marketCap: number) => {
    if (marketCap >= 1000000000000) {
      return `${(marketCap / 1000000000000).toFixed(1)}조`;
    } else if (marketCap >= 100000000) {
      return `${(marketCap / 100000000).toFixed(1)}억`;
    }
    return formatPrice(marketCap);
  };

  if (loading) {
    return (
      <div className="bg-white dark:bg-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/4"></div>
          <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded"></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <div
                key={i}
                className="h-20 bg-gray-200 dark:bg-gray-700 rounded"
              ></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="bg-white dark:bg-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">
            종목 정보를 불러올 수 없습니다.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => router.back()}
          className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
        >
          <ArrowLeftIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
        </button>
        <div className="flex items-center gap-2 flex-1">
          {/* Company Logo Placeholder */}
          <div className="w-9 h-9 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center flex-shrink-0">
            {detail.logo ? (
              <img
                src={detail.logo}
                alt={detail.name}
                className="w-9 h-9 rounded-full object-cover"
              />
            ) : (
              <span className="text-sm font-semibold text-gray-600 dark:text-gray-400">
                {detail.name.charAt(0)}
              </span>
            )}
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold text-gray-900 dark:text-white">
              {detail.name}
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {detail.symbol} · {detail.sector} · {detail.industry}
            </p>
          </div>
        </div>
      </div>

      {/* Price Section */}
      <div className="mb-4 px-4 py-2 bg-gray-50 dark:bg-gray-900 rounded-lg">
        <div className="flex items-end gap-3 mb-3">
          <div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
              현재가
            </p>
            <p
              className={`text-2xl sm:text-3xl font-bold ${
                detail.changePercent >= 0
                  ? "text-red-600 dark:text-red-400"
                  : detail.changePercent < 0
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-gray-900 dark:text-white"
              }`}
            >
              {formatPrice(detail.currentPrice)}
            </p>
          </div>
          <div className="flex items-center gap-1.5 mb-1.5">
            {detail.changePercent > 0 ? (
              <ArrowUpIcon className="w-4 h-4 text-red-600 dark:text-red-400" />
            ) : detail.changePercent < 0 ? (
              <ArrowDownIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            ) : null}
            <span
              className={`text-base font-semibold ${
                detail.changePercent > 0
                  ? "text-red-600 dark:text-red-400"
                  : detail.changePercent < 0
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-gray-900 dark:text-white"
              }`}
            >
              {detail.changePercent >= 0 ? "+" : ""}
              {detail.changePercent.toFixed(2)}%
            </span>
            <span
              className={`text-base font-semibold ${
                detail.change >= 0
                  ? "text-red-600 dark:text-red-400"
                  : detail.change < 0
                  ? "text-blue-500 dark:text-blue-400"
                  : "text-gray-900 dark:text-white"
              }`}
            >
              ({detail.change >= 0 ? "+" : ""}
              {formatPrice(detail.change)})
            </span>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4">
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            전일종가
          </p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatPrice(detail.previousClose)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            시가
          </p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatPrice(detail.open)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            고가
          </p>
          <p className="text-sm font-semibold text-red-600 dark:text-red-400">
            {formatPrice(detail.high)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            저가
          </p>
          <p className="text-sm font-semibold text-blue-500 dark:text-blue-400">
            {formatPrice(detail.low)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            거래량(주)
          </p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatVolume(detail.volume)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">
            시가총액
          </p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatMarketCap(detail.marketCap)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">PER</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {detail.pe.toFixed(2)}
          </p>
        </div>
        <div className="p-2.5 bg-gray-50 dark:bg-gray-900 rounded-lg">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">PBR</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {detail.pbr.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Chart Section */}
      {detail.candleData && detail.candleData.length > 0 && (
        <div className="mt-4 p-3 bg-gray-900 rounded-lg">
          <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
            <h2 className="text-base font-semibold text-white">주가 차트</h2>
          </div>
          <div className="h-80 sm:h-96">
            <CandlestickChart
              data={detail.candleData.map((candle) => ({
                time: candle.date,
                open: candle.open,
                high: candle.high,
                low: candle.low,
                close: candle.close,
                volume: candle.volume,
              }))}
            />
          </div>
        </div>
      )}

      {/* Bottom Spacing */}
      <div className="h-16"></div>
    </div>
  );
}
