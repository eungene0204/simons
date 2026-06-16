"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { StrategyWaveBackground } from "@/components/strategy/StrategyWaveBackground";
import { BacktestHistoryItem } from "@/types/strategy";
import { resolveUniverseDisplayName } from "@/lib/strategy-summary";
import {
  Clock,
  Trash,
  X,
} from "phosphor-react";

type SortField = 'timestamp' | 'totalReturn' | 'cagr' | 'mdd' | 'profitFactor' | 'trades' | 'score';
const HISTORY_CACHE_KEY = "simons.backtestHistory";

function readCachedHistory() {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(HISTORY_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    return parsed as BacktestHistoryItem[];
  } catch {
    return null;
  }
}

function writeCachedHistory(nextHistory: BacktestHistoryItem[]) {
  if (typeof window === "undefined") return;

  try {
    window.sessionStorage.setItem(HISTORY_CACHE_KEY, JSON.stringify(nextHistory));
  } catch {
    // Cache writes are best effort only.
  }
}

function HistoryMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-1">{label}</span>
      <span className="text-sm font-black text-white">{value}</span>
    </div>
  );
}

export default function BacktestHistoryPage() {
  const router = useRouter();
  const [history, setHistory] = useState<BacktestHistoryItem[]>(() => readCachedHistory() ?? []);
  const [isLoading, setIsLoading] = useState(() => readCachedHistory() === null);
  const [sortField, setSortField] = useState<SortField>("timestamp");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const strategyBadgeClass =
    "inline-flex items-center min-h-7 px-2.5 rounded-md border border-[#FF9933]/25 bg-[#1C1806] text-[11px] whitespace-nowrap";

  useEffect(() => {
    fetch("/api/backtest/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        setHistory(data);
        writeCachedHistory(data);
        setIsLoading(false);
      })
      .catch(() => setIsLoading(false));
  }, []);

  const handleDeleteItem = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const response = await fetch(`/api/backtest/history?id=${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        setHistory((prev) => {
          const nextHistory = prev.filter((item) => item.id !== id);
          writeCachedHistory(nextHistory);
          return nextHistory;
        });
      }
    } catch (error) {
      console.error("Failed to delete history item:", error);
    }
  };

  const handleClearAll = async () => {
    if (!confirm("모든 테스트 기록을 삭제하시겠습니까?")) return;
    try {
      const response = await fetch("/api/backtest/history", { method: "DELETE" });
      if (response.ok) {
        setHistory([]);
        writeCachedHistory([]);
      }
    } catch (error) {
      console.error("Failed to clear history:", error);
    }
  };

  const sortedHistory = [...history].sort((a, b) => {
    let av: number, bv: number;
    if (sortField === "timestamp") {
      av = a.timestamp; bv = b.timestamp;
    } else if (sortField === "score") {
      av = a.metrics.score ?? -Infinity; bv = b.metrics.score ?? -Infinity;
    } else if (sortField === "cagr") {
      av = a.metrics.cagr ?? -Infinity; bv = b.metrics.cagr ?? -Infinity;
    } else if (sortField === "totalReturn") {
      av = a.metrics.totalReturn ?? -Infinity; bv = b.metrics.totalReturn ?? -Infinity;
    } else if (sortField === "mdd") {
      av = a.metrics.mdd ?? Infinity; bv = b.metrics.mdd ?? Infinity;
    } else if (sortField === "profitFactor") {
      av = a.metrics.profitFactor ?? -Infinity; bv = b.metrics.profitFactor ?? -Infinity;
    } else {
      av = a.metrics.trades ?? -Infinity; bv = b.metrics.trades ?? -Infinity;
    }
    return sortDir === "asc" ? av - bv : bv - av;
  });

  if (!isLoading && sortedHistory.length === 0) {
    return (
      <DashboardLayout userName="">
        <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))]">
          <div className="relative flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] flex-col items-center justify-center overflow-hidden px-5 py-8 text-center">
            <StrategyWaveBackground />
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,15,15,0.18)_0%,rgba(15,15,15,0.72)_72%)]" />
            <p className="relative z-10 max-w-4xl text-4xl font-black leading-tight text-white md:text-6xl">
              전략을 만들고
              <br />
              백테스트 해보세요
            </p>
            <div className="relative z-10 mt-8">
              <div className="pointer-events-none absolute -inset-x-8 -inset-y-4 bg-[radial-gradient(ellipse_at_center,rgba(55,122,244,0.28)_0%,rgba(34,197,94,0.12)_38%,rgba(15,15,15,0)_72%)] blur-2xl" />
              <button
                type="button"
                onClick={() => router.push("/analytics")}
                className="relative rounded-lg border border-white/[0.12] bg-[#111111] px-7 py-4 text-base font-black text-white transition-colors hover:bg-[#181818]"
              >
                전략 만들기
              </button>
            </div>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (isLoading) {
    return (
      <DashboardLayout userName="">
        <div className="min-h-[calc(100vh-var(--top-menu-bar-height,76px))]">
          <div className="relative flex min-h-[calc(100vh-var(--top-menu-bar-height,76px))] items-center justify-center overflow-hidden px-5 py-8 text-center">
            <StrategyWaveBackground />
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(15,15,15,0.18)_0%,rgba(15,15,15,0.72)_72%)]" />
            <p className="relative z-10 text-sm font-bold text-gray-500">불러오는 중...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout userName="">
      <div className="p-6 max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-black text-white flex items-center gap-3">
              <Clock className="w-7 h-7 text-main-blue" />
              백테스트 기록
            </h1>
            <p className="text-sm text-gray-500 mt-1">최근 50개 기록</p>
          </div>
          {history.length > 0 && (
            <button
              onClick={handleClearAll}
              className="flex items-center gap-2 px-3 py-1.5 bg-transparent text-gray-500 text-xs font-bold rounded-lg border border-white/[0.08] transition-colors hover:text-[var(--main-red)] hover:border-[var(--main-red)]/30"
            >
              <Trash className="w-4 h-4" />
              기록 전체 삭제
            </button>
          )}
        </div>

        {/* Sort buttons */}
        {history.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            {([
              { field: "timestamp", label: "날짜" },
              { field: "score", label: "점수" },
              { field: "cagr", label: "CAGR" },
              { field: "totalReturn", label: "총수익률" },
              { field: "mdd", label: "MDD" },
              { field: "profitFactor", label: "손익비" },
              { field: "trades", label: "매매횟수" },
            ] as const).map(({ field, label }) => {
              const isActive = sortField === field;
              return (
                <button
                  key={field}
                  onClick={() => {
                    if (isActive) {
                      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
                    } else {
                      setSortField(field);
                      setSortDir("desc");
                    }
                  }}
                  className={`flex items-center justify-center px-2.5 py-1 rounded-md text-xs font-bold border transition-colors ${
                    isActive
                      ? "bg-white/10 text-white border-white/15"
                      : "bg-white/5 text-gray-400 border-white/10 hover:border-white/15 hover:text-white"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {/* Content */}
        {sortedHistory.length > 0 ? (
          <div className="space-y-4">
            {sortedHistory.map((item) => (
              <div
                key={item.id}
                onClick={() => router.push(`/backtest/${item.id}`)}
                className="flat-card rounded-2xl border border-white/[0.08] p-5 hover:border-white/[0.14] transition-colors group cursor-pointer"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="mb-2">
                      <span className="text-base font-black text-white">{item.strategyName}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {(() => {
                        const universeLabel = resolveUniverseDisplayName(item.universe, item.strategyName);
                        if (!universeLabel) return null;
                        return (
                          <span className={strategyBadgeClass}>
                            <span className="font-black text-white mr-1">유니버스</span>
                            <span className="font-bold text-[#FF9933]">{universeLabel}</span>
                          </span>
                        );
                      })()}

                      {(() => {
                        const conds = item.conditions as any;
                        const entry =
                          conds?.entry ||
                          (Array.isArray(item.conditions)
                            ? { logic: "AND", names: item.conditions }
                            : { logic: conds?.logic || "AND", names: conds?.names || [] });
                        const names = entry.names || [];
                        if (names.length === 0) return null;

                        return names.map((name: string, idx: number) => (
                          <span
                            key={`entry-${idx}`}
                            className={strategyBadgeClass}
                          >
                            <span className="font-black text-white mr-1">진입 신호</span>
                            <span className="font-bold text-[#FF9933]">{name}</span>
                          </span>
                        ));
                      })()}

                      {(() => {
                        const conds = item.conditions as any;
                        if (!conds?.exit || (conds.exit.names || []).length === 0) return null;
                        const names = conds.exit.names || [];

                        return names.map((name: string, idx: number) => (
                          <span
                            key={`exit-${idx}`}
                            className={strategyBadgeClass}
                          >
                            <span className="font-black text-white mr-1">청산 신호</span>
                            <span className="font-bold text-[#FF9933]">{name}</span>
                          </span>
                        ));
                      })()}

                      {(() => {
                        const conds = item.conditions as any;
                        if (!conds?.position) return null;
                        return (
                          <span
                            className={strategyBadgeClass}
                          >
                            <span className="font-black text-white mr-1">포지션/비중</span>
                            <span className="font-bold text-[#FF9933]">{conds.position}</span>
                          </span>
                        );
                      })()}

                      {(() => {
                        const conds = item.conditions as any;
                        if (!conds?.risk) return null;
                        return (
                          <span
                            className={strategyBadgeClass}
                          >
                            <span className="font-black text-white mr-1">리스크 관리</span>
                            <span className="font-bold text-[#FF9933]">{conds.risk}</span>
                          </span>
                        );
                      })()}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <button
                      onClick={(e) => handleDeleteItem(item.id, e)}
                      className="p-1.5 text-red-500 border border-red-500/30 bg-transparent rounded-lg transition-all opacity-0 group-hover:opacity-100"
                      title="기록 삭제"
                    >
                      <X className="w-4 h-4" />
                    </button>
                    <div className="text-xs text-gray-500 font-mono">
                      {new Date(item.timestamp).toLocaleString()}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
                  <HistoryMetric label="총 수익률" value={`${item.metrics.totalReturn.toFixed(1)}%`} />
                  <HistoryMetric label="CAGR" value={`${item.metrics.cagr.toFixed(1)}%`} />
                  <HistoryMetric label="MDD" value={`${item.metrics.mdd.toFixed(1)}%`} />
                  <HistoryMetric label="손익비" value={item.metrics.profitFactor.toFixed(2)} />
                  <HistoryMetric label="매수후보유" value={`${item.metrics.buyHold.toFixed(1)}%`} />
                  <HistoryMetric label="매매횟수" value={`${item.metrics.trades}회`} />
                  <HistoryMetric label="소요시간" value={item.metrics.executionTime !== undefined ? `${item.metrics.executionTime.toFixed(2)}초` : "-"} />
                  {item.metrics.score != null && (
                    <HistoryMetric
                      label="점수"
                      value={`${item.metrics.score} / 100`}
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </DashboardLayout>
  );
}
