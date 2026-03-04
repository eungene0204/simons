"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { MarketIndex } from "@/types/market";
import { CaretUp, CaretDown, CaretLeft, CaretRight } from "phosphor-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";

interface MarketIndicesData {
  kospi: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  kosdaq: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  nasdaq?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  dow?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  sp500?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  vix?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  nikkei?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  topix?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  shanghai?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  shenzhen?: MarketIndex & { timeSeries?: Array<{ date: string; value: number }> };
  exchangeRate?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  goldPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  oilPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  silverPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  naturalGasPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  copperPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
  wheatPrice?: MarketIndex & {
    timeSeries?: Array<{ date: string; value: number }>;
  };
}

export default function MarketIndices() {
  const [indices, setIndices] = useState<MarketIndicesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  const [isMouseOverSlider, setIsMouseOverSlider] = useState(false);
  const [canScrollLeftCommodities, setCanScrollLeftCommodities] = useState(false);
  const [canScrollRightCommodities, setCanScrollRightCommodities] = useState(false);
  const [isMouseOverCommoditiesSlider, setIsMouseOverCommoditiesSlider] = useState(false);

  const fetchIndices = async () => {
    try {
      const response = await fetch("/api/market/indices");
      if (response.ok) {
        const data = await response.json();
        setIndices(data);
      }
    } catch (error) {
      console.error("Failed to fetch indices:", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIndices();

    // Refresh every minute
    const interval = setInterval(fetchIndices, 60000);

    return () => clearInterval(interval);
  }, []);

  // Check scroll position when indices change (only for initial check and resize)
  useEffect(() => {
    if (!indices) return;
    
    const indicesContainer = document.getElementById('indices-slider');
    const commoditiesContainer = document.getElementById('commodities-slider');
    
    const checkIndicesScroll = () => {
      if (indicesContainer) {
        const scrollLeft = indicesContainer.scrollLeft;
        const scrollWidth = indicesContainer.scrollWidth;
        const clientWidth = indicesContainer.clientWidth;
        
        setCanScrollLeft(scrollLeft > 0);
        setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
      }
    };
    
    const checkCommoditiesScroll = () => {
      if (commoditiesContainer) {
        const scrollLeft = commoditiesContainer.scrollLeft;
        const scrollWidth = commoditiesContainer.scrollWidth;
        const clientWidth = commoditiesContainer.clientWidth;
        
        setCanScrollLeftCommodities(scrollLeft > 0);
        setCanScrollRightCommodities(scrollLeft < scrollWidth - clientWidth - 10);
      }
    };
    
    const checkAllScroll = () => {
      checkIndicesScroll();
      checkCommoditiesScroll();
    };
    
    // Initial check after render
    setTimeout(checkAllScroll, 100);
    
    // Only listen to resize, not scroll (onScroll handler will handle scroll events)
    window.addEventListener('resize', checkAllScroll);
    
    return () => {
      window.removeEventListener('resize', checkAllScroll);
    };
  }, [indices]);


  const IndexCard = ({
    index,
    showVolume = true,
  }: {
    index: MarketIndex & {
      timeSeries?: Array<{ date: string; value: number }>;
    };
    showVolume?: boolean;
  }) => {
    const isPositive = index.change >= 0;
    const colorClass = isPositive
      ? "text-[var(--main-red)]"
      : "text-[var(--main-blue)]";
    const chartColor = isPositive ? "rgb(239, 68, 68)" : "rgb(55, 122, 244)";

    // Format date for chart display
    const chartData =
      index.timeSeries?.map((item) => ({
        date: new Date(item.date).toLocaleDateString("ko-KR", {
          month: "short",
          day: "numeric",
        }),
        value: item.value,
      })) || [];

    const CardContent = (
      <div className="glass-card p-4 h-full flex flex-col group hover:scale-[1.02] transition-transform duration-300">
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-xs font-black text-gray-100 uppercase tracking-wider font-outfit">
            {index.name}
          </h4>
          <span className="text-[10px] text-gray-500 font-bold tabular-nums">
            {index.symbol}
          </span>
        </div>
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-2xl font-black text-white tabular-nums font-outfit tracking-tighter">
            {index.value.toLocaleString("ko-KR", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </span>
          {isPositive ? (
            <CaretUp weight="fill" className="w-4 h-4 text-[var(--main-red)] animate-pulse" />
          ) : (
            <CaretDown weight="fill" className="w-4 h-4 text-[var(--main-blue)] animate-pulse" />
          )}
        </div>
        <div className="flex items-center gap-2 mb-3">
          <span className={`text-xs font-bold ${colorClass}`}>
            {isPositive ? "+" : ""}
            {index.change.toFixed(2)}
          </span>
          <span className={`text-xs font-bold ${colorClass} bg-white/5 px-1.5 py-0.5 rounded`}>
            {isPositive ? "+" : ""}
            {index.changePercent.toFixed(2)}%
          </span>
        </div>

        {/* Time Series Chart */}
        {chartData.length > 0 && (
          <div className="mt-auto h-16 sm:h-20 w-full overflow-hidden">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <defs>
                  <linearGradient id={`gradient-${index.symbol}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={chartColor} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={chartColor} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke={chartColor}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, strokeWidth: 0 }}
                />
                <YAxis hide domain={["auto", "auto"]} />
                <XAxis hide dataKey="date" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="mt-3 pt-3 border-t border-white/5 grid grid-cols-2 gap-2 text-[10px] text-gray-400 font-medium">
          {showVolume && (
            <div className="flex justify-between">
              <span>Vol</span>
              <span className="text-gray-200">
                {(index.volume / 1000000).toFixed(1)}M
              </span>
            </div>
          )}
          <div className="flex justify-between">
            <span>High</span>
            <span className="text-gray-200">{index.high.toLocaleString()}</span>
          </div>
          <div className="flex justify-between">
            <span>Low</span>
            <span className="text-gray-200">{index.low.toLocaleString()}</span>
          </div>
          <div className="flex justify-between">
            <span>Open</span>
            <span className="text-gray-200">{index.open.toLocaleString()}</span>
          </div>
        </div>
      </div>
    );

    // Wrap with Link if it's KOSPI
    if (index.symbol === "KOSPI") {
      return (
        <Link href="/kospi" className="block h-full">
          {CardContent}
        </Link>
      );
    }

    return CardContent;
  };

  if (loading) {
    return (
      <div className="space-y-4 sm:space-y-6 w-full max-w-full">
        <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
          <div className="animate-pulse space-y-4">
            <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-1/4"></div>
            <div className="flex gap-3 overflow-x-auto">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex-shrink-0 w-[187px] sm:w-[213px]">
                  <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded"></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!indices) {
    return (
      <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
        <p className="text-gray-500 dark:text-gray-400">
          지수 데이터를 불러올 수 없습니다.
        </p>
      </div>
    );
  }

  // Collect all main indices for slider
  const mainIndices = [
    indices.kospi,
    indices.kosdaq,
    indices.nasdaq,
    indices.dow,
    indices.sp500,
    indices.vix,
    indices.nikkei,
    indices.topix,
    indices.shanghai,
    indices.shenzhen,
  ].filter(Boolean) as Array<MarketIndex & { timeSeries?: Array<{ date: string; value: number }> }>;

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const scrollLeft = target.scrollLeft;
    const scrollWidth = target.scrollWidth;
    const clientWidth = target.clientWidth;
    
    setScrollPosition(scrollLeft);
    setCanScrollLeft(scrollLeft > 0);
    setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 10);
    
    // Don't stop propagation - scroll events don't bubble anyway
  };

  const handleCommoditiesScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    const scrollLeft = target.scrollLeft;
    const scrollWidth = target.scrollWidth;
    const clientWidth = target.clientWidth;
    
    setCanScrollLeftCommodities(scrollLeft > 0);
    setCanScrollRightCommodities(scrollLeft < scrollWidth - clientWidth - 10);
  };

  const scrollCommoditiesLeft = () => {
    const container = document.getElementById('commodities-slider');
    if (container) {
      container.scrollBy({ left: -213, behavior: 'smooth' });
    }
  };

  const scrollCommoditiesRight = () => {
    const container = document.getElementById('commodities-slider');
    if (container) {
      container.scrollBy({ left: 213, behavior: 'smooth' });
    }
  };

  const scrollLeft = () => {
    const container = document.getElementById('indices-slider');
    if (container) {
      container.scrollBy({ left: -213, behavior: 'smooth' });
    }
  };

  const scrollRight = () => {
    const container = document.getElementById('indices-slider');
    if (container) {
      container.scrollBy({ left: 213, behavior: 'smooth' });
    }
  };

  return (
    <div className="space-y-3 sm:space-y-4 w-full max-w-full min-w-0">
      {/* Main Indices Section - Vertical List for Sidebar */}
      <div className="glass-card p-5 w-full">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-black text-white uppercase tracking-widest font-outfit">
            주요 지수
          </h3>
          <div className="flex items-center gap-2">
             <div className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
             <span className="text-[10px] text-gray-500 font-bold uppercase">Live</span>
          </div>
        </div>

        <div className="space-y-3">
          {mainIndices.map((index) => (
            <IndexCard key={index.symbol} index={index} />
          ))}
        </div>
      </div>

      {/* Exchange Rate and Commodities - Compact 2-Column Grid */}
      <div className="glass-card p-5 w-full">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-sm font-black text-white uppercase tracking-widest font-outfit">
            환율 및 원자재
          </h3>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-1 xl:grid-cols-2 gap-3">
          {[
            indices.exchangeRate,
            indices.goldPrice,
            indices.oilPrice,
            indices.silverPrice,
            indices.naturalGasPrice
          ].filter(Boolean).map((item) => (
            <IndexCard key={item!.symbol} index={item!} />
          ))}
        </div>
      </div>

      {/* Exchange Rate and Commodities Section */}
      {(indices.exchangeRate || indices.goldPrice || indices.oilPrice || indices.silverPrice || indices.naturalGasPrice || indices.copperPrice || indices.wheatPrice) && (
        <div className="bg-[#1a1a1a] border-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden min-w-0">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm sm:text-base font-semibold text-white">
              환율 및 원자재
            </h3>
            <button
              onClick={fetchIndices}
              className="text-[10px] sm:text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
            >
              새로고침
            </button>
          </div>

          {/* Commodities Slider Container */}
          <div 
            className="relative overflow-hidden" 
            onMouseEnter={() => setIsMouseOverCommoditiesSlider(true)}
            onMouseLeave={() => setIsMouseOverCommoditiesSlider(false)}
          >
            {/* Commodities Slider */}
            <div
              id="commodities-slider"
              onScroll={handleCommoditiesScroll}
              className="flex gap-2 overflow-x-auto overflow-y-hidden scrollbar-hide"
              style={{ 
                scrollbarWidth: 'none',
                msOverflowStyle: 'none',
                WebkitOverflowScrolling: 'touch',
                touchAction: 'pan-x',
                overscrollBehaviorX: 'contain',
                overscrollBehaviorY: 'auto',
                scrollBehavior: 'auto'
              }}
              onWheel={(e) => {
                if (!isMouseOverCommoditiesSlider) {
                  return;
                }
                
                const container = e.currentTarget;
                const canScroll = container.scrollWidth > container.clientWidth;
                
                if (canScroll) {
                  if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    container.scrollBy({
                      left: e.deltaX,
                      behavior: 'auto'
                    });
                  }
                }
              }}
            >
              {indices.exchangeRate && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.exchangeRate} showVolume={false} />
                </div>
              )}
              {indices.goldPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.goldPrice} showVolume={false} />
                </div>
              )}
              {indices.oilPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.oilPrice} showVolume={false} />
                </div>
              )}
              {indices.silverPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.silverPrice} showVolume={false} />
                </div>
              )}
              {indices.naturalGasPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.naturalGasPrice} showVolume={false} />
                </div>
              )}
              {indices.copperPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.copperPrice} showVolume={false} />
                </div>
              )}
              {indices.wheatPrice && (
                <div className="flex-shrink-0" style={{ minWidth: '187px', maxWidth: '187px' }}>
                  <IndexCard index={indices.wheatPrice} showVolume={false} />
                </div>
              )}
            </div>

            {/* Left Scroll Button */}
            {canScrollLeftCommodities && (
              <button
                onClick={scrollCommoditiesLeft}
                className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-[#1a1a1a] border-gray-800 border border-gray-800 rounded-full p-2 shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
                aria-label="왼쪽으로 스크롤"
              >
                <CaretLeft size={20} className="text-gray-600 dark:text-gray-400" />
              </button>
            )}

            {/* Right Scroll Button */}
            {canScrollRightCommodities && (
              <button
                onClick={scrollCommoditiesRight}
                className="absolute right-0 top-1/2 -translate-y-1/2 z-10 bg-[#1a1a1a] border-gray-800 border border-gray-800 rounded-full p-2 shadow-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-all"
                aria-label="오른쪽으로 스크롤"
              >
                <CaretRight size={20} className="text-gray-600 dark:text-gray-400" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
