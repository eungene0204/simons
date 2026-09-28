"use client";

import type { AnalyticsHistogramBin, AnalyticsResult, AnalyticsStat } from "@/types/strategy";
import { formatCompactNumberEn, getLanguage, t } from "@/lib/i18n";
import { Question } from "phosphor-react";
import { explainFactorEstimate, interpretFactor, summarizeFactorPattern, summarizeFactorStatistics } from "./factorInterpretation";

interface Props {
  analytics: AnalyticsResult;
  dates: string[];
  currency?: "krw" | "usd";
  stockMetadata?: Record<string, { name: string; sector: string }>;
}

const POSITIVE = "#ef4444";
const NEGATIVE = "#377af4";
const METRIC_GUIDELINES = {
  annualTurnover: [
    { range: "< 100%", levelKo: "낮음", levelEn: "Low", ko: "장기보유형", en: "Longer holding style" },
    { range: "100–300%", levelKo: "보통", levelEn: "Moderate", ko: "일반적인 중저빈도 전략", en: "Typical low-to-medium frequency" },
    { range: "300–1000%", levelKo: "높음", levelEn: "High", ko: "거래비용 영향 큼", en: "Trading costs have greater impact" },
    { range: "> 1000%", levelKo: "매우 높음", levelEn: "Very high", ko: "슬리피지·수수료 검증 필수", en: "Validate slippage and fees" },
  ],
  periodTurnover: [
    { range: "—", levelKo: "참고", levelEn: "Reference", ko: "기간 길이가 달라 고정 구간으로 분류하지 않습니다. 같은 기간의 결과끼리 비교하세요.", en: "No fixed bands are used because period length varies. Compare results covering the same period." },
  ],
  var95: [
    { range: "< 1%", levelKo: "낮음", levelEn: "Low", ko: "일일 변동 위험 낮음", en: "Lower daily loss threshold" },
    { range: "1–2%", levelKo: "보통", levelEn: "Moderate", ko: "비교적 안정적", en: "Moderate range" },
    { range: "2–4%", levelKo: "높음", levelEn: "High", ko: "공격적인 전략", en: "More aggressive profile" },
    { range: "> 4%", levelKo: "매우 높음", levelEn: "Very high", ko: "큰 일일 손실 가능성", en: "Larger daily losses in the tail" },
  ],
  cvar95: [
    { range: "< 1.5%", levelKo: "낮음", levelEn: "Low", ko: "꼬리위험 작음", en: "Smaller tail loss" },
    { range: "1.5–3%", levelKo: "보통", levelEn: "Moderate", ko: "관리 가능한 수준", en: "Moderate range" },
    { range: "3–6%", levelKo: "높음", levelEn: "High", ko: "극단 손실 주의", en: "Larger extreme losses" },
    { range: "> 6%", levelKo: "매우 높음", levelEn: "Very high", ko: "꼬리위험 큼", en: "Greater tail risk" },
  ],
  var99: [
    { range: "< 2%", levelKo: "낮음", levelEn: "Low", ko: "극단 손실 위험 낮음", en: "Lower extreme-loss threshold" },
    { range: "2–4%", levelKo: "보통", levelEn: "Moderate", ko: "중간 수준", en: "Moderate range" },
    { range: "4–7%", levelKo: "높음", levelEn: "High", ko: "높은 위험", en: "Higher extreme-loss threshold" },
    { range: "> 7%", levelKo: "매우 높음", levelEn: "Very high", ko: "큰 일일 충격 가능", en: "Larger daily shocks in the tail" },
  ],
  cvar99: [
    { range: "< 3%", levelKo: "낮음", levelEn: "Low", ko: "최악 구간 손실 제한적", en: "Lower average loss in the worst tail" },
    { range: "3–6%", levelKo: "보통", levelEn: "Moderate", ko: "중간 수준", en: "Moderate range" },
    { range: "6–10%", levelKo: "높음", levelEn: "High", ko: "매우 공격적", en: "More aggressive profile" },
    { range: "> 10%", levelKo: "매우 높음", levelEn: "Very high", ko: "극단적 꼬리위험", en: "Extreme tail risk" },
  ],
} as const;

