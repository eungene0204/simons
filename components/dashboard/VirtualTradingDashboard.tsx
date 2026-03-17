"use client";

import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  ReferenceLine,
  Cell,
} from "recharts";
import type { DashboardStats } from "@/app/api/virtual-account/[id]/dashboard/route";

interface Props {
  accountId: string;
  initialAmount: number;
}

const fmt = (n: number) =>
  new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }).format(n);

const fmtShort = (n: number) => {
  if (Math.abs(n) >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  if (Math.abs(n) >= 10_000) return `${(n / 10_000).toFixed(0)}만`;
  return fmt(n);
};

const pnlColor = (v: number) => (v >= 0 ? "#f87171" : "#60a5fa");

const StatCard = ({
  label,
  value,
  sub,
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  highlight?: "red" | "blue" | "neutral";
}) => {
  const color =
    highlight === "red"
      ? "text-red-400"
      : highlight === "blue"
      ? "text-blue-400"
      : "text-white";
  return (
    <div className="bg-[#1a1a1a] rounded-lg p-4">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className={`text-lg font-bold ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-[#111] border border-[#333] rounded-lg p-3 text-xs">
      <p className="text-gray-400 mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color ?? p.fill }}>
          {p.name}: {fmt(p.value)} 원
        </p>
      ))}
    </div>
  );
};

export default function VirtualTradingDashboard({ accountId, initialAmount }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [dailyRange, setDailyRange] = useState<30 | 60 | 90>(30);

  useEffect(() => {
    fetch(`/api/virtual-account/${accountId}/dashboard`)
      .then((r) => r.json())
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [accountId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        성과 데이터를 불러오는 중...
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
        성과 데이터를 불러올 수 없습니다.
      </div>
    );
  }

  const hasTrades = stats.totalTrades > 0;

  // 일별 PnL 슬라이스
  const dailyData = stats.dailyPnl.slice(-dailyRange);

  // 월별 레이블: "24.03" 형식
  const monthlyData = stats.monthlyPnl.map((m) => ({
    ...m,
    label: m.month.replace(/^(\d{4})-(\d{2})$/, (_, y, mo) => `${y.slice(2)}.${mo}`),
  }));

  // 종목별: 수익 Top5, 손실 Bottom5
  const topSymbols = stats.bySymbol.slice(0, 5);
  const bottomSymbols = [...stats.bySymbol].reverse().slice(0, 5).filter((s) => s.pnl < 0);

  return (
    <div className="space-y-6">
      {/* ── 종합 성과 카드 ─────────────────────────────────────────── */}
      <div>
        <h3 className="text-sm font-semibold text-gray-300 mb-3">종합 성과</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard
            label="총 실현 손익"
            value={`${stats.totalRealizedPnl >= 0 ? "+" : ""}${fmt(Math.round(stats.totalRealizedPnl))} 원`}
            highlight={stats.totalRealizedPnl >= 0 ? "red" : "blue"}
          />
          <StatCard
            label="수익률 (실현)"
            value={`${stats.totalReturn >= 0 ? "+" : ""}${stats.totalReturn.toFixed(2)}%`}
            sub={`초기자본 ${fmtShort(initialAmount)} 원 기준`}
            highlight={stats.totalReturn >= 0 ? "red" : "blue"}
          />
          <StatCard
            label="승률"
            value={hasTrades ? `${stats.winRate.toFixed(1)}%` : "-"}
            sub={hasTrades ? `${stats.winCount}승 ${stats.lossCount}패 (${stats.totalTrades}거래)` : "거래 없음"}
          />
          <StatCard
            label="손익비 (Profit Factor)"
            value={hasTrades ? (stats.profitFactor >= 999 ? "∞" : stats.profitFactor.toFixed(2)) : "-"}
            sub={hasTrades ? `평균 수익 ${fmtShort(stats.avgWin)}원 / 평균 손실 ${fmtShort(Math.abs(stats.avgLoss))}원` : undefined}
          />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
          <StatCard
            label="평균 수익 (승)"
            value={hasTrades && stats.winCount > 0 ? `+${fmtShort(stats.avgWin)} 원` : "-"}
            highlight="red"
          />
          <StatCard
            label="평균 손실 (패)"
            value={hasTrades && stats.lossCount > 0 ? `${fmtShort(stats.avgLoss)} 원` : "-"}
            highlight="blue"
          />
          <StatCard
            label="총 수수료"
            value={`-${fmt(Math.round(stats.totalFees))} 원`}
          />
          <StatCard
            label="총 증권거래세"
            value={`-${fmt(Math.round(stats.totalTax))} 원`}
          />
        </div>
      </div>

      {/* ── 일별 PnL ───────────────────────────────────────────────── */}
      <div className="bg-[#1a1a1a] rounded-lg p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-300">일별 PnL</h3>
          <div className="flex gap-1">
            {([30, 60, 90] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDailyRange(d)}
                className={`px-2.5 py-1 text-xs rounded transition-colors ${
                  dailyRange === d
                    ? "bg-[#333] text-white"
                    : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {d}일
              </button>
            ))}
          </div>
        </div>
        {!hasTrades ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-xs">
            거래 내역이 없습니다.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={dailyData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickFormatter={(v: string) => v.slice(5)}
                interval={Math.floor(dailyRange / 6)}
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickFormatter={(v) => fmtShort(v)}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#444" />
              <Bar dataKey="pnl" name="일일 PnL" radius={[2, 2, 0, 0]}>
                {dailyData.map((entry, index) => (
                  <Cell key={index} fill={pnlColor(entry.pnl)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── 누적 PnL 라인 ──────────────────────────────────────────── */}
      <div className="bg-[#1a1a1a] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">누적 실현 PnL</h3>
        {!hasTrades ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-xs">
            거래 내역이 없습니다.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={dailyData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickFormatter={(v: string) => v.slice(5)}
                interval={Math.floor(dailyRange / 6)}
              />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickFormatter={(v) => fmtShort(v)}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#444" />
              <Line
                type="monotone"
                dataKey="cumPnl"
                name="누적 PnL"
                stroke="#a78bfa"
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── 월별 PnL ───────────────────────────────────────────────── */}
      <div className="bg-[#1a1a1a] rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">월별 PnL (최근 12개월)</h3>
        {!hasTrades ? (
          <div className="flex items-center justify-center h-32 text-gray-500 text-xs">
            거래 내역이 없습니다.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={monthlyData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} />
              <YAxis
                tick={{ fill: "#6b7280", fontSize: 10 }}
                tickFormatter={(v) => fmtShort(v)}
                width={52}
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#444" />
              <Bar dataKey="pnl" name="월별 PnL" radius={[3, 3, 0, 0]}>
                {monthlyData.map((entry, index) => (
                  <Cell key={index} fill={pnlColor(entry.pnl)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── 종목별 성과 ────────────────────────────────────────────── */}
      {hasTrades && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* 수익 Top 5 */}
          <div className="bg-[#1a1a1a] rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-300 mb-3">수익 상위 종목</h3>
            {topSymbols.length === 0 ? (
              <p className="text-xs text-gray-500">수익 종목 없음</p>
            ) : (
              <div className="space-y-2">
                {topSymbols.map((s) => (
                  <div key={s.symbol} className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-white">{s.name}</p>
                      <p className="text-xs text-gray-500">{s.symbol} · {s.trades}거래 · 승률 {s.winRate.toFixed(0)}%</p>
                    </div>
                    <p className={`text-sm font-bold ${s.pnl >= 0 ? "text-red-400" : "text-blue-400"}`}>
                      {s.pnl >= 0 ? "+" : ""}{fmtShort(Math.round(s.pnl))} 원
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 손실 Bottom 5 */}
          <div className="bg-[#1a1a1a] rounded-lg p-4">
            <h3 className="text-sm font-semibold text-gray-300 mb-3">손실 하위 종목</h3>
            {bottomSymbols.length === 0 ? (
              <p className="text-xs text-gray-500">손실 종목 없음</p>
            ) : (
              <div className="space-y-2">
                {bottomSymbols.map((s) => (
                  <div key={s.symbol} className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-white">{s.name}</p>
                      <p className="text-xs text-gray-500">{s.symbol} · {s.trades}거래 · 승률 {s.winRate.toFixed(0)}%</p>
                    </div>
                    <p className="text-sm font-bold text-blue-400">
                      {fmtShort(Math.round(s.pnl))} 원
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 승률 도넛 대용 (텍스트 요약) ─────────────────────────── */}
      {hasTrades && (
        <div className="bg-[#1a1a1a] rounded-lg p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">승률 분포</h3>
          <div className="flex items-center gap-3 mb-2">
            <div className="flex-1 bg-[#111] rounded-full h-4 overflow-hidden flex">
              <div
                className="h-full bg-red-500 transition-all"
                style={{ width: `${stats.winRate}%` }}
              />
              <div
                className="h-full bg-blue-500 transition-all"
                style={{ width: `${100 - stats.winRate}%` }}
              />
            </div>
            <span className="text-sm font-bold text-white w-16 text-right">
              {stats.winRate.toFixed(1)}%
            </span>
          </div>
          <div className="flex gap-4 text-xs text-gray-400">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-red-500 inline-block" />
              승 {stats.winCount}회
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm bg-blue-500 inline-block" />
              패 {stats.lossCount}회
            </span>
            <span className="text-gray-500">총 {stats.totalTrades}거래</span>
          </div>
        </div>
      )}
    </div>
  );
}
