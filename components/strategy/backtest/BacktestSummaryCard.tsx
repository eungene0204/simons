"use client";

import { useState, useEffect } from "react";
import { BacktestResult } from "@/types/strategy";
import { Sparkle, ArrowsClockwise } from "phosphor-react";
import { motion, AnimatePresence } from "framer-motion";

interface BacktestSummaryCardProps {
  result: BacktestResult;
  strategySummary?: {
    strategyName?: string;
    universeName?: string;
    entryBlocks?: string[];
    exitBlocks?: string[];
  };
}

export default function BacktestSummaryCard({
  result,
  strategySummary,
}: BacktestSummaryCardProps) {
  const [summary, setSummary] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = async () => {
    setLoading(true);
    setError(null);
    setSummary("");

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
      setSummary(data.summary);
    } catch (e: any) {
      setError(e.message ?? "요약 생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  // Auto-fetch on mount
  useEffect(() => {
    fetchSummary();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.executionId]);

  return (
    <div className="mb-4 rounded-2xl border border-white/5 bg-[#0d0d0d] px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-gray-500">
          <Sparkle className="w-3.5 h-3.5 text-blue-400" weight="fill" />
          AI 결과 요약
          <span className="text-[10px] font-mono text-gray-700 normal-case tracking-normal">
            {typeof navigator !== "undefined" && navigator.platform?.toLowerCase().includes("mac")
              ? "mlx · Qwen2.5-3B"
              : "ollama · qwen2.5:3b"}
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

        {!loading && summary && (
          <motion.p
            key="summary"
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="text-sm text-gray-300 leading-relaxed"
          >
            {summary}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
