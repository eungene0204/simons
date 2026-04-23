"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowsClockwise,
  CheckCircle,
  Lightning,
  Newspaper,
  Robot,
  TestTube,
  Warning,
  X,
} from "phosphor-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Issue {
  code: string;
  severity: "low" | "medium" | "high";
  message: string;
}

interface ProposedChange {
  field: string;
  action: string;
  value: unknown;
  description: string;
}

interface Recommendation {
  type: string;
  priority: number;
  title: string;
  reason: string;
  proposed_change?: ProposedChange | null;
}

interface NewsAnalysis {
  summary: string;
  risk_level: "low" | "medium" | "high";
  key_events: string[];
}

interface AIModelRecommendation {
  recommended: boolean;
  reason: string;
}

export interface AdvisorResult {
  strategy_score: number;
  risk_score: number;
  overfit_risk: "low" | "medium" | "high";
  issues: Issue[];
  recommendations: Recommendation[];
  news_analysis?: NewsAnalysis | null;
  suggested_experiments: string[];
  ai_model_recommendation: AIModelRecommendation;
}

export interface AdvisorRequest {
  user_prompt: string;
  parsed_strategy: Record<string, unknown>;
  backtest_result?: {
    cagr?: number | null;
    mdd?: number | null;
    sharpe?: number | null;
    profit_factor?: number | null;
    trade_count?: number | null;
    win_rate?: number | null;
  } | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-400";
  if (score >= 60) return "text-blue-400";
  if (score >= 40) return "text-amber-400";
  return "text-red-400";
}

function riskColor(level: "low" | "medium" | "high" | string) {
  if (level === "high") return "text-red-400";
  if (level === "medium") return "text-amber-400";
  return "text-emerald-400";
}

