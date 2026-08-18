"use client";

import { useState } from "react";
import { Activity, ChartLine, Stack, CheckCircle } from "phosphor-react";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";
import { t } from "@/lib/i18n";

// 총 평가금·전체 계좌 수는 상단 PortfolioSummaryBar와 중복이므로
// 이 줄은 자동매매 운영 상태(실행/자동/포지션/체결)에만 집중한다.
export default function VirtualTradingStatus({ initialData }: { initialData: TradingStatusData }) {
  const [data] = useState<TradingStatusData>(initialData);
  const loading = false;

  const stats = [
    {
      icon: Activity,
      label: t("실행중인 계좌 수"),
      value: loading ? "--" : t("{0}개", data.runningAccounts),
      sub: loading ? "" : data.runningAccounts > 0 ? t("매매 진행 중") : t("일시 정지"),
      highlight: data.runningAccounts > 0,
    },
    {
      icon: Stack,
      label: t("자동매매 계좌"),
      value: loading ? "--" : t("{0}개", data.autoAccounts),
      sub: loading ? "" : t("자동 매매 설정"),
      highlight: false,
    },
    {
      icon: ChartLine,
      label: t("보유 종목"),
      value: loading ? "--" : t("{0}개", data.totalPositions),
      sub: loading ? "" : t("현재 포지션"),
      highlight: false,
    },
    {
      icon: CheckCircle,
      label: t("오늘 체결"),
      value: loading ? "--" : t("{0}건", data.todayFilledOrders),
      sub: loading ? "" : t("금일 주문"),
      highlight: data.todayFilledOrders > 0,
    },
  ];

  return (
    <div
      className="grid grid-cols-2 items-stretch lg:flex lg:divide-x lg:divide-white/[0.08]"
      data-testid="virtual-trading-status-grid"
    >
      {/* 5개 통계 */}
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div
            key={s.label}
            className="flex flex-1 flex-col justify-between border-white/[0.08] px-3 py-4 odd:border-r [&:nth-child(-n+2)]:border-b lg:border-b-0 lg:border-r-0 lg:px-4"
          >
              <div className="flex items-center gap-2">
                <Icon
                  size={15}
                  weight="bold"
                  className="text-gray-500"
                />
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                  {s.label}
                </span>
              </div>
              <div className="mt-2">
                <p className="text-xl font-black tabular-nums font-outfit text-white">
                  {s.value}
                </p>
                <p className="text-[10px] text-gray-600 mt-0.5">{s.sub}</p>
              </div>
            </div>
          );
        })}
    </div>
  );
}
