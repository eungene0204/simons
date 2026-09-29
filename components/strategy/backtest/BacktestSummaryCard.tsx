"use client";

import { useEffect, useId, useState, type ReactNode } from "react";
import { BacktestResult } from "@/types/strategy";
import {
  Sparkle,
  ArrowsClockwise,
  TrendUp,
  Warning,
  Question,
  CaretDown,
  Lightbulb,
  ShieldWarning,
  Compass,
  ListChecks,
  Scales,
  Flask,
} from "phosphor-react";
import { buildAiReportMetrics } from "./aiReportMetrics";
import { profitFactorForRanking } from "@/lib/format-profit-factor";
import { type AiReportData, reportFromSummaryResponse } from "./aiReport";
import { t } from "@/lib/i18n";

interface BacktestSummaryCardProps {
  result: BacktestResult;
  strategySummary?: {
    strategyName?: string;
    universeName?: string;
    entryBlocks?: string[];
    exitBlocks?: string[];
  };
  initialReport?: AiReportData | null;
  parsedStrategy?: Record<string, unknown>;
  promptText?: string;
  onSummaryReady?: (report: AiReportData) => void;
}

function scoreLabel(score: number): string {
  if (score >= 80) return t("우수");
  if (score >= 60) return t("보통");
  if (score >= 40) return t("미흡");
  return t("위험");
}

function scoreGaugeColor(score: number): string {
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#60a5fa";
  if (score >= 40) return "#fbbf24";
  return "#f87171";
}

function scoreLevel(score: number): string {
  if (score >= 80) return "LEVEL 3";
  if (score >= 60) return "LEVEL 2";
  if (score >= 40) return "LEVEL 1";
  return "LEVEL 0";
}

function clampScore(score: number): number {
  return Math.max(0, Math.min(100, Math.round(score)));
}

function ScoreRing({ score, label, compact = false }: { score: number; label: string; compact?: boolean }) {
  const value = Math.max(0, Math.min(score, 100));
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
      className={`relative shrink-0 ${compact ? "h-14 w-14" : "h-44 w-44 sm:h-48 sm:w-48"}`}
    >
      <svg viewBox="0 0 100 100" aria-hidden="true" className="h-full w-full -rotate-90">
        <circle cx="50" cy="50" r="44" fill="none" stroke="var(--glass-border)" strokeWidth="3" />
        <circle
          cx="50" cy="50" r="44" fill="none"
          stroke={scoreGaugeColor(score)} strokeWidth="3" strokeLinecap="round"
          pathLength="100" strokeDasharray={`${value} 100`}
          opacity={value === 0 ? 0 : 1}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`font-semibold tabular-nums leading-none tracking-tight text-white ${compact ? "text-lg" : "text-6xl"}`}>
          {score}
        </span>
        {!compact && <span className="mt-2 text-xs font-medium tabular-nums text-[var(--text-label)]">/ 100</span>}
      </div>
    </div>
  );
}

// 리스크 점수: 높을수록 위험하므로 색을 반전한다.
function riskScoreColor(score: number): string {
  if (score >= 70) return "text-red-400";
  if (score >= 40) return "text-orange-400";
  return "text-emerald-400";
}

function riskScoreLabel(score: number): string {
  if (score >= 70) return t("위험");
  if (score >= 40) return t("주의");
  return t("안정");
}

function overfitMeta(level: string): { label: string; color: string } {
  switch (level) {
    case "high":
      return { label: t("높음"), color: "text-red-400" };
    case "medium":
      return { label: t("보통"), color: "text-orange-400" };
    case "low":
      return { label: t("낮음"), color: "text-emerald-400" };
    default:
      return { label: level, color: "text-gray-400" };
  }
}

function metricToScore(
  value: number | undefined,
  thresholds: [number, number, number],
  reverse = false,
  floor = 10
): number {
  if (value == null || Number.isNaN(value)) return 0;
  const [low, mid, high] = thresholds;
  if (reverse) {
    if (value <= low) return 100;
    if (value <= mid) return 70;
    if (value <= high) return 40;
    return floor;
  }
  if (value >= high) return 100;
  if (value >= mid) return 70;
  if (value >= low) return 40;
  return floor;
}

