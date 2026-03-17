"use client";

import { useEffect, useState } from "react";
import { CaretUp, CaretDown } from "phosphor-react";
import type { MarketSnapshotItem } from "@/types/dashboard";

interface IndicesData {
  kospi?: { name: string; value: number; change: number; changePercent: number };
  kosdaq?: { name: string; value: number; change: number; changePercent: number };
  nasdaq?: { name: string; value: number; change: number; changePercent: number };
  sp500?: { name: string; value: number; change: number; changePercent: number };
  vix?: { name: string; value: number; change: number; changePercent: number };
  exchangeRate?: { name: string; value: number; change: number; changePercent: number };
}

const SNAPSHOT_KEYS: { key: keyof IndicesData; symbol: string; label: string }[] = [
  { key: "kospi", symbol: "KOSPI", label: "코스피" },
  { key: "kosdaq", symbol: "KOSDAQ", label: "코스닥" },
  { key: "nasdaq", symbol: "NASDAQ", label: "나스닥" },
  { key: "sp500", symbol: "S&P500", label: "S&P 500" },
  { key: "exchangeRate", symbol: "USD/KRW", label: "원/달러" },
  { key: "vix", symbol: "VIX", label: "VIX" },
];

function formatValue(value: number, symbol: string): string {
  if (symbol === "USD/KRW") return value.toFixed(1);
  if (symbol === "VIX") return value.toFixed(2);
  return value.toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}

export default function MarketSnapshot() {
  const [items, setItems] = useState<MarketSnapshotItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const res = await fetch("/api/market/indices");
      if (!res.ok) return;
      const data: IndicesData = await res.json();
      const parsed: MarketSnapshotItem[] = SNAPSHOT_KEYS.map(({ key, symbol, label }) => {
        const idx = data[key];
        return {
          symbol,
          name: label,
          value: idx?.value ?? 0,
          change: idx?.change ?? 0,
          changePercent: idx?.changePercent ?? 0,
        };
      });
      setItems(parsed);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const id = setInterval(fetchData, 60000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            시장 지표
          </h2>
          <span className="flex items-center gap-1 text-[10px] text-green-400 font-bold">
            <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
            LIVE
          </span>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="glass-card p-3 animate-pulse">
              <div className="h-2 bg-white/5 rounded w-2/3 mb-3" />
              <div className="h-5 bg-white/5 rounded w-3/4 mb-2" />
              <div className="h-3 bg-white/5 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {items.map((item) => {
            const isPos = item.changePercent >= 0;
            const colorClass = isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]";
            return (
              <div key={item.symbol} className="glass-card p-3">
                <p className="text-[10px] uppercase tracking-widest text-gray-400 font-bold mb-1">
                  {item.name}
                </p>
                <p className="text-lg font-black text-white tabular-nums font-outfit leading-tight">
                  {formatValue(item.value, item.symbol)}
                </p>
                <div className={`flex items-center gap-0.5 mt-1 ${colorClass}`}>
                  {isPos ? <CaretUp size={10} weight="fill" /> : <CaretDown size={10} weight="fill" />}
                  <span className="text-xs font-bold">
                    {Math.abs(item.changePercent).toFixed(2)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
