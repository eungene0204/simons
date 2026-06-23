"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CaretUp,
  CaretDown,
  Info,
} from "phosphor-react";
import CandlestickChart from "@/components/stock/CandlestickChart";
import { formatMarketCap } from "@/lib/format-market-cap";
import NewsImpactPanel from "@/components/stock/NewsImpactPanel";
import {
  fetchStockNews,
  recordStockNewsPriorityEvent,
  STOCK_NEWS_LIMIT,
  stockNewsQueryKey,
} from "@/lib/hooks/useStockNews";

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

type TabId = "chart" | "news";
const NEWS_TAB_ENABLED = process.env.NEXT_PUBLIC_NEWS_TAB_ENABLED === "true";

export default function StockDetail({ symbol }: { symbol: string }) {
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>("chart");
  const router = useRouter();
  const queryClient = useQueryClient();
  const recordedPrioritySymbols = useRef(new Set<string>());

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

  const fetchPrice = async () => {
    try {
      const response = await fetch(`/api/stock/${symbol}/price`);
      if (!response.ok) return;
      const data = await response.json();
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              currentPrice: data.price,
              change: data.change,
              changePercent: data.changePercent,
              open: data.open ?? prev.open,
              high: data.high ?? prev.high,
              low: data.low ?? prev.low,
              volume: data.volume ?? prev.volume,
            }
          : prev
      );
    } catch {
      // 폴링 실패는 무시
    }
  };

  useEffect(() => {
    fetchDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  useEffect(() => {
    if (!NEWS_TAB_ENABLED) return;

    if (!recordedPrioritySymbols.current.has(symbol)) {
      recordedPrioritySymbols.current.add(symbol);
      void recordStockNewsPriorityEvent(symbol, "current_view", {
        surface: "stock_detail",
      }).catch(() => {
        // Priority events are best-effort; never block stock detail rendering.
      });
    }

    void queryClient.prefetchQuery({
      queryKey: stockNewsQueryKey(symbol),
      queryFn: () => fetchStockNews(symbol, STOCK_NEWS_LIMIT),
      staleTime: 60_000,
    });
  }, [queryClient, symbol]);

  useEffect(() => {
    const id = setInterval(fetchPrice, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(price);
  };

  const formatVolume = (volume: number) => {
    return new Intl.NumberFormat("ko-KR").format(volume);
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
    <div className="bg-white dark:bg-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border-t border-x border-gray-200 dark:border-gray-700">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={() => router.back()}
          className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
        >
          <ArrowLeft size={16} className="text-gray-600 dark:text-gray-400" />
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
              <CaretUp size={16} weight="fill" className="text-red-600 dark:text-red-400" />
            ) : detail.changePercent < 0 ? (
              <CaretDown size={16} weight="fill" className="text-blue-600 dark:text-blue-400" />
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
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
        {[
          { label: "전일종가", sub: "Prev Close", value: formatPrice(detail.previousClose), color: "white" },
          { label: "시가", sub: "Open", value: formatPrice(detail.open), color: "white" },
          { label: "고가", sub: "High", value: formatPrice(detail.high), color: "red" },
          { label: "저가", sub: "Low", value: formatPrice(detail.low), color: "blue" },
          { label: "거래량", sub: "Volume", value: formatVolume(detail.volume), color: "white" },
          { label: "시가총액", sub: "Mkt Cap", value: formatMarketCap(detail.marketCap), color: "white" },
          { label: "PER", sub: "P/E Ratio", value: detail.pe ? detail.pe.toFixed(2) : "—", color: "white" },
          { label: "PBR", sub: "P/B Ratio", value: detail.pbr ? detail.pbr.toFixed(2) : "—", color: "white" },
        ].map(({ label, sub, value, color }) => (
          <div key={label} className="relative p-3 bg-gray-900 rounded-lg flex flex-col justify-between min-h-[72px]">
            <div className="flex items-start justify-between mb-1">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">{label}</p>
                <p className="text-[9px] text-gray-600 uppercase tracking-wider">{sub}</p>
              </div>
              <Info size={12} className="text-gray-600 mt-0.5 flex-shrink-0" />
            </div>
            <p className={`text-lg font-black tabular-nums font-outfit leading-none ${
              color === "red" ? "text-red-400" :
              color === "blue" ? "text-blue-400" :
              "text-white"
            }`}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {/* Tab Bar */}
      <div className="flex border-b border-white/[0.05] mt-4">
        <button
          type="button"
          onClick={() => setActiveTab("chart")}
          className={`px-4 py-2.5 text-xs font-bold uppercase tracking-widest border-b-2 -mb-px transition-colors ${
            activeTab === "chart"
              ? "border-white/60 text-white"
              : "border-transparent text-gray-500 hover:text-gray-300"
          }`}
        >
          차트
        </button>
        {NEWS_TAB_ENABLED && (
          <button
            type="button"
            onClick={() => setActiveTab("news")}
            className={`px-4 py-2.5 text-xs font-bold uppercase tracking-widest border-b-2 -mb-px transition-colors ${
              activeTab === "news"
                ? "border-white/60 text-white"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            뉴스
          </button>
        )}
      </div>

      {/* Chart Tab — always mounted, hidden when not active */}
      <div className={activeTab === "chart" ? "block" : "hidden"}>
        {detail.candleData && detail.candleData.length > 0 && (
          <div className="mt-4 p-3 bg-gray-900 rounded-lg">
            <h2 className="text-base font-semibold text-white mb-2">주가 차트</h2>
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
      </div>

      {NEWS_TAB_ENABLED && (
        <div className={activeTab === "news" ? "block" : "hidden"}>
          <NewsImpactPanel symbol={symbol} />
        </div>
      )}

    </div>
  );
}
