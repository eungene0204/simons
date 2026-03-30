"use client";

import { useState } from "react";
import { Wallet, TrendUp, CurrencyKrw, ArrowUpRight, ArrowDownRight, Info, CalendarBlank } from "phosphor-react";
import type { PortfolioStats } from "@/lib/dashboard-data";

function formatKRW(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString()}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}`;
}

function Badge({ value, isPositive }: { value: string; isPositive: boolean }) {
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${
        isPositive
          ? "bg-[var(--main-red)]/10 text-[var(--main-red)]"
          : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
      }`}
    >
      {value}
      {isPositive ? (
        <ArrowUpRight size={12} weight="bold" />
      ) : (
        <ArrowDownRight size={12} weight="bold" />
      )}
    </span>
  );
}

export default function PortfolioSummaryBar({ initialStats }: { initialStats: PortfolioStats }) {
  const [stats] = useState<PortfolioStats>(initialStats);
  const loading = false;

  const isPositive = stats.totalProfit >= 0;
  const isDailyPos = stats.dailyPnl >= 0;

  const cards = [
    {
      label: "총 투자금",
      icon: Wallet,
      value: `${formatKRW(stats.totalInvested)}원`,
      valueColor: "text-white",
      badge: `${stats.accountCount}개 계좌`,
      badgeIsPositive: true,
      badgeIsNeutral: true,
    },
    {
      label: "전체 수익률",
      icon: TrendUp,
      value: `${isPositive ? "+" : ""}${stats.totalReturnPct.toFixed(2)}%`,
      valueColor: "text-white",
      badge: `${Math.abs(stats.totalReturnPct).toFixed(2)}%`,
      badgeIsPositive: isPositive,
      badgeIsNeutral: false,
    },
    {
      label: "총 수익금",
      icon: CurrencyKrw,
      value: `${isPositive ? "+" : ""}${formatKRW(stats.totalProfit)}원`,
      valueColor: "text-white",
      badge: `${Math.abs(stats.totalReturnPct).toFixed(2)}%`,
      badgeIsPositive: isPositive,
      badgeIsNeutral: false,
    },
    {
      label: "일간 손익",
      icon: CalendarBlank,
      value: `${isDailyPos && stats.dailyPnl !== 0 ? "+" : ""}${formatKRW(stats.dailyPnl)}원`,
      valueColor: "text-white",
      badge: "오늘",
      badgeIsPositive: isDailyPos,
      badgeIsNeutral: true,
    },
  ];

  return (
    <div className="flex gap-4">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="flex-1 flex flex-col justify-between gap-3 px-5 py-4 glass-card"
          >
              {/* Top row: icon + label / info */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon size={18} weight="bold" className="text-gray-400" />
                  <span className="text-sm font-bold text-gray-400">{card.label}</span>
                </div>
                <Info size={16} className="text-gray-600" />
              </div>

              {/* Bottom row: value + badge */}
              <div className="flex items-end gap-3">
                {loading ? (
                  <span className="text-3xl font-black text-gray-600 font-outfit">--</span>
                ) : (
                  <span className={`text-3xl font-black tabular-nums font-outfit leading-none ${card.valueColor}`}>
                    {card.value}
                  </span>
                )}
                {!loading && (
                  card.badgeIsNeutral ? (
                    <span className="inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-md bg-white/[0.06] text-gray-400 mb-0.5">
                      {card.badge}
                    </span>
                  ) : (
                    <span className="mb-0.5">
                      <Badge value={card.badge} isPositive={card.badgeIsPositive} />
                    </span>
                  )
                )}
              </div>
            </div>
          );
        })}
    </div>
  );
}