function calculateRollingSharpeStability(equity: number[]): number {
  if (!Array.isArray(equity) || equity.length < 32) return 0;

  const returns: number[] = [];
  for (let i = 1; i < equity.length; i += 1) {
    const prev = equity[i - 1];
    const curr = equity[i];
    if (!Number.isFinite(prev) || !Number.isFinite(curr) || prev === 0) continue;
    returns.push((curr - prev) / prev);
  }

  const window = 21;
  if (returns.length < window) return 0;

  const rollingSharpes: number[] = [];
  for (let i = window - 1; i < returns.length; i += 1) {
    const slice = returns.slice(i - window + 1, i + 1);
    const mean = slice.reduce((sum, value) => sum + value, 0) / slice.length;
    const variance = slice.reduce((sum, value) => sum + (value - mean) ** 2, 0) / slice.length;
    const std = Math.sqrt(variance);
    if (std === 0) continue;
    rollingSharpes.push((mean / std) * Math.sqrt(252));
  }

  if (rollingSharpes.length < 3) return 0;

  const avgAbsSharpe =
    rollingSharpes.reduce((sum, value) => sum + Math.abs(value), 0) / rollingSharpes.length;
  const meanSharpe =
    rollingSharpes.reduce((sum, value) => sum + value, 0) / rollingSharpes.length;
  const sharpeVariance =
    rollingSharpes.reduce((sum, value) => sum + (value - meanSharpe) ** 2, 0) / rollingSharpes.length;
  const sharpeStd = Math.sqrt(sharpeVariance);

  return 1 / (1 + sharpeStd / Math.max(avgAbsSharpe, 0.25));
}

