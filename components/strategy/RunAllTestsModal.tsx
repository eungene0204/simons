"use client";

import { useEffect, useMemo, useState } from "react";
import type { BacktestResult } from "@/types/strategy";
import { formatProfitFactor, profitFactorForRanking } from "@/lib/format-profit-factor";
import {
  ArrowsClockwise,
  CheckCircle,
  ClockCounterClockwise,
  Copy,
  Crown,
  Sparkle,
  Warning,
  X,
} from "phosphor-react";
import { getLocale, t } from "@/lib/i18n";

type BatchStatus = "waiting" | "running" | "computed" | "cache_hit" | "failed" | "skipped";
type SortKey = "cagr" | "totalReturn" | "sharpe" | "maxDrawdown" | "profitFactor" | "trades";
type SortDirection = "asc" | "desc";
type BatchRunLifecycle = "QUEUED" | "RUNNING" | "COMPLETED" | "CANCELED";
const BATCH_RUN_POLL_MS = 250;

interface BatchItem {
  id: string;
  prompt: string;
  name: string;
  status: BatchStatus;
  message: string;
  result?: BacktestResult;
  error?: string;
}

interface BatchRunRecord {
  runId: string;
  createdAt: string;
  totalPrompts: number;
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  runStatus: BatchRunLifecycle;
  currentStrategyName?: string | null;
  rankingSnapshot: Array<{
    rank: number;
    strategyId: string;
    name: string;
    status: BatchStatus;
    cagr: number;
    totalReturn: number;
    sharpe: number;
    maxDrawdown: number;
    profitFactor: number;
    trades: number;
  }>;
  items: BatchItem[];
  logs: string[];
}

interface BatchRunSummaryRecord {
  runId: string;
  createdAt: string;
  totalPrompts: number;
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  runStatus?: BatchRunLifecycle;
  rankingSnapshot: BatchRunRecord["rankingSnapshot"];
}

function toHistorySummary(record: BatchRunRecord): BatchRunSummaryRecord {
  return {
    runId: record.runId,
    createdAt: record.createdAt,
    totalPrompts: record.totalPrompts,
    completedCount: record.completedCount,
    failedCount: record.failedCount,
    skippedCount: record.skippedCount,
    runStatus: record.runStatus,
    rankingSnapshot: record.rankingSnapshot,
  };
}

