"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import DashboardLayout from "@/components/layout/DashboardLayout";
import { BacktestHistoryItem } from "@/types/strategy";
import {
  Clock,
  Trash,
  X,
  CaretUp,
  CaretDown,
} from "phosphor-react";

type SortField = 'timestamp' | 'totalReturn' | 'cagr' | 'mdd' | 'profitFactor' | 'trades' | 'score';

function HistoryMetric({
  label,
  value,
  trend,
  colorOverride,
}: {
  label: string;
  value: string;
  trend?: "up" | "down";
  colorOverride?: string;
}) {
  const dynamicColor = colorOverride
    ? colorOverride
    : trend === "up"
    ? "text-main-red"
    : trend === "down"
    ? "text-main-blue"
    : "text-white";

  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500 font-bold uppercase tracking-wider mb-1">{label}</span>
      <span className={`text-sm font-black ${dynamicColor}`}>{value}</span>
    </div>
  );
}

export default function BacktestHistoryPage() {
  const router = useRouter();
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [sortField, setSortField] = useState<SortField>("timestamp");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    fetch("/api/backtest/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        setHistory(data);
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
        setHistory((prev) => prev.filter((item) => item.id !== id));
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

  return (
    <DashboardLayout>
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
              className="flex items-center gap-2 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-500 text-xs font-bold rounded-lg border border-red-500/20 transition-all"
            >
              <Trash className="w-4 h-4" />
              기록 전체 삭제
            </button>
          )}
        </div>

        {/* Sort buttons */}
        {history.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <span className="text-[10px] text-gray-500 font-bold uppercase tracking-widest">정렬:</span>
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
                  className={`flex items-center justify-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold border transition-all ${
                    isActive
                      ? "bg-main-blue/15 text-main-blue border-main-blue/30"
                      : "bg-white/5 text-gray-400 border-white/10 hover:border-white/20 hover:text-white"
                  }`}
                >
                  {label}
                  {isActive ? (
                    sortDir === "desc" ? (
                      <CaretDown className="w-3 h-3" />
                    ) : (
                      <CaretUp className="w-3 h-3" />
                    )
                  ) : (
                    <span className="w-3 h-3 opacity-0">
                      <CaretDown className="w-3 h-3" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Content */}
        {isLoading ? (
          <div className="h-[300px] flex items-center justify-center text-gray-500">
            <p className="text-sm font-bold">불러오는 중...</p>
          </div>
        ) : sortedHistory.length > 0 ? (
          <div className="space-y-4">
            {sortedHistory.map((item) => (
              <div
                key={item.id}
                onClick={() => router.push(`/backtest/${item.id}`)}
                className="bg-[#161616] border border-white/5 rounded-2xl p-5 hover:border-white/10 hover:bg-[#1a1a1a] transition-all group cursor-pointer"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3 mb-1.5">
                      <span className="text-base font-black text-white">{item.strategyName}</span>
                      <span className="px-2.5 py-1 bg-main-blue/10 text-main-blue text-xs font-black rounded uppercase tracking-wider border border-main-blue/20">
                        {item.universe}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-y-2 gap-x-4">
                      {/* Entry Blocks */}
                      {(() => {
                        const conds = item.conditions as any;
                        const entry =
                          conds?.entry ||
                          (Array.isArray(item.conditions)
                            ? { logic: "AND", names: item.conditions }
                            : { logic: conds.logic || "AND", names: conds.names || [] });
                        const isEntryAnd = String(entry.logic).trim().toUpperCase() === "AND";
                        const names = entry.names || [];
                        if (names.length === 0) return null;
                        return (
                          <div className="flex items-center">
                            {names.map((name: string, idx: number) => (
                              <div key={`entry-${idx}`} className="flex items-center">
                                {idx > 0 && isEntryAnd && <div className="w-5 h-[1.5px] bg-red-500/40" />}
                                {idx > 0 && !isEntryAnd && <div className="w-4" />}
                                <span
                                  className={`px-2.5 py-1 ${
                                    !isEntryAnd
                                      ? "bg-red-500/5 text-red-400/80 border-red-500/20"
                                      : "bg-red-500/10 text-red-500 border-red-500/10"
                                  } text-[10px] font-bold rounded-md border whitespace-nowrap`}
                                >
                                  {name}
                                </span>
                              </div>
                            ))}
                          </div>
                        );
                      })()}

                      {/* Divider */}
                      {(item.conditions as any).entry?.names?.length > 0 &&
                        (item.conditions as any).exit?.names?.length > 0 && (
                          <div className="w-6" />
                        )}

                      {/* Exit Blocks */}
                      {(() => {
                        const conds = item.conditions as any;
                        if (!conds?.exit || (conds.exit.names || []).length === 0) return null;
                        const exit = conds.exit;
                        const isExitAnd = String(exit.logic).trim().toUpperCase() === "AND";
                        const names = exit.names || [];
                        return (
                          <div className="flex items-center">
                            {names.map((name: string, idx: number) => (
                              <div key={`exit-${idx}`} className="flex items-center">
                                {idx > 0 && isExitAnd && <div className="w-5 h-[1.5px] bg-blue-500/40" />}
                                {idx > 0 && !isExitAnd && <div className="w-4" />}
                                <span
                                  className={`px-2.5 py-1 ${
                                    !isExitAnd
                                      ? "bg-blue-500/5 text-blue-400/80 border-blue-500/20"
                                      : "bg-blue-500/10 text-blue-500 border-blue-500/10"
                                  } text-[10px] font-bold rounded-md border whitespace-nowrap`}
                                >
                                  {name}
                                </span>
                              </div>
                            ))}
                          </div>
                        );
                      })()}

                      {/* Position and Risk */}
                      {(() => {
                        const conds = item.conditions as any;
                        if (!conds?.position && !conds?.risk) return null;
                        return (
                          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 mt-1 sm:mt-0">
                            {conds.position && (
                              <div className="flex items-center gap-1.5 bg-gray-800/30 px-2 py-1 rounded text-[10px] border border-gray-700/50">
                                <span className="text-gray-500 font-bold">포지션/비중</span>
                                <span className="text-gray-300">{conds.position}</span>
                              </div>
                            )}
                            {conds.risk && (
                              <div className="flex items-center gap-1.5 bg-gray-800/30 px-2 py-1 rounded text-[10px] border border-gray-700/50">
                                <span className="text-gray-500 font-bold">리스크 관리</span>
                                <span className="text-gray-300">{conds.risk}</span>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <button
                      onClick={(e) => handleDeleteItem(item.id, e)}
                      className="p-1.5 text-gray-600 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
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
                  <HistoryMetric label="총 수익률" value={`${item.metrics.totalReturn.toFixed(1)}%`} trend={item.metrics.totalReturn > 0 ? "up" : "down"} />
                  <HistoryMetric label="CAGR" value={`${item.metrics.cagr.toFixed(1)}%`} trend={item.metrics.cagr > 0 ? "up" : "down"} />
                  <HistoryMetric label="MDD" value={`${item.metrics.mdd.toFixed(1)}%`} trend="down" />
                  <HistoryMetric label="손익비" value={item.metrics.profitFactor.toFixed(2)} />
                  <HistoryMetric label="매수후보유" value={`${item.metrics.buyHold.toFixed(1)}%`} colorOverride="text-main-green" />
                  <HistoryMetric label="매매횟수" value={`${item.metrics.trades}회`} />
                  <HistoryMetric label="소요시간" value={item.metrics.executionTime !== undefined ? `${item.metrics.executionTime.toFixed(2)}초` : "-"} />
                  {item.metrics.score != null && (
                    <HistoryMetric
                      label="점수"
                      value={`${item.metrics.score} / 100`}
                      colorOverride={
                        item.metrics.score >= 80 ? "text-emerald-400"
                        : item.metrics.score >= 60 ? "text-yellow-400"
                        : item.metrics.score >= 40 ? "text-orange-400"
                        : "text-red-400"
                      }
                    />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-[300px] flex flex-col items-center justify-center text-gray-600 space-y-3">
            <div className="p-4 bg-white/5 rounded-full border border-white/5">
              <Clock className="w-10 h-10 opacity-20" />
            </div>
            <p className="text-base font-bold">기록된 테스트가 없습니다</p>
            <p className="text-sm text-gray-500">백테스트를 실행하면 이곳에 자동으로 기록됩니다.</p>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
