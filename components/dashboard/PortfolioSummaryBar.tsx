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

function profitColorClass(value: number): string {
  if (value > 0) return "text-[var(--main-red)]";
  if (value < 0) return "text-[var(--main-blue)]";
  return "text-white";
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

  const isPositive = stats.totalProfit > 0;
  const isDailyPos = stats.dailyPnl > 0;

  const cards = [
    {
      label: "총 모의 투자금",
      description: "전체 가상계좌에 설정된 초기 모의 투자금 합계입니다.",
      icon: Wallet,
      value: `${formatKRW(stats.totalInvested)}원`,
      valueColor: "text-white",
      badge: `${stats.accountCount}개 계좌`,
      badgeIsPositive: true,
      badgeIsNeutral: true,
    },
    {
      label: "전체 수익률",
      description: "총 수익금을 총 모의 투자금으로 나눈 전체 평가 수익률입니다.",
      icon: TrendUp,
      value: `${isPositive ? "+" : ""}${stats.totalReturnPct.toFixed(2)}%`,
      valueColor: profitColorClass(stats.totalReturnPct),
      badge: "",
      badgeIsPositive: isPositive,
      badgeIsNeutral: true,
    },
    {
      label: "총 수익금",
      description: "현재 현금과 보유 포지션 평가액을 합산한 뒤 총 모의 투자금을 뺀 평가손익입니다.",
      icon: CurrencyKrw,
      value: `${isPositive ? "+" : ""}${formatKRW(stats.totalProfit)}원`,
      valueColor: profitColorClass(stats.totalProfit),
      badge: "",
      badgeIsPositive: isPositive,
      badgeIsNeutral: true,
    },
    {
      label: "일간 손익",
      description: "오늘 매도 체결로 확정된 실현손익 합계입니다.",
      icon: CalendarBlank,
      value: `${isDailyPos && stats.dailyPnl !== 0 ? "+" : ""}${formatKRW(stats.dailyPnl)}원`,
      valueColor: profitColorClass(stats.dailyPnl),
      badge: "오늘",
      badgeIsPositive: isDailyPos,
      badgeIsNeutral: true,
    },
  ];

  return (
    <div className="flex divide-x divide-white/[0.08]">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="flex-1 flex flex-col justify-between gap-3 px-5 py-4"
          >
              {/* Top row: icon + label / info */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Icon size={18} weight="bold" className="text-gray-500" />
                  <span className="text-sm font-bold text-gray-500">{card.label}</span>
                </div>
                <span
                  className="group relative inline-flex h-5 w-5 items-center justify-center rounded-full text-gray-600 transition-colors hover:text-gray-300 focus-visible:text-gray-300"
                  tabIndex={0}
                  aria-label={`${card.label} 설명`}
                >
                  <Info size={16} />
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute right-0 top-7 z-20 w-64 rounded-md border border-white/[0.08] bg-[#111111] px-3 py-2 text-left text-[11px] font-bold leading-relaxed text-gray-300 opacity-0 shadow-xl shadow-black/40 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100"
                  >
                    {card.description}
                  </span>
                </span>
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
                {!loading && card.badge && (
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