function MetricHelp({ id, label, ko, en, guidelineKey, align = "left" }: {
  id: string;
  label: string;
  ko: string;
  en: string;
  guidelineKey: keyof typeof METRIC_GUIDELINES;
  align?: "left" | "right" | "right-mobile" | "right-sm";
}) {
  const isEnglish = getLanguage() === "en";
  const guidelines = METRIC_GUIDELINES[guidelineKey];
  const alignClass = {
    left: "left-0",
    right: "right-0",
    "right-mobile": "right-0 sm:left-0 sm:right-auto",
    "right-sm": "left-0 sm:left-auto sm:right-0",
  }[align];
  return (
    <span className="group relative inline-flex shrink-0">
      <button
        type="button"
        aria-label={t(isEnglish ? `${label} help` : `${label} 도움말`)}
        aria-describedby={id}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full text-gray-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
      >
        <Question className="h-3 w-3" weight="bold" />
      </button>
      <div
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute top-full z-30 mt-2 w-[360px] max-w-[calc(100vw-2rem)] rounded-md border border-white/[0.10] bg-[var(--card-bg)] p-3 text-xs font-medium leading-relaxed text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 ${alignClass}`}
      >
        {t(isEnglish ? en : ko)}
        <div className="mt-3 border-t border-white/[0.08] pt-2">
          <div className="mb-1 font-black text-[var(--text-label)]">{t(isEnglish ? "Approximate guide interpretation" : "대략적 가이드 해석")}</div>
          <div className="mb-1 grid grid-cols-[72px_56px_minmax(0,1fr)] gap-2 text-[10px] font-bold text-[var(--text-label)]">
            <span>{t(isEnglish ? "Range" : "범위")}</span>
            <span>{t(isEnglish ? "Level" : "수준")}</span>
            <span>{t(isEnglish ? "Interpretation" : "해석")}</span>
          </div>
          <div className="divide-y divide-white/[0.06]">
            {guidelines.map((item) => (
              <div key={item.range} className="grid grid-cols-[72px_56px_minmax(0,1fr)] gap-2 py-1.5">
                <span className="tabular-nums">{item.range}</span>
                <span>{t(isEnglish ? item.levelEn : item.levelKo)}</span>
                <span>{t(isEnglish ? item.en : item.ko)}</span>
              </div>
            ))}
          </div>
          <div className="mt-2 text-[10px] text-[var(--text-label)]">
            {t(isEnglish
              ? "Approximate reference bands only. Results can vary with the backtest period and assumptions."
              : "대략적인 참고 구간이며 백테스트 기간과 설정에 따라 해석이 달라질 수 있습니다.")}
          </div>
        </div>
      </div>
    </span>
  );
}

function DefinitionHelp({ id, label, ko, en, align = "left" }: { id: string; label: string; ko: string; en: string; align?: "left" | "right" }) {
  const isEnglish = getLanguage() === "en";
  return (
    <span className="group relative inline-flex shrink-0">
      <button
        type="button"
        aria-label={t(isEnglish ? `${label} help` : `${label} 도움말`)}
        aria-describedby={id}
        className="flex h-4 w-4 cursor-help items-center justify-center rounded-full text-gray-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
      >
        <Question className="h-3 w-3" weight="bold" />
      </button>
      <div
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute ${align === "right" ? "right-0" : "left-0"} top-full z-30 mt-2 w-[360px] max-w-[calc(100vw-2rem)] rounded-md border border-white/[0.10] bg-[var(--card-bg)] p-3 text-xs font-medium leading-relaxed text-white opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100`}
      >
        {t(isEnglish ? en : ko)}
      </div>
    </span>
  );
}

function LiquidityMetricLabel({ id, label, ko, en, align }: { id: string; label: string; ko: string; en: string; align?: "left" | "right" }) {
  return (
    <dt className="flex items-center gap-1 text-[var(--text-label)]">
      <span>{label}</span>
      <DefinitionHelp id={id} label={label} ko={ko} en={en} align={align} />
    </dt>
  );
}

function pct(v: number | null | undefined, digits = 2, signed = true): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function num(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function money(v: number | null | undefined, currency: "krw" | "usd"): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (currency === "usd") return `$${Math.round(v).toLocaleString()}`;
  const compactEn = formatCompactNumberEn(v);
  if (compactEn !== null) return compactEn;
  if (Math.abs(v) >= 1_0000_0000) return t("{0}억", (v / 1_0000_0000).toFixed(1));
  if (Math.abs(v) >= 10_000) return t("{0}만", (v / 10_000).toFixed(0));
  return `${Math.round(v).toLocaleString()}원`;
}

function liquidityInterpretation(liquidity: AnalyticsResult["liquidity"], capital: string, english: boolean): string {
  const { orders, meanParticipation, p95Participation, maxParticipation, shareAboveCap, cap } = liquidity;
  const orderSummary = english
    ? "Across " + orders + " orders, participation averaged " + pct(meanParticipation, 2, false) + "; the top 5% threshold was " + pct(p95Participation, 2, false) + ", and the maximum was " + pct(maxParticipation, 2, false) + "."
    : "주문 " + orders + "건의 평균 참여율은 " + pct(meanParticipation, 2, false) + "이고, 큰 주문 상위 5%의 기준은 " + pct(p95Participation, 2, false) + ", 최대는 " + pct(maxParticipation, 2, false) + "였습니다.";
  const withinCap = maxParticipation != null && maxParticipation <= cap && shareAboveCap === 0;
  const orderInterpretation = english
    ? withinCap
      ? "All tested orders stayed within the " + cap + "% threshold, so order sizes were small relative to average traded value in this backtest."
      : pct(shareAboveCap, 1, false) + " of orders exceeded the " + cap + "% threshold, so some orders were large relative to average traded value."
    : withinCap
      ? "모든 주문이 " + cap + "% 기준 안에 있어, 이 백테스트에서는 거래대금 대비 주문 규모가 작은 편이었습니다."
      : "전체 주문 중 " + pct(shareAboveCap, 1, false) + "가 " + cap + "% 기준을 넘어, 거래대금에 비해 큰 주문이 일부 있었습니다.";
  const capitalInterpretation = english
    ? "Estimated capital at that threshold is " + capital + ", based on this backtest."
    : cap + "% 기준에 맞춘 운용 가능 자본은 " + capital + "으로, 이 백테스트 기준 추정치입니다.";
  return orderSummary + " " + orderInterpretation + " " + capitalInterpretation;
}

