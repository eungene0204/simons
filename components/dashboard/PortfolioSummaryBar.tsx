"use client";

import { useState } from "react";
import { Wallet, Vault, TrendUp, CurrencyKrw, ArrowUpRight, ArrowDownRight, Info, CalendarBlank } from "phosphor-react";
import type { PortfolioStats } from "@/lib/dashboard-data";
import { formatCompactNumberEn, t } from "@/lib/i18n";

function formatKRW(v: number): string {
  const compactEn = formatCompactNumberEn(v);
  if (compactEn !== null) return compactEn;
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 100_000_000) return t("{0}{1}억", sign, (abs / 100_000_000).toFixed(1));
  if (abs >= 10_000) return t("{0}{1}만", sign, Math.round(abs / 10_000).toLocaleString());
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
      label: t("총 모의 투자금"),
      description: t("운용중인 가상계좌에 설정된 초기 모의 투자금 합계입니다. 삭제된 계좌는 제외됩니다."),
      icon: Wallet,
      value: t("{0}원", formatKRW(stats.totalInvested)),
      valueColor: "text-white",
      badge: t("운용중 {0}개", stats.accountCount),
      badgeIsPositive: true,
      badgeIsNeutral: true,
    },
    {
      label: t("총 평가금액"),
      description: t("운용중인 계좌의 현금과 보유 포지션 평가액을 합산한 현재 가치입니다. 삭제된 계좌는 제외됩니다."),
      icon: Vault,
      value: t("{0}원", formatKRW(stats.totalValue)),
      valueColor: "text-white",
      badge: "",
      badgeIsPositive: true,
      badgeIsNeutral: true,
    },
    {
      label: t("전체 수익률"),
      description: t("운용중인 계좌 기준으로 총 수익금을 총 모의 투자금으로 나눈 평가 수익률입니다."),
      icon: TrendUp,
      value: `${isPositive ? "+" : ""}${stats.totalReturnPct.toFixed(2)}%`,
      valueColor: profitColorClass(stats.totalReturnPct),
      badge: "",
      badgeIsPositive: isPositive,
      badgeIsNeutral: true,
    },
    {
      label: t("총 수익금"),
      description: t("운용중인 계좌의 총 평가금액에서 총 모의 투자금을 뺀 평가손익입니다."),
      icon: CurrencyKrw,
      value: t("{0}원", `${isPositive ? "+" : ""}${formatKRW(stats.totalProfit)}`),
      valueColor: profitColorClass(stats.totalProfit),
      badge: "",
      badgeIsPositive: isPositive,
      badgeIsNeutral: true,
    },
    {
      label: t("일간 손익"),
      description: t("오늘 매도 체결로 확정된 실현손익 합계입니다."),
      icon: CalendarBlank,
      value: t("{0}원", `${isDailyPos && stats.dailyPnl !== 0 ? "+" : ""}${formatKRW(stats.dailyPnl)}`),
      valueColor: profitColorClass(stats.dailyPnl),
      badge: t("오늘"),
      badgeIsPositive: isDailyPos,
      badgeIsNeutral: true,
    },
  ];

  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:flex lg:divide-x lg:divide-white/[0.08]"
      data-testid="portfolio-summary-grid"
    >
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="flex flex-1 flex-col justify-between gap-3 border-b border-white/[0.08] px-4 py-4 last:border-b-0 sm:odd:border-r lg:border-b-0 lg:border-r-0 lg:px-5"
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
                  aria-label={t("{0} 설명", card.label)}
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
              <div className="flex flex-wrap items-end gap-3 lg:flex-nowrap">
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
