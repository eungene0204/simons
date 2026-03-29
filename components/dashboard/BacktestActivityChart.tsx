"use client";

import { useEffect, useState } from "react";
import type { DashboardBacktestRecord } from "@/types/dashboard";

interface DayBar {
  date: string;      // "MM/DD"
  count: number;
}

function buildLast7Days(records: DashboardBacktestRecord[]): DayBar[] {
  const days: DayBar[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const label = `${d.getMonth() + 1}/${d.getDate()}`;
    const start = d.getTime();
    const end = start + 86_400_000;
    const count = records.filter((r) => r.timestamp >= start && r.timestamp < end).length;
    days.push({ date: label, count });
  }
  return days;
}

export default function BacktestActivityChart() {
  const [bars, setBars] = useState<DayBar[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  useEffect(() => {
    // TODO: MOCK DATA - 테스트용, 나중에 제거
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const mockCounts = [1, 4, 2, 0, 3, 8, 6];
    const mockBars: DayBar[] = mockCounts.map((count, i) => {
      const d = new Date(today);
      d.setDate(today.getDate() - (6 - i));
      return { date: `${d.getMonth() + 1}/${d.getDate()}`, count };
    });
    setTimeout(() => { setBars(mockBars); setLoading(false); }, 400);
  }, []);

  const maxCount = Math.max(...bars.map((b) => b.count), 1);

  // 가장 높은 값의 인덱스 (하이라이트)
  const peakIdx = bars.reduce((best, b, i) => (b.count > bars[best].count ? i : best), 0);
  const activeIdx = hoveredIdx !== null ? hoveredIdx : peakIdx;

  const totalCount = bars.reduce((s, b) => s + b.count, 0);

  return (
    <div className="glass-card p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            백테스트 활동
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">최근 7일 실행 횟수</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-black text-white font-outfit tabular-nums">{totalCount}</p>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 font-bold">총 실행</p>
        </div>
      </div>

      {loading ? (
        <div className="flex items-end gap-1.5 flex-1">
          {[...Array(7)].map((_, i) => (
            <div
              key={i}
              className="flex-1 bg-white/[0.04] rounded-xl animate-pulse"
              style={{ height: `${30 + Math.random() * 60}%` }}
            />
          ))}
        </div>
      ) : (
        <div className="flex items-end gap-1.5 flex-1">
          {bars.map((bar, i) => {
            const heightPct = maxCount > 0 ? (bar.count / maxCount) * 100 : 4;
            const isActive = i === activeIdx && bar.count > 0;
            const isEmpty = bar.count === 0;

            return (
              <div
                key={bar.date}
                className="flex-1 flex flex-col items-center gap-1 group cursor-pointer h-full"
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
              >
                {/* 값 라벨 */}
                <div className="h-5 flex items-end justify-center">
                  {isActive && (
                    <span className="text-[11px] font-black text-white tabular-nums font-outfit">
                      {bar.count.toLocaleString()}
                    </span>
                  )}
                </div>

                {/* 바 */}
                <div className="w-full flex items-end flex-1">
                  <div
                    className="w-full rounded-xl transition-all duration-300"
                    style={{
                      height: `${Math.max(heightPct, isEmpty ? 8 : 10)}%`,
                      background: isActive
                        ? "linear-gradient(180deg, #818cf8 0%, #6366f1 100%)"
                        : isEmpty
                        ? "rgba(255,255,255,0.04)"
                        : "rgba(255,255,255,0.08)",
                      boxShadow: isActive ? "0 0 16px rgba(99,102,241,0.35)" : "none",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* X축 날짜 — 모두 표시 */}
      {!loading && (
        <div className="flex mt-2">
          {bars.map((bar, i) => (
            <div key={i} className="flex-1 flex justify-center">
              <span className="text-xs text-gray-600 font-bold">{bar.date}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
