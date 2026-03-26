"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CaretUp, CaretDown } from "phosphor-react";
import type { DashboardBacktestRecord } from "@/types/dashboard";

type SortField = 'strategyName' | 'universe' | 'cagr' | 'sharpe' | 'mdd' | 'timestamp';

function fmt(v: number | undefined, digits = 1, suffix = "%"): string {
  if (v === undefined || v === null) return "-";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}${suffix}`;
}

function fmtDate(ts: number): string {
  return new Date(ts).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

function SortIcon({ field, active, dir }: { field: SortField; active: SortField; dir: 'asc' | 'desc' }) {
  if (field !== active) return <span className="inline-block w-3 h-3 opacity-0" />;
  return dir === 'asc' ? <CaretUp className="inline-block w-3 h-3 ml-0.5" weight="bold" /> : <CaretDown className="inline-block w-3 h-3 ml-0.5" weight="bold" />;
}

export default function BacktestHistory() {
  const [records, setRecords] = useState<DashboardBacktestRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    fetch("/api/backtest/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: DashboardBacktestRecord[]) => setRecords(data.slice(0, 10)))
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  function handleSort(field: SortField) {
    if (field === sortField) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  }

  const sorted = [...records].sort((a, b) => {
    let av: number | string, bv: number | string;
    if (sortField === 'strategyName') { av = a.strategyName ?? ''; bv = b.strategyName ?? ''; }
    else if (sortField === 'universe') { av = a.universe ?? ''; bv = b.universe ?? ''; }
    else if (sortField === 'cagr') { av = a.metrics?.cagr ?? -Infinity; bv = b.metrics?.cagr ?? -Infinity; }
    else if (sortField === 'sharpe') { av = a.metrics?.sharpe ?? -Infinity; bv = b.metrics?.sharpe ?? -Infinity; }
    else if (sortField === 'mdd') { av = a.metrics?.mdd ?? Infinity; bv = b.metrics?.mdd ?? Infinity; }
    else { av = a.timestamp; bv = b.timestamp; }
    if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
    return sortDir === 'asc' ? (av as number) - (bv as number) : (bv as number) - (av as number);
  });

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
                {([
                  { field: 'strategyName' as SortField, label: '전략명', align: 'left', cls: '' },
                  { field: 'universe' as SortField, label: '유니버스', align: 'left', cls: 'hidden sm:table-cell' },
                  { field: 'cagr' as SortField, label: 'CAGR', align: 'right', cls: '' },
                  { field: 'sharpe' as SortField, label: 'Sharpe', align: 'right', cls: 'hidden md:table-cell' },
                  { field: 'mdd' as SortField, label: 'MDD', align: 'right', cls: 'hidden md:table-cell' },
                  { field: 'timestamp' as SortField, label: '날짜', align: 'right', cls: 'hidden lg:table-cell' },
                ]).map(({ field, label, align, cls }) => (
                  <th
                    key={field}
                    onClick={() => handleSort(field)}
                    className={`py-2 pr-3 text-[10px] uppercase tracking-widest font-bold cursor-pointer select-none transition-colors ${
                      sortField === field ? 'text-main-blue' : 'text-gray-500 hover:text-gray-300'
                    } ${align === 'right' ? 'text-right' : 'text-left'} ${cls}`}
                  >
                    {label}
                    <SortIcon field={field} active={sortField} dir={sortDir} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => {
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
