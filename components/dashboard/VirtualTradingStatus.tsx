"use client";

import { useState } from "react";
import { Activity, ChartLine, Stack, CheckCircle } from "phosphor-react";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";

// 총 평가금·전체 계좌 수는 상단 PortfolioSummaryBar와 중복이므로
// 이 줄은 자동매매 운영 상태(실행/자동/포지션/체결)에만 집중한다.
export default function VirtualTradingStatus({ initialData }: { initialData: TradingStatusData }) {
  const [data] = useState<TradingStatusData>(initialData);
  const loading = false;

  const stats = [
    {
      icon: Activity,
      label: "실행중인 계좌 수",
      value: loading ? "--" : `${data.runningAccounts}개`,
      sub: loading ? "" : data.runningAccounts > 0 ? "매매 진행 중" : "일시 정지",
      highlight: data.runningAccounts > 0,
    },
    {
      icon: Stack,
      label: "자동매매 계좌",
      value: loading ? "--" : `${data.autoAccounts}개`,
      sub: loading ? "" : "자동 매매 설정",
      highlight: false,
    },
    {
      icon: ChartLine,
      label: "보유 종목",
      value: loading ? "--" : `${data.totalPositions}개`,
      sub: loading ? "" : "현재 포지션",
      highlight: false,
    },
    {
      icon: CheckCircle,
      label: "오늘 체결",
      value: loading ? "--" : `${data.todayFilledOrders}건`,
      sub: loading ? "" : "금일 주문",
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
