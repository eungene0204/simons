"use client";

import { useEffect, useMemo, useState } from "react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import {
  ArrowClockwise,
  ChartBar,
  DownloadSimple,
  FunnelSimple,
  Play,
  SlidersHorizontal,
  Stop,
} from "phosphor-react";
import { t } from "@/lib/i18n";

type SortKey = "cagr" | "sharpe" | "max_drawdown" | "profit_factor" | "trades" | "quality_score";
type TabKey = "leaderboard" | "indicators" | "combinations" | "parameters" | "failures" | "insights";

type PromptSeed = {
  id: string;
  text: string;
  category: string;
  complexity: string;
  risk_profile: string;
  expected_blocks: string[];
};

type ExperimentCandidate = {
  prompt_id: string;
  prompt: string;
  category: string;
  complexity: string;
  risk_profile: string;
  expected_blocks: string[];
  strategy_id?: string | null;
  status: string;
  error_type?: string | null;
  error_message?: string | null;
  metrics?: Record<string, number> | null;
  quality_score?: number | null;
  extracted_blocks?: string[];
  extracted_parameters?: Record<string, unknown>;
};

type ExperimentDetail = {
  id: string;
  status: string;
  totalPrompts: number;
  completedCount: number;
  cacheHitCount: number;
  failedCount: number;
  skippedCount: number;
  candidates: ExperimentCandidate[];
  resultFilePath?: string | null;
  summaryFilePath?: string | null;
  datasetFilePath?: string | null;
  rulesFilePath?: string | null;
  patternsFilePath?: string | null;
};

type AnalysisPayload = {
  best_single_indicators?: Record<string, any>;
  best_indicator_combinations?: Record<string, any>;
  best_parameter_ranges?: Record<string, any>;
  parser_failure_patterns?: Record<string, any>;
  weak_patterns?: Array<Record<string, any>>;
  high_risk_patterns?: Array<Record<string, any>>;
  low_confidence_patterns?: Array<Record<string, any>>;
};

const CATEGORY_DEFAULTS: Record<string, number> = {
  technical_momentum: 45,
  technical_mean_reversion: 45,
  value_fundamental: 45,
  hybrid_value_technical: 60,
  breakout_volume: 35,
  ai_hybrid: 25,
  risk_management_variants: 30,
  ambiguous_beginner_prompts: 15,
};

const SORT_LABELS: Record<SortKey, string> = {
  cagr: "CAGR",
  sharpe: "Sharpe",
  max_drawdown: "MDD",
  profit_factor: "Profit Factor",
  trades: "Trades",
  quality_score: "Quality Score",
};

const TABS: Array<{ id: TabKey; label: string }> = [
  { id: "leaderboard", label: "리더보드" },
  { id: "indicators", label: "지표별 성과 분석" },
  { id: "combinations", label: "조합별 성과 분석" },
  { id: "parameters", label: "파라미터별 성과 분석" },
  { id: "failures", label: "실패 프롬프트 분석" },
  { id: "insights", label: "코치 개선 인사이트" },
];

function formatNumber(value: unknown, digits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return numeric.toFixed(digits);
}

function metric(candidate: ExperimentCandidate, key: SortKey) {
  if (key === "quality_score") return Number(candidate.quality_score ?? 0);
  return Number(candidate.metrics?.[key] ?? 0);
}

function confidenceFromTrades(trades: number) {
  if (trades >= 100) return "high_confidence";
  if (trades >= 30) return "medium_confidence";
  if (trades >= 10) return "low_confidence";
  return "very_low_confidence";
}

function statusClass(status: string) {
  if (status === "computed") return "bg-emerald-500/15 text-emerald-400";
  if (status === "cache_hit") return "bg-sky-500/15 text-sky-400";
  if (status === "failed") return "bg-[var(--main-red)]/10 text-[var(--main-red)]";
  if (status === "running" || status === "parsed") return "bg-amber-500/15 text-amber-400";
  return "bg-white/[0.06] text-gray-400";
}

function buildRows(record: Record<string, any> | undefined) {
  return Object.entries(record ?? {}).sort(
    ([, left], [, right]) => Number(right?.median_quality_score ?? 0) - Number(left?.median_quality_score ?? 0)
  );
}