function severityBadge(sev: "low" | "medium" | "high") {
  const map = {
    high: "bg-red-500/15 text-red-400 border-red-500/20",
    medium: "bg-amber-500/15 text-amber-400 border-amber-500/20",
    low: "bg-white/[0.05] text-gray-400 border-white/[0.08]",
  };
  const label = { high: "높음", medium: "중간", low: "낮음" };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-black border ${map[sev]}`}>
      {label[sev]}
    </span>
  );
}

function overfitBadge(risk: "low" | "medium" | "high") {
  const map = {
    high: "bg-red-500/15 text-red-400 border-red-500/20",
    medium: "bg-amber-500/15 text-amber-400 border-amber-500/20",
    low: "bg-emerald-500/15 text-emerald-400 border-emerald-500/20",
  };
  const label = { high: "높음", medium: "중간", low: "낮음" };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-black border ${map[risk]}`}>
      과최적화 위험 {label[risk]}
    </span>
  );
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({
  icon,
  title,
  count,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">{title}</span>
        {count !== undefined && count > 0 && (
          <span className="ml-auto text-[10px] font-black text-gray-600">{count}건</span>
        )}
      </div>
      {children}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function StrategyAdvisorPanel({
  request,
  onDismiss,
}: {
  request: AdvisorRequest | null;
  onDismiss?: () => void;
}) {
  const [result, setResult] = useState<AdvisorResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // track last fetched request to avoid duplicate calls
  const lastReqKey = useRef<string | null>(null);

  useEffect(() => {
    if (!request) return;

    const key = JSON.stringify(request);
    if (key === lastReqKey.current) return;
    lastReqKey.current = key;

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch("/api/advisor/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`advisor error ${res.status}`);
        return res.json();
      })
      .then((data) => {
        if (!cancelled) {
          setResult(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
      // reset so the next effect can re-fetch if React re-renders before this fetch completes
      lastReqKey.current = null;
    };
  }, [request]);

  if (!request) return null;

  return (
    <div className="flex flex-col h-full bg-[var(--card-bg)] border border-white/[0.06] rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] flex-shrink-0">
        <div className="flex items-center gap-2">
          <Robot size={13} weight="fill" className="text-indigo-400" />
          <span className="text-xs font-black text-white">전략 코치</span>
        </div>
        <div className="flex items-center gap-2">
          {loading && (
            <ArrowsClockwise size={11} className="text-indigo-400 animate-spin" />
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="text-gray-600 hover:text-gray-400 transition-colors"
            >
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto scrollbar-hide px-4 py-4 space-y-5">

        {/* Loading skeleton */}
        {loading && !result && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-10 rounded-xl bg-white/[0.03] animate-pulse"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            ))}
            <p className="text-[10px] font-bold text-gray-600 text-center pt-1">전략 분석 중...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-xl bg-red-500/10 border border-red-500/20">
            <Warning size={12} className="text-red-400 flex-shrink-0 mt-0.5" weight="fill" />
            <p className="text-[10px] font-bold text-red-400">{error}</p>
          </div>
        )}

        {result && (
          <>
            {/* Score bar */}
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-3">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <p className="text-[10px] font-bold text-gray-500">전략 점수</p>
                  <p className={`text-2xl font-black ${scoreColor(result.strategy_score)}`}>
                    {result.strategy_score.toFixed(0)}
                    <span className="text-xs font-bold text-gray-600 ml-0.5">/ 100</span>
                  </p>
                </div>
                <div className="space-y-0.5 text-right">
                  <p className="text-[10px] font-bold text-gray-500">리스크 점수</p>
                  <p className={`text-2xl font-black ${riskColor(result.risk_score >= 60 ? "high" : result.risk_score >= 30 ? "medium" : "low")}`}>
                    {result.risk_score.toFixed(0)}
                    <span className="text-xs font-bold text-gray-600 ml-0.5">/ 100</span>
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${
                      result.strategy_score >= 80 ? "bg-emerald-500" :
                      result.strategy_score >= 60 ? "bg-blue-500" :
                      result.strategy_score >= 40 ? "bg-amber-500" : "bg-red-500"
                    }`}
                    style={{ width: `${result.strategy_score}%` }}
                  />
                </div>
                {overfitBadge(result.overfit_risk)}
              </div>
            </div>

            {/* Issues */}
            {result.issues.length > 0 && (
              <Section
                icon={<Warning size={11} className="text-amber-400" weight="fill" />}
                title="진단"
                count={result.issues.length}
              >
                <div className="space-y-1.5">
                  {result.issues.map((issue, i) => (
                    <div
                      key={i}
                      className="flex items-start gap-2 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]"
                    >
                      <div className="flex-shrink-0 mt-0.5">
                        {severityBadge(issue.severity)}
                      </div>
                      <p className="text-[11px] font-bold text-gray-300 leading-relaxed">{issue.message}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Recommendations */}
            {result.recommendations.length > 0 && (
              <Section
                icon={<Lightning size={11} className="text-indigo-400" weight="fill" />}
                title="개선 제안"
                count={result.recommendations.length}
              >
                <div className="space-y-1.5">
                  {result.recommendations.slice(0, 5).map((rec, i) => (
                    <div
                      key={i}
                      className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-[11px] font-black text-white">{rec.title}</p>
                        <span className="text-[9px] font-black text-gray-600 bg-white/[0.04] rounded px-1 py-0.5">
                          P{rec.priority}
                        </span>
                      </div>
                      <p className="text-[10px] font-bold text-gray-500 leading-relaxed">{rec.reason}</p>
                      {rec.proposed_change && rec.proposed_change.description && (
                        <p className="text-[10px] font-bold text-indigo-400/80 leading-relaxed">
                          → {rec.proposed_change.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* News analysis */}
            {result.news_analysis && (
              <Section
                icon={<Newspaper size={11} className="text-sky-400" weight="fill" />}
                title="뉴스 리스크"
              >
                <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] font-bold text-gray-500">리스크 수준</span>
                    <span className={`text-[10px] font-black ${riskColor(result.news_analysis.risk_level)}`}>
                      {result.news_analysis.risk_level === "high" ? "높음" :
                       result.news_analysis.risk_level === "medium" ? "중간" : "낮음"}
                    </span>
                  </div>
                  <p className="text-[10px] font-bold text-gray-400 leading-relaxed">{result.news_analysis.summary}</p>
                  {result.news_analysis.key_events.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {result.news_analysis.key_events.map((ev, i) => (
                        <span
                          key={i}
                          className="inline-flex items-center px-2 py-0.5 rounded bg-sky-500/10 border border-sky-500/15 text-[9px] font-black text-sky-400"
                        >
                          {ev}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* AI model recommendation */}
            <Section
              icon={<Robot size={11} className="text-purple-400" weight="fill" />}
              title="AI 모델"
            >
              <div className="flex items-start gap-2 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05]">
                <CheckCircle
                  size={12}
                  weight="fill"
                  className={`flex-shrink-0 mt-0.5 ${result.ai_model_recommendation.recommended ? "text-purple-400" : "text-gray-600"}`}
                />
                <p className="text-[10px] font-bold text-gray-400 leading-relaxed">
                  {result.ai_model_recommendation.reason}
                </p>
              </div>
            </Section>

            {/* Suggested experiments */}
            {result.suggested_experiments.length > 0 && (
              <Section
                icon={<TestTube size={11} className="text-teal-400" weight="fill" />}
                title="추천 실험"
                count={result.suggested_experiments.length}
              >
                <div className="space-y-1">
                  {result.suggested_experiments.map((exp, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span className="text-[10px] font-black text-teal-600 flex-shrink-0 mt-0.5">
                        {i + 1}.
                      </span>
                      <p className="text-[10px] font-bold text-gray-500 leading-relaxed">{exp}</p>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </>
        )}
      </div>
    </div>
  );
}
