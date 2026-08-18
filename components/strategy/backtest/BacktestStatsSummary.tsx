"use client";

import { BacktestResult } from "@/types/strategy";
import { formatProfitFactor } from "@/lib/format-profit-factor";
import { formatCompactNumberEn, t } from "@/lib/i18n";

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
  const compactEn = formatCompactNumberEn(v);
  if (compactEn !== null) return compactEn;
  if (Math.abs(v) >= 1_0000_0000) return t("{0}억", (v / 1_0000_0000).toFixed(1));
  if (Math.abs(v) >= 10_000) return t("{0}만", (v / 10_000).toFixed(0));
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

  // 초과 수익은 **같은 기간 기준**끼리 뺀다. 과거에는 연율값(CAGR)에서 벤치마크의
  // 구간 누적 수익률을 빼서 6년 백테스트에서 −48.5%p 같은 값이 나왔다(올바른 값은
  // 총수익률 − 벤치마크 = −29.2%p). 벤치마크가 구간 일부만 덮으면 두 수익률의 기간이
  // 달라 뺄셈 자체가 성립하지 않으므로 값을 내지 않는다(BacktestDashboard와 동일 규칙).
  const alpha = result.benchmarkPartial
    ? null
    : (result.totalReturn || 0) - (result.buyAndHoldReturn || 0);

  const groups: Group[] = [
    {
      title: t("수익 성과"),
      items: [
        {
          label: t("총 수익률"),
          value: pct(result.totalReturn),
          color: returnColor(result.totalReturn),
        },
        {
          label: "CAGR",
          value: pct(result.cagr),
          color: returnColor(result.cagr),
        },
        {
          label: result.benchmarkLabel?.replace(/\s*\(\d+\)$/, "") || t("벤치마크"),
          value: pct(result.buyAndHoldReturn),
          color: returnColor(result.buyAndHoldReturn),
        },
        {
          label: t("초과 수익 (α)"),
          value: alpha == null ? "—" : pct(alpha),
          color: returnColor(alpha ?? undefined),
        },
        {
          label: t("최종 자산"),
          value: t("{0}원", krw(result.finalEquity)),
          color: "text-gray-300",
        },
        {
          label: t("순 수익"),
          value: t("{0}{1}원", result.finalEquity - result.initialCapital >= 0 ? "+" : "", krw(result.finalEquity - result.initialCapital)),
          color: returnColor(result.finalEquity - result.initialCapital),
        },
      ],
    },
    {
      title: t("리스크"),
      items: [
        {
          label: t("최대낙폭 (MDD)"),
          value: `${result.maxDrawdown.toFixed(2)}%`,
          color: result.maxDrawdown > -20 ? "text-emerald-400" : result.maxDrawdown > -30 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("연간 변동성"),
          value: `${volatility.toFixed(2)}%`,
          color: volatility < 15 ? "text-emerald-400" : volatility < 25 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("칼마 비율"),
          value: result.calmar != null ? num(result.calmar) : (result.maxDrawdown !== 0 ? num((result.cagr || 0) / Math.abs(result.maxDrawdown)) : "—"),
          color: "text-gray-300",
        },
        {
          label: t("샤프 지수"),
          value: num(result.sharpe),
          color: result.sharpe >= 1.5 ? "text-emerald-400" : result.sharpe >= 1 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("소르티노"),
          value: num(result.sortino),
          color: result.sortino >= 2 ? "text-emerald-400" : result.sortino >= 1 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("켈리 기준"),
          value: result.kelly == null ? "—" : pct(result.kelly),
          color: "text-gray-300",
        },
      ],
    },
    {
      title: t("거래 통계"),
      items: [
        {
          label: t("총 거래 수"),
          value: t("{0}회", result.trades),
          color: "text-gray-300",
        },
        {
          label: t("승률"),
          value: `${result.winRate.toFixed(1)}%`,
          color: result.winRate >= 55 ? "text-emerald-400" : result.winRate >= 50 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("손익비"),
          value: formatProfitFactor(result.profitFactor),
          color: (result.profitFactor ?? Infinity) >= 2 ? "text-emerald-400" : (result.profitFactor ?? Infinity) >= 1.5 ? "text-yellow-400" : "text-red-400",
        },
        {
          label: t("평균 수익"),
          value: result.avgProfit != null ? pct(result.avgProfit) : "—",
          color: returnColor(result.avgProfit),
        },
        {
          // 백엔드는 평균 손실을 양수(절댓값)로 내려보내므로, 손실임을 드러내도록 음수로 표시
          label: t("평균 손실"),
          value: result.avgLoss != null ? pct(-result.avgLoss) : "—",
          color: returnColor(result.avgLoss != null ? -result.avgLoss : undefined),
        },
        {
          label: t("최대 연속승 / 연속패"),
          value: result.maxConsecutiveWins != null && result.maxConsecutiveLosses != null
            ? t("{0}승 / {1}패", result.maxConsecutiveWins, result.maxConsecutiveLosses)
            : "—",
          color: "text-gray-300",
        },
      ],
    },
  ];

  return (
    <div
      data-testid="backtest-stats-summary"
      className="mb-4 rounded-2xl border border-white/5 bg-[#0d0d0d] px-3 py-4 sm:px-4 lg:px-5"
    >
      <p className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">
        {t("상세 통계 요약")}
      </p>
      <div
        data-testid="backtest-stats-summary-grid"
        className="grid grid-cols-1 gap-0 divide-y divide-white/5 lg:grid-cols-3 lg:divide-x lg:divide-y-0"
      >
        {groups.map((group) => (
          <div
            key={group.title}
            data-testid="backtest-stats-summary-group"
            className="py-4 first:pt-0 last:pb-0 lg:py-0 lg:first:pl-0 lg:pl-5 lg:first:pr-5 lg:pr-0"
          >
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