export default function PromptBacktestExperimentPage() {
  const [seed, setSeed] = useState(42);
  const [categoryCounts, setCategoryCounts] = useState(CATEGORY_DEFAULTS);
  const [prompts, setPrompts] = useState<PromptSeed[]>([]);
  const [experiment, setExperiment] = useState<ExperimentDetail | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("leaderboard");
  const [sortKey, setSortKey] = useState<SortKey>("quality_score");
  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [blockFilter, setBlockFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [confidenceFilter, setConfidenceFilter] = useState("all");
  const [errorFilter, setErrorFilter] = useState("all");
  const [isBusy, setIsBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const totalConfigured = useMemo(
    () => Object.values(categoryCounts).reduce((sum, count) => sum + Number(count ?? 0), 0),
    [categoryCounts]
  );
  const candidates = experiment?.candidates ?? [];
  const progress = experiment?.totalPrompts ? Math.round(((experiment.completedCount + experiment.failedCount + experiment.skippedCount) / experiment.totalPrompts) * 100) : 0;
  const currentPrompt = candidates.find((candidate) => candidate.status === "running" || candidate.status === "parsed")?.prompt ?? null;

  const blocks = useMemo(
    () => Array.from(new Set(candidates.flatMap((candidate) => candidate.extracted_blocks ?? candidate.expected_blocks ?? []))).sort(),
    [candidates]
  );

  const visibleCandidates = useMemo(() => {
    return candidates
      .filter((candidate) => statusFilter === "all" || candidate.status === statusFilter)
      .filter((candidate) => categoryFilter === "all" || candidate.category === categoryFilter)
      .filter((candidate) => riskFilter === "all" || candidate.risk_profile === riskFilter)
      .filter((candidate) => errorFilter === "all" || candidate.error_type === errorFilter)
      .filter((candidate) => blockFilter === "all" || (candidate.extracted_blocks ?? candidate.expected_blocks ?? []).includes(blockFilter))
      .filter((candidate) => confidenceFilter === "all" || confidenceFromTrades(Number(candidate.metrics?.trades ?? 0)) === confidenceFilter)
      .sort((left, right) => {
        const leftValue = metric(left, sortKey);
        const rightValue = metric(right, sortKey);
        if (sortKey === "max_drawdown") return rightValue - leftValue;
        return rightValue - leftValue;
      });
  }, [blockFilter, candidates, categoryFilter, confidenceFilter, errorFilter, riskFilter, sortKey, statusFilter]);

  async function fetchExperiment(experimentId: string) {
    const response = await fetch(`/api/strategy/prompt-experiments?id=${encodeURIComponent(experimentId)}`);
    if (!response.ok) throw new Error("Experiment fetch failed");
    const payload = await response.json();
    setExperiment(payload);
    setLog((prev) => [`상태 갱신: ${payload.status} / ${payload.completedCount} completed`, ...prev].slice(0, 20));
    if (payload.status === "completed") {
      const analysisResponse = await fetch(`/api/strategy/prompt-experiments?id=${encodeURIComponent(experimentId)}&analysis=true`);
      if (analysisResponse.ok) setAnalysis(await analysisResponse.json());
    }
    return payload as ExperimentDetail;
  }

  async function generatePrompts() {
    setIsBusy(true);
    try {
      const response = await fetch("/api/strategy/prompt-experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "generate", seed, categoryCounts }),
      });
      const payload = await response.json();
      setPrompts(payload.prompts ?? []);
      setLog((prev) => [`${payload.totalPrompts ?? 0}개 전략 프롬프트 생성`, ...prev].slice(0, 20));
    } finally {
      setIsBusy(false);
    }
  }

  async function startExperiment() {
    setIsBusy(true);
    try {
      const response = await fetch("/api/strategy/prompt-experiments", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: "Strategy Prompt Experiment",
          seed,
          categoryCounts,
          prompts: prompts.length > 0 ? prompts : undefined,
          concurrency: 2,
        }),
      });
      const payload = await response.json();
      setLog((prev) => [`실험 시작: ${payload.experimentId}`, ...prev].slice(0, 20));
      await fetchExperiment(payload.experimentId);
    } finally {
      setIsBusy(false);
    }
  }

  async function cancelExperiment() {
    if (!experiment) return;
    await fetch("/api/strategy/prompt-experiments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "cancel", experimentId: experiment.id }),
    });
    setLog((prev) => ["실행 취소 요청", ...prev].slice(0, 20));
    await fetchExperiment(experiment.id);
  }

  useEffect(() => {
    if (!experiment || experiment.status === "completed" || experiment.status === "canceled") return;
    const timer = window.setInterval(() => {
      void fetchExperiment(experiment.id);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [experiment]);

  return (
    <DashboardLayout userName="">
      <div className="p-2 md:p-3 space-y-1 w-full min-w-0">
        <div className="border border-white/[0.08]">
          <div className="divide-y divide-white/[0.08]">
            <section className="p-5 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
              <div className="space-y-2 min-w-0">
                <div className="flex items-center gap-2.5">
                  <ChartBar size={21} className="text-sky-400" weight="fill" />
                  <h1 className="text-xl font-black text-white">{t("전략 프롬프트 실험")}</h1>
                </div>
                <p className="text-xs font-bold text-gray-500">
                  {t("프롬프트 생성, 백테스트 실행, 코치 개선 인사이트 생성을 한 화면에서 관리합니다.")}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={generatePrompts}
                  disabled={isBusy}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-md bg-white/[0.08] text-xs font-black text-white hover:bg-white/[0.12] disabled:opacity-50"
                >
                  <ArrowClockwise size={14} weight="bold" />
                  {t("300개 전략 프롬프트 생성")}
                </button>
                <button
                  onClick={startExperiment}
                  disabled={isBusy}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-md bg-[var(--main-blue)] text-xs font-black text-white disabled:opacity-50"
                >
                  <Play size={14} weight="fill" />
                  {t("배치 실행 시작")}
                </button>
                <button
                  onClick={cancelExperiment}
                  disabled={!experiment || experiment.status === "completed" || experiment.status === "canceled"}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded-md border border-white/[0.08] text-xs font-black text-gray-300 disabled:opacity-40"
                >
                  <Stop size={14} weight="fill" />
                  {t("실행 취소")}
                </button>
              </div>
            </section>

            <section className="grid grid-cols-1 xl:grid-cols-10 divide-y xl:divide-y-0 xl:divide-x divide-white/[0.08]">
              <div className="xl:col-span-3 p-5 space-y-4">
                <div className="flex items-center gap-2">
                  <SlidersHorizontal size={15} className="text-gray-500" weight="bold" />
                  <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("생성 설정")}</span>
                </div>
                <label className="block space-y-1">
                  <span className="text-xs font-bold text-gray-500">Seed</span>
                  <input
                    value={seed}
                    onChange={(event) => setSeed(Number(event.target.value))}
                    type="number"
                    className="w-full rounded-md bg-white/[0.04] border border-white/[0.08] px-3 py-2 text-sm font-bold text-white outline-none"
                  />
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {Object.entries(categoryCounts).map(([category, count]) => (
                    <label key={category} className="space-y-1">
                      <span className="block text-[10px] font-bold text-gray-500 truncate">{category}</span>
                      <input
                        value={count}
                        onChange={(event) =>
                          setCategoryCounts((prev) => ({ ...prev, [category]: Number(event.target.value) }))
                        }
                        type="number"
                        className="w-full rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-1.5 text-xs font-bold text-white outline-none"
                      />
                    </label>
                  ))}
                </div>
                <div className="text-xs font-bold text-gray-500 tabular-nums">Configured total: {totalConfigured}</div>
              </div>

              <div className="xl:col-span-7 p-5 space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-6 border-t border-l border-white/[0.08]">
                  {[
                    ["진행률", `${progress}%`],
                    ["성공", experiment?.completedCount ?? 0],
                    ["실패", experiment?.failedCount ?? 0],
                    ["캐시 히트", experiment?.cacheHitCount ?? 0],
                    ["스킵", experiment?.skippedCount ?? 0],
                    ["생성", prompts.length],
                  ].map(([label, value]) => (
                    <div key={label} className="border-r border-b border-white/[0.08] p-3">
                      <div className="text-[10px] font-bold uppercase tracking-widest text-gray-500">{label}</div>
                      <div className="mt-1 text-xl font-black text-white tabular-nums font-outfit">{value}</div>
                    </div>
                  ))}
                </div>
                <div className="h-2 bg-white/[0.04] rounded-md overflow-hidden">
                  <div className="h-full bg-[var(--main-blue)] transition-all" style={{ width: `${progress}%` }} />
                </div>
                <div className="min-h-10 text-xs font-bold text-gray-500">
                  {t("현재 실행 중인 프롬프트:")}{" "}
                  <span className="text-gray-300">{currentPrompt ?? t("대기 중인 실행이 없습니다")}</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <a
                    href={experiment ? `/api/strategy/prompt-experiments?id=${experiment.id}&export=json` : "#"}
                    className="inline-flex items-center gap-2 rounded-md border border-white/[0.08] px-3 py-2 text-xs font-black text-gray-300"
                  >
                    <DownloadSimple size={14} weight="bold" />
                    JSON export
                  </a>
                  <a
                    href={experiment ? `/api/strategy/prompt-experiments?id=${experiment.id}&export=csv` : "#"}
                    className="inline-flex items-center gap-2 rounded-md border border-white/[0.08] px-3 py-2 text-xs font-black text-gray-300"
                  >
                    <DownloadSimple size={14} weight="bold" />
                    CSV export
                  </a>
                </div>
              </div>
            </section>

            <section className="p-5 space-y-3">
              <div className="flex items-center gap-2">
                <FunnelSimple size={15} className="text-gray-500" weight="bold" />
                <span className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("필터와 정렬")}</span>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-2">
                <select aria-label="sort" value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  {Object.entries(SORT_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                </select>
                <select aria-label="category filter" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  <option value="all">category all</option>
                  {Object.keys(CATEGORY_DEFAULTS).map((category) => <option key={category} value={category}>{category}</option>)}
                </select>
                <select aria-label="block filter" value={blockFilter} onChange={(event) => setBlockFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  <option value="all">block all</option>
                  {blocks.map((block) => <option key={block} value={block}>{block}</option>)}
                </select>
                <select aria-label="status filter" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  {["all", "waiting", "running", "parsed", "computed", "cache_hit", "failed", "skipped"].map((status) => <option key={status} value={status}>{status}</option>)}
                </select>
                <select aria-label="risk filter" value={riskFilter} onChange={(event) => setRiskFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  {["all", "conservative", "moderate", "aggressive"].map((risk) => <option key={risk} value={risk}>{risk}</option>)}
                </select>
                <select aria-label="confidence filter" value={confidenceFilter} onChange={(event) => setConfidenceFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  {["all", "very_low_confidence", "low_confidence", "medium_confidence", "high_confidence"].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <select aria-label="error filter" value={errorFilter} onChange={(event) => setErrorFilter(event.target.value)} className="rounded-md bg-white/[0.04] border border-white/[0.08] px-2 py-2 text-xs font-bold text-white">
                  {["all", "parse_error", "conversion_error", "backtest_error", "data_error", "timeout", "zero_trade", "invalid_strategy", "unknown_error"].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </div>
            </section>

            <section>
              <div className="flex overflow-x-auto border-b border-white/[0.08]">
                {TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`shrink-0 px-4 py-3 text-xs font-black ${activeTab === tab.id ? "text-white bg-white/[0.06]" : "text-gray-500"}`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {activeTab === "leaderboard" && (
                <div className="p-5 overflow-x-auto">
                  <div className="min-w-[1180px]">
                    <div className="grid grid-cols-[48px_minmax(260px,1fr)_140px_150px_100px_100px_160px_80px_90px_80px_80px_110px_70px_110px_90px_120px] gap-2 px-2 pb-2 text-xs font-bold uppercase tracking-widest text-gray-500">
                      {["Rank", "Prompt", "Strategy ID", "Category", "Complexity", "Risk Profile", "Blocks", "CAGR", "Total Return", "Sharpe", "MDD", "Profit Factor", "Trades", "Quality Score", "Status", "Error Type"].map((head) => <span key={head}>{head}</span>)}
                    </div>
                    <div className="border-t border-white/[0.05] divide-y divide-white/[0.04]">
                      {visibleCandidates.map((candidate, index) => (
                        <div key={candidate.prompt_id} className="grid grid-cols-[48px_minmax(260px,1fr)_140px_150px_100px_100px_160px_80px_90px_80px_80px_110px_70px_110px_90px_120px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02]">
                          <span className="text-xs font-black text-gray-400 tabular-nums">{index + 1}</span>
                          <span className="text-xs font-bold text-white truncate">{candidate.prompt}</span>
                          <span className="text-[10px] font-bold text-gray-500 truncate">{candidate.strategy_id ?? "-"}</span>
                          <span className="text-[10px] font-bold text-gray-400 truncate">{candidate.category}</span>
                          <span className="text-xs font-bold text-gray-400">{candidate.complexity}</span>
                          <span className="text-xs font-bold text-gray-400">{candidate.risk_profile}</span>
                          <span className="text-[10px] font-bold text-gray-500 truncate">{(candidate.extracted_blocks ?? candidate.expected_blocks ?? []).join(", ")}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.cagr)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.total_return)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.sharpe)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.max_drawdown)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.profit_factor)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.metrics?.trades, 0)}</span>
                          <span className="text-xs font-bold text-white tabular-nums">{formatNumber(candidate.quality_score, 3)}</span>
                          <span className={`w-fit rounded-md px-2 py-1 text-[10px] font-black ${statusClass(candidate.status)}`}>{candidate.status}</span>
                          <span className="text-[10px] font-bold text-gray-500 truncate">{candidate.error_type ?? "-"}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "indicators" && <AnalysisTable rows={buildRows(analysis?.best_single_indicators)} emptyText={t("지표별 성과 분석 데이터가 없습니다.")} />}
              {activeTab === "combinations" && <AnalysisTable rows={buildRows(analysis?.best_indicator_combinations)} emptyText={t("조합별 성과 분석 데이터가 없습니다.")} />}
              {activeTab === "parameters" && <AnalysisTable rows={buildRows(analysis?.best_parameter_ranges)} emptyText={t("파라미터별 성과 분석 데이터가 없습니다.")} />}
              {activeTab === "failures" && <FailurePanel analysis={analysis} candidates={candidates} />}
              {activeTab === "insights" && <InsightsPanel experiment={experiment} analysis={analysis} />}
            </section>

            <section className="p-5">
              <div className="text-xs font-bold uppercase tracking-widest text-gray-500 mb-3">{t("실행 로그")}</div>
              <div className="min-h-24 divide-y divide-white/[0.04] border border-white/[0.08]">
                {(log.length ? log : ["아직 실행 로그가 없습니다."]).map((item, index) => (
                  <div key={`${item}-${index}`} className="px-3 py-2 text-xs font-bold text-gray-500">{item}</div>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}

function AnalysisTable({ rows, emptyText }: { rows: Array<[string, any]>; emptyText: string }) {
  if (rows.length === 0) {
    return <div className="p-8 text-sm font-bold text-gray-600">{emptyText}</div>;
  }
  return (
    <div className="p-5 overflow-x-auto">
      <div className="min-w-[820px]">
        <div className="grid grid-cols-[minmax(180px,1fr)_90px_100px_100px_100px_120px_100px_110px] gap-2 px-2 pb-2 text-xs font-bold uppercase tracking-widest text-gray-500">
          {["Pattern", "Count", "CAGR", "Sharpe", "MDD", "Profit Factor", "Trades", "Confidence"].map((head) => <span key={head}>{head}</span>)}
        </div>
        <div className="border-t border-white/[0.05] divide-y divide-white/[0.04]">
          {rows.map(([key, stats]) => (
            <div key={key} className="grid grid-cols-[minmax(180px,1fr)_90px_100px_100px_100px_120px_100px_110px] gap-2 px-2 py-3 text-xs font-bold text-gray-300">
              <span className="truncate text-white">{key}</span>
              <span className="tabular-nums">{stats.count ?? stats.combination_count ?? 0}</span>
              <span className="tabular-nums">{formatNumber(stats.median_cagr)}</span>
              <span className="tabular-nums">{formatNumber(stats.median_sharpe)}</span>
              <span className="tabular-nums">{formatNumber(stats.median_mdd)}</span>
              <span className="tabular-nums">{formatNumber(stats.median_profit_factor)}</span>
              <span className="tabular-nums">{formatNumber(stats.median_trades, 0)}</span>
              <span>{stats.confidence ?? "low"}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function FailurePanel({ analysis, candidates }: { analysis: AnalysisPayload | null; candidates: ExperimentCandidate[] }) {
  const failureRows = Object.entries(analysis?.parser_failure_patterns ?? {});
  const failedCandidates = candidates.filter((candidate) => candidate.status === "failed");
  return (
    <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="border border-white/[0.08]">
        <div className="px-3 py-2 text-xs font-bold uppercase tracking-widest text-gray-500 border-b border-white/[0.08]">{t("error_type 집계")}</div>
        <div className="divide-y divide-white/[0.04]">
          {failureRows.length === 0 ? (
            <div className="p-3 text-xs font-bold text-gray-600">{t("실패 프롬프트 분석 데이터가 없습니다.")}</div>
          ) : failureRows.map(([key, value]: any) => (
            <div key={key} className="p-3">
              <div className="text-sm font-black text-white">{key}</div>
              <div className="mt-1 text-xs font-bold text-gray-500">count {value.count}</div>
              <div className="mt-2 text-xs font-bold text-gray-400">{value.parser_improvement_suggestion}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="border border-white/[0.08]">
        <div className="px-3 py-2 text-xs font-bold uppercase tracking-widest text-gray-500 border-b border-white/[0.08]">{t("실패 항목")}</div>
        <div className="divide-y divide-white/[0.04] max-h-80 overflow-y-auto">
          {failedCandidates.length === 0 ? (
            <div className="p-3 text-xs font-bold text-gray-600">{t("실패 항목이 없습니다.")}</div>
          ) : failedCandidates.map((candidate) => (
            <div key={candidate.prompt_id} className="p-3">
              <div className="text-xs font-bold text-white">{candidate.prompt}</div>
              <div className="mt-1 text-[10px] font-bold text-[var(--main-red)]">{candidate.error_type}: {candidate.error_message}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function InsightsPanel({ experiment, analysis }: { experiment: ExperimentDetail | null; analysis: AnalysisPayload | null }) {
  const weakPatterns = analysis?.weak_patterns ?? [];
  return (
    <div className="p-5 grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="border border-white/[0.08] p-4 space-y-3">
        <div className="text-xs font-bold uppercase tracking-widest text-gray-500">strategy_experiment_learning</div>
        <pre className="overflow-auto rounded-md bg-white/[0.03] p-3 text-[11px] font-bold text-gray-400">
{JSON.stringify({
  source_file: experiment?.summaryFilePath ?? "data/advisor-learning/strategy_prompt_experiment_summary.json",
  matched_rules: [],
  matched_patterns: weakPatterns.map((pattern) => pattern.pattern),
  similar_samples: [],
  recommended_advice: weakPatterns.slice(0, 1).map((pattern) => pattern.coach_message),
  warnings: analysis?.high_risk_patterns ?? [],
  confidence: "medium",
}, null, 2)}
        </pre>
      </div>
      <div className="border border-white/[0.08] p-4 space-y-3">
        <div className="text-xs font-bold uppercase tracking-widest text-gray-500">{t("파일 다운로드 링크")}</div>
        {[
          ["result", experiment?.resultFilePath],
          ["summary", experiment?.summaryFilePath],
          ["dataset", experiment?.datasetFilePath],
          ["rules", experiment?.rulesFilePath],
          ["patterns", experiment?.patternsFilePath],
        ].map(([label, pathValue]) => (
          <div key={label} className="flex items-center justify-between gap-3 text-xs font-bold">
            <span className="text-gray-500">{label}</span>
            <span className="truncate text-gray-300">{pathValue ?? "-"}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
