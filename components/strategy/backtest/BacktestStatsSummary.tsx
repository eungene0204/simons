"use client";

import { BacktestResult } from "@/types/strategy";

interface Props {
  result: BacktestResult;
}

interface StatItem {
  label: string;
  value: string;
  color?: string;
}

interface Group {
  title: string;
  items: StatItem[];
}

function pct(v: number | undefined, decimals = 2) {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;
}

function num(v: number | undefined, decimals = 2) {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function krw(v: number) {
  if (Math.abs(v) >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(1)}억`;
  if (Math.abs(v) >= 10_000) return `${(v / 10_000).toFixed(0)}만`;
  return v.toLocaleString();
}

function returnColor(v: number | undefined) {
  if (v == null) return "text-gray-400";
  if (v > 0) return "text-main-red";
  if (v < 0) return "text-main-blue";
  return "text-gray-400";
}

function riskColor(v: number | undefined, invert = false) {
  if (v == null) return "text-gray-400";
  const good = invert ? v < 0 : v > 0;
  return good ? "text-main-red" : "text-main-blue";
}

export default function BacktestStatsSummary({ result }: Props) {
  const volatility =
    result.volatility ??
    (result.sharpe > 0 ? (result.cagr || 0) / result.sharpe : 0);

  const alpha = (result.cagr || 0) - (result.buyAndHoldReturn || 0);

  const groups: Group[] = [
    {
      title: "수익 성과",
      items: [
        {
          label: "총 수익률",
          value: pct(result.totalReturn),
          color: returnColor(result.totalReturn),
        },
        {
          label: "CAGR",
          value: pct(result.cagr),
          color: returnColor(result.cagr),
        },
        {
          label: "바이앤홀드",
          value: pct(result.buyAndHoldReturn),
          color: returnColor(result.buyAndHoldReturn),
        },
        {
          label: "초과 수익 (α)",
          value: pct(alpha),
          color: returnColor(alpha),
        },
        {
          label: "최종 자산",
          value: `${krw(result.finalEquity)}원`,
          color: "text-gray-300",
        },
        {
          label: "순 수익",
          value: `${result.finalEquity - result.initialCapital >= 0 ? "+" : ""}${krw(result.finalEquity - result.initialCapital)}원`,
          color: returnColor(result.finalEquity - result.initialCapital),
        },
      ],
    },
    {
      title: "리스크",
      items: [
        {
          label: "최대낙폭 (MDD)",
          value: `${result.maxDrawdown.toFixed(2)}%`,
          color: result.maxDrawdown > -20 ? "text-emerald-400" : result.maxDrawdown > -30 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "연간 변동성",
          value: `${volatility.toFixed(2)}%`,
          color: volatility < 15 ? "text-emerald-400" : volatility < 25 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "칼마 비율",
          value: result.calmar != null ? num(result.calmar) : (result.maxDrawdown !== 0 ? num((result.cagr || 0) / Math.abs(result.maxDrawdown)) : "—"),
          color: "text-gray-300",
        },
        {
          label: "샤프 지수",
          value: num(result.sharpe),
          color: result.sharpe >= 1.5 ? "text-emerald-400" : result.sharpe >= 1 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "소르티노",
          value: num(result.sortino),
          color: result.sortino >= 2 ? "text-emerald-400" : result.sortino >= 1 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "켈리 기준",
          value: pct(result.kelly),
          color: "text-gray-300",
        },
      ],
    },
    {
      title: "거래 통계",
      items: [
        {
          label: "총 거래 수",
          value: `${result.trades}회`,
          color: "text-gray-300",
        },
        {
          label: "승률",
          value: `${result.winRate.toFixed(1)}%`,
          color: result.winRate >= 55 ? "text-emerald-400" : result.winRate >= 50 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "손익비",
          value: num(result.profitFactor),
          color: result.profitFactor >= 2 ? "text-emerald-400" : result.profitFactor >= 1.5 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: "평균 수익",
          value: result.avgProfit != null ? pct(result.avgProfit) : "—",
          color: returnColor(result.avgProfit),
        },
        {
          label: "평균 손실",
          value: result.avgLoss != null ? pct(result.avgLoss) : "—",
          color: returnColor(result.avgLoss),
        },
        {
          label: "최대 연속승 / 연속패",
          value: result.maxConsecutiveWins != null && result.maxConsecutiveLosses != null
            ? `${result.maxConsecutiveWins}승 / ${result.maxConsecutiveLosses}패`
            : "—",
          color: "text-gray-300",
        },
      ],
    },
  ];

  return (
    <div className="mb-4 bg-[#0d0d0d] border border-white/5 rounded-2xl px-5 py-4">
      <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">
        상세 통계 요약
      </p>
      <div className="grid grid-cols-3 gap-0 divide-x divide-white/5">
        {groups.map((group) => (
          <div key={group.title} className="first:pl-0 pl-5 first:pr-5 pr-0">
            <p className="text-sm font-bold text-gray-400 mb-2.5">
              {group.title}
            </p>
            <div className="space-y-1.5">
              {group.items.map((item) => (
                <div key={item.label} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-gray-600 shrink-0">{item.label}</span>
                  <span className={`text-xs font-bold font-mono tabular-nums ${item.color ?? "text-gray-300"}`}>
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
