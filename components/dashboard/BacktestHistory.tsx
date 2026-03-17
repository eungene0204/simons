"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { DashboardBacktestRecord } from "@/types/dashboard";

function fmt(v: number | undefined, digits = 1, suffix = "%"): string {
  if (v === undefined || v === null) return "-";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}${suffix}`;
}

function fmtDate(ts: number): string {
  return new Date(ts).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

export default function BacktestHistory() {
  const [records, setRecords] = useState<DashboardBacktestRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/backtest/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: DashboardBacktestRecord[]) => setRecords(data.slice(0, 10)))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="glass-card p-5 h-full">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            최근 백테스트
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">최근 10개 실행 기록</p>
        </div>
        <Link
          href="/analytics"
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          전략 연구소 →
        </Link>
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-10 bg-white/5 rounded-lg" />
          ))}
        </div>
      ) : records.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <p className="text-gray-400 font-medium">아직 백테스트 기록이 없습니다</p>
          <p className="text-gray-600 text-sm mt-1">전략을 만들고 백테스트를 실행해보세요</p>
          <Link
            href="/analytics"
            className="mt-4 px-4 py-2 bg-blue-600/80 text-white text-sm font-bold rounded-lg hover:bg-blue-600 transition-colors"
          >
            전략 만들기
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5">
                <th className="text-left py-2 pr-3 text-[10px] uppercase tracking-widest text-gray-500 font-bold">
                  전략명
                </th>
                <th className="text-left py-2 pr-3 text-[10px] uppercase tracking-widest text-gray-500 font-bold hidden sm:table-cell">
                  유니버스
                </th>
                <th className="text-right py-2 pr-3 text-[10px] uppercase tracking-widest text-gray-500 font-bold">
                  CAGR
                </th>
                <th className="text-right py-2 pr-3 text-[10px] uppercase tracking-widest text-gray-500 font-bold hidden md:table-cell">
                  Sharpe
                </th>
                <th className="text-right py-2 pr-3 text-[10px] uppercase tracking-widest text-gray-500 font-bold hidden md:table-cell">
                  MDD
                </th>
                <th className="text-right py-2 text-[10px] uppercase tracking-widest text-gray-500 font-bold hidden lg:table-cell">
                  날짜
                </th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => {
                const cagr = r.metrics?.cagr;
                const isPos = (cagr ?? 0) >= 0;
                return (
                  <tr
                    key={r.id}
                    className="border-b border-white/[0.03] hover:bg-white/[0.03] transition-colors"
                  >
                    <td className="py-2.5 pr-3 font-medium text-white max-w-[140px] truncate">
                      {r.strategyName || "-"}
                    </td>
                    <td className="py-2.5 pr-3 text-gray-400 text-xs hidden sm:table-cell">
                      {r.universe || "-"}
                    </td>
                    <td
                      className={`py-2.5 pr-3 text-right font-bold tabular-nums ${
                        isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"
                      }`}
                    >
                      {fmt(cagr)}
                    </td>
                    <td className="py-2.5 pr-3 text-right text-gray-300 tabular-nums hidden md:table-cell">
                      {r.metrics?.sharpe !== undefined ? r.metrics.sharpe.toFixed(2) : "-"}
                    </td>
                    <td className="py-2.5 pr-3 text-right text-[var(--main-blue)] tabular-nums hidden md:table-cell">
                      {r.metrics?.mdd !== undefined ? `${r.metrics.mdd.toFixed(1)}%` : "-"}
                    </td>
                    <td className="py-2.5 text-right text-gray-500 text-xs hidden lg:table-cell">
                      {fmtDate(r.timestamp)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