function summarizeRollingRisk(
  rollingSharpe: Array<number | null>,
  rollingBeta: Array<number | null>,
  window: number,
  english: boolean,
): string {
  const sharpe = rollingSharpe.filter((value): value is number => value != null && Number.isFinite(value));
  const beta = rollingBeta.filter((value): value is number => value != null && Number.isFinite(value));
  const parts = [
    english
      ? `Each point uses the previous ${window} trading days.`
      : `각 값은 직전 ${window}거래일을 기준으로 계산됩니다.`,
  ];

  if (sharpe.length >= 2) {
    const min = Math.min(...sharpe);
    const max = Math.max(...sharpe);
    const direction = min < 0 && max > 0
      ? (english ? "It crossed zero, so risk-adjusted returns were positive in some periods and negative in others." : "0 위아래를 오가며, 위험 대비 수익이 양수인 구간과 음수인 구간이 모두 있었습니다.")
      : min >= 0
        ? (english ? "It stayed at or above zero, indicating non-negative risk-adjusted returns across these windows." : "0 이상을 유지해, 이 구간들에서는 위험 대비 수익이 음수가 아니었습니다.")
        : (english ? "It stayed below zero, indicating negative risk-adjusted returns across these windows." : "계속 0 아래에 있어, 이 구간들에서는 위험 대비 수익이 음수였습니다.");
    parts.push(english
      ? `The rolling Sharpe ranged from ${min.toFixed(2)} to ${max.toFixed(2)}. ${direction}`
      : `롤링 샤프는 ${min.toFixed(2)}에서 ${max.toFixed(2)} 사이였습니다. ${direction}`);
  }

  if (beta.length >= 2) {
    const min = Math.min(...beta);
    const max = Math.max(...beta);
    const direction = min < 0 && max > 0
      ? (english ? "The relationship shifted between moving with and against the benchmark." : "벤치마크와 같은 방향으로 움직이는 구간과 반대 방향으로 움직이는 구간이 모두 있었습니다.")
      : min < 0
        ? (english ? "Some windows moved opposite to the benchmark." : "벤치마크와 반대 방향으로 움직인 구간이 있었습니다.")
        : min <= 0.1 && max >= 1
          ? (english ? "Sensitivity ranged from near zero to greater than the benchmark's." : "벤치마크 변화에 거의 반응하지 않은 구간부터 더 크게 반응한 구간까지 있어, 시장 민감도가 시기별로 달랐습니다.")
          : max < 1
            ? (english ? "The strategy generally moved less than the benchmark across these windows." : "이 구간들에서는 대체로 벤치마크보다 작게 움직였습니다.")
            : (english ? "The strategy was at least as sensitive as the benchmark across these windows." : "이 구간들에서는 벤치마크와 비슷하거나 더 크게 움직였습니다.");
    parts.push(english
      ? `The rolling beta ranged from ${min.toFixed(2)} to ${max.toFixed(2)}. Beta describes sensitivity to benchmark moves: 1 is similar-sized movement, while 0 is little co-movement. ${direction}`
      : `롤링 베타는 ${min.toFixed(2)}에서 ${max.toFixed(2)} 사이였습니다. 베타는 벤치마크 움직임에 대한 민감도로, 1은 비슷한 크기의 움직임, 0은 함께 움직이는 정도가 작음을 뜻합니다. ${direction}`);
  }

  if (sharpe.length < 2 && beta.length < 2) {
    parts.push(english ? "There is not enough data to interpret these charts." : "표본이 부족해 두 차트를 해석하기 어렵습니다.");
  }
  return parts.join(" ");
}

function colorClass(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  return v > 0 ? "text-main-red" : v < 0 ? "text-main-blue" : "text-gray-400";
}

/** 상관계수 셀 배경 — 높을수록 붉게(같이 움직임), 낮을수록 푸르게(분산 효과). */
function corrStyle(v: number | null): { background: string } {
  if (v == null || !Number.isFinite(v)) return { background: "transparent" };
  const a = Math.min(Math.abs(v), 1) * 0.45;
  return { background: v >= 0 ? `rgba(239,68,68,${a})` : `rgba(55,122,244,${a})` };
}

function binLabel(bin: AnalyticsHistogramBin): string {
  const unit = bin.unit === "days" ? t("일") : "%";
  if (bin.from == null) return `< ${bin.to}${unit}`;
  if (bin.to == null) return `≥ ${bin.from}${unit}`;
  return `${bin.from}~${bin.to}${unit}`;
}

function Histogram({ bins, color, ariaLabel }: { bins: AnalyticsHistogramBin[]; color: (bin: AnalyticsHistogramBin) => string; ariaLabel: string }) {
  const max = Math.max(1, ...bins.map((b) => b.count));
  const width = 100 / Math.max(1, bins.length);
  return (
    <div>
      <svg viewBox="0 0 100 40" className="h-28 w-full" role="img" aria-label={ariaLabel} preserveAspectRatio="none">
        {bins.map((b, i) => {
          const h = (b.count / max) * 34;
          return <rect key={i} x={i * width + width * 0.1} y={38 - h} width={width * 0.8} height={h} fill={color(b)} opacity={0.85} />;
        })}
      </svg>
      <div className="mt-1 grid text-[9px] font-bold text-[var(--text-label)]" style={{ gridTemplateColumns: `repeat(${bins.length}, minmax(0, 1fr))` }}>
        {bins.map((b, i) => (
          <span key={i} className="truncate text-center" title={`${binLabel(b)}: ${b.count}`}>{b.count}</span>
        ))}
      </div>
      <div className="grid text-[8px] text-[var(--text-label)]" style={{ gridTemplateColumns: `repeat(${bins.length}, minmax(0, 1fr))` }}>
        {bins.map((b, i) => (
          <span key={i} className="truncate text-center">{binLabel(b)}</span>
        ))}
      </div>
    </div>
  );
}

