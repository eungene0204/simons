"use client";

import { useEffect, useState } from "react";
import { CaretUp, CaretDown, Star } from "phosphor-react";
import type { WatchlistSnapshotItem } from "@/app/api/dashboard/watchlist-snapshot/route";
import { t } from "@/lib/i18n";

function formatPrice(v: number): string {
  if (v === 0) return "--";
  return v.toLocaleString("ko-KR");
}

export default function WatchlistSnapshot() {
  const [items, setItems] = useState<WatchlistSnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch("/api/dashboard/watchlist-snapshot");
      if (!res.ok) return;
      const data: WatchlistSnapshotItem[] = await res.json();
      setItems(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => clearInterval(id);
  }, []);

  if (!loading && items.length === 0) return null;

  return (
    <div>
      <div
        className="mb-4 flex items-center justify-between px-3 pt-4 sm:px-4 lg:px-5"
        data-testid="watchlist-snapshot-header"
      >
        <div className="flex items-center gap-2">
          <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
            {t("관심 종목")}
          </h2>
        </div>
      </div>

      {loading ? (
        <div
          className="grid grid-cols-2 border-l border-t border-white/[0.08] sm:grid-cols-3 lg:grid-cols-6"
          data-testid="watchlist-snapshot-grid"
        >
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="animate-pulse border-b border-r border-white/[0.08] p-2 sm:p-3"
            >
              <div className="h-2 bg-white/5 rounded w-2/3 mb-3" />
              <div className="h-5 bg-white/5 rounded w-3/4 mb-2" />
              <div className="h-3 bg-white/5 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : (
        <div
          className="grid grid-cols-2 border-l border-t border-white/[0.08] sm:grid-cols-3 lg:grid-cols-6"
          data-testid="watchlist-snapshot-grid"
        >
          {items.map((item) => {
            const isPos = item.changePercent >= 0;
            const hasData = item.price > 0;
            const colorClass = hasData
              ? isPos
                ? "text-[var(--main-red)]"
                : "text-[var(--main-blue)]"
              : "text-gray-600";

            return (
              <div
                key={item.symbol}
                className="border-b border-r border-white/[0.08] p-2 sm:p-3"
                data-testid="watchlist-snapshot-cell"
              >
                <div className="flex items-start justify-between mb-1">
                  <p className="text-[10px] uppercase tracking-widest text-gray-400 font-bold leading-tight truncate pr-1">
                    {item.name}
                  </p>
                  <Star size={11} className="text-yellow-500/60 flex-shrink-0 mt-0.5" weight="fill" />
                </div>
                <p className="text-base font-black text-white tabular-nums font-outfit leading-tight">
                  {formatPrice(item.price)}
                </p>
                {hasData ? (
                  <div className={`flex items-center gap-0.5 mt-1 ${colorClass}`}>
                    {isPos ? <CaretUp size={10} weight="fill" /> : <CaretDown size={10} weight="fill" />}
                    <span className="text-xs font-bold">
                      {Math.abs(item.changePercent).toFixed(2)}%
                    </span>
                  </div>
                ) : (
                  <p className="text-[10px] text-gray-600 mt-1">{item.symbol}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
