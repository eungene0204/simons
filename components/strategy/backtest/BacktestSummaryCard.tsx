"use client";

import { useEffect, useState } from "react";
import { BacktestResult } from "@/types/strategy";
import { Sparkle, ArrowsClockwise, TrendUp, Warning, Question } from "phosphor-react";
import { motion, AnimatePresence } from "framer-motion";
import { buildAiReportMetrics } from "./aiReportMetrics";

interface BacktestSummaryCardProps {
  result: BacktestResult;
  strategySummary?: {
    strategyName?: string;
    universeName?: string;
    entryBlocks?: string[];
    exitBlocks?: string[];
  };
  initialSummary?: string;
  initialScore?: number;
  initialStrengths?: string[];
  initialWeaknesses?: string[];
  initialImprovements?: string[];
  initialAdvisorScore?: number | null;
  initialRiskScore?: number | null;
  initialOverfitRisk?: string | null;
  parsedStrategy?: Record<string, unknown>;
  promptText?: string;
  onSummaryReady?: (
    summary: string,
    score: number,
    strengths: string[],
    weaknesses: string[],
    improvements: string[],
    advisorScore: number | null,
    riskScore: number | null,
    overfitRisk: string | null
  ) => void;
}

function scoreColor(score: number): string {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-orange-400";
  return "text-red-400";
}

function scoreBorder(score: number): string {
  if (score >= 80) return "border-emerald-400/40";
  if (score >= 60) return "border-yellow-400/40";
  if (score >= 40) return "border-orange-400/40";
  return "border-red-400/40";
}

function scoreLabel(score: number): string {
  if (score >= 80) return "우수";
  if (score >= 60) return "보통";
  if (score >= 40) return "미흡";
  return "위험";
}

