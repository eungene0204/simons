"use client";

import { useEffect, useState } from "react";
import { Activity, ChartLine, Stack, CheckCircle, Vault } from "phosphor-react";
import type { TradingStatusData } from "@/app/api/dashboard/trading-status/route";

function formatKRW(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`;
  if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString()}만`;
  return `${sign}${abs.toLocaleString("ko-KR")}`;
}

const DEFAULT: TradingStatusData = {
  totalAccounts: 0,
  runningAccounts: 0,
  autoAccounts: 0,
  todayFilledOrders: 0,
  totalPositions: 0,
  dailyPnl: 0,
  totalEvaluation: 0,
};

export default function VirtualTradingStatus() {
  const [data, setData] = useState<TradingStatusData>(DEFAULT);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/dashboard/trading-status")
      .then((r) => (r.ok ? r.json() : DEFAULT))
      .then((d: TradingStatusData) => setData(d))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const stats = [
    {
      icon: Vault,
      label: "총 평가금",
      value: loading ? "--" : `${formatKRW(data.totalEvaluation)}원`,
      sub: loading ? "" : "전체 계좌 합산",
      highlight: false,
    },
    {
      icon: Stack,
      label: "전체 계좌",
      value: loading ? "--" : `${data.totalAccounts}개`,
      sub: loading ? "" : `자동 ${data.autoAccounts}개`,
      highlight: false,
    },
    {
      icon: Activity,
      label: "실행중인 계좌 수",
      value: loading ? "--" : `${data.runningAccounts}개`,
      sub: loading ? "" : data.runningAccounts > 0 ? "매매 진행 중" : "일시 정지",
      highlight: data.runningAccounts > 0,
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
    <div className="flex gap-3 items-stretch">
      {/* 5개 통계 */}
      {stats.map((s) => {
        const Icon = s.icon;
        return (
          <div
            key={s.label}
            className={`flex-1 flex flex-col justify-between px-4 py-4 glass-card transition-colors ${
              s.highlight ? "!bg-indigo-500/10 !border-indigo-500/20" : ""
            }`}
          >
              <div className="flex items-center gap-2">
                <Icon
                  size={15}
                  weight="bold"
                  className={s.highlight ? "text-indigo-400" : "text-gray-500"}
                />
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                  {s.label}
                </span>
              </div>
              <div className="mt-2">
                <p
                  className={`text-xl font-black tabular-nums font-outfit ${
                    s.highlight ? "text-indigo-300" : "text-white"
                  }`}
                >
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
