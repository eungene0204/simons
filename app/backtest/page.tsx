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
  const [history, setHistory] = useState<BacktestHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [sortField, setSortField] = useState<SortField>("timestamp");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [deleteTarget, setDeleteTarget] = useState<BacktestHistoryItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const strategyBadgeClass =
    "inline-flex min-h-7 max-w-full items-center break-words rounded-md border border-[#FF9933]/25 bg-[#1C1806] px-2.5 text-[11px] whitespace-normal lg:max-w-none lg:break-normal lg:whitespace-nowrap";

  useEffect(() => {
    let isActive = true;

    fetch("/api/backtest/history")
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (!isActive) return;
        setHistory(data);
        setIsLoading(false);
      })
      .catch(() => {
        if (!isActive) return;
        setIsLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, []);

  const handleRequestDeleteItem = (item: BacktestHistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteTarget(item);
  };

  const handleCancelDeleteItem = () => {
    if (isDeleting) return;
    setDeleteTarget(null);
  };

  const handleConfirmDeleteItem = async () => {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setIsDeleting(true);

    try {
      const response = await fetch(`/api/backtest/history?id=${id}`, {
        method: "DELETE",
      });
      if (response.ok) {
        setHistory((prev) => prev.filter((item) => item.id !== id));
        setDeleteTarget(null);
      }
    } catch (error) {
      console.error("Failed to delete history item:", error);
    } finally {
      setIsDeleting(false);
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
      <div
        className="mx-auto max-w-7xl p-3 sm:p-4 lg:p-6"
        data-testid="backtest-history-page"
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-black text-white flex items-center gap-3">
              <Clock className="w-7 h-7 text-main-blue" />
              전략 백테스트 기록
            </h1>
            <p className="text-sm text-gray-500 mt-1">최근 50개 기록</p>
          </div>
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
                className="flat-card group cursor-pointer rounded-2xl border border-white/[0.08] p-4 transition-colors hover:border-white/[0.14] lg:p-5"
                data-testid="backtest-history-card"
              >
                <div
                  className="mb-4 flex flex-col items-start gap-3 lg:flex-row lg:justify-between lg:gap-0"
                  data-testid="backtest-history-card-header"
                >
                  <div className="w-full lg:w-auto">
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
                  <div className="flex w-full items-center justify-between gap-2 lg:w-auto lg:flex-col lg:items-end">
                    <button
                      onClick={(e) => handleRequestDeleteItem(item, e)}
                      className="rounded-lg border border-red-500/30 bg-transparent p-1.5 text-red-500 opacity-100 transition-all lg:opacity-0 lg:group-hover:opacity-100"
                      aria-label={`${item.strategyName} 기록 삭제`}
                      title="기록 삭제"
                    >
                      <X className="w-4 h-4" />
                    </button>
                    <div className="break-all font-mono text-xs text-gray-500 lg:break-normal">
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

        {deleteTarget && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-backtest-history-title"
            onClick={handleCancelDeleteItem}
          >
            <div
              className="w-full max-w-sm rounded-2xl border border-white/[0.08] bg-[#111111] p-5 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 id="delete-backtest-history-title" className="text-lg font-black text-white">
                백테스트 기록을 삭제할까요?
              </h2>
              <p className="mt-2 text-sm leading-6 text-gray-400">
                백테스트 기록이 삭제됩니다. 삭제한 기록은 다시 복구할 수 없습니다.
              </p>
              <div className="mt-5 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={handleCancelDeleteItem}
                  disabled={isDeleting}
                  className="rounded-lg border border-white/[0.10] px-4 py-2 text-sm font-bold text-gray-300 transition-colors hover:border-white/[0.18] hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  취소
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDeleteItem}
                  disabled={isDeleting}
                  className="rounded-lg border border-white/[0.10] bg-[var(--main-red)]/10 px-4 py-2 text-sm font-bold text-[var(--main-red)] transition-colors hover:border-white/[0.18] hover:bg-[var(--main-red)]/15 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isDeleting ? "삭제 중..." : "삭제"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
