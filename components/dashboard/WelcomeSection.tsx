"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChartLineUp, Flask, Bank } from "phosphor-react";

interface Stats {
  strategyCount: number;
  backtestsThisWeek: number;
  virtualAccountCount: number;
}

function StatPill({
  label,
  value,
  loading,
}: {
  label: string;
  value: number;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5">
      <span className="text-[9px] uppercase tracking-widest text-gray-500 font-bold">{label}</span>
      {loading ? (
        <span className="text-xl font-black text-gray-600 font-outfit">--</span>
      ) : (
        <span className="text-xl font-black text-white font-outfit">{value}</span>
      )}
    </div>
  );
}

export default function WelcomeSection({ userName }: { userName: string }) {
  const [stats, setStats] = useState<Stats>({ strategyCount: 0, backtestsThisWeek: 0, virtualAccountCount: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    Promise.all([
      fetch("/api/strategy").then((r) => (r.ok ? r.json() : [])),
      fetch("/api/backtest/history").then((r) => (r.ok ? r.json() : [])),
      fetch("/api/virtual-account").then((r) => (r.ok ? r.json() : [])),
    ])
      .then(([strategies, history, accounts]) => {
        const thisWeek = (history as { timestamp: number }[]).filter(
          (h) => h.timestamp > weekAgo
        ).length;
        setStats({
          strategyCount: strategies.length,
          backtestsThisWeek: thisWeek,
          virtualAccountCount: accounts.length,
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="glass-card p-6 bg-gradient-to-br from-blue-600/[0.07] to-transparent border-white/[0.06] relative overflow-hidden">
      <div className="absolute top-0 right-0 w-80 h-80 bg-blue-500/[0.04] blur-[80px] rounded-full pointer-events-none" />
      <div className="relative z-10 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
        {/* Left: greeting + stats */}
        <div>
          <p className="text-xs uppercase tracking-widest text-gray-500 font-bold mb-1">
            퀀트 투자 플랫폼
          </p>
          <h1 className="text-2xl font-black text-white tracking-tight font-outfit">
            안녕하세요, <span className="text-blue-400">{userName}</span>님
          </h1>
          <div className="flex gap-3 mt-4">
            <StatPill label="보유 전략" value={stats.strategyCount} loading={loading} />
            <StatPill label="이번 주 백테스트" value={stats.backtestsThisWeek} loading={loading} />
            <StatPill label="가상계좌" value={stats.virtualAccountCount} loading={loading} />
          </div>
        </div>

        {/* Right: CTAs */}
        <div className="flex flex-col sm:flex-row md:flex-col gap-2 shrink-0 w-full md:w-auto">
          <Link
            href="/analytics"
            className="flex items-center justify-center gap-2 px-5 py-3 bg-blue-600/90 hover:bg-blue-600 text-white font-black text-sm rounded-xl transition-colors border border-blue-500/30"
          >
            <ChartLineUp size={16} weight="bold" />
            전략 만들기
          </Link>
          <Link
            href="/analytics"
            className="flex items-center justify-center gap-2 px-5 py-3 bg-white/[0.05] hover:bg-white/[0.08] text-white font-bold text-sm rounded-xl transition-colors border border-white/[0.08]"
          >
            <Flask size={16} weight="bold" />
            백테스트 보기
          </Link>
          <Link
            href="/virtual-account"
            className="flex items-center justify-center gap-2 px-5 py-3 bg-white/[0.05] hover:bg-white/[0.08] text-white font-bold text-sm rounded-xl transition-colors border border-white/[0.08]"
          >
            <Bank size={16} weight="bold" />
            가상매매
          </Link>
        </div>
      </div>
    </div>
  );
}