function scoreGaugeColor(score: number): string {
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#facc15";
  if (score >= 40) return "#fb923c";
  return "#ff2d3d";
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

// 리스크 점수: 높을수록 위험하므로 색을 반전한다.
function riskScoreColor(score: number): string {
  if (score >= 70) return "text-red-400";
  if (score >= 40) return "text-orange-400";
  return "text-emerald-400";
}

function riskScoreLabel(score: number): string {
  if (score >= 70) return "위험";
  if (score >= 40) return "주의";
  return "안정";
}

function overfitMeta(level: string): { label: string; color: string } {
  switch (level) {
    case "high":
      return { label: "높음", color: "text-red-400" };
    case "medium":
      return { label: "보통", color: "text-orange-400" };
    case "low":
      return { label: "낮음", color: "text-emerald-400" };
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

export default function BacktestSummaryCard({
  result,
  strategySummary,
  initialSummary,
  initialScore,
  initialStrengths,
  initialWeaknesses,
  initialImprovements,
  initialRiskScore,
  initialOverfitRisk,
  parsedStrategy,
  promptText,
  onSummaryReady,
}: BacktestSummaryCardProps) {
  const gaugeLength = 251.2;
  const miniGaugeLength = 219.8;
  const [summary, setSummary] = useState<string>(initialSummary ?? "");
  const [score, setScore] = useState<number | null>(initialScore ?? null);
  const [strengths, setStrengths] = useState<string[]>(initialStrengths ?? []);
  const [weaknesses, setWeaknesses] = useState<string[]>(initialWeaknesses ?? []);
  const [improvements, setImprovements] = useState<string[]>(initialImprovements ?? []);
  const [riskScore, setRiskScore] = useState<number | null>(initialRiskScore ?? null);
  const [overfitRisk, setOverfitRisk] = useState<string | null>(initialOverfitRisk ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 대시보드가 백그라운드에서 생성을 끝내면 initial* props가 갱신된다.
  // 카드가 이미 마운트된 상태(리포트 탭을 열어둔 채)에서도 반영되도록 동기화한다.
  useEffect(() => {
    if (loading) return; // 카드 자체 요청이 진행 중이면 덮어쓰지 않음
    if (initialSummary && initialScore != null) {
      setSummary(initialSummary);
      setScore(initialScore);
      setStrengths(initialStrengths ?? []);
      setWeaknesses(initialWeaknesses ?? []);
      setImprovements(initialImprovements ?? []);
      setRiskScore(initialRiskScore ?? null);
      setOverfitRisk(initialOverfitRisk ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSummary, initialScore]);

  const fetchSummary = async (force = false) => {
    setLoading(true);
    setError(null);
    setSummary("");
    setScore(null);
    setStrengths([]);
    setWeaknesses([]);
    setImprovements([]);
    setRiskScore(null);
    setOverfitRisk(null);

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
      if (!res.ok) throw new Error(data.error || "Unknown error");
      // degraded = LLM 출력 파싱 실패 폴백 — 리포트로 표시/전파하지 않고 재시도를 안내한다.
      if (data.degraded) {
        throw new Error(data.summary || "AI 리포트 생성에 실패했습니다. 다시 시도해 주세요.");
      }
      setScore(data.score ?? null);
      setSummary(data.summary ?? "");
      setStrengths(data.strengths ?? []);
      setWeaknesses(data.weaknesses ?? []);
      setImprovements(data.improvements ?? []);
      setRiskScore(data.riskScore ?? null);
      setOverfitRisk(data.overfitRisk ?? null);
      if (data.summary && data.score != null) {
        onSummaryReady?.(
          data.summary,
          data.score,
          data.strengths ?? [],
          data.weaknesses ?? [],
          data.improvements ?? [],
          data.advisorScore ?? null,
          data.riskScore ?? null,
          data.overfitRisk ?? null
        );
      }
    } catch (e: any) {
      setError(e.message ?? "요약 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };


  const hasContent = !loading && !!summary;
  const profitabilityScore = clampScore(
    metricToScore(result.cagr, [5, 10, 20], false, 0) * 0.6 +
    metricToScore(result.profitFactor, [1, 1.5, 2]) * 0.4
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
      label: "성장성",
      value: profitabilityScore,
      detail: "CAGR + PF",
      tooltipTitle: "성장성",
      tooltipBody:
        "성장성은 CAGR + Profit Factor를 결합한 지표입니다. CAGR은 전체 수익을 연간 복리 성장률로 환산한 값이고, Profit Factor는 총이익을 총손실로 나눈 값입니다. 장기적으로 자산을 꾸준히 키우면서 손실 대비 이익 효율도 좋은 전략일수록 높게 평가합니다.",
      tooltipGuide: [
        { label: "우수", value: "CAGR 20% 이상, Profit Factor 2.0 이상", tone: "good" },
        { label: "보통", value: "CAGR 10~20%, Profit Factor 1.5~2.0", tone: "mid" },
        { label: "미흡", value: "CAGR 10% 미만, Profit Factor 1.5 미만", tone: "bad" },
      ],
    },
    {
      label: "안정성",
      value: stabilityScore,
      detail: "MDD + Sharpe",
      tooltipTitle: "안정성",
      tooltipBody:
        "안정성은 MDD + Sharpe를 결합한 지표입니다. MDD는 고점 대비 최대 손실 폭을 뜻하고, Sharpe는 감수한 변동성 대비 얼마만큼의 수익을 냈는지를 나타냅니다. 큰 하락 없이 버티면서도 위험 대비 효율적으로 성과를 낸 전략일수록 높게 평가합니다.",
      tooltipGuide: [
        { label: "우수", value: "MDD 10% 이하, Sharpe 1.5 이상", tone: "good" },
        { label: "보통", value: "MDD 10~20%, Sharpe 1.0~1.5", tone: "mid" },
        { label: "미흡", value: "MDD 20% 초과, Sharpe 1.0 미만", tone: "bad" },
      ],
    },
    {
      label: "일관성",
      value: consistencyScore,
      detail: "Calmar + RSS",
      tooltipTitle: "일관성",
      tooltipBody:
        "일관성은 Calmar Ratio + Rolling Sharpe Stability를 결합한 지표입니다. Calmar Ratio는 CAGR을 최대낙폭으로 나눈 값이라 낙폭을 감수하고도 성과를 안정적으로 냈는지를 보여주고, Rolling Sharpe Stability는 구간별 샤프 지수가 시간에 따라 얼마나 덜 흔들리는지를 나타냅니다. 즉 낙폭 대비 성과가 균형 잡혀 있고, 성과 효율이 특정 구간에 치우치지 않고 비교적 안정적으로 유지될수록 더 높게 평가합니다.",
      tooltipGuide: [
        { label: "우수", value: "Calmar 1.5 이상, RSS 0.75 이상", tone: "good" },
        { label: "보통", value: "Calmar 1.0~1.5, RSS 0.55~0.75", tone: "mid" },
        { label: "미흡", value: "Calmar 1.0 미만, RSS 0.55 미만", tone: "bad" },
      ],
    },
  ];

  const reportCardClass =
    "mx-auto w-full max-w-[760px] rounded-[28px] border border-white/10 px-5 py-5 sm:px-7 sm:py-6";
  const reportCardTitleClass = "text-lg font-black tracking-tight text-white";

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2 text-base font-black uppercase tracking-widest text-white">
          <Sparkle className="w-4 h-4 text-white/30" weight="fill" />
          AI 백테스트 리포트
        </div>
        <button
          onClick={() => fetchSummary(true)}
          disabled={loading}
          className="text-gray-600 hover:text-gray-400 transition-colors disabled:opacity-30"
          title="다시 생성"
        >
          <ArrowsClockwise
            className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
          />
        </button>
      </div>

      <AnimatePresence mode="wait">
        {loading && (
          <motion.div
            key="loading"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flat-card px-5 py-8 flex items-center justify-center gap-2 text-sm text-gray-600"
          >
            <span className="inline-flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1 h-1 rounded-full bg-gray-600 animate-bounce"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </span>
            <span>분석 중...</span>
          </motion.div>
        )}

        {!loading && error && (
          <motion.p
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="text-xs text-red-400/70 px-1"
          >
            {error}
          </motion.p>
        )}

        {!loading && !error && !hasContent && (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flat-card px-5 py-8 flex flex-col items-center justify-center gap-3"
          >
            <p className="text-xs text-gray-600">AI 리포트가 아직 생성되지 않았습니다.</p>
            <button
              onClick={() => fetchSummary()}
              className="px-4 py-1.5 text-xs font-bold text-white bg-white/[0.06] hover:bg-white/[0.12] border border-white/10 rounded-lg transition-colors"
            >
              리포트 생성
            </button>
          </motion.div>
        )}

        {hasContent && (
          <motion.div
            key="result"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="flex flex-col gap-4"
          >
            {score !== null && (
              <div className="mx-auto w-full max-w-[760px] overflow-visible rounded-[28px] border border-white/10 px-5 py-6 sm:px-8 sm:py-8">
                <div className="relative flex flex-col items-center gap-5">
                  <div className="relative w-full max-w-[380px]">
                    <svg viewBox="0 0 240 160" className="w-full h-auto">
                      <path
                        d="M 40 120 A 80 80 0 0 1 200 120"
                        fill="none"
                        stroke="#5c4038"
                        strokeWidth="18"
                        strokeLinecap="round"
                      />
                      <path
                        d="M 40 120 A 80 80 0 0 1 200 120"
                        fill="none"
                        stroke={scoreGaugeColor(score)}
                        strokeWidth="18"
                        strokeLinecap="round"
                        strokeDasharray={`${(Math.max(0, Math.min(score, 100)) / 100) * gaugeLength} ${gaugeLength}`}
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center pt-10">
                      <span className="mb-2 text-[11px] font-black tracking-[0.3em] text-white/40">
                        SCORE
                      </span>
                      <span className={`flex items-end gap-1 text-6xl sm:text-7xl font-black tabular-nums leading-none ${scoreColor(score)}`}>
                        <span>{score}</span>
                        <span className="pb-2 text-lg sm:text-2xl">점</span>
                      </span>
                    </div>
                  </div>
                  <span className="rounded-full bg-[#566178] px-6 py-2 text-sm font-black uppercase tracking-[0.2em] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
                    {scoreLevel(score)}
                  </span>
                  <div className="flex flex-col items-center gap-1">
                    <span className={`text-sm font-bold tracking-[0.22em] ${scoreColor(score)}`}>
                      {scoreLabel(score)}
                    </span>
                  </div>
                </div>

                <div className="mt-8 border-t border-[#8d5d3a]" />

                <div className="mt-8 grid grid-cols-1 gap-8 sm:grid-cols-3 sm:gap-6">
                  {scoreBreakdown.map((item) => (
                    <div key={item.label} className="flex flex-col items-center text-center">
                      <div className="relative h-[148px] w-[148px]">
                        <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
                          <circle
                            cx="60"
                            cy="60"
                            r="35"
                            fill="none"
                            stroke="#351613"
                            strokeWidth="10"
                          />
                          <circle
                            cx="60"
                            cy="60"
                            r="35"
                            fill="none"
                            stroke={scoreGaugeColor(item.value)}
                            strokeWidth="10"
                            strokeLinecap="round"
                            strokeDasharray={`${(item.value / 100) * miniGaugeLength} ${miniGaugeLength}`}
                          />
                        </svg>
                        <div className="absolute inset-0 flex items-center justify-center">
                          <span className={`text-[38px] font-black tabular-nums leading-none ${scoreColor(item.value)}`}>
                            {item.value}
                          </span>
                        </div>
                      </div>
                      <span className="mt-1 text-lg font-black tracking-tight text-white">
                        {item.label}
                      </span>
                      <div className="relative mt-1 flex items-center gap-1.5 text-sm font-medium text-[#c9a98b]">
                        <span>{item.detail}</span>
                        <div className="group relative">
                          <span className="flex h-4 w-4 translate-y-[1px] cursor-help items-center justify-center text-white/45 transition-colors hover:text-white/75">
                            <Question className="h-3 w-3" weight="bold" />
                          </span>
                          <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-3 w-[320px] -translate-x-1/2 rounded-[30px] border border-white/10 bg-[#171717] px-6 py-6 text-left opacity-0 shadow-[0_24px_48px_rgba(0,0,0,0.45)] transition-opacity duration-150 group-hover:opacity-100">
                            <div className="text-[15px] font-bold text-[#3b82f6]">
                              {item.tooltipTitle}
                            </div>
                            <p className="mt-5 text-[13px] font-medium leading-7 text-[#b3b3b3]">
                              {item.tooltipBody}
                            </p>
                            <div className="mt-6 text-[13px] font-bold text-[#bfbfbf]">
                              [ 가이드라인 ]
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
                  ))}
                </div>
              </div>
            )}

            {/* 전략 리스크 진단 (advisor) */}
            {(riskScore != null || overfitRisk != null) && (
              <div className={reportCardClass}>
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <Warning className="w-4 h-4 text-[#62A8CB]" weight="bold" />
                    <p className={reportCardTitleClass}>전략 리스크 진단</p>
                  </div>
                  <div className="h-px w-full bg-white/10" />
                  <div className="grid grid-cols-2 gap-4 sm:gap-6">
                    {riskScore != null && (
                      <div className="flex flex-col items-center justify-between text-center">
                        <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-gray-500">
                          리스크 점수
                        </span>
                        <div className="flex flex-col items-center gap-1">
                          <span className={`text-3xl font-black tabular-nums leading-none ${riskScoreColor(riskScore)}`}>
                            {clampScore(riskScore)}
                          </span>
                          <span className={`text-xs font-bold h-5 flex items-center ${riskScoreColor(riskScore)}`}>
                            {riskScoreLabel(riskScore)}
                          </span>
                        </div>
                        <span className="text-[10px] text-gray-600">높을수록 위험</span>
                      </div>
                    )}
                    {overfitRisk != null && (
                      <div className="flex flex-col items-center justify-between text-center">
                        <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-gray-500">
                          과적합 위험
                        </span>
                        <div className="flex flex-col items-center gap-1">
                          <span className={`text-3xl font-black leading-none ${overfitMeta(overfitRisk).color}`}>
                            {overfitMeta(overfitRisk).label}
                          </span>
                          <span className="h-5" />
                        </div>
                        <span className="text-[10px] text-gray-600">과거에만 맞춘 전략일 위험</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* 총평 */}
            <div className={reportCardClass}>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2.5">
                  <p className={reportCardTitleClass}>총평</p>
                </div>
                <p className="text-sm leading-7 text-gray-300 whitespace-pre-wrap sm:text-[15px]">{summary}</p>
              </div>
            </div>

            {/* 장점 */}
            <div className={reportCardClass}>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <TrendUp className="w-4 h-4 text-emerald-400" weight="bold" />
                  <p className={reportCardTitleClass}>장점</p>
                </div>
                {score !== null && (
                  <div className="h-px w-full bg-white/10" />
                )}
                {strengths.length > 0 ? (
                  <ul className="space-y-3">
                    {strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-3 rounded-2xl px-4 py-3">
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-emerald-400 flex-none" />
                        <span className="text-sm leading-6 text-gray-300 sm:text-[15px]">{s}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">없음</p>
                )}
              </div>
            </div>

            {/* 단점 */}
            <div className={reportCardClass}>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <Warning className="w-4 h-4 text-red-400" weight="bold" />
                  <p className={reportCardTitleClass}>단점</p>
                </div>
                <div className="h-px w-full bg-white/10" />
                {weaknesses.length > 0 ? (
                  <ul className="space-y-3">
                    {weaknesses.map((w, i) => (
                      <li key={i} className="flex items-start gap-3 rounded-2xl px-4 py-3">
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-red-400 flex-none" />
                        <span className="text-sm leading-6 text-gray-300 sm:text-[15px]">{w}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">없음</p>
                )}
              </div>
            </div>

            {/* 개선 방안 */}
            <div className={reportCardClass}>
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-2">
                  <Sparkle className="w-4 h-4 text-amber-400" weight="bold" />
                  <p className={reportCardTitleClass}>개선 방안</p>
                </div>
                <div className="h-px w-full bg-white/10" />
                {improvements.length > 0 ? (
                  <ul className="space-y-3">
                    {improvements.map((imp, i) => (
                      <li key={i} className="flex items-start gap-3 rounded-2xl px-4 py-3">
                        <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-400 flex-none" />
                        <span className="text-sm leading-6 text-gray-300 sm:text-[15px]">{imp}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-gray-500">없음</p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