function splitPromptDataset(raw: string): string[] {
  return raw
    .split(/\n\s*\n/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mapRawBacktestResult(raw: any): BacktestResult {
  const equity: number[] = raw.equity ?? [];
  return {
    executionId: `batch_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    strategyId: raw.strategy_id ?? "batch_strategy",
    symbols: raw.symbols,
    totalReturn: raw.totalReturn ?? 0,
    cagr: raw.cagr ?? 0,
    buyAndHoldReturn: raw.buyAndHoldReturn ?? 0,
    maxDrawdown: raw.maxDrawdown ?? 0,
    winRate: raw.winRate ?? 0,
    profitFactor: raw.profitFactor ?? null,
    sharpe: raw.sharpe ?? 0,
    sortino: raw.sortino ?? 0,
    kelly: raw.kelly ?? null,
    volatility: raw.volatility ?? 0,
    trades: raw.trades ?? 0,
    avgProfit: raw.avgProfit ?? 0,
    avgLoss: raw.avgLoss ?? 0,
    maxConsecutiveWins: raw.maxConsecutiveWins ?? 0,
    maxConsecutiveLosses: raw.maxConsecutiveLosses ?? 0,
    finalEquity: equity[equity.length - 1] ?? 0,
    initialCapital: equity[0] ?? 0,
    equity,
    benchmarkEquity: raw.benchmark_equity,
    benchmarkLabel: raw.benchmark_label,
    benchmarkPartial: raw.benchmark_partial,
    dates: raw.dates ?? [],
    tradesList: (raw.signals ?? []).map((signal: any) => ({
      date: signal.date,
      symbol: signal.symbol,
      type: signal.type as "buy" | "sell",
      price: signal.price,
      quantity: signal.quantity ?? 0,
      amount: signal.amount ?? 0,
      reason: signal.condition,
    })),
    monthlyReturns: {},
    yearlyReturns: {},
    signals: (raw.signals ?? []).map((signal: any) => ({
      date: signal.date,
      symbol: signal.symbol,
      type: signal.type === "buy" ? "entry" : "exit",
      condition: signal.condition,
      price: Number(signal.price),
      quantity: Number(signal.quantity),
      amount: Number(signal.amount),
    })),
    perAssetStats: raw.perAssetStats,
    universeId: raw.universe_id,
    warnings: raw.warnings,
    executionTime: raw.executionTime,
    fromCache: raw.fromCache,
    cacheKey: raw.cacheKey,
  };
}

function formatMetric(value: number | undefined, digits = 2, suffix = "") {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}${suffix}`;
}

function getStatusLabel(status: BatchStatus) {
  if (status === "cache_hit") return "Cache Hit";
  if (status === "computed") return "Computed";
  if (status === "failed") return "Failed";
  if (status === "skipped") return "Skipped";
  if (status === "running") return "Running";
  return "Waiting";
}

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(getLocale(), {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function rankItems(items: BatchItem[], sortKey: SortKey, sortDirection: SortDirection) {
  const successful = items.filter((item) => item.result);
  return successful.sort((left, right) => {
    const leftValue = left.result?.[sortKey] ?? 0;
    const rightValue = right.result?.[sortKey] ?? 0;
    if (leftValue === rightValue) {
      return left.name.localeCompare(right.name, "ko");
    }
    return sortDirection === "desc" ? rightValue - leftValue : leftValue - rightValue;
  });
}

async function fetchBatchRunHistory(): Promise<BatchRunSummaryRecord[]> {
  const response = await fetch("/api/strategy/batch-runs");
  if (!response.ok) {
    throw new Error(t("배치 실행 이력을 불러오지 못했습니다."));
  }

  const payload = await response.json();
  return Array.isArray(payload?.runs) ? payload.runs : [];
}

function mapMetricsToResult(raw: any, strategyId: string): BacktestResult {
  return mapRawBacktestResult({
    ...raw,
    strategy_id: raw?.strategy_id ?? strategyId,
  });
}

function mapBatchRunDetail(payload: any): BatchRunRecord {
  const candidates = Array.isArray(payload?.candidates) ? payload.candidates : [];

  return {
    runId: String(payload?.runId ?? ""),
    createdAt: String(payload?.createdAt ?? new Date().toISOString()),
    totalPrompts: Number(payload?.totalPrompts ?? candidates.length ?? 0),
    completedCount: Number(payload?.completedCount ?? 0),
    failedCount: Number(payload?.failedCount ?? 0),
    skippedCount: Number(payload?.skippedCount ?? 0),
    runStatus: (payload?.status ?? "QUEUED") as BatchRunLifecycle,
    currentStrategyName:
      typeof payload?.currentStrategyName === "string" ? payload.currentStrategyName : null,
    rankingSnapshot: Array.isArray(payload?.rankingSnapshot) ? payload.rankingSnapshot : [],
    items: candidates.map((candidate: any, index: number) => {
      const strategyId =
        typeof candidate?.strategyId === "string" && candidate.strategyId.trim()
          ? candidate.strategyId.trim()
          : "unknown";
      const metrics = candidate?.metrics && typeof candidate.metrics === "object" ? candidate.metrics : null;
      return {
        id: String(candidate?.id ?? `${payload?.runId ?? "batch_run"}_${index}`),
        prompt: String(candidate?.prompt ?? ""),
        name: String(candidate?.strategyName ?? t("전략 {0}", index + 1)),
        status: (candidate?.status ?? "waiting") as BatchStatus,
        message: getStatusLabel((candidate?.status ?? "waiting") as BatchStatus),
        result: metrics ? mapMetricsToResult(metrics, strategyId) : undefined,
        error: typeof candidate?.errorMessage === "string" ? candidate.errorMessage : undefined,
      };
    }),
    logs: Array.isArray(payload?.logs) ? payload.logs : [],
  };
}

async function fetchBatchRunDetail(runId: string): Promise<BatchRunRecord> {
  const response = await fetch(`/api/strategy/batch-runs?runId=${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(t("배치 실행 상세를 불러오지 못했습니다."));
  }

  const payload = await response.json();
  return mapBatchRunDetail(payload);
}

async function startBatchRun(prompts: string[]) {
  const response = await fetch("/api/strategy/batch-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompts,
      concurrency: 2,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload?.detail ?? payload?.error ?? t("배치 실행을 시작하지 못했습니다."));
  }

  return response.json();
}

async function cancelBatchRun(runId: string) {
  const response = await fetch("/api/strategy/batch-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action: "cancel",
      runId,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload?.detail ?? payload?.error ?? t("배치 실행 중단 요청에 실패했습니다."));
  }
}

export default function RunAllTestsModal({
  isOpen,
  onClose,
  currentPrompt,
}: {
  isOpen: boolean;
  onClose: () => void;
  currentPrompt?: string;
}) {
  const [datasetText, setDatasetText] = useState("");
  const [items, setItems] = useState<BatchItem[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentItemId, setCurrentItemId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("cagr");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [history, setHistory] = useState<BatchRunSummaryRecord[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyLoadingRunId, setHistoryLoadingRunId] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [currentStrategyName, setCurrentStrategyName] = useState<string | null>(null);

  const completedCount = items.filter((item) => item.status === "computed" || item.status === "cache_hit").length;
  const failedCount = items.filter((item) => item.status === "failed").length;
  const skippedCount = items.filter((item) => item.status === "skipped").length;
  const waitingCount = items.filter((item) => item.status === "waiting").length;
  const progress = items.length === 0 ? 0 : Math.round(((completedCount + failedCount + skippedCount) / items.length) * 100);
  const currentItem = items.find((item) => item.id === currentItemId) ?? null;

  const rankedItems = useMemo(() => rankItems(items, sortKey, sortDirection), [items, sortDirection, sortKey]);

  const failedItems = items.filter((item) => item.status === "failed" || item.status === "skipped");

  useEffect(() => {
    if (!isOpen) return;
    void loadHistory();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !activeRunId || !isRunning) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const record = await fetchBatchRunDetail(activeRunId);
        if (cancelled) return;
        loadHistoryRecord(record);
        syncHistorySummary(record);

        if (record.runStatus === "COMPLETED" || record.runStatus === "CANCELED") {
          setIsRunning(false);
          setActiveRunId(null);
          void loadHistory();
        }
      } catch (error: any) {
        if (!cancelled) {
          setHistoryError(error?.message ?? t("실행 상태를 불러오지 못했습니다."));
        }
      }
    };

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, BATCH_RUN_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeRunId, isOpen, isRunning]);

  async function loadHistory() {
    setIsHistoryLoading(true);
    setHistoryError(null);

    try {
      setHistory(await fetchBatchRunHistory());
    } catch (error: any) {
      setHistoryError(error?.message ?? t("실행 이력을 불러오지 못했습니다."));
    } finally {
      setIsHistoryLoading(false);
    }
  }

  function appendCurrentPrompt() {
    const nextPrompt = currentPrompt?.trim();
    if (!nextPrompt) return;
    setDatasetText((current) => (current.trim() ? `${current.trim()}\n\n${nextPrompt}` : nextPrompt));
  }

  function handleSort(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((current) => (current === "desc" ? "asc" : "desc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection(nextKey === "maxDrawdown" ? "asc" : "desc");
  }

  function syncHistorySummary(record: BatchRunRecord) {
    setHistory((current) => {
      const summary = toHistorySummary(record);
      const rest = current.filter((item) => item.runId !== summary.runId);
      return [summary, ...rest];
    });
  }

  function createHistoryRecord(
    runId: string,
    createdAt: string,
    nextItems: BatchItem[],
    nextLogs: string[]
  ): BatchRunRecord {
    const rankedSnapshot = rankItems(nextItems, "cagr", "desc").map((item, index) => ({
      rank: index + 1,
      strategyId: item.result?.strategyId ?? "unknown",
      name: item.name,
      status: item.status,
      cagr: item.result?.cagr ?? 0,
      totalReturn: item.result?.totalReturn ?? 0,
      sharpe: item.result?.sharpe ?? 0,
      maxDrawdown: item.result?.maxDrawdown ?? 0,
      // 정렬용 — null(=∞)은 상한값으로 접는다
      profitFactor: profitFactorForRanking(item.result?.profitFactor) ?? 0,
      trades: item.result?.trades ?? 0,
    }));
    const runningItem = nextItems.find((item) => item.status === "running") ?? null;

    return {
      runId,
      createdAt,
      totalPrompts: nextItems.length,
      completedCount: nextItems.filter((item) => item.status === "computed" || item.status === "cache_hit").length,
      failedCount: nextItems.filter((item) => item.status === "failed").length,
      skippedCount: nextItems.filter((item) => item.status === "skipped").length,
      runStatus: nextItems.some((item) => item.status === "waiting" || item.status === "running")
        ? "RUNNING"
        : "COMPLETED",
      currentStrategyName: runningItem?.name ?? null,
      rankingSnapshot: rankedSnapshot,
      items: nextItems,
      logs: nextLogs,
    };
  }

  function loadHistoryRecord(record: BatchRunRecord) {
    setItems(record.items);
    setLogs(record.logs);
    const runningItem = record.items.find((item) => item.status === "running") ?? null;
    setCurrentItemId(runningItem?.id ?? null);
    setCurrentStrategyName(record.currentStrategyName ?? runningItem?.name ?? null);
    setIsRunning(record.runStatus === "QUEUED" || record.runStatus === "RUNNING");
  }

  async function handleLoadHistoryRecord(runId: string) {
    setHistoryLoadingRunId(runId);
    setHistoryError(null);

    try {
      const record = await fetchBatchRunDetail(runId);
      loadHistoryRecord(record);
      setActiveRunId(record.runStatus === "QUEUED" || record.runStatus === "RUNNING" ? record.runId : null);
    } catch (error: any) {
      setHistoryError(error?.message ?? t("실행 이력을 불러오지 못했습니다."));
    } finally {
      setHistoryLoadingRunId(null);
    }
  }

  async function handleRunAll() {
    const prompts = splitPromptDataset(datasetText);
    if (prompts.length === 0 || isRunning) return;

    const optimisticItems = prompts.map((prompt, index) => ({
      id: `queued_${index}`,
      prompt,
      name: t("전략 {0}", index + 1),
      status: "waiting" as BatchStatus,
      message: t("대기 중"),
    }));

    setItems(optimisticItems);
    setLogs([t("총 {0}개 프롬프트 실행 요청 중", prompts.length)]);
    setCurrentItemId(null);
    setCurrentStrategyName(null);
    setHistoryError(null);
    setIsRunning(true);

    try {
      const payload = await startBatchRun(prompts);
      const runId = String(payload?.runId ?? "");
      if (!runId) {
        throw new Error(t("배치 실행 식별자를 받지 못했습니다."));
      }

      setActiveRunId(runId);
      await loadHistory();
      const record = await fetchBatchRunDetail(runId);
      loadHistoryRecord(record);
      syncHistorySummary(record);
    } catch (error: any) {
      setHistoryError(error?.message ?? t("배치 실행을 시작하지 못했습니다."));
      setIsRunning(false);
      setActiveRunId(null);
    }
  }

  async function handleStop() {
    if (!isRunning || !activeRunId) return;

    try {
      await cancelBatchRun(activeRunId);
      setLogs((current) => [...current, t("배치 실행 중단 요청을 전송했습니다.")]);
    } catch (error: any) {
      setHistoryError(error?.message ?? t("배치 실행 중단 요청에 실패했습니다."));
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-2 lg:p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div
        data-testid="run-all-tests-modal-panel"
        className="relative flex h-[calc(100dvh-1rem)] w-full max-w-6xl flex-col overflow-hidden rounded-3xl border border-white/[0.08] bg-[#0f0f0f] lg:h-[min(88vh,920px)]"
      >
        <div
          data-testid="run-all-tests-modal-header"
          className="flex items-start justify-between gap-4 border-b border-white/[0.08] px-4 py-3 lg:px-5 lg:py-4"
        >
            <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Sparkle size={16} className="text-sky-400" weight="fill" />
              <h2 className="text-base font-black text-white">{t("모두 테스트")}</h2>
            </div>
            <p className="text-xs font-bold text-gray-500">
              {t("기존 research와 분리된 독립 배치 실행기입니다. 프롬프트를 빈 줄로 구분해 입력하고, 실행 이력은 서버에 영구 저장됩니다.")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-white/[0.08] p-2 text-gray-500 transition-colors duration-200 hover:text-white"
            aria-label={t("모달 닫기")}
          >
            <X size={14} />
          </button>
        </div>

        <div data-testid="run-all-tests-modal-content" className="flex-1 overflow-auto p-3 lg:p-5">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-black text-white">Prompt Dataset</h3>
                  {currentPrompt?.trim() && (
                    <button
                      type="button"
                      onClick={appendCurrentPrompt}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-white/[0.08] px-3 py-2 text-xs font-black text-gray-300"
                    >
                      <Copy size={12} />
                      {t("현재 입력 추가")}
                    </button>
                  )}
                </div>
                <textarea
                  value={datasetText}
                  onChange={(event) => setDatasetText(event.target.value)}
                  rows={12}
                  placeholder={t("프롬프트 1\n\n프롬프트 2\n\n프롬프트 3")}
                  className="w-full rounded-2xl border border-white/[0.08] bg-black/20 px-4 py-3 text-sm font-bold text-white outline-none placeholder:text-gray-600"
                />
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-3">
                  <p className="text-xs font-bold text-gray-500">
                    {t("총 {0}개 프롬프트", splitPromptDataset(datasetText).length)}
                  </p>
                  <div className="flex items-center gap-2">
                    {isRunning && (
                      <button
                        type="button"
                        onClick={handleStop}
                        className="rounded-xl border border-[var(--main-red)]/20 bg-[var(--main-red)]/10 px-4 py-2 text-xs font-black text-[var(--main-red)]"
                      >
                        {t("중단")}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleRunAll}
                      disabled={splitPromptDataset(datasetText).length === 0 || isRunning}
                      className="inline-flex items-center gap-2 rounded-xl bg-[var(--main-blue)] px-4 py-2 text-xs font-black text-white disabled:opacity-40"
                    >
                      {isRunning ? <ArrowsClockwise size={13} className="animate-spin" /> : <Sparkle size={13} weight="fill" />}
                      {t("모두 테스트 시작")}
                    </button>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center gap-2">
                  <ClockCounterClockwise size={14} className="text-gray-500" />
                  <h3 className="text-sm font-black text-white">{t("실행 상태")}</h3>
                </div>
                <div className="space-y-3">
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full bg-[var(--main-blue)] transition-all duration-300"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Progress</p>
                      <p className="mt-1 text-xs font-black text-white">{progress}%</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Completed</p>
                      <p className="mt-1 text-xs font-black text-white">{completedCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Failed</p>
                      <p className="mt-1 text-xs font-black text-white">{failedCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Skipped</p>
                      <p className="mt-1 text-xs font-black text-white">{skippedCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/[0.06] bg-black/20 p-3">
                      <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Waiting</p>
                      <p className="mt-1 text-xs font-black text-white">{waitingCount}</p>
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                    <p className="text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">Current</p>
                    <p className="mt-1 text-sm font-black text-white">{currentItem?.name ?? currentStrategyName ?? "-"}</p>
                    <p className="mt-1 text-xs font-bold text-gray-500">{currentItem?.message ?? t("대기 중")}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center gap-2">
                  <ArrowsClockwise size={14} className="text-gray-500" />
                  <h3 className="text-sm font-black text-white">{t("실시간 로그")}</h3>
                </div>
                <div className="space-y-2">
                  {logs.length === 0 ? (
                    <p className="text-xs font-bold text-gray-500">{t("아직 실행 로그가 없습니다.")}</p>
                  ) : (
                    logs.slice().reverse().map((log, index) => (
                      <div key={`${log}-${index}`} className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3 text-xs font-bold text-gray-300">
                        {log}
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-black text-white">{t("최근 실행 이력")}</h3>
                  <span className="text-[11px] font-black uppercase tracking-[0.16em] text-gray-600">
                    {history.length} Runs
                  </span>
                </div>

                {historyError && (
                  <p className="mb-3 rounded-2xl border border-[var(--main-red)]/20 bg-[var(--main-red)]/10 px-4 py-3 text-xs font-bold text-[var(--main-red)]">
                    {historyError}
                  </p>
                )}

                {isHistoryLoading ? (
                  <p className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-5 text-xs font-bold text-gray-500">
                    {t("실행 이력을 불러오는 중입니다.")}
                  </p>
                ) : history.length === 0 ? (
                  <p className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-5 text-xs font-bold text-gray-500">
                    {t("저장된 배치 실행 이력이 없습니다.")}
                  </p>
                ) : (
                  <div className="space-y-2">
                    {history.map((record) => (
                      <div key={record.runId} className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <p className="truncate text-xs font-black text-white">{record.runId}</p>
                            <p className="mt-1 text-[11px] font-bold text-gray-500">{formatDateTime(record.createdAt)}</p>
                          </div>
                          <button
                            type="button"
                            onClick={() => void handleLoadHistoryRecord(record.runId)}
                            className="rounded-xl border border-white/[0.08] px-3 py-2 text-[11px] font-black text-white"
                          >
                            {historyLoadingRunId === record.runId ? t("불러오는 중...") : t("이력 불러오기")}
                          </button>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-bold text-gray-400">
                          <span>{t("총 {0}", record.totalPrompts)}</span>
                          <span>{t("완료 {0}", record.completedCount)}</span>
                          <span>{t("실패 {0}", record.failedCount)}</span>
                          <span>{t("스킵 {0}", record.skippedCount)}</span>
                        </div>
                        {record.rankingSnapshot[0] && (
                          <p className="mt-2 text-[11px] font-bold text-gray-300">
                            {t("최고 성과: {0} / CAGR {1}", record.rankingSnapshot[0].name, formatMetric(record.rankingSnapshot[0].cagr, 2, "%"))}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-sm font-black text-white">Leaderboard</h3>
                  <span className="text-[11px] font-black uppercase tracking-[0.16em] text-gray-600">
                    {rankedItems.length} Results
                  </span>
                </div>

                {rankedItems.length === 0 ? (
                  <p className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-5 text-xs font-bold text-gray-500">
                    {t("완료된 결과가 아직 없습니다.")}
                  </p>
                ) : (
                  <div
                    data-testid="run-all-tests-leaderboard-scroll"
                    className="overflow-x-auto lg:overflow-x-visible"
                  >
                    <div
                      data-testid="run-all-tests-leaderboard-grid"
                      className="min-w-[760px] space-y-2 lg:min-w-0"
                    >
                      <div className="grid grid-cols-[0.7fr_2.2fr_repeat(6,minmax(0,1fr))] gap-2 px-2 text-[10px] font-black uppercase tracking-[0.15em] text-gray-600">
                        <span>Rank</span>
                        <span>Strategy</span>
                        {[
                          ["cagr", "CAGR"],
                          ["totalReturn", "Total Return"],
                          ["sharpe", "Sharpe"],
                          ["maxDrawdown", "MDD"],
                          ["profitFactor", "Profit Factor"],
                          ["trades", "Trades"],
                        ].map(([key, label]) => (
                          <button
                            key={key}
                            type="button"
                            onClick={() => handleSort(key as SortKey)}
                            className="text-left"
                          >
                            {label}
                          </button>
                        ))}
                      </div>

                      {rankedItems.map((item, index) => {
                        const isBest = index === 0;
                        return (
                          <div
                            key={item.id}
                            className={`grid grid-cols-[0.7fr_2.2fr_repeat(6,minmax(0,1fr))] gap-2 rounded-2xl border px-3 py-3 text-xs ${
                              isBest ? "border-emerald-400/30 bg-emerald-400/10" : "border-white/[0.06] bg-black/20"
                            }`}
                          >
                            <div className="flex items-center gap-1 text-white">
                              <span className="font-black">{index + 1}</span>
                              {isBest && <Crown size={12} className="text-emerald-300" weight="fill" />}
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="truncate font-black text-white">{item.name}</p>
                                {isBest && (
                                  <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.14em] text-emerald-200">
                                    <CheckCircle size={10} weight="fill" />
                                    {t("최고 성과")}
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 truncate text-[11px] font-bold text-gray-500">
                                {getStatusLabel(item.status)} · {item.result?.strategyId ?? "-"}
                              </p>
                            </div>
                            <span className="font-black text-white">{formatMetric(item.result?.cagr, 2, "%")}</span>
                            <span className="font-black text-white">{formatMetric(item.result?.totalReturn, 2, "%")}</span>
                            <span className="font-black text-white">{formatMetric(item.result?.sharpe)}</span>
                            <span className="font-black text-white">{formatMetric(item.result?.maxDrawdown, 2, "%")}</span>
                            <span className="font-black text-white">{formatProfitFactor(item.result?.profitFactor)}</span>
                            <span className="font-black text-white">{formatMetric(item.result?.trades, 0)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                <div className="mb-3 flex items-center gap-2">
                  <Warning size={14} className="text-[var(--main-red)]" weight="fill" />
                  <h3 className="text-sm font-black text-white">{t("실패 및 스킵 목록")}</h3>
                </div>
                <div className="space-y-2">
                  {failedItems.length === 0 ? (
                    <p className="text-xs font-bold text-gray-500">{t("실패하거나 스킵된 전략이 없습니다.")}</p>
                  ) : (
                    failedItems.map((item) => (
                      <div key={item.id} className="rounded-2xl border border-white/[0.06] bg-black/20 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-xs font-black text-white">{item.name}</p>
                          <span className="text-[11px] font-black text-gray-500">{getStatusLabel(item.status)}</span>
                        </div>
                        <p className="mt-1 text-[11px] font-bold text-[var(--main-red)]">{item.error}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