function LineSeries({ values, dates, ariaLabel, zero }: { values: Array<number | null>; dates: string[]; ariaLabel: string; zero?: boolean }) {
  const finite = values.filter((v): v is number => v != null && Number.isFinite(v));
  if (finite.length < 2) return <p className="text-xs font-bold text-[var(--text-label)]">{t("표본이 부족해 그릴 수 없습니다.")}</p>;
  const min = Math.min(...finite, zero ? 0 : Infinity);
  const max = Math.max(...finite, zero ? 0 : -Infinity);
  const span = max - min || 1;
  const n = values.length;
  let d = "";
  let pen = false;
  values.forEach((v, i) => {
    if (v == null || !Number.isFinite(v)) { pen = false; return; }
    const x = (i / Math.max(1, n - 1)) * 100;
    const y = 38 - ((v - min) / span) * 36;
    d += `${pen ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)} `;
    pen = true;
  });
  const zeroY = zero ? 38 - ((0 - min) / span) * 36 : null;
  return (
    <div>
      <svg viewBox="0 0 100 40" className="h-28 w-full" role="img" aria-label={ariaLabel} preserveAspectRatio="none">
        {zeroY != null && <line x1={0} x2={100} y1={zeroY} y2={zeroY} stroke="#525252" strokeWidth={0.3} strokeDasharray="1 1" />}
        <path d={d} fill="none" stroke="#38bdf8" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[9px] font-bold text-[var(--text-label)]">
        <span>{dates[0]}</span>
        <span>{t("최소 {0} · 최대 {1}", num(min), num(max))}</span>
        <span>{dates[dates.length - 1]}</span>
      </div>
    </div>
  );
}

function StatRow({ label, stat }: { label: string; stat: AnalyticsStat | null }) {
  if (!stat) return null;
  return (
    <tr className="transition-colors duration-150 hover:bg-white/[0.02]">
      <td className="whitespace-nowrap py-3 pl-2 pr-4 text-left text-sm font-black text-white">{label}</td>
      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit">{pct(stat.mean)}</td>
      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit">{pct(stat.median)}</td>
      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit">{pct(stat.worst)}</td>
      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit">{pct(stat.best)}</td>
      <td className="px-3 py-3 text-right text-sm font-black tabular-nums font-outfit text-[var(--text-label)]">{stat.count}</td>
    </tr>
  );
}

const FACTOR_LABELS: Record<string, string> = { MKT: "시장", SMB: "규모(소형−대형)", HML: "가치(저PBR−고PBR)", MOM: "모멘텀(12-1)" };
const TH = "px-3 py-2 text-xs font-bold uppercase tracking-widest text-[var(--text-label)] whitespace-nowrap";
const TD = "px-3 py-3 text-sm font-black tabular-nums font-outfit";

