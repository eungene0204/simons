"use client";

import { useState, useEffect } from "react";
import { BacktestResult } from "@/types/strategy";
import { Sparkle, ArrowsClockwise, TrendUp, Warning } from "phosphor-react";
import { motion, AnimatePresence } from "framer-motion";

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
  initialRisks?: string[];
  onSummaryReady?: (summary: string, score: number, strengths: string[], risks: string[]) => void;
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

export default function BacktestSummaryCard({
  result,
  strategySummary,
  initialSummary,
  initialScore,
  initialStrengths,
  initialRisks,
  onSummaryReady,
}: BacktestSummaryCardProps) {
  const [summary, setSummary] = useState<string>(initialSummary ?? "");
  const [score, setScore] = useState<number | null>(initialScore ?? null);
  const [strengths, setStrengths] = useState<string[]>(initialStrengths ?? []);
  const [risks, setRisks] = useState<string[]>(initialRisks ?? []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = async () => {
    setLoading(true);
    setError(null);
    setSummary("");
    setScore(null);
    setStrengths([]);
    setRisks([]);

    try {
      const res = await fetch("/api/backtest/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          metrics: {
            totalReturn: result.totalReturn,
            cagr: result.cagr,
            buyAndHoldReturn: result.buyAndHoldReturn,
            maxDrawdown: result.maxDrawdown,
            sharpe: result.sharpe,
            sortino: result.sortino,
            profitFactor: result.profitFactor,
            winRate: result.winRate,
            trades: result.trades,
            volatility: result.volatility,
            kelly: result.kelly,
            initialCapital: result.initialCapital,
            finalEquity: result.finalEquity,
          },
          strategySummary,
        }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Unknown error");
      setScore(data.score ?? null);
      setSummary(data.summary ?? "");
      setStrengths(data.strengths ?? []);
      setRisks(data.risks ?? []);
      if (data.summary && data.score != null) {
        onSummaryReady?.(data.summary, data.score, data.strengths ?? [], data.risks ?? []);
      }
    } catch (e: any) {
      setError(e.message ?? "요약 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // 캐시된 결과가 있으면 즉시 표시, 없으면 사용자 클릭 대기 (자동 호출 제거)
    if (initialSummary && initialScore != null) return;
    // AI 요약은 모델 로드에 수십 초 소요 → 자동 호출하지 않고 버튼 클릭 시에만 생성
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.executionId]);

  const hasContent = !loading && !!summary;

  return (
    <div className="glass-card h-full px-5 py-4 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2 text-base font-black uppercase tracking-widest text-white">
          <Sparkle className="w-4 h-4 text-white/30" weight="fill" />
          AI 백테스트 리포트
          <span className="text-[10px] font-mono text-gray-700 normal-case tracking-normal">
            {typeof navigator !== "undefined" && navigator.platform?.toLowerCase().includes("mac")
              ? "mlx · Qwen2.5-32B"
              : "ollama · qwen2.5:32b"}
          </span>
        </div>
        <button
          onClick={fetchSummary}
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
            className="flex items-center gap-2 text-sm text-gray-600"
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
            className="text-xs text-red-400/70"
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
            className="flex-1 flex flex-col items-center justify-center gap-3"
          >
            <p className="text-xs text-gray-600">AI 리포트가 아직 생성되지 않았습니다.</p>
            <button
              onClick={fetchSummary}
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
            className="grid grid-cols-3 gap-4 flex-1"
          >
            {/* 총평 */}
            <div className="flex flex-col gap-2">
              <p className="text-xs font-bold uppercase tracking-widest text-gray-500">총평</p>
              <div className="flex items-start gap-2.5">
                {score !== null && (
                  <div className={`flex-none flex flex-col items-center justify-center w-10 h-10 rounded-lg border ${scoreBorder(score)}`}>
                    <span className={`text-base font-black tabular-nums leading-none ${scoreColor(score)}`}>{score}</span>
                    <span className={`text-[8px] font-bold ${scoreColor(score)}`}>{scoreLabel(score)}</span>
                  </div>
                )}
                <p className="text-xs text-gray-300 leading-relaxed">{summary}</p>
              </div>
            </div>

            {/* 강점 */}
            <div className="border-l border-white/5 pl-4">
              <div className="flex items-center gap-1.5 mb-2">
                <TrendUp className="w-3 h-3 text-emerald-400" weight="bold" />
                <p className="text-xs font-bold uppercase tracking-widest text-gray-500">강점</p>
              </div>
              {strengths.length > 0 ? (
                <ul className="space-y-1.5">
                  {strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="mt-1.5 w-1 h-1 rounded-full bg-emerald-500/60 flex-none" />
                      <span className="text-xs text-gray-400 leading-relaxed">{s}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gray-600">없음</p>
              )}
            </div>

            {/* 리스크 */}
            <div className="border-l border-white/5 pl-4">
              <div className="flex items-center gap-1.5 mb-2">
                <Warning className="w-3 h-3 text-orange-400" weight="bold" />
                <p className="text-xs font-bold uppercase tracking-widest text-gray-500">리스크 및 개선안</p>
              </div>
              {risks.length > 0 ? (
                <ul className="space-y-1.5">
                  {risks.map((r, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span className="mt-1.5 w-1 h-1 rounded-full bg-orange-500/60 flex-none" />
                      <span className="text-xs text-gray-400 leading-relaxed">{r}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gray-600">없음</p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