// 리포트 섹션 접기/펼치기 — 핵심 섹션은 기본 펼침, 나머지는 접힘(점진적 표시).
function CollapsibleSection({
  title,
  icon,
  defaultOpen = false,
  children,
}: {
  title: string;
  icon: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const contentId = useId();
  return (
    <div className="px-5 py-5 sm:px-8">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={contentId}
        className="flex w-full items-center justify-between gap-4 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-label)]"
      >
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="text-[var(--text-label)] [&>svg]:text-inherit">{icon}</span>
          <span className="text-base font-semibold tracking-tight text-white">{title}</span>
        </div>
        <CaretDown
          className={`h-4 w-4 shrink-0 text-[var(--text-label)] transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
          weight="bold"
        />
      </button>
      {open && <div id={contentId} role="region" aria-label={title} className="mt-5">{children}</div>}
    </div>
  );
}

// 근거 기반 항목 목록(장점/약점/숨은 위험/개선 우선순위 공통).
function BulletList({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-[var(--text-label)]">{t("없음")}</p>;
  return (
    <ul className="space-y-4">
      {items.map((s, i) => (
        <li key={i} className="flex items-start gap-3">
          <span aria-hidden="true" className="mt-2.5 h-1 w-1 flex-none rounded-full bg-[var(--text-label)]" />
          <span className="min-w-0 break-words text-sm leading-7 text-gray-300 sm:text-[15px]">{s}</span>
        </li>
      ))}
    </ul>
  );
}

export default function BacktestSummaryCard({
  result,
  strategySummary,
  initialReport,
  parsedStrategy,
  promptText,
  onSummaryReady,
}: BacktestSummaryCardProps) {
  const [report, setReport] = useState<AiReportData | null>(initialReport ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 대시보드가 백그라운드 생성을 끝내면 initialReport prop이 갱신된다.
  // 카드가 이미 마운트된 상태(리포트 탭을 열어둔 채)에서도 반영되도록 동기화한다.
  useEffect(() => {
    if (loading) return; // 카드 자체 요청이 진행 중이면 덮어쓰지 않음
    if (initialReport && initialReport.summary) {
      setReport(initialReport);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialReport]);

  const fetchSummary = async (force = false) => {
    setLoading(true);
    setError(null);
    setReport(null);

    try {
      const res = await fetch("/api/backtest/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cacheKey: result.cacheKey,
          metrics: buildAiReportMetrics(result),
          strategySummary,
          parsedStrategy,
          userPrompt: promptText,
          force,
        }),
      });

      const data = await res.json();
      // 서버 플랜 안내(error)는 한국어 정본 — /us에서는 사전으로 번역해 표시한다.
      if (!res.ok) throw new Error(data.error ? t(data.error) : "Unknown error");
      // degraded = LLM 출력 파싱 실패 폴백 — 리포트로 표시/전파하지 않고 재시도를 안내한다.
      if (data.degraded) {
        throw new Error(data.summary || t("AI 리포트 생성에 실패했습니다. 다시 시도해 주세요."));
      }
      const nextReport = reportFromSummaryResponse(data);
      if (!nextReport) {
        throw new Error(t("AI 리포트 생성에 실패했습니다. 다시 시도해 주세요."));
      }
      setReport(nextReport);
      onSummaryReady?.(nextReport);
    } catch (e: any) {
      setError(e.message ?? t("요약 생성에 실패했습니다."));
    } finally {
      setLoading(false);
    }
  };

  const summary = report?.summary ?? "";
  const score = report?.score ?? null;
  const strengths = report?.strengths ?? [];
  const weaknesses = report?.weaknesses ?? [];
  const improvements = report?.improvements ?? [];
  const riskScore = report?.riskScore ?? null;
  const overfitRisk = report?.overfitRisk ?? null;
  const topInsights = report?.topInsights ?? [];
  const hiddenRisks = report?.hiddenRisks ?? [];
  const overfittingAnalysis = report?.overfittingAnalysis ?? "";
  const strategyProfile = report?.strategyProfile ?? [];
  const strategyProfileNote = report?.strategyProfileNote ?? "";
  const validationRoadmap = report?.validationRoadmap ?? [];
  const finalVerdict = report?.finalVerdict ?? "";

  const hasContent = !loading && !!summary;
  const profitabilityScore = clampScore(
    metricToScore(result.cagr, [5, 10, 20], false, 0) * 0.6 +
    metricToScore(profitFactorForRanking(result.profitFactor), [1, 1.5, 2]) * 0.4
  );
  const stabilityScore = clampScore(
    metricToScore(Math.abs(result.maxDrawdown ?? 0), [10, 20, 30], true) * 0.6 +
    metricToScore(result.sharpe, [0.5, 1, 1.5]) * 0.4
  );
  const rollingSharpeStability = calculateRollingSharpeStability(result.equity);
  const consistencyScore = clampScore(
    metricToScore(result.calmar, [0.5, 1, 1.5], false, 0) * 0.55 +
    metricToScore(rollingSharpeStability, [0.35, 0.55, 0.75], false, 0) * 0.45
  );
  const scoreBreakdown = [
    {
      label: t("성장성"),
      value: profitabilityScore,
      detail: "CAGR + PF",
      tooltipTitle: t("성장성"),
      tooltipBody:
        t("성장성은 CAGR + Profit Factor를 결합한 지표입니다. CAGR은 전체 수익을 연간 복리 성장률로 환산한 값이고, Profit Factor는 총이익을 총손실로 나눈 값입니다. 장기적으로 자산을 꾸준히 키우면서 손실 대비 이익 효율도 좋은 전략일수록 높게 평가합니다."),
      tooltipGuide: [
        { label: t("우수"), value: t("CAGR 20% 이상, Profit Factor 2.0 이상"), tone: "good" },
        { label: t("보통"), value: "CAGR 10~20%, Profit Factor 1.5~2.0", tone: "mid" },
        { label: t("미흡"), value: t("CAGR 10% 미만, Profit Factor 1.5 미만"), tone: "bad" },
      ],
    },
    {
      label: t("안정성"),
      value: stabilityScore,
      detail: "MDD + Sharpe",
      tooltipTitle: t("안정성"),
      tooltipBody:
        t("안정성은 MDD + Sharpe를 결합한 지표입니다. MDD는 고점 대비 최대 손실 폭을 뜻하고, Sharpe는 감수한 변동성 대비 얼마만큼의 수익을 냈는지를 나타냅니다. 큰 하락 없이 버티면서도 위험 대비 효율적으로 성과를 낸 전략일수록 높게 평가합니다."),
      tooltipGuide: [
        { label: t("우수"), value: t("MDD 10% 이하, Sharpe 1.5 이상"), tone: "good" },
        { label: t("보통"), value: "MDD 10~20%, Sharpe 1.0~1.5", tone: "mid" },
        { label: t("미흡"), value: t("MDD 20% 초과, Sharpe 1.0 미만"), tone: "bad" },
      ],
    },
    {
      label: t("일관성"),
      value: consistencyScore,
      detail: "Calmar + RSS",
      tooltipTitle: t("일관성"),
      tooltipBody:
        t("일관성은 Calmar Ratio + Rolling Sharpe Stability를 결합한 지표입니다. Calmar Ratio는 CAGR을 최대낙폭으로 나눈 값이라 낙폭을 감수하고도 성과를 안정적으로 냈는지를 보여주고, Rolling Sharpe Stability는 구간별 샤프 지수가 시간에 따라 얼마나 덜 흔들리는지를 나타냅니다. 즉 낙폭 대비 성과가 균형 잡혀 있고, 성과 효율이 특정 구간에 치우치지 않고 비교적 안정적으로 유지될수록 더 높게 평가합니다."),
      tooltipGuide: [
        { label: t("우수"), value: t("Calmar 1.5 이상, RSS 0.75 이상"), tone: "good" },
        { label: t("보통"), value: "Calmar 1.0~1.5, RSS 0.55~0.75", tone: "mid" },
        { label: t("미흡"), value: t("Calmar 1.0 미만, RSS 0.55 미만"), tone: "bad" },
      ],
    },
  ];

  const reportCardClass =
    "w-full rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] px-5 py-6 sm:px-8 sm:py-7";
  const reportCardTitleClass = "text-base font-semibold tracking-tight text-[var(--text-label)]";

  return (
    <div className="mx-auto flex w-full max-w-[840px] flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 px-1">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold tracking-tight text-white">{t("AI 백테스트 리포트")}</h2>
          {strategySummary?.strategyName && <p className="mt-2 break-words text-sm text-[var(--text-label)]">{strategySummary.strategyName}</p>}
        </div>
        <button
          type="button"
          onClick={() => fetchSummary(true)}
          disabled={loading}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.06] text-[var(--text-label)] transition-colors hover:bg-white/[0.12] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-label)] disabled:opacity-40"
          title={t("다시 생성")}
          aria-label={t("다시 생성")}
        >
          <ArrowsClockwise
            className={`w-3.5 h-3.5 ${loading ? "animate-spin motion-reduce:animate-none" : ""}`}
          />
        </button>
      </div>

      <>
        {loading && (
          <div
            key="loading"
            role="status"
            className={`${reportCardClass} flex min-h-[240px] items-center justify-center gap-3 text-sm text-[var(--text-label)]`}
          >
            <span className="inline-flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1 h-1 rounded-full bg-gray-600 animate-bounce motion-reduce:animate-none"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </span>
            <span>{t("분석 중...")}</span>
          </div>
        )}

        {!loading && error && (
          <p
            key="error"
            role="alert"
            className={`${reportCardClass} text-sm leading-6 text-red-400`}
          >
            {error}
          </p>
        )}

        {!loading && !error && !hasContent && (
          <div
            key="idle"
            className={`${reportCardClass} flex min-h-[280px] flex-col items-center justify-center gap-5 text-center`}
          >
            <p className="text-sm leading-6 text-[var(--text-label)]">{t("AI 리포트가 아직 생성되지 않았습니다.")}</p>
            <button
              type="button"
              onClick={() => fetchSummary()}
              className="rounded-xl bg-[var(--chat-accent)] px-5 py-2.5 text-sm font-semibold text-[var(--chat-accent-ink)] transition-colors hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-label)]"
            >
              {t("리포트 생성")}
            </button>
          </div>
        )}

        {hasContent && (
          <div
            key="result"
            className="flex flex-col gap-4 sm:gap-5"
          >
            {score !== null && (
              <div className="w-full rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)] px-5 py-6 sm:px-8 sm:py-8">
                <div className="flex flex-col items-center gap-5 sm:flex-row sm:justify-center sm:gap-10">
                  <ScoreRing score={score} label={t("점수")} />
                  <div className="flex flex-col items-center gap-3 sm:items-start">
                    <span className="text-sm font-medium text-[var(--text-label)]">{t("점수")}</span>
                    <span className="text-2xl font-semibold tracking-tight text-white">{scoreLabel(score)}</span>
                    <span className="rounded-md bg-white/[0.06] px-2.5 py-1 text-xs font-semibold tracking-wide text-[var(--text-label)]">
                      {scoreLevel(score)}
                    </span>
                  </div>
                </div>

                <div className="mt-6 grid grid-cols-1 divide-y divide-white/[0.08] border-t border-white/[0.08] sm:mt-8 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
                  {scoreBreakdown.map((item) => (
                    <div key={item.label} className="flex min-w-0 items-center gap-3 py-4 sm:flex-col sm:gap-3 sm:px-3 sm:pb-0 sm:pt-6">
                      <ScoreRing score={item.value} label={item.label} compact />
                      <div className="min-w-0 sm:text-center">
                        <span className="text-sm font-semibold tracking-tight text-white">
                          {item.label}
                        </span>
                        <div className="relative mt-1 flex items-center gap-1 text-xs font-medium text-[var(--text-label)] sm:justify-center">
                          <span>{item.detail}</span>
                        <div className="group relative">
                          <button
                            type="button"
                            aria-label={t("{0} 점수 설명", item.label)}
                            className="flex h-8 w-8 cursor-help items-center justify-center rounded-full text-[var(--text-label)] transition-colors hover:bg-white/[0.06] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--text-label)]"
                          >
                            <Question className="h-3 w-3" weight="bold" />
                          </button>
                          <div
                            role="tooltip"
                            className="pointer-events-none fixed inset-x-4 bottom-4 z-50 max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-2xl border border-white/10 bg-[var(--card-bg)] px-4 py-4 text-left opacity-0 shadow-[0_24px_48px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100 lg:absolute lg:bottom-full lg:left-1/2 lg:right-auto lg:z-10 lg:mb-3 lg:w-[320px] lg:max-h-none lg:-translate-x-1/2 lg:overflow-visible lg:rounded-2xl lg:px-6 lg:py-6"
                          >
                            <div className="text-[15px] font-semibold text-white">
                              {item.tooltipTitle}
                            </div>
                            <p className="mt-5 text-[13px] font-medium leading-7 text-[#b3b3b3]">
                              {item.tooltipBody}
                            </p>
                            <div className="mt-6 text-[13px] font-bold text-[#bfbfbf]">
                              {t("[ 가이드라인 ]")}
                            </div>
                            <div className="mt-4 space-y-2.5">
                              {item.tooltipGuide.map((guide) => (
                                <div key={guide.label} className="flex items-center gap-2.5 text-[12px] font-bold text-[#bfbfbf]">
                                  <span
                                    className={`h-2.5 w-2.5 rounded-full ${
                                      guide.tone === "good"
                                        ? "bg-[#22c55e]"
                                        : guide.tone === "mid"
                                          ? "bg-[#eab308]"
                                          : "bg-[#ef4444]"
                                    }`}
                                  />
                                  <span>{guide.label}: {guide.value}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 전략 리스크 진단 (advisor) */}
            {(riskScore != null || overfitRisk != null) && (
              <div className={reportCardClass}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <Warning className="w-4 h-4 text-[var(--text-label)]" weight="bold" />
                    <p className={reportCardTitleClass}>{t("전략 리스크 진단")}</p>
                  </div>
                  <div className="h-px w-full bg-white/[0.06]" />
                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 sm:gap-8">
                    {riskScore != null && (
                      <div className="flex flex-col items-start gap-3">
                        <span className="text-sm font-medium text-[var(--text-label)]">
                          {t("리스크 점수")}
                        </span>
                        <div className="flex flex-col items-start gap-1">
                          <span className="text-4xl font-semibold tabular-nums tracking-tight leading-none text-white">
                            {clampScore(riskScore)}
                          </span>
                          <span className={`text-xs font-medium h-5 flex items-center ${riskScoreColor(riskScore)}`}>
                            {riskScoreLabel(riskScore)}
                          </span>
                        </div>
                        <span className="text-xs leading-5 text-[var(--text-label)]">{t("높을수록 위험")}</span>
                      </div>
                    )}
                    {overfitRisk != null && (
                      <div className="flex flex-col items-start gap-3">
                        <span className="text-sm font-medium text-[var(--text-label)]">
                          {t("과적합 위험")}
                        </span>
                        <div className="flex flex-col items-start gap-1">
                          <span className="text-4xl font-semibold tracking-tight leading-none text-white">
                            {overfitMeta(overfitRisk).label}
                          </span>
                          <span className="h-5" />
                        </div>
                        <span className="text-xs leading-5 text-[var(--text-label)]">{t("과거에만 맞춘 전략일 위험")}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* 1. 핵심 요약 (Executive Summary) — 항상 펼침 */}
            <div className={reportCardClass}>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2.5">
                  <Sparkle className="h-4 w-4 text-[var(--text-label)]" weight="fill" />
                  <p className={reportCardTitleClass}>{t("핵심 요약")}</p>
                </div>
                <p className="text-base leading-8 text-gray-200 whitespace-pre-wrap break-words">{summary}</p>
              </div>
            </div>

            {(topInsights.length > 0 || hiddenRisks.length > 0) && (
            <div className="flex flex-col gap-4 sm:gap-5">
            {/* 2. 핵심 통찰 (Top Insights) — 항상 펼침 */}
            {topInsights.length > 0 && (
              <div className={reportCardClass}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <Lightbulb className="h-4 w-4 text-[var(--text-label)]" weight="bold" />
                    <p className={reportCardTitleClass}>{t("핵심 통찰")}</p>
                  </div>
                  <div className="h-px w-full bg-white/[0.06]" />
                  <BulletList items={topInsights} />
                </div>
              </div>
            )}

            {/* 5. 숨은 위험 (Hidden Risks) — 항상 펼침(위험 우선) */}
            {hiddenRisks.length > 0 && (
              <div className={reportCardClass}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <ShieldWarning className="h-4 w-4 text-[var(--text-label)]" weight="bold" />
                    <p className={reportCardTitleClass}>{t("숨은 위험")}</p>
                  </div>
                  <div className="h-px w-full bg-white/[0.06]" />
                  <BulletList items={hiddenRisks} />
                </div>
              </div>
            )}

            </div>
            )}

            <div className="divide-y divide-white/[0.08] rounded-2xl border border-[var(--card-border)] bg-[var(--card-bg)]">
            {/* 3. 강점 (Strengths) — 접힘 */}
            <CollapsibleSection title={t("강점")} icon={<TrendUp className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
              <BulletList items={strengths} />
            </CollapsibleSection>

            {/* 4. 약점 (Weaknesses) — 접힘 */}
            <CollapsibleSection title={t("약점")} icon={<Warning className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
              <BulletList items={weaknesses} />
            </CollapsibleSection>

            {/* 6. 과최적화 분석 (Overfitting Analysis) — 접힘 */}
            {overfittingAnalysis && (
              <CollapsibleSection title={t("과최적화 분석")} icon={<Warning className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
                <p className="text-sm leading-7 text-gray-300 whitespace-pre-wrap break-words sm:text-[15px]">
                  {overfittingAnalysis}
                </p>
              </CollapsibleSection>
            )}

            {/* 7. 전략 성향 (Strategy Profile) — 접힘 */}
            {(strategyProfile.length > 0 || strategyProfileNote) && (
              <CollapsibleSection title={t("전략 성향")} icon={<Compass className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
                <div className="flex flex-col gap-4">
                  {strategyProfile.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {strategyProfile.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-md bg-white/[0.06] px-3 py-1.5 text-xs font-medium text-gray-300"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  {strategyProfileNote && (
                    <p className="text-sm leading-7 text-gray-300 whitespace-pre-wrap break-words sm:text-[15px]">
                      {strategyProfileNote}
                    </p>
                  )}
                </div>
              </CollapsibleSection>
            )}

            {/* 8. 검증 로드맵 (Validation Roadmap) — 접힘 */}
            {validationRoadmap.length > 0 && (
              <CollapsibleSection title={t("검증 로드맵")} icon={<Flask className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
                <ol className="space-y-4">
                  {validationRoadmap.map((item, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <span className="mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-md bg-white/[0.06] text-xs font-semibold tabular-nums text-[var(--text-label)]">
                        {i + 1}
                      </span>
                      <div className="flex min-w-0 flex-col gap-1 break-words">
                        <span className="text-sm font-semibold text-white sm:text-[15px]">{item.title}</span>
                        {item.reason && (
                          <span className="text-sm leading-6 text-[var(--text-label)]">{item.reason}</span>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </CollapsibleSection>
            )}

            {/* 9. 개선 우선순위 (Improvement Priorities) — 접힘 */}
            <CollapsibleSection title={t("개선 우선순위")} icon={<ListChecks className="h-4 w-4 text-[var(--text-label)]" weight="bold" />}>
              <BulletList items={improvements} />
            </CollapsibleSection>

            </div>

            {/* 10. 최종 평가 (Final Verdict) — 항상 펼침 */}
            {finalVerdict && (
              <div className={reportCardClass}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <Scales className="h-4 w-4 text-[var(--text-label)]" weight="bold" />
                    <p className={reportCardTitleClass}>{t("최종 평가")}</p>
                  </div>
                  <div className="h-px w-full bg-white/[0.06]" />
                  <p className="text-base leading-8 text-gray-200 whitespace-pre-wrap break-words">{finalVerdict}</p>
                </div>
              </div>
            )}
          </div>
        )}
      </>
    </div>
  );
}