export default function AdvancedAnalyticsSection({ analytics, dates, currency = "krw", stockMetadata = {} }: Props) {
  const a = analytics;
  const td = a.tradeDistribution;
  const fe = a.factorExposure;
  const isEnglish = getLanguage() === "en";

  return (
    <section data-testid="backtest-advanced-analytics" className="flex flex-col gap-4">
        <div className="grid gap-x-8 gap-y-4 lg:grid-cols-2">
          {/* 귀인 */}
          <div className="border-t border-white/[0.08] py-4 lg:col-span-2" data-testid="analytics-attribution">
            <div className="mb-2 text-sm font-black text-white">{t("성과 귀인 (초기 자본 대비 기여도)")}</div>
            {a.attribution.symbols.length === 0 ? (
              <p className="mt-2 text-xs font-bold text-[var(--text-label)]">{t("완결된 거래가 없어 기여도를 계산하지 못했습니다.")}</p>
            ) : (
              <div className="mt-2 grid gap-4 lg:grid-cols-2">
                <div className="min-w-0">
                  <div className="text-xs font-bold text-[var(--text-label)]">{t(getLanguage() === "en" ? "By symbol" : "종목별 기여도")}</div>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full min-w-[560px] border-collapse">
                      <thead>
                        <tr><th className={`${TH} text-left`}>{t("종목")}</th><th className={`${TH} text-left`}>{t("섹터")}</th><th className={`${TH} text-right`}>{t("손익")}</th><th className={`${TH} text-right`}>{t("기여도")}</th></tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.04]">
                        {a.attribution.symbols.map((r) => (
                          <tr key={r.symbol} className="transition-colors duration-150 hover:bg-white/[0.02]">
                            <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">{r.name} <span className="text-[var(--text-label)]">{r.symbol}</span></td>
                            <td className="px-3 py-3 text-sm font-bold text-[var(--text-label)]">{r.sector}</td>
                            <td className={`${TD} text-right ${colorClass(r.pnl)}`}>{money(r.pnl, currency)}</td>
                            <td className={`${TD} text-right ${colorClass(r.contributionPct)}`}>{pct(r.contributionPct)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold text-[var(--text-label)]">{t("섹터별 기여도")}</div>
                  <div className="mt-2 divide-y divide-white/[0.04] border-t border-white/[0.05]">
                    {a.attribution.sectors.slice(0, 8).map((s) => (
                      <div key={s.sector} className="flex justify-between py-2 text-sm font-bold transition-colors duration-150 hover:bg-white/[0.02]"><span className="text-white">{s.sector} <span className="text-[var(--text-label)]">({s.symbols})</span></span><span className={colorClass(s.contributionPct)}>{pct(s.contributionPct)}</span></div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 팩터 노출 */}
          <div className="border-t border-white/[0.08] py-4" data-testid="analytics-factor">
            <div className="mb-1 text-sm font-black text-white">{t(isEnglish ? "Factor exposure: what did the strategy move with?" : "팩터 노출: 전략은 무엇과 함께 움직였나요?")}</div>
            <p className="text-xs leading-relaxed text-[var(--text-label)] sm:text-sm">
              {t(isEnglish
                ? "This compares the strategy's past returns with the market, company size, PBR, and recent price trends."
                : "과거 수익률을 시장, 기업 규모, PBR, 최근 주가 흐름과 비교한 결과입니다.")}
            </p>
            {!fe.available ? (
              <p className="mt-2 text-xs font-bold text-[var(--text-label)]">
                {fe.reason === "universe_too_small"
                  ? t("유니버스가 {0}종목이라 팩터 포트폴리오를 만들 수 없습니다(최소 {1}종목).", fe.symbols ?? 0, fe.minSymbols ?? 30)
                  : fe.reason === "too_few_observations"
                    ? t("관측이 {0}일로 부족합니다(최소 60일).", fe.observations ?? 0)
                    : t("팩터 자료(시가총액·PBR·모멘텀)가 없어 계산하지 못했습니다.")}
              </p>
            ) : (
              <>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[640px] border-collapse">
                    <thead>
                      <tr><th className={`${TH} text-left`}>{t("팩터")}</th><th className={`${TH} text-right`}>{t("베타")}</th><th className={`${TH} text-right`}>t</th><th className={`${TH} text-left`}>{t(isEnglish ? "Interpretation" : "해석")}</th></tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04]">
                      {(fe.loadings ?? []).map((l) => (
                        <tr key={l.factor} className="transition-colors duration-150 hover:bg-white/[0.02]">
                          <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">{t(FACTOR_LABELS[l.factor] ?? l.factor)}</td>
                          <td className={`${TD} text-right ${colorClass(l.beta)}`}>{num(l.beta)}</td>
                          <td className={`${TD} text-right text-[var(--text-label)]`}>{num(l.tStat, 1)}</td>
                          <td className="px-3 py-3 text-sm font-bold leading-relaxed text-gray-300">{t(interpretFactor(l, isEnglish))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs font-bold text-gray-400 sm:text-sm">
                  {t("알파(연환산) {0} (t={1}) · R² {2} · 관측 {3}일 · 유니버스 {4}종목", pct(fe.alphaAnnualPct), num(fe.alphaTStat, 1), num(fe.r2), fe.observations ?? 0, fe.symbols ?? 0)}
                </p>
                <div className="mt-3 rounded-lg bg-white/[0.03] p-3" data-testid="factor-interpretation-summary">
                  <div className="mb-2 text-sm font-black text-white sm:text-base">{t(isEnglish ? "In plain language" : "한눈에 보는 해석")}</div>
                  <p className="text-sm leading-relaxed text-gray-300 sm:text-base">{t(summarizeFactorPattern(fe, isEnglish))}</p>
                  <div className="mt-4 border-t border-white/[0.08] pt-3">
                    <div className="mb-2 text-sm font-black text-white">{t(isEnglish ? "What the numbers say" : "숫자가 말하는 것")}</div>
                    <p className="text-sm leading-relaxed text-gray-300 sm:text-base">{t(summarizeFactorStatistics(fe, isEnglish))}</p>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-gray-300 sm:text-base">{t(explainFactorEstimate(fe, isEnglish))}</p>
                  <p className="mt-3 text-xs leading-relaxed text-[var(--text-label)] sm:text-sm">
                    {t(isEnglish
                      ? "The market comparison uses the benchmark. The other three compare returns of the top and bottom 30% of stocks in this backtest each month; they are not official Fama-French factors."
                      : "시장 비교에는 벤치마크를 썼습니다. 나머지 세 기준은 백테스트 종목을 매달 상·하위 30%로 나눠 수익률 차이를 낸 것으로, 공식 Fama-French 지표는 아닙니다.")}
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-[var(--text-label)] sm:text-sm">
                    {t(isEnglish
                      ? "An absolute t-value of about 1.96 or more is used as a rough guide for a clear pattern. A high PBR alone does not prove a company is a growth stock."
                      : "t값의 절댓값 1.96 이상을 대략적인 '뚜렷함' 기준으로 삼았습니다. PBR이 높다고 성장주라고 단정할 수 없습니다.")}
                  </p>
                </div>
              </>
            )}
          </div>

          {/* 거래 분포 */}
          <div className="border-t border-white/[0.08] py-4" data-testid="analytics-trades">
            <div className="mb-2 text-sm font-black text-white">{t("거래 분포 ({0}건)", td.trades)}</div>
            {td.trades === 0 ? (
              <p className="mt-2 text-xs font-bold text-[var(--text-label)]">{t("완결된 거래가 없습니다.")}</p>
            ) : (
              <>
                <div className="mt-2 text-xs font-bold text-[var(--text-label)]">{t("거래 수익률 분포")}</div>
                <Histogram bins={td.returnHistogram} ariaLabel={t("거래 수익률 분포")} color={(b) => ((b.from ?? -1) >= 0 ? POSITIVE : NEGATIVE)} />
                <div className="mt-3 text-xs font-bold text-[var(--text-label)]">
                  {t("보유 기간 분포")}{td.holdingDays ? ` · ${t("평균 {0}일 · 중앙값 {1}일 · 최장 {2}일", num(td.holdingDays.mean, 0), num(td.holdingDays.median, 0), td.holdingDays.max)}` : ""}
                </div>
                <Histogram bins={td.holdingHistogram} ariaLabel={t("보유 기간 분포")} color={() => "#a3a3a3"} />
                <table className="mt-3 w-full min-w-[640px] border-collapse">
                  <thead>
                    <tr><th className={`${TH} text-left`}>MAE/MFE</th><th className={`${TH} text-right`}>{t("평균")}</th><th className={`${TH} text-right`}>{t("중앙값")}</th><th className={`${TH} text-right`}>{t("최악")}</th><th className={`${TH} text-right`}>{t("최선")}</th><th className={`${TH} text-right`}>n</th></tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    <StatRow label={t("MAE 전체")} stat={td.mae?.all ?? null} />
                    <StatRow label={t("MAE 승리")} stat={td.mae?.winners ?? null} />
                    <StatRow label={t("MAE 패배")} stat={td.mae?.losers ?? null} />
                    <StatRow label={t("MFE 전체")} stat={td.mfe?.all ?? null} />
                    <StatRow label={t("MFE 승리")} stat={td.mfe?.winners ?? null} />
                    <StatRow label={t("MFE 패배")} stat={td.mfe?.losers ?? null} />
                  </tbody>
                </table>
                <p className="mt-1 text-[10px] text-[var(--text-label)]">{t("MAE=보유 중 진입가 대비 최저 도달률, MFE=최고 도달률. 손절·익절 폭을 과거 거래와 견줄 때 씁니다.")}</p>
              </>
            )}
          </div>

          {/* 유동성 */}
          <div className="border-t border-white/[0.08] py-4" data-testid="analytics-liquidity">
            <div className="mb-2 text-sm font-black text-white">{t("유동성 (주문금액 ÷ 20일 평균 거래대금)")}</div>
            {a.liquidity.orders === 0 || a.liquidity.maxParticipation == null ? (
              <p className="mt-2 text-xs font-bold text-[var(--text-label)]">{t("거래대금 자료가 없어 참여율을 계산하지 못했습니다.")}</p>
            ) : (
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3 text-xs font-bold text-gray-200">
                <div>
                  <LiquidityMetricLabel id="help-liquidity-orders" label={t("주문 수")} ko="백테스트에서 계산에 사용한 전체 주문 건수입니다." en="The total number of backtest orders included in this calculation." />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{a.liquidity.orders}</dd>
                </div>
                <div>
                  <LiquidityMetricLabel id="help-liquidity-max" label={t("최대 참여율")} ko="주문 금액이 해당 종목의 직전 20거래일 평균 거래대금에서 차지한 비율 중 가장 큰 값입니다." en="The largest order amount as a share of that stock's average traded value over the preceding 20 trading days." align="right" />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.liquidity.maxParticipation, 2, false)}</dd>
                </div>
                <div>
                  <LiquidityMetricLabel id="help-liquidity-mean" label={t("평균 참여율")} ko="각 주문의 참여율을 모두 더해 주문 수로 나눈 평균입니다." en="The sum of order participation rates divided by the number of orders." />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.liquidity.meanParticipation, 2, false)}</dd>
                </div>
                <div>
                  <LiquidityMetricLabel id="help-liquidity-p95" label={t("상위 5% 참여율")} ko="주문을 참여율이 낮은 순서로 놓았을 때, 높은 쪽 5%가 시작되는 기준값입니다." en="The threshold where the highest-participation 5% of orders begin." align="right" />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.liquidity.p95Participation, 2, false)}</dd>
                </div>
                <div>
                  <LiquidityMetricLabel id="help-liquidity-over-cap" label={t("참여율 {0}% 초과 주문 비율", a.liquidity.cap)} ko={`전체 주문 중 참여율이 ${a.liquidity.cap}%를 넘은 주문의 비율입니다.`} en={`The share of all orders whose participation rate exceeded ${a.liquidity.cap}%.`} />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.liquidity.shareAboveCap, 1, false)}</dd>
                </div>
                <div>
                  <LiquidityMetricLabel id="help-liquidity-capital" label={t("참여율 {0}% 이내 운용 가능 자본(추정)", a.liquidity.cap)} ko={`가장 큰 주문도 참여율 ${a.liquidity.cap}% 이내가 되도록 백테스트 자본을 비례 조정한 추정값입니다.`} en={`An estimate that scales the backtest capital so even the largest order stays within ${a.liquidity.cap}% participation.`} align="right" />
                  <dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{money(a.liquidity.capitalAtCap, currency)}</dd>
                </div>
              </dl>
            )}
            {a.liquidity.orders > 0 && a.liquidity.maxParticipation != null && (
              <div className="mt-4 rounded-lg bg-white/[0.03] p-3" data-testid="analytics-liquidity-interpretation">
                <div className="mb-1 text-xs font-black text-white">{t(isEnglish ? "Overall interpretation" : "전체 해석")}</div>
                <p className="text-xs leading-relaxed text-gray-300 sm:text-sm">
                  {liquidityInterpretation(a.liquidity, money(a.liquidity.capitalAtCap, currency), isEnglish)}
                </p>
              </div>
            )}
          </div>

          {/* 벤치마크 비교 */}
          <div className="border-t border-white/[0.08] py-4" data-testid="analytics-benchmarks">
            <div className="mb-2 text-sm font-black text-white">{t("다중 벤치마크 비교")}</div>
            {a.benchmarks.length === 0 ? (
              <p className="mt-2 text-xs font-bold text-[var(--text-label)]">{t("벤치마크 자료가 없습니다.")}</p>
            ) : (
                <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse">
                <thead>
                  <tr><th className={`${TH} text-left`}>{t("벤치마크")}</th><th className={`${TH} text-right`}>{t("총수익률")}</th><th className={`${TH} text-right`}>CAGR</th><th className={`${TH} text-right`}>MDD</th><th className={`${TH} text-right`}>β</th><th className={`${TH} text-right`}>α</th><th className={`${TH} text-right`}>IR</th></tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {a.benchmarks.map((b) => (
                    <tr key={b.symbol} className="transition-colors duration-150 hover:bg-white/[0.02]">
                      <td className="whitespace-nowrap py-3 pl-2 pr-4 text-sm font-black text-white">{b.name}{b.partial ? <span className="ml-1 text-[9px] text-amber-300">{t("일부 기간")}</span> : null}</td>
                      <td className={`${TD} text-right ${colorClass(b.totalReturn)}`}>{pct(b.totalReturn)}</td>
                      <td className={`${TD} text-right ${colorClass(b.cagr)}`}>{pct(b.cagr)}</td>
                      <td className={`${TD} text-right text-main-blue`}>{pct(b.maxDrawdown)}</td>
                      <td className={`${TD} text-right`}>{num(b.beta)}</td>
                      <td className={`${TD} text-right ${colorClass(b.alpha)}`}>{pct(b.alpha)}</td>
                      <td className={`${TD} text-right`}>{num(b.informationRatio)}</td>
                    </tr>
                  ))}
                </tbody>
                </table>
                </div>
            )}
            <p className="mt-1 text-[10px] text-[var(--text-label)]">{t("β·α·정보비율은 전략 일간 수익률을 각 벤치마크에 회귀한 값입니다.")}</p>
          </div>

          <div className="grid gap-x-8 gap-y-4 lg:col-span-2 lg:grid-cols-2 lg:items-start">
          {/* 자산 상관관계(엔진 v16.33) — 과거 통계이며 추천이 아니다. */}
          {a.portfolioMix ? (
            <div className="border-t border-white/[0.08] py-4" data-testid="analytics-portfolio-mix">
              <div className="mb-2 text-sm font-black text-white">{t(isEnglish ? "Asset correlations" : "자산 상관관계")}</div>
              {!a.portfolioMix.available || !a.portfolioMix.symbols?.length ? (
                <p className="mt-2 text-xs font-bold text-[var(--text-label)]">{t(isEnglish ? "Not enough data to calculate asset correlations." : "표본이 부족해 자산 상관관계를 계산하지 못했습니다.")}</p>
              ) : (
                <>
                  <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-3 text-xs font-bold text-gray-200">
                    <div><dt className="text-[var(--text-label)]">{t("대상 종목")}</dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{a.portfolioMix.symbols.length}</dd></div>
                    <div><dt className="text-[var(--text-label)]">{t("평균 상관계수")}</dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{num(a.portfolioMix.avgCorrelation)}</dd></div>
                    <div><dt className="text-[var(--text-label)]">{t("최대 상관계수")}</dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{num(a.portfolioMix.maxCorrelation)}</dd></div>
                    <div><dt className="text-[var(--text-label)]">{t("최소 상관계수")}</dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{num(a.portfolioMix.minCorrelation)}</dd></div>
                  </dl>
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-[10px] font-bold text-gray-300">
                      <thead className="text-[var(--text-label)]">
                        <tr>
                          <th className="px-1 py-0.5 text-left" />
                          {a.portfolioMix.symbols.map((sym) => (
                            <th key={sym} className="px-1 py-1 text-right align-bottom">
                              <span className="block max-w-[100px] truncate text-[var(--text-label)]" title={stockMetadata[sym]?.name ?? sym}>
                                {stockMetadata[sym]?.name ?? sym}
                              </span>
                              <span className="block text-[9px] text-gray-400">{sym}</span>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(a.portfolioMix.correlation ?? []).map((row, i) => (
                          <tr key={a.portfolioMix?.symbols?.[i] ?? i}>
                            <th className="px-1 py-1 text-left align-middle">
                              <span className="block max-w-[120px] truncate text-white" title={stockMetadata[a.portfolioMix?.symbols?.[i] ?? ""]?.name ?? a.portfolioMix?.symbols?.[i]}>
                                {stockMetadata[a.portfolioMix?.symbols?.[i] ?? ""]?.name ?? a.portfolioMix?.symbols?.[i]}
                              </span>
                              <span className="block text-[9px] text-[var(--text-label)]">{a.portfolioMix?.symbols?.[i]}</span>
                            </th>
                            {row.map((v, j) => (
                              <td key={j} className="px-1 py-0.5 text-right" style={corrStyle(v)}>{num(v, 2)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="mt-1 text-[10px] text-[var(--text-label)]">
                    {isEnglish
                      ? "Statistics calculated from historical daily returns of held stocks (excluding short selling and leverage)."
                      : "보유했던 종목의 과거 일간 수익률로 계산한 통계입니다(공매도·레버리지 제외)."}
                  </p>
                </>
              )}
            </div>
          ) : null}

          {/* 회전율·위험 */}
          <div className="border-t border-white/[0.08] py-4" data-testid="analytics-risk">
            <div className="mb-3 text-sm font-black text-white">{t(isEnglish ? "Trading turnover and downside risk" : "매매 회전율·손실 위험")}</div>
            <div className="grid gap-5 sm:grid-cols-2">
              <section data-testid="analytics-turnover-summary">
                <h3 className="mb-2 text-xs font-black text-[var(--text-label)]">{t(isEnglish ? "Trading turnover" : "매매 회전율")}</h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs font-bold text-gray-200">
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">{t("연환산 회전율")}<MetricHelp id="help-turnover-annual" label={t("연환산 회전율")} ko="기간 회전율을 백테스트 기간(연수)으로 나눈 연환산 값입니다." en="Period turnover divided by the backtest duration in years." guidelineKey="annualTurnover" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.turnover.annual, 0, false)}</dd></div>
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">{t("기간 회전율")}<MetricHelp id="help-turnover-total" label={t("기간 회전율")} ko="총 매수·매도 체결 금액의 절반을 기간 평균 자산으로 나눈 비율입니다." en="Half of total buy and sell execution value, divided by average portfolio value over the period." guidelineKey="periodTurnover" align="right" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.turnover.total, 0, false)}</dd></div>
                </dl>
              </section>
              <section data-testid="analytics-downside-summary">
                <h3 className="mb-2 text-xs font-black text-[var(--text-label)]">{t(isEnglish ? "Downside risk" : "하방 위험")}</h3>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs font-bold text-gray-200">
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">VaR 95%<MetricHelp id="help-var-95" label="VaR 95%" ko="일간 수익률 분포에서 하위 5% 경계에 해당하는 손실률입니다." en="The loss threshold at the bottom 5% of the historical daily-return distribution." guidelineKey="var95" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.riskStats.var95, 2, false)}</dd></div>
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">CVaR 95%<MetricHelp id="help-cvar-95" label="CVaR 95%" ko="일간 수익률 분포의 하위 5% 구간에서 계산한 평균 손실률입니다." en="The average loss within the bottom 5% of the historical daily-return distribution." guidelineKey="cvar95" align="right" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.riskStats.cvar95, 2, false)}</dd></div>
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">VaR 99%<MetricHelp id="help-var-99" label="VaR 99%" ko="일간 수익률 분포에서 하위 1% 경계에 해당하는 손실률입니다." en="The loss threshold at the bottom 1% of the historical daily-return distribution." guidelineKey="var99" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.riskStats.var99, 2, false)}</dd></div>
                  <div><dt className="flex items-center gap-1 text-[var(--text-label)]">CVaR 99%<MetricHelp id="help-cvar-99" label="CVaR 99%" ko="일간 수익률 분포의 하위 1% 구간에서 계산한 평균 손실률입니다." en="The average loss within the bottom 1% of the historical daily-return distribution." guidelineKey="cvar99" align="right" /></dt><dd className="mt-1 text-sm font-black tabular-nums font-outfit text-white">{pct(a.riskStats.cvar99, 2, false)}</dd></div>
                </dl>
              </section>
            </div>
            <p className="mt-2 text-[10px] text-[var(--text-label)]">{t("VaR·CVaR는 일간 수익률의 역사적 분포에서 구한 하루 손실 한도(%)입니다.")}</p>
            <div className="mt-3 text-xs font-bold text-[var(--text-label)]">{t("{0}거래일 롤링 샤프", a.riskStats.window)}</div>
            <LineSeries values={a.riskStats.rollingSharpe} dates={dates} ariaLabel={t("롤링 샤프")} zero />
            {a.riskStats.rollingBeta.length > 0 && (
              <>
                <div className="mt-3 text-xs font-bold text-[var(--text-label)]">{t("{0}거래일 롤링 베타 (벤치마크 대비)", a.riskStats.window)}</div>
                <LineSeries values={a.riskStats.rollingBeta} dates={dates} ariaLabel={t("롤링 베타")} zero />
              </>
            )}
            <div className="mt-3 rounded-lg bg-white/[0.03] p-3" data-testid="rolling-risk-interpretation">
              <div className="mb-2 text-sm font-black text-white sm:text-base">{t(isEnglish ? "In plain language" : "한눈에 보는 해석")}</div>
              <p className="text-sm leading-relaxed text-gray-300 sm:text-base">
                {summarizeRollingRisk(a.riskStats.rollingSharpe, a.riskStats.rollingBeta, a.riskStats.window, isEnglish)}
              </p>
            </div>
          </div>
          </div>
        </div>
    </section>
  );
}
