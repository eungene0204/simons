"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChartLineUp } from "phosphor-react";
import type { StrategyDSL } from "@/types/strategy";
import type { DashboardBacktestRecord } from "@/types/dashboard";

interface StrategyCardData {
  id: string;
  name: string;
  description?: string;
  backtest?: DashboardBacktestRecord;
}

function MetricCell({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-widest text-gray-500 font-bold">{label}</span>
      <span className={`text-sm font-black tabular-nums font-outfit ${color ?? "text-gray-300"}`}>
        {value}
      </span>
    </div>
  );
}

export default function StrategyOverview() {
  const [cards, setCards] = useState<StrategyCardData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/strategy").then((r) => (r.ok ? r.json() : [])),
      fetch("/api/backtest/history").then((r) => (r.ok ? r.json() : [])),
    ])
      .then(([strategies, history]: [StrategyDSL[], DashboardBacktestRecord[]]) => {
        const mapped: StrategyCardData[] = strategies.map((s) => {
          const latest = history.find((h) => h.strategyName === s.name);
          return { id: s.id, name: s.name, description: s.description, backtest: latest };
        });
        setCards(mapped);
      })
      .catch(() => setCards([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
            내 전략
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">보유 전략 현황</p>
        </div>
        <Link
          href="/analytics"
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          전략 연구소 →
        </Link>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="glass-card p-4 animate-pulse">
              <div className="h-4 bg-white/5 rounded w-2/3 mb-3" />
              <div className="h-3 bg-white/5 rounded w-full mb-2" />
              <div className="flex gap-4 mt-4">
                <div className="h-8 bg-white/5 rounded w-16" />
                <div className="h-8 bg-white/5 rounded w-16" />
                <div className="h-8 bg-white/5 rounded w-16" />
              </div>
            </div>
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="glass-card p-12 flex flex-col items-center justify-center text-center">
          <ChartLineUp size={48} className="text-gray-700 mb-4" />
          <p className="text-gray-400 font-medium">아직 전략이 없습니다</p>
          <p className="text-gray-600 text-sm mt-1">
            블록 기반 노코드 전략 빌더로 나만의 전략을 만들어보세요
          </p>
          <Link
            href="/analytics"
            className="mt-4 px-5 py-2.5 bg-blue-600/80 text-white text-sm font-bold rounded-lg hover:bg-blue-600 transition-colors"
          >
            첫 번째 전략 만들기
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {cards.slice(0, 8).map((card) => {
            const hasBacktest = !!card.backtest;
            const cagr = card.backtest?.metrics?.cagr;
            const sharpe = card.backtest?.metrics?.sharpe;
            const mdd = card.backtest?.metrics?.mdd;
            const cagrColor =
              cagr === undefined
                ? "text-gray-600"
                : cagr >= 0
                ? "text-[var(--main-red)]"
                : "text-[var(--main-blue)]";
            return (
              <Link href="/analytics" key={card.id}>
                <div className="glass-card p-4 cursor-pointer group">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <p className="font-black text-white text-sm leading-snug group-hover:text-blue-300 transition-colors truncate">
                      {card.name}
                    </p>
                    <span
                      className={`shrink-0 text-[9px] uppercase tracking-widest font-bold px-1.5 py-0.5 rounded ${
                        hasBacktest
                          ? "text-green-400 bg-green-500/10 border border-green-500/20"
                          : "text-gray-500 bg-white/5 border border-white/10"
                      }`}
                    >
                      {hasBacktest ? "검증됨" : "미검증"}
                    </span>
                  </div>
                  {card.description && (
                    <p className="text-xs text-gray-500 mb-3 line-clamp-2">{card.description}</p>
                  )}
                  <div className="flex gap-4 pt-2 border-t border-white/5">
                    <MetricCell
                      label="CAGR"
                      value={cagr !== undefined ? `${cagr >= 0 ? "+" : ""}${cagr.toFixed(1)}%` : "-"}
                      color={cagrColor}
                    />
                    <MetricCell
                      label="Sharpe"
                      value={sharpe !== undefined ? sharpe.toFixed(2) : "-"}
                    />
                    <MetricCell
                      label="MDD"
                      value={mdd !== undefined ? `${mdd.toFixed(1)}%` : "-"}
                      color="text-[var(--main-blue)]"
                    />
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
