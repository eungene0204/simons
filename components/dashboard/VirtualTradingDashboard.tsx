"use client";

import { useEffect, useState, type ReactNode } from "react";
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

type MetricTone = "positive" | "negative" | "neutral";

const metricTone = (value: number): MetricTone =>
  value > 0 ? "positive" : value < 0 ? "negative" : "neutral";

const formatSignedCurrency = (
  value: number,
  formatter: (amount: number) => string = fmt
) => {
  const normalized = Object.is(value, -0) ? 0 : value;
  return `${normalized > 0 ? "+" : ""}${formatter(normalized)}원`;
};

const formatSignedPercent = (value: number) =>
  `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;

const pnlColor = (v: number) =>
  v > 0 ? "#f87171" : v < 0 ? "#60a5fa" : "#ffffff";

const axisStyle = { fill: "#6b7280", fontSize: 10 };

const valueTone = (v: number) =>
  v > 0
    ? "text-[var(--main-red)]"
    : v < 0
    ? "text-[var(--main-blue)]"
    : "text-white";

function MetricCell({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: MetricTone;
}) {
  const toneClass =
    tone === "positive"
      ? "text-[var(--main-red)]"
      : tone === "negative"
      ? "text-[var(--main-blue)]"
      : "text-white";

  return (
    <div className="p-3 sm:p-4 lg:p-5" data-testid="dashboard-metric-cell">
      <p className="text-xs font-bold uppercase tracking-widest text-gray-400">{label}</p>
      <p
        className={`mt-2 text-lg font-black font-outfit tabular-nums leading-none sm:text-xl lg:text-2xl ${toneClass}`}
        data-testid="dashboard-metric-value"
      >
        {value}
      </p>
      {sub && <p className="mt-1 text-[10px] font-bold text-gray-500">{sub}</p>}
    </div>
  );
}

function SectionTitle({
  title,
  description,
  right,
}: {
  title: string;
  description: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <h2 className="text-base font-black uppercase tracking-widest text-gray-400 font-outfit">
          {title}
        </h2>
        <p className="text-xs font-bold text-gray-500 mt-0.5">{description}</p>
      </div>
      {right}
    </div>
  );
}

function EmptyChartState() {
  return (
    <div className="flex h-48 items-center justify-center text-xs font-bold text-gray-500">
      거래 내역이 없습니다.
    </div>
  );
}

function SymbolList({
  items,
  emptyLabel,
}: {
  items: DashboardStats["bySymbol"];
  emptyLabel: string;
}) {
  if (items.length === 0) {
    return <p className="text-xs font-bold text-gray-500">{emptyLabel}</p>;
  }

  return (
    <div
      className="overflow-x-auto lg:overflow-x-visible"
      data-testid="symbol-list-scroll"
    >
      <div className="min-w-[440px] lg:min-w-0" data-testid="symbol-list-table">
        <div className="grid grid-cols-[minmax(0,1fr)_72px_84px_110px] gap-2 px-2 mb-2">
          <span className="text-xs font-bold uppercase tracking-widest text-gray-600">종목</span>
          <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">거래</span>
          <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">승률</span>
          <span className="text-xs font-bold uppercase tracking-widest text-gray-600 text-right">실현손익</span>
        </div>
        <div className="border-t border-white/[0.05] mb-1" />
        <div className="divide-y divide-white/[0.04]">
          {items.map((item) => (
            <div
              key={item.symbol}
              className="grid grid-cols-[minmax(0,1fr)_72px_84px_110px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-black text-white">{item.name}</p>
                <p className="text-[10px] font-bold text-gray-500">{item.symbol}</p>
              </div>
              <p className="text-right text-sm font-bold text-gray-400 tabular-nums">{item.trades}</p>
              <p className="text-right text-sm font-bold text-white tabular-nums">{item.winRate.toFixed(0)}%</p>
              <p className={`text-right text-sm font-black font-outfit tabular-nums ${valueTone(item.pnl)}`}>
                {formatSignedCurrency(Math.round(item.pnl), fmtShort)}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.08] bg-[#111] p-3 text-xs">
      <p className="mb-1 font-bold text-gray-400">{label}</p>
      {payload.map((item: any) => (
        <p key={item.name} style={{ color: item.color ?? item.fill }}>
          {item.name}: {fmt(item.value)} 원
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
      <div className="flex h-48 items-center justify-center text-sm font-bold text-gray-400">
        성과 데이터를 불러오는 중...
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="flex h-48 items-center justify-center text-sm font-bold text-gray-400">
        성과 데이터를 불러올 수 없습니다.
      </div>
    );
  }

  const hasTrades = stats.totalTrades > 0;
  const dailyData = stats.dailyPnl.slice(-dailyRange);
  const monthlyData = stats.monthlyPnl.map((m) => ({
    ...m,
    label: m.month.replace(/^(\d{4})-(\d{2})$/, (_, y, mo) => `${y.slice(2)}.${mo}`),
  }));
  const topSymbols = stats.bySymbol.slice(0, 5);
  const bottomSymbols = [...stats.bySymbol].reverse().slice(0, 5).filter((s) => s.pnl < 0);
  const totalFees = -Math.abs(stats.totalFees);
  const totalTax = -Math.abs(stats.totalTax);
  const metricRows = [
    [
      {
        label: "총 실현 손익",
        value: formatSignedCurrency(Math.round(stats.totalRealizedPnl)),
        sub: "누적 매도 체결 기준",
        tone: metricTone(stats.totalRealizedPnl),
      },
      {
        label: "실현 수익률",
        value: formatSignedPercent(stats.totalReturn),
        sub: `초기 자본 ${fmtShort(initialAmount)}원 기준`,
        tone: metricTone(stats.totalReturn),
      },
      {
        label: "승률",
        value: hasTrades ? `${stats.winRate.toFixed(1)}%` : "-",
        sub: hasTrades ? `${stats.winCount}승 ${stats.lossCount}패` : "거래 없음",
        tone: "neutral",
      },
      {
        label: "손익비",
        value: hasTrades ? (stats.profitFactor >= 999 ? "∞" : stats.profitFactor.toFixed(2)) : "-",
        sub: hasTrades ? `총 ${stats.totalTrades}건 체결` : "거래 없음",
        tone: "neutral",
      },
    ],
    [
      {
        label: "평균 수익",
        value: formatSignedCurrency(stats.avgWin, fmtShort),
        sub: "이익 거래 평균",
        tone: metricTone(stats.avgWin),
      },
      {
        label: "평균 손실",
        value: formatSignedCurrency(stats.avgLoss, fmtShort),
        sub: "손실 거래 평균",
        tone: metricTone(stats.avgLoss),
      },
      {
        label: "총 수수료",
        value: formatSignedCurrency(Math.round(totalFees)),
        sub: "누적 비용",
        tone: metricTone(totalFees),
      },
      {
        label: "총 증권거래세",
        value: formatSignedCurrency(Math.round(totalTax)),
        sub: "누적 비용",
        tone: metricTone(totalTax),
      },
    ],
  ] as const;

  return (
    <div className="divide-y divide-white/[0.08]">
        <div className="divide-y divide-white/[0.08]">
          {metricRows.map((row, rowIndex) => (
            <div
              key={rowIndex}
              className="grid grid-cols-2 xl:grid-cols-4 xl:divide-x divide-white/[0.08]"
            >
              {row.map((metric) => (
                <MetricCell
                  key={metric.label}
                  label={metric.label}
                  value={metric.value}
                  sub={metric.sub}
                  tone={metric.tone}
                />
              ))}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
          <div className="lg:col-span-6 p-5">
            <SectionTitle
              title="일별 손익"
              description="최근 기간별 실현 손익 변동"
              right={
                <div className="flex gap-1">
                  {([30, 60, 90] as const).map((range) => (
                    <button
                      key={range}
                      onClick={() => setDailyRange(range)}
                      className={`rounded-md px-2.5 py-1 text-xs font-bold transition-colors ${
                        dailyRange === range
                          ? "bg-white/[0.08] text-white"
                          : "text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {range}일
                    </button>
                  ))}
                </div>
              }
            />
            {hasTrades ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={dailyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={axisStyle}
                    tickFormatter={(v: string) => v.slice(5)}
                    interval={Math.floor(dailyRange / 6)}
                  />
                  <YAxis tick={axisStyle} tickFormatter={(v) => fmtShort(v)} width={52} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="pnl" name="일별 PnL" radius={[8, 8, 0, 0]}>
                    {dailyData.map((entry, index) => (
                      <Cell key={index} fill={pnlColor(entry.pnl)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChartState />
            )}
          </div>

          <div className="lg:col-span-4 p-5">
            <SectionTitle
              title="승률 분포"
              description="체결 거래 기준 승패 비중"
              right={
                <div className="text-right">
                  <p className="text-2xl font-black font-outfit tabular-nums text-white">
                    {hasTrades ? stats.winRate.toFixed(1) : "-"}{hasTrades ? "%" : ""}
                  </p>
                  <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                    Win Rate
                  </p>
                </div>
              }
            />
            {hasTrades ? (
              <div className="space-y-5">
                <div className="overflow-hidden rounded-xl bg-white/[0.04]">
                  <div className="flex h-5">
                    <div
                      className="h-full bg-[var(--main-red)]"
                      style={{ width: `${stats.winRate}%` }}
                    />
                    <div
                      className="h-full bg-[var(--main-blue)]"
                      style={{ width: `${100 - stats.winRate}%` }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-white/[0.04] p-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-400">승</p>
                    <p className="mt-2 text-2xl font-black font-outfit tabular-nums text-[var(--main-red)]">
                      {stats.winCount}
                    </p>
                  </div>
                  <div className="rounded-xl bg-white/[0.04] p-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-400">패</p>
                    <p className="mt-2 text-2xl font-black font-outfit tabular-nums text-[var(--main-blue)]">
                      {stats.lossCount}
                    </p>
                  </div>
                </div>
                <div className="divide-y divide-white/[0.08]">
                  <div className="py-3 flex items-center justify-between gap-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-600">평균 수익</p>
                    <p className={`text-sm font-black font-outfit tabular-nums ${valueTone(stats.avgWin)}`}>
                      {formatSignedCurrency(stats.avgWin, fmtShort)}
                    </p>
                  </div>
                  <div className="py-3 flex items-center justify-between gap-4">
                    <p className="text-xs font-bold uppercase tracking-widest text-gray-600">평균 손실</p>
                    <p className={`text-sm font-black font-outfit tabular-nums ${valueTone(stats.avgLoss)}`}>
                      {formatSignedCurrency(stats.avgLoss, fmtShort)}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <EmptyChartState />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
          <div className="lg:col-span-4 p-5">
            <SectionTitle
              title="누적 손익"
              description="일별 누적 실현 손익 추이"
              right={undefined}
            />
            {hasTrades ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={dailyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={axisStyle}
                    tickFormatter={(v: string) => v.slice(5)}
                    interval={Math.floor(dailyRange / 6)}
                  />
                  <YAxis tick={axisStyle} tickFormatter={(v) => fmtShort(v)} width={52} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Line
                    type="monotone"
                    dataKey="cumPnl"
                    name="누적 PnL"
                    stroke="#e5e7eb"
                    dot={false}
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChartState />
            )}
          </div>

          <div className="lg:col-span-6 p-5">
            <SectionTitle
              title="월별 손익"
              description="최근 12개월 실현 손익 분포"
              right={
                <span className="inline-flex items-center rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-bold text-gray-400">
                  12M
                </span>
              }
            />
            {hasTrades ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={monthlyData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" vertical={false} />
                  <XAxis dataKey="label" tick={axisStyle} />
                  <YAxis tick={axisStyle} tickFormatter={(v) => fmtShort(v)} width={52} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={0} stroke="#444" />
                  <Bar dataKey="pnl" name="월별 PnL" radius={[8, 8, 0, 0]}>
                    {monthlyData.map((entry, index) => (
                      <Cell key={index} fill={pnlColor(entry.pnl)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChartState />
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
          <div className="lg:col-span-5 p-5">
            <SectionTitle
              title="수익 상위 종목"
              description="실현 손익 기준 상위 5개"
            />
            <SymbolList items={topSymbols} emptyLabel="수익 종목이 없습니다." />
          </div>

          <div className="lg:col-span-5 p-5">
            <SectionTitle
              title="손실 하위 종목"
              description="실현 손익 기준 하위 5개"
            />
            <SymbolList items={bottomSymbols} emptyLabel="손실 종목이 없습니다." />
          </div>
        </div>
    </div>
  );
}
