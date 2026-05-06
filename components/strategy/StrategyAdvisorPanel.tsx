"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowsClockwise,
  CheckCircle,
  GitBranch,
  Lightbulb,
  Newspaper,
  Robot,
  TestTube,
  Warning,
  X,
} from "phosphor-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AdviceItem {
  severity: "low" | "medium" | "high";
  title: string;
  body: string;
  proposed_change?: { field: string; action: string; value: unknown; description: string } | null;
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

interface StrategyMemoryContext {
  confidence: "low" | "medium" | "high" | string;
  data_sufficiency: "sufficient" | "insufficient" | string;
  similar_strategy_ids?: string[];
  retrieved_cases?: Array<{
    case_strategy_id?: string;
    lesson?: string;
    advice_success?: boolean | null;
  }>;
}

interface AdviceEvaluation {
  advice_success: boolean;
  improved_metrics: string[];
  worsened_metrics: string[];
  net_effect: "positive" | "neutral" | "negative" | string;
  reason: string;
  overfitting_risk: "low" | "medium" | "high" | string;
  oos_validation_required: boolean;
}

interface ResponseSection {
  title: string;
  body: string;
}

export interface AdvisorResult {
  strategy_score: number;
  risk_score: number;
  overfit_risk: "low" | "medium" | "high";
  advice: AdviceItem[];
  news_analysis?: NewsAnalysis | null;
  strategy_memory_context?: StrategyMemoryContext | null;
  candidate_strategy?: Record<string, unknown> | null;
  advice_evaluation?: AdviceEvaluation | null;
  response_sections?: ResponseSection[];
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

function riskColor(level: "low" | "medium" | "high" | string) {
  if (level === "high") return "text-[var(--main-red)]";
  if (level === "medium") return "text-amber-400";
  return "text-emerald-400";
}

function metricLabel(metric: string) {
  const labels: Record<string, string> = {
    cagr: "CAGR",
    mdd: "MDD",
    sharpe: "Sharpe",
    sortino: "Sortino",
    calmar: "Calmar",
    profit_factor: "Profit Factor",
    win_rate: "승률",
    trade_count: "거래 횟수",
    turnover: "Turnover",
    avg_trade_return: "평균 손익",
    max_losing_streak: "최대 연속 손실",
  };
  return labels[metric] ?? metric;
}

function confidenceLabel(value: string) {
  if (value === "high") return "높음";
  if (value === "medium") return "중간";
  if (value === "low") return "낮음";
  return value;
}

function netEffectLabel(value: string) {
  if (value === "positive") return "개선";
  if (value === "neutral") return "중립";
  if (value === "negative") return "악화";
  return value;
}

// ─── Section label ────────────────────────────────────────────────────────────

function SectionLabel({ icon, title, count }: { icon: React.ReactNode; title: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.08]">
      {icon}
      <span className="text-sm font-black uppercase tracking-widest text-white font-outfit">{title}</span>
      {count !== undefined && count > 0 && (
        <span className="ml-auto text-xs font-bold text-gray-500">{count}건</span>
      )}
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
      lastReqKey.current = null;
    };
  }, [request]);

  if (!request) return null;

  return (
    <div className="flex flex-col h-full bg-[var(--card-bg)] border border-white/[0.08] rounded-2xl overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.08] flex-shrink-0">
        <div className="flex items-center gap-2">
          <Robot size={16} weight="bold" className="text-gray-500" />
          <span className="text-sm font-black uppercase tracking-widest text-white font-outfit">전략 코치</span>
        </div>
        <div className="flex items-center gap-2">
          {loading && (
            <ArrowsClockwise size={14} className="text-gray-500 animate-spin" />
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="p-1 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/10 transition-all duration-200"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">

        {/* Loading skeleton */}
        {loading && !result && (
          <div className="p-4 space-y-2">
            {[80, 60, 70].map((w, i) => (
              <div
                key={i}
                className="h-11 bg-white/[0.04] rounded-xl animate-pulse"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            ))}
            <p className="text-xs font-bold text-gray-600 text-center pt-2">전략 분석 중...</p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="flex items-start gap-2 m-4 p-3 rounded-xl bg-[var(--main-red)]/5 border border-[var(--main-red)]/20">
            <Warning size={14} weight="bold" className="text-[var(--main-red)] flex-shrink-0 mt-0.5" />
            <p className="text-sm font-bold text-[var(--main-red)]">{error}</p>
          </div>
        )}

        {result && (
          <div className="p-4 space-y-3">

            {/* Structured response */}
            {(result.response_sections?.length ?? 0) > 0 && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<CheckCircle size={14} weight="bold" className="text-gray-500" />}
                  title="전략 리뷰"
                  count={result.response_sections?.length}
                />
                <div className="divide-y divide-white/[0.04]">
                  {result.response_sections?.map((section, i) => (
                    <div key={`${section.title}-${i}`} className="px-4 py-3 hover:bg-white/[0.02] transition-colors duration-150">
                      <div className="flex items-start gap-3">
                        <span className="text-[10px] font-black text-gray-600 tabular-nums font-outfit mt-0.5">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-black uppercase tracking-widest text-gray-400 font-outfit">
                            {section.title}
                          </p>
                          <p className="text-sm font-bold text-gray-500 leading-relaxed mt-1">
                            {section.body}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 조언 드립니다 */}
            {result.advice.length > 0 && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<Lightbulb size={14} weight="fill" className="text-yellow-400" />}
                  title="조언 드립니다"
                  count={result.advice.length}
                />
                <div className="divide-y divide-white/[0.04]">
                  {result.advice.map((item, i) => (
                    <div key={i} className="px-4 py-3 hover:bg-white/[0.02] transition-colors duration-150">
                      <p className="text-sm font-bold text-white leading-snug">{item.title}</p>
                      {item.body && (
                        <p className="text-xs font-bold text-gray-500 leading-relaxed mt-1">{item.body}</p>
                      )}
                      {item.proposed_change?.description && (
                        <p className="text-xs font-bold text-indigo-400 leading-relaxed mt-1.5">
                          → {item.proposed_change.description}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Experience Memory */}
            {result.strategy_memory_context && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<GitBranch size={14} weight="bold" className="text-gray-500" />}
                  title="유사 전략 경험"
                  count={result.strategy_memory_context.retrieved_cases?.length ?? 0}
                />
                <div className="px-4 py-3 space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    <span className={`px-2 py-0.5 rounded-md text-xs font-black bg-white/[0.06] ${riskColor(result.strategy_memory_context.confidence)}`}>
                      신뢰도 {confidenceLabel(result.strategy_memory_context.confidence)}
                    </span>
                    <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-white/[0.06] text-gray-400">
                      {result.strategy_memory_context.data_sufficiency === "sufficient" ? "사례 충분" : "사례 부족"}
                    </span>
                    {(result.strategy_memory_context.similar_strategy_ids?.length ?? 0) > 0 && (
                      <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-white/[0.06] text-gray-500">
                        유사 전략 {result.strategy_memory_context.similar_strategy_ids?.length}개
                      </span>
                    )}
                  </div>

                  {result.strategy_memory_context.data_sufficiency !== "sufficient" && (
                    <p className="text-xs font-bold text-amber-400 leading-relaxed">
                      저장된 유사 사례가 부족합니다. 현재 조언은 재백테스트 전 가설로만 다뤄야 합니다.
                    </p>
                  )}

                  {(result.strategy_memory_context.retrieved_cases?.length ?? 0) > 0 && (
                    <div className="divide-y divide-white/[0.04] border-t border-white/[0.05]">
                      {result.strategy_memory_context.retrieved_cases?.slice(0, 3).map((caseItem, i) => (
                        <div key={`${caseItem.case_strategy_id ?? "case"}-${i}`} className="py-2">
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] font-black text-gray-600 tabular-nums font-outfit">
                              {caseItem.case_strategy_id?.slice(0, 10) ?? `case-${i + 1}`}
                            </span>
                            {caseItem.advice_success !== null && caseItem.advice_success !== undefined && (
                              <span className={`text-[10px] font-black ${caseItem.advice_success ? "text-emerald-400" : "text-[var(--main-red)]"}`}>
                                {caseItem.advice_success ? "성공" : "실패"}
                              </span>
                            )}
                          </div>
                          {caseItem.lesson && (
                            <p className="text-xs font-bold text-gray-500 leading-relaxed mt-1">{caseItem.lesson}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Candidate / evaluation */}
            {(result.candidate_strategy || result.advice_evaluation) && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<CheckCircle size={14} weight="bold" className="text-gray-500" />}
                  title="개선 후보 평가"
                />
                <div className="px-4 py-3 space-y-3">
                  {result.candidate_strategy && (
                    <div>
                      <p className="text-xs font-bold uppercase tracking-widest text-gray-500">후보 전략</p>
                      <p className="text-sm font-bold text-gray-400 leading-relaxed mt-1">
                        조언을 반영한 후보 DSL이 생성되었습니다. 동일한 백테스트 조건에서 기존 전략과 비교해야 합니다.
                      </p>
                    </div>
                  )}

                  {result.advice_evaluation && (
                    <div className="space-y-2">
                      <div className="flex flex-wrap gap-1.5">
                        <span className={`px-2 py-0.5 rounded-md text-xs font-black bg-white/[0.06] ${
                          result.advice_evaluation.net_effect === "positive"
                            ? "text-emerald-400"
                            : result.advice_evaluation.net_effect === "neutral"
                              ? "text-amber-400"
                              : "text-[var(--main-red)]"
                        }`}>
                          {netEffectLabel(result.advice_evaluation.net_effect)}
                        </span>
                        <span className={`px-2 py-0.5 rounded-md text-xs font-bold bg-white/[0.06] ${riskColor(result.advice_evaluation.overfitting_risk)}`}>
                          과최적화 {confidenceLabel(result.advice_evaluation.overfitting_risk)}
                        </span>
                        {result.advice_evaluation.oos_validation_required && (
                          <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-white/[0.06] text-amber-400">
                            OOS 필요
                          </span>
                        )}
                      </div>

                      <p className="text-sm font-bold text-gray-400 leading-relaxed">
                        {result.advice_evaluation.reason}
                      </p>

                      {(result.advice_evaluation.improved_metrics.length > 0 || result.advice_evaluation.worsened_metrics.length > 0) && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-gray-600">개선</p>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {result.advice_evaluation.improved_metrics.map((metric) => (
                                <span key={metric} className="px-2 py-0.5 rounded-md text-xs font-bold bg-emerald-500/10 text-emerald-400">
                                  {metricLabel(metric)}
                                </span>
                              ))}
                            </div>
                          </div>
                          <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-gray-600">악화</p>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {result.advice_evaluation.worsened_metrics.map((metric) => (
                                <span key={metric} className="px-2 py-0.5 rounded-md text-xs font-bold bg-[var(--main-red)]/10 text-[var(--main-red)]">
                                  {metricLabel(metric)}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 뉴스 리스크 */}
            {result.news_analysis && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<Newspaper size={14} weight="bold" className="text-gray-500" />}
                  title="뉴스 리스크"
                />
                <div className="px-4 py-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-gray-500">리스크 수준</span>
                    <span className={`text-xs font-black ${riskColor(result.news_analysis.risk_level)}`}>
                      {result.news_analysis.risk_level === "high" ? "높음" :
                       result.news_analysis.risk_level === "medium" ? "중간" : "낮음"}
                    </span>
                  </div>
                  <p className="text-sm font-bold text-gray-400 leading-relaxed">
                    {result.news_analysis.summary}
                  </p>
                  {result.news_analysis.key_events.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {result.news_analysis.key_events.map((ev, i) => (
                        <span key={i} className="px-2 py-0.5 rounded-md text-xs font-bold bg-white/[0.06] text-gray-400">
                          {ev}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* AI 모델 */}
            <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
              <SectionLabel
                icon={<Robot size={14} weight="bold" className="text-gray-500" />}
                title="AI 모델"
              />
              <div className="px-4 py-3 flex items-start gap-2">
                <CheckCircle
                  size={16}
                  weight="fill"
                  className={`flex-shrink-0 mt-0.5 ${result.ai_model_recommendation.recommended ? "text-indigo-400" : "text-gray-600"}`}
                />
                <p className="text-sm font-bold text-gray-400 leading-relaxed">
                  {result.ai_model_recommendation.reason}
                </p>
              </div>
            </div>

            {/* 추천 실험 */}
            {result.suggested_experiments.length > 0 && (
              <div className="border border-white/[0.08] rounded-2xl overflow-hidden">
                <SectionLabel
                  icon={<TestTube size={14} weight="bold" className="text-gray-500" />}
                  title="추천 실험"
                  count={result.suggested_experiments.length}
                />
                <div className="divide-y divide-white/[0.04]">
                  {result.suggested_experiments.map((exp, i) => (
                    <div key={i} className="px-4 py-3 flex items-start gap-3 hover:bg-white/[0.02] transition-colors duration-150">
                      <span className="text-xs font-black text-gray-600 flex-shrink-0 mt-0.5 tabular-nums font-outfit">
                        {i + 1}
                      </span>
                      <p className="text-sm font-bold text-gray-400 leading-relaxed">{exp}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
}
