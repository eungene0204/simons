import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { getExecutionState, type BatchExecutionJob } from "./executionState";
import { profitFactorForRanking } from "@/lib/format-profit-factor";

type CandidateStatus =
  | "waiting"
  | "running"
  | "computed"
  | "cache_hit"
  | "failed"
  | "skipped";

type BatchRunCandidatePayload = {
  id?: string;
  strategyId?: string | null;
  prompt: string;
  strategyName: string;
  status: CandidateStatus | string;
  errorMessage?: string | null;
  metrics?: any;
  rank?: number | null;
  backtestRequest?: Record<string, any> | null;
};

type BatchRunSnapshotPayload = {
  runId: string;
  createdAt?: string;
  totalPrompts: number;
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  rankingSnapshot: Array<Record<string, any>>;
  logs: string[];
  candidates: BatchRunCandidatePayload[];
};

type SaveBatchRunSnapshotOptions = {
  replaceCandidates?: boolean;
  candidateIds?: Set<string>;
};

const MAX_ACTIVE_BATCH_RUNS = 1;
const DEFAULT_CANDIDATE_CONCURRENCY = 2;
const MAX_CANDIDATE_CONCURRENCY = 4;
const CANCEL_REQUEST_LOG_MARKER = "[batch-run-cancel-requested]";
const BATCH_RUN_TRANSACTION_TIMEOUT_MS = 30_000;
const BATCH_RUN_TRANSACTION_RETRY_LIMIT = 3;
const CANDIDATE_QUERY_PAGE_SIZE = 500;
const candidateSummarySelect = {
  id: true,
  strategyId: true,
  prompt: true,
  strategyName: true,
  status: true,
  errorMessage: true,
  metrics: true,
  rank: true,
  createdAt: true,
};
const candidateResumeSelect = {
  ...candidateSummarySelect,
  backtestRequest: true,
};

function parseJsonField<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableBatchRunPersistenceError(error: any) {
  return error?.code === "P1008" || error?.code === "P2034" || error?.code === "P2028";
}

function hasCancelMarker(logs: string[]) {
  return logs.some((log) => log.includes(CANCEL_REQUEST_LOG_MARKER));
}

async function fetchCandidatesPaged(runId: string, orderBy: any[], select: Record<string, boolean>) {
  const candidates: any[] = [];
  for (let skip = 0; ; skip += CANDIDATE_QUERY_PAGE_SIZE) {
    const page = await prisma.batchRunCandidate.findMany({
      where: { runId },
      orderBy,
      skip,
      take: CANDIDATE_QUERY_PAGE_SIZE,
      select,
    });
    candidates.push(...page);
    if (page.length < CANDIDATE_QUERY_PAGE_SIZE) break;
  }
  return candidates;
}

async function fetchRunWithCandidates(runId: string, orderBy: any[], select: Record<string, boolean>) {
  if (typeof prisma.batchRunCandidate?.findMany !== "function") {
    return prisma.batchRun.findUnique({
      where: { id: runId },
      include: {
        Candidate: {
          orderBy,
          select,
        },
      },
    });
  }

  const run = await prisma.batchRun.findUnique({
    where: { id: runId },
  });
  if (!run) return null;

  return {
    ...run,
    Candidate: await fetchCandidatesPaged(runId, orderBy, select),
  };
}

function clampConcurrency(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return DEFAULT_CANDIDATE_CONCURRENCY;
  return Math.max(1, Math.min(MAX_CANDIDATE_CONCURRENCY, Math.floor(numeric)));
}

function buildRunId() {
  return `batch_run_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function inferStrategyName(prompt: string, parsed: any, index: number) {
  const parsedName =
    typeof parsed?.name === "string" && parsed.name.trim()
      ? parsed.name.trim()
      : typeof parsed?.description === "string" && parsed.description.trim()
        ? parsed.description.trim()
        : "";

  if (parsedName) return parsedName;
  const firstLine = prompt.split("\n")[0]?.trim() ?? "";
  return firstLine.slice(0, 48) || `전략 ${index + 1}`;
}

export function buildRankingSnapshot(candidates: BatchRunCandidatePayload[]) {
  const ranked = candidates
    .filter((candidate) => candidate.metrics)
    .slice()
    .sort((left, right) => {
      const leftValue = Number(left.metrics?.cagr ?? 0);
      const rightValue = Number(right.metrics?.cagr ?? 0);
      if (leftValue === rightValue) {
        return left.strategyName.localeCompare(right.strategyName, "ko");
      }
      return rightValue - leftValue;
    });

  const rankByCandidateId = new Map<string, number>();
  const snapshot = ranked.map((candidate, index) => {
    rankByCandidateId.set(candidate.id ?? `${candidate.strategyName}_${index}`, index + 1);
    return {
      rank: index + 1,
      strategyId: candidate.strategyId ?? "unknown",
      name: candidate.strategyName,
      status: candidate.status,
      cagr: Number(candidate.metrics?.cagr ?? 0),
      totalReturn: Number(candidate.metrics?.totalReturn ?? 0),
      sharpe: Number(candidate.metrics?.sharpe ?? 0),
      maxDrawdown: Number(candidate.metrics?.maxDrawdown ?? 0),
      // null(=손실 0건이라 ∞)을 0(최악)으로 접지 않는다 — RunAllTestsModal의
      // 클라이언트 스냅샷과 같은 999 상한 접기 규약
      profitFactor: profitFactorForRanking(candidate.metrics?.profitFactor) ?? 0,
      trades: Number(candidate.metrics?.trades ?? 0),
    };
  });

  const normalizedCandidates = candidates.map((candidate) => ({
    ...candidate,
    rank: candidate.metrics ? rankByCandidateId.get(candidate.id ?? "") ?? null : null,
  }));

  return {
    rankingSnapshot: snapshot,
    candidates: normalizedCandidates,
  };
}

function summarizeMetricsForList(metrics: any) {
  if (!metrics || typeof metrics !== "object") return null;
  return {
    strategy_id: metrics.strategy_id ?? metrics.strategyId,
    strategyId: metrics.strategyId ?? metrics.strategy_id,
    totalReturn: metrics.totalReturn,
    totalProfit: metrics.totalProfit,
    cagr: metrics.cagr,
    buyAndHoldReturn: metrics.buyAndHoldReturn,
    maxDrawdown: metrics.maxDrawdown,
    winRate: metrics.winRate,
    trades: metrics.trades,
    avgProfit: metrics.avgProfit,
    avgLoss: metrics.avgLoss,
    maxConsecutiveWins: metrics.maxConsecutiveWins,
    maxConsecutiveLosses: metrics.maxConsecutiveLosses,
    profitFactor: metrics.profitFactor,
    sharpe: metrics.sharpe,
    sortino: metrics.sortino,
    calmar: metrics.calmar,
    avgHoldingDays: metrics.avgHoldingDays,
    volatility: metrics.volatility,
    benchmark_label: metrics.benchmark_label,
    universe_id: metrics.universe_id,
    executionTime: metrics.executionTime,
    cacheKey: metrics.cacheKey,
    fromCache: metrics.fromCache,
    cachedAt: metrics.cachedAt,
  };
}

function buildSnapshotFromJob(job: BatchExecutionJob): BatchRunSnapshotPayload {
  const { rankingSnapshot, candidates } = buildRankingSnapshot(job.candidates);
  const completedCount = candidates.filter(
    (candidate) => candidate.status === "computed" || candidate.status === "cache_hit"
  ).length;
  const failedCount = candidates.filter((candidate) => candidate.status === "failed").length;
  const skippedCount = candidates.filter((candidate) => candidate.status === "skipped").length;

  return {
    runId: job.runId,
    createdAt: job.createdAt,
    totalPrompts: candidates.length,
    completedCount,
    failedCount,
    skippedCount,
    rankingSnapshot,
    logs: job.logs,
    candidates,
  };
}

function buildCandidatePersistenceRow(
  snapshot: BatchRunSnapshotPayload,
  candidate: BatchRunCandidatePayload,
  index: number
) {
  return {
    id:
      typeof candidate.id === "string" && candidate.id.trim()
        ? candidate.id.trim()
        : `${snapshot.runId}_candidate_${index}`,
    runId: snapshot.runId,
    strategyId:
      typeof candidate.strategyId === "string" && candidate.strategyId.trim()
        ? candidate.strategyId.trim()
        : null,
    prompt: String(candidate.prompt ?? ""),
    strategyName: String(candidate.strategyName ?? `전략 ${index + 1}`),
    status: String(candidate.status ?? "unknown"),
    errorMessage:
      typeof candidate.errorMessage === "string" ? candidate.errorMessage : null,
    metrics: JSON.stringify(candidate.metrics ?? null),
    rank: typeof candidate.rank === "number" ? candidate.rank : null,
    backtestRequest: candidate.backtestRequest
      ? JSON.stringify(candidate.backtestRequest)
      : null,
  };
}

async function saveBatchRunSnapshot(
  snapshot: BatchRunSnapshotPayload,
  options: SaveBatchRunSnapshotOptions = {}
) {
  for (let attempt = 0; attempt <= BATCH_RUN_TRANSACTION_RETRY_LIMIT; attempt += 1) {
    try {
      await prisma.$transaction(async (tx) => {
        const createData = {
          id: snapshot.runId,
          totalPrompts: Number(snapshot.totalPrompts ?? snapshot.candidates.length ?? 0),
          completedCount: Number(snapshot.completedCount ?? 0),
          failedCount: Number(snapshot.failedCount ?? 0),
          skippedCount: Number(snapshot.skippedCount ?? 0),
          rankingSnapshot: JSON.stringify(snapshot.rankingSnapshot ?? []),
          logs: JSON.stringify(snapshot.logs ?? []),
          ...(snapshot.createdAt ? { createdAt: new Date(snapshot.createdAt) } : {}),
        };

        await tx.batchRun.upsert({
          where: { id: snapshot.runId },
          create: createData,
          update: {
            totalPrompts: Number(snapshot.totalPrompts ?? snapshot.candidates.length ?? 0),
            completedCount: Number(snapshot.completedCount ?? 0),
            failedCount: Number(snapshot.failedCount ?? 0),
            skippedCount: Number(snapshot.skippedCount ?? 0),
            rankingSnapshot: JSON.stringify(snapshot.rankingSnapshot ?? []),
            logs: JSON.stringify(snapshot.logs ?? []),
          },
        });

        if (options.replaceCandidates) {
          await tx.batchRunCandidate.deleteMany({
            where: { runId: snapshot.runId },
          });
          if (snapshot.candidates.length > 0) {
            await tx.batchRunCandidate.createMany({
              data: snapshot.candidates.map((candidate, index) =>
                buildCandidatePersistenceRow(snapshot, candidate, index)
              ),
            });
          }
          return;
        }

        const candidateIds = options.candidateIds;
        if (!candidateIds || candidateIds.size === 0) {
          return;
        }

        if (typeof tx.batchRunCandidate.upsert !== "function") {
          await tx.batchRunCandidate.deleteMany({
            where: { runId: snapshot.runId },
          });
          await tx.batchRunCandidate.createMany({
            data: snapshot.candidates.map((candidate, index) =>
              buildCandidatePersistenceRow(snapshot, candidate, index)
            ),
          });
          return;
        }

        for (const [index, candidate] of snapshot.candidates.entries()) {
          const row = buildCandidatePersistenceRow(snapshot, candidate, index);
          if (!candidateIds.has(row.id)) continue;
          await tx.batchRunCandidate.upsert({
            where: { id: row.id },
            create: row,
            update: {
              strategyId: row.strategyId,
              prompt: row.prompt,
              strategyName: row.strategyName,
              status: row.status,
              errorMessage: row.errorMessage,
              metrics: row.metrics,
              rank: row.rank,
              backtestRequest: row.backtestRequest,
            },
          });
        }
      }, { timeout: BATCH_RUN_TRANSACTION_TIMEOUT_MS });
      return;
    } catch (error: any) {
      if (
        attempt >= BATCH_RUN_TRANSACTION_RETRY_LIMIT ||
        !isRetryableBatchRunPersistenceError(error)
      ) {
        throw error;
      }
      await sleep(500 * (attempt + 1));
    }
  }
}

function deriveRunStatus(run: {
  totalPrompts: number;
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  candidates?: Array<{ status: string; strategyName: string }>;
  logs?: string[];
}) {
  const candidates = run.candidates ?? [];
  const logs = run.logs ?? [];
  const runningCount = candidates.filter((candidate) => candidate.status === "running").length;
  const waitingCount = candidates.filter((candidate) => candidate.status === "waiting").length;
  const currentStrategyName = candidates.find((candidate) => candidate.status === "running")?.strategyName ?? null;
  const cancelRequested = hasCancelMarker(logs);

  if (runningCount > 0) {
    return {
      status: cancelRequested ? "CANCELED" : "RUNNING",
      waitingCount,
      runningCount,
      currentStrategyName,
    };
  }

  const finishedCount = run.completedCount + run.failedCount + run.skippedCount;
  if (finishedCount >= run.totalPrompts) {
    return {
      status:
        cancelRequested || (run.skippedCount > 0 && run.completedCount + run.failedCount < run.totalPrompts)
          ? "CANCELED"
          : "COMPLETED",
      waitingCount,
      runningCount,
      currentStrategyName: null,
    };
  }

  return {
    status: "QUEUED",
    waitingCount,
    runningCount,
    currentStrategyName: null,
  };
}

function formatRunResponse(run: any) {
  const candidates = Array.isArray(run.Candidate)
    ? run.Candidate.map((candidate: any) => ({
        id: candidate.id,
        strategyId: candidate.strategyId,
        prompt: candidate.prompt,
        strategyName: candidate.strategyName,
        status: candidate.status,
        errorMessage: candidate.errorMessage,
        metrics: summarizeMetricsForList(parseJsonField(candidate.metrics, null)),
        rank: candidate.rank,
        createdAt: candidate.createdAt,
      }))
    : [];

  const derived = deriveRunStatus({
    totalPrompts: run.totalPrompts,
    completedCount: run.completedCount,
    failedCount: run.failedCount,
    skippedCount: run.skippedCount,
    candidates,
    logs: parseJsonField(run.logs, []),
  });

  return {
    runId: run.id,
    createdAt: run.createdAt,
    totalPrompts: run.totalPrompts,
    completedCount: run.completedCount,
    failedCount: run.failedCount,
    skippedCount: run.skippedCount,
    rankingSnapshot: parseJsonField(run.rankingSnapshot, []),
    logs: parseJsonField(run.logs, []),
    status: derived.status,
    waitingCount: derived.waitingCount,
    runningCount: derived.runningCount,
    currentStrategyName: derived.currentStrategyName,
    candidates,
  };
}

function buildAdvisorLearningResults(run: any) {
  const candidates = Array.isArray(run.Candidate)
    ? run.Candidate.map((candidate: any) => {
        const metrics = parseJsonField<any>(candidate.metrics, null);
        const sampleId =
          typeof metrics?.sample_id === "string" && metrics.sample_id.trim()
            ? metrics.sample_id.trim()
            : candidate.id;

        return {
          sample_id: sampleId,
          candidate_id: candidate.id,
          strategy_id: candidate.strategyId,
          prompt: candidate.prompt,
          strategy_name: candidate.strategyName,
          status: candidate.status,
          metrics,
        };
      })
    : [];

  return {
    runId: run.id,
    createdAt: run.createdAt,
    totalResults: candidates.filter((candidate: any) =>
      (candidate.status === "computed" || candidate.status === "cache_hit") && candidate.metrics
    ).length,
    results: candidates.filter((candidate: any) =>
      (candidate.status === "computed" || candidate.status === "cache_hit") && candidate.metrics
    ),
  };
}

function mapRunToStoredCandidates(run: any): BatchRunCandidatePayload[] {
  return (run.Candidate ?? []).map((candidate: any) => ({
    id: candidate.id,
    strategyId: candidate.strategyId,
    prompt: candidate.prompt,
    strategyName: candidate.strategyName,
    status: candidate.status,
    errorMessage: candidate.errorMessage,
    metrics: parseJsonField(candidate.metrics, null),
    rank: candidate.rank,
    backtestRequest: parseJsonField(candidate.backtestRequest, null),
  }));
}

function shouldResumeRun(run: any) {
  const candidates = mapRunToStoredCandidates(run);
  const logs = parseJsonField(run.logs, []);
  const derived = deriveRunStatus({
    totalPrompts: run.totalPrompts,
    completedCount: run.completedCount,
    failedCount: run.failedCount,
    skippedCount: run.skippedCount,
    candidates,
    logs,
  });

  return derived.status === "QUEUED" || derived.status === "RUNNING";
}

async function recoverCanceledRun(run: any) {
  const logs = parseJsonField<string[]>(run.logs, []);
  if (!hasCancelMarker(logs)) {
    return run;
  }

  const candidates = mapRunToStoredCandidates(run).map((candidate) =>
    candidate.status === "waiting" || candidate.status === "running"
      ? {
          ...candidate,
          status: "skipped" as CandidateStatus,
          errorMessage: candidate.errorMessage ?? "사용자 요청으로 스킵됨",
        }
      : candidate
  );

  const snapshot = buildSnapshotFromJob({
    runId: run.id,
    origin: "",
    backend: "ollama",
    concurrency: 1,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: logs.includes("취소 요청을 반영해 남은 배치 실행을 종료했습니다.")
      ? logs
      : [...logs, "취소 요청을 반영해 남은 배치 실행을 종료했습니다."],
    persistChain: Promise.resolve(),
    dirtyCandidateIds: new Set<string>(),
  });

  await saveBatchRunSnapshot(snapshot, { replaceCandidates: true });

  return fetchRunWithCandidates(run.id, [{ rank: "asc" }, { createdAt: "asc" }], candidateSummarySelect);
}

function hydrateJobFromStoredRun(run: any, origin: string): BatchExecutionJob {
  const logs = parseJsonField(run.logs, []);
  const candidates = mapRunToStoredCandidates(run).map((candidate) =>
    candidate.status === "running"
      ? {
          ...candidate,
          status: "waiting" as CandidateStatus,
          errorMessage: null,
        }
      : candidate
  );

  return {
    runId: run.id,
    origin,
    backend: "ollama",
    concurrency: 1,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: candidates.some((candidate) => candidate.status === "waiting") &&
      (run.Candidate ?? []).some((candidate: any) => candidate.status === "running")
        ? [...logs, "서버 재시작 후 중단된 전략을 다시 대기열에 복구했습니다."]
        : logs,
    persistChain: Promise.resolve(),
    dirtyCandidateIds: new Set<string>(
      candidates
        .filter((candidate) => candidate.status === "waiting" || candidate.status === "running")
        .map((candidate, index) => candidate.id ?? `${run.id}_candidate_${index}`)
    ),
  };
}

function isRunnableCandidate(candidate: BatchRunCandidatePayload) {
  return candidate.status === "waiting" || candidate.status === "running";
}

async function ensureRunScheduled(runId: string, origin: string) {
  const state = getExecutionState();
  if (
    state.activeRunIds.has(runId) ||
    state.schedulingRunIds.has(runId) ||
    state.queue.some((job) => job.runId === runId)
  ) {
    return;
  }
  state.schedulingRunIds.add(runId);

  try {
    const run = await prisma.batchRun.findUnique({
      where: { id: runId },
    });

    if (!run) return;

    const logs = parseJsonField<string[]>(run.logs, []);
    const finishedCount = run.completedCount + run.failedCount + run.skippedCount;
    if (finishedCount >= run.totalPrompts && !hasCancelMarker(logs)) {
      return;
    }

    const runWithCandidates = await fetchRunWithCandidates(runId, [{ createdAt: "asc" }], candidateResumeSelect);

    if (!runWithCandidates) return;

    const recoveredRun = await recoverCanceledRun(runWithCandidates);
    if (!recoveredRun || !shouldResumeRun(recoveredRun)) {
      return;
    }

    if (state.activeRunIds.has(runId) || state.queue.some((job) => job.runId === runId)) {
      return;
    }

    enqueueBatchRun(hydrateJobFromStoredRun(recoveredRun, origin));
    pumpBatchRunQueue();
  } finally {
    state.schedulingRunIds.delete(runId);
  }
}

async function resumeIncompleteRuns(origin: string) {
  const runs = await prisma.batchRun.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
  });

  for (const run of runs) {
    const logs = parseJsonField<string[]>(run.logs, []);
    const finishedCount = run.completedCount + run.failedCount + run.skippedCount;
    if (finishedCount >= run.totalPrompts && !hasCancelMarker(logs)) {
      continue;
    }

    const runWithCandidates = await fetchRunWithCandidates(run.id, [{ createdAt: "asc" }], candidateSummarySelect);
    if (!runWithCandidates) {
      continue;
    }

    if (shouldResumeRun(runWithCandidates)) {
      await ensureRunScheduled(run.id, origin);
    } else if (hasCancelMarker(logs)) {
      await recoverCanceledRun(runWithCandidates);
    }
  }
}

async function fetchJsonFromApp(origin: string, path: string, body: Record<string, any>) {
  const response = await fetch(`${origin}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? "요청 처리에 실패했습니다.");
  }

  return payload;
}

async function runBacktestViaApp(origin: string, body: Record<string, any>) {
  const response = await fetch(`${origin}/api/strategy/backtest-stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload?.detail ?? payload?.error ?? "백테스트 실행에 실패했습니다.");
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("백테스트 스트림을 읽을 수 없습니다.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let result: any = null;
  let sawCacheHit = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (!payload || payload === "[DONE]") continue;

      const event = JSON.parse(payload);
      if (event.type === "status" && String(event.message ?? "").includes("캐시")) {
        sawCacheHit = true;
      }
      if (event.type === "result" && event.data) {
        result = event.data;
        if (event.data.fromCache) {
          sawCacheHit = true;
        }
      }
      if (event.type === "error") {
        throw new Error(event.message ?? "백테스트 실행 중 오류가 발생했습니다.");
      }
    }
  }

  if (!result) {
    throw new Error("백테스트 결과를 받지 못했습니다.");
  }

  return {
    result,
    status: (sawCacheHit ? "cache_hit" : "computed") as CandidateStatus,
  };
}

function enqueueBatchRun(job: BatchExecutionJob) {
  const state = getExecutionState();
  state.queue.push(job);
}

async function markQueuedRunCanceled(runId: string) {
  const run = await fetchRunWithCandidates(runId, [{ createdAt: "asc" }], candidateResumeSelect);

  if (!run) return;

  const logs = parseJsonField(run.logs, []);
  const nextLogs = hasCancelMarker(logs)
    ? logs
    : [...logs, CANCEL_REQUEST_LOG_MARKER, "사용자 요청으로 대기 중이던 배치 실행을 취소했습니다."];

  const candidates = (run.Candidate ?? []).map((candidate) => ({
    id: candidate.id,
    strategyId: candidate.strategyId,
    prompt: candidate.prompt,
    strategyName: candidate.strategyName,
    status: (candidate.status === "waiting" ? "skipped" : candidate.status) as CandidateStatus,
    errorMessage:
      candidate.status === "waiting"
        ? "사용자 요청으로 실행 전에 취소됨"
        : candidate.errorMessage,
    metrics: parseJsonField(candidate.metrics, null),
    rank: candidate.rank,
    backtestRequest: parseJsonField(candidate.backtestRequest, null),
  }));

  const snapshot = buildSnapshotFromJob({
    runId,
    origin: "",
    backend: "ollama",
    concurrency: 1,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: nextLogs,
    persistChain: Promise.resolve(),
    dirtyCandidateIds: new Set<string>(),
  });

  await saveBatchRunSnapshot(snapshot, { replaceCandidates: true });
}

async function persistJobState(job: BatchExecutionJob) {
  const snapshot = buildSnapshotFromJob(job);
  const dirtyCandidateIds = new Set(job.dirtyCandidateIds);
  job.persistChain = job.persistChain
    .catch(() => undefined)
    .then(async () => {
      await saveBatchRunSnapshot(snapshot, { candidateIds: dirtyCandidateIds });
      for (const candidateId of dirtyCandidateIds) {
        job.dirtyCandidateIds.delete(candidateId);
      }
    });
  await job.persistChain;
}

async function executeBatchRun(job: BatchExecutionJob) {
  const state = getExecutionState();
  let cursor = 0;

  const appendLog = (message: string) => {
    job.logs = [...job.logs, message];
  };

  const updateCandidate = (index: number, patch: Partial<BatchRunCandidatePayload>) => {
    const candidateId = job.candidates[index]?.id ?? `${job.runId}_candidate_${index}`;
    job.dirtyCandidateIds.add(candidateId);
    job.candidates = job.candidates.map((candidate, candidateIndex) =>
      candidateIndex === index ? { ...candidate, ...patch } : candidate
    );
  };

  appendLog(`배치 실행 시작 (concurrency ${job.concurrency})`);
  await persistJobState(job);

  const worker = async () => {
    while (true) {
      const index = cursor;
      cursor += 1;

      if (index >= job.candidates.length) {
        return;
      }

      if (state.canceledRunIds.has(job.runId)) {
        return;
      }

      const candidate = job.candidates[index];
      if (!isRunnableCandidate(candidate)) {
        continue;
      }

      updateCandidate(index, { status: "running", errorMessage: null });
      appendLog(`${index + 1}/${job.candidates.length} 전략 실행 시작`);
      await persistJobState(job);

      try {
        let strategyName = candidate.strategyName;
        let backtestRequest = candidate.backtestRequest;

        if (!backtestRequest) {
          const parsedPayload = await fetchJsonFromApp(job.origin, "/api/strategy/parse", {
            prompt: candidate.prompt,
            backend: job.backend,
          });

          const parsed = parsedPayload?.parsed;
          backtestRequest = parsedPayload?.backtest_request;
          strategyName = inferStrategyName(candidate.prompt, parsed, index);
        }

        if (!backtestRequest) {
          throw new Error("백테스트 요청을 만들지 못했습니다.");
        }

        updateCandidate(index, { strategyName });
        const backtestPayload = await runBacktestViaApp(job.origin, backtestRequest);

        updateCandidate(index, {
          strategyName,
          status: backtestPayload.status,
          strategyId:
            backtestPayload.result?.strategy_id ?? backtestPayload.result?.strategyId ?? null,
          metrics: backtestPayload.result,
          errorMessage: null,
        });
        appendLog(
          `${strategyName} 완료 (${backtestPayload.status === "cache_hit" ? "Cache Hit" : "Computed"})`
        );
      } catch (error: any) {
        const message = error?.message ?? "실행 실패";
        updateCandidate(index, {
          status: "failed",
          errorMessage: message,
        });
        appendLog(`${candidate.strategyName} 실패: ${message}`);
      }

      await persistJobState(job);
    }
  };

  await Promise.all(
    Array.from({ length: Math.min(job.concurrency, job.candidates.length) }, () => worker())
  );

  if (state.canceledRunIds.has(job.runId)) {
    job.candidates = job.candidates.map((candidate) =>
      candidate.status === "waiting"
        ? {
            ...candidate,
            status: "skipped",
            errorMessage: "사용자 요청으로 스킵됨",
          }
        : candidate
    );
    for (const [index, candidate] of job.candidates.entries()) {
      if (candidate.status === "skipped") {
        job.dirtyCandidateIds.add(candidate.id ?? `${job.runId}_candidate_${index}`);
      }
    }
    appendLog("사용자 요청으로 남은 배치 실행을 중단했습니다.");
  } else {
    appendLog("배치 실행이 완료되었습니다.");
  }

  await persistJobState(job);
  state.canceledRunIds.delete(job.runId);
}

function pumpBatchRunQueue() {
  const state = getExecutionState();

  while (state.activeRunIds.size < MAX_ACTIVE_BATCH_RUNS && state.queue.length > 0) {
    const job = state.queue.shift();
    if (!job) break;

    if (state.canceledRunIds.has(job.runId)) {
      state.canceledRunIds.delete(job.runId);
      void markQueuedRunCanceled(job.runId);
      continue;
    }

    state.activeRunIds.add(job.runId);
    state.activeJobs.set(job.runId, job);

    void executeBatchRun(job)
      .catch((error) => {
        console.error("Failed to execute batch run:", error);
      })
      .finally(() => {
        state.activeRunIds.delete(job.runId);
        state.activeJobs.delete(job.runId);
        pumpBatchRunQueue();
      });
  }
}

export async function GET(req: NextRequest) {
  try {
    const runId = req.nextUrl.searchParams.get("runId");

    if (runId) {
      await ensureRunScheduled(runId, req.nextUrl.origin);
      const scheduled = await fetchRunWithCandidates(
        runId,
        [{ rank: "asc" }, { createdAt: "asc" }],
        candidateSummarySelect
      );

      if (!scheduled) {
        return NextResponse.json({ error: "BatchRun not found" }, { status: 404 });
      }

      const run = await recoverCanceledRun(scheduled);
      if (req.nextUrl.searchParams.get("format") === "advisor-learning-results") {
        return NextResponse.json(buildAdvisorLearningResults(run));
      }
      return NextResponse.json(formatRunResponse(run));
    }

    await resumeIncompleteRuns(req.nextUrl.origin);
    const runs = await prisma.batchRun.findMany({
      orderBy: { createdAt: "desc" },
      take: 20,
    });

    return NextResponse.json({
      runs: runs.map((run) => ({
        runId: run.id,
        createdAt: run.createdAt,
        totalPrompts: run.totalPrompts,
        completedCount: run.completedCount,
        failedCount: run.failedCount,
        skippedCount: run.skippedCount,
        rankingSnapshot: parseJsonField(run.rankingSnapshot, []),
        status: deriveRunStatus({
          totalPrompts: run.totalPrompts,
          completedCount: run.completedCount,
          failedCount: run.failedCount,
          skippedCount: run.skippedCount,
          logs: parseJsonField(run.logs, []),
        }).status,
      })),
    });
  } catch (error) {
    console.error("Failed to fetch batch runs:", error);
    return NextResponse.json({ error: "Failed to fetch batch runs" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (body?.action === "cancel") {
      const runId = typeof body.runId === "string" ? body.runId.trim() : "";
      if (!runId) {
        return NextResponse.json({ error: "runId is required" }, { status: 400 });
      }

      const state = getExecutionState();
      state.canceledRunIds.add(runId);
      state.queue = state.queue.filter((job) => job.runId !== runId);

      const run = await fetchRunWithCandidates(runId, [{ createdAt: "asc" }], candidateResumeSelect);

      if (run) {
        const logs = parseJsonField(run.logs, []);
        const candidates = mapRunToStoredCandidates(run).map((candidate) =>
          candidate.status === "waiting"
            ? {
                ...candidate,
                status: "skipped" as CandidateStatus,
                errorMessage: candidate.errorMessage ?? "사용자 요청으로 스킵됨",
              }
            : candidate
        );

        await saveBatchRunSnapshot(
          buildSnapshotFromJob({
            runId,
            origin: "",
            backend: "ollama",
            concurrency: 1,
            createdAt: run.createdAt.toISOString(),
            candidates,
            logs: hasCancelMarker(logs)
              ? logs
              : [...logs, CANCEL_REQUEST_LOG_MARKER, "사용자 요청으로 배치 실행 취소를 요청했습니다."],
            persistChain: Promise.resolve(),
            dirtyCandidateIds: new Set<string>(),
          }),
          { replaceCandidates: true }
        );
      }

      if (!state.activeRunIds.has(runId)) {
        await markQueuedRunCanceled(runId);
      }

      return NextResponse.json({ ok: true, runId, status: "cancel_requested" }, { status: 202 });
    }

    if (Array.isArray(body?.prompts)) {
      const prompts = body.prompts
        .map((prompt: unknown) => String(prompt ?? "").trim())
        .filter(Boolean);

      if (prompts.length === 0) {
        return NextResponse.json({ error: "prompts is required" }, { status: 400 });
      }

      const runId =
        typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : buildRunId();
      const createdAt = new Date().toISOString();
      const job: BatchExecutionJob = {
        runId,
        origin: req.nextUrl.origin,
        backend: body.backend === "mlx" ? "mlx" : "ollama",
        concurrency: clampConcurrency(body.concurrency),
        createdAt,
        candidates: prompts.map((prompt: string, index: number) => ({
          id: `${runId}_candidate_${index}`,
          prompt,
          strategyName: `전략 ${index + 1}`,
          status: "waiting",
          errorMessage: null,
          metrics: null,
          rank: null,
        })),
        logs: [`총 ${prompts.length}개 프롬프트 실행 대기열 등록`],
        persistChain: Promise.resolve(),
        dirtyCandidateIds: new Set<string>(),
      };

      await saveBatchRunSnapshot(buildSnapshotFromJob(job), { replaceCandidates: true });
      enqueueBatchRun(job);
      pumpBatchRunQueue();

      return NextResponse.json(
        {
          ok: true,
          runId,
          status: "queued",
          concurrency: job.concurrency,
        },
        { status: 202 }
      );
    }

    if (body?.action === "run_backtest_requests" && Array.isArray(body?.candidates)) {
      const candidates = body.candidates
        .map((candidate: any, index: number) => ({
          id:
            typeof candidate?.id === "string" && candidate.id.trim()
              ? candidate.id.trim()
              : undefined,
          prompt: String(candidate?.prompt ?? candidate?.hypothesis ?? ""),
          strategyName: String(candidate?.strategyName ?? candidate?.name ?? `전략 ${index + 1}`),
          backtestRequest:
            candidate?.backtestRequest && typeof candidate.backtestRequest === "object"
              ? candidate.backtestRequest
              : candidate?.backtest_request && typeof candidate.backtest_request === "object"
                ? candidate.backtest_request
                : null,
        }))
        .filter((candidate: any) => candidate.backtestRequest);

      if (candidates.length === 0) {
        return NextResponse.json({ error: "candidates with backtestRequest are required" }, { status: 400 });
      }

      const runId =
        typeof body.runId === "string" && body.runId.trim() ? body.runId.trim() : buildRunId();
      const createdAt = new Date().toISOString();
      const job: BatchExecutionJob = {
        runId,
        origin: req.nextUrl.origin,
        backend: body.backend === "mlx" ? "mlx" : "ollama",
        concurrency: clampConcurrency(body.concurrency),
        createdAt,
        candidates: candidates.map((candidate: any, index: number) => ({
          id: candidate.id ?? `${runId}_candidate_${index}`,
          prompt: candidate.prompt,
          strategyName: candidate.strategyName,
          status: "waiting",
          errorMessage: null,
          metrics: null,
          rank: null,
          backtestRequest: candidate.backtestRequest,
        })),
        logs: [`총 ${candidates.length}개 사전 구성 백테스트 실행 대기열 등록`],
        persistChain: Promise.resolve(),
        dirtyCandidateIds: new Set<string>(),
      };

      await saveBatchRunSnapshot(buildSnapshotFromJob(job), { replaceCandidates: true });
      enqueueBatchRun(job);
      pumpBatchRunQueue();

      return NextResponse.json(
        {
          ok: true,
          runId,
          status: "queued",
          concurrency: job.concurrency,
        },
        { status: 202 }
      );
    }

    const runId = typeof body.runId === "string" ? body.runId.trim() : "";
    const candidates = Array.isArray(body.candidates) ? body.candidates : [];

    if (!runId) {
      return NextResponse.json({ error: "runId is required" }, { status: 400 });
    }

    await saveBatchRunSnapshot(
      {
        runId,
        createdAt: typeof body.createdAt === "string" ? body.createdAt : undefined,
        totalPrompts: Number(body.totalPrompts ?? candidates.length ?? 0),
        completedCount: Number(body.completedCount ?? 0),
        failedCount: Number(body.failedCount ?? 0),
        skippedCount: Number(body.skippedCount ?? 0),
        rankingSnapshot: Array.isArray(body.rankingSnapshot) ? body.rankingSnapshot : [],
        logs: Array.isArray(body.logs) ? body.logs : [],
        candidates: candidates.map((candidate: any, index: number) => ({
          id:
            typeof candidate?.id === "string" && candidate.id.trim()
              ? candidate.id.trim()
              : `${runId}_candidate_${index}`,
          strategyId:
            typeof candidate?.strategyId === "string" && candidate.strategyId.trim()
              ? candidate.strategyId.trim()
              : null,
          prompt: String(candidate?.prompt ?? ""),
          strategyName: String(candidate?.strategyName ?? candidate?.name ?? `전략 ${index + 1}`),
          status: String(candidate?.status ?? "unknown"),
          errorMessage:
            typeof candidate?.errorMessage === "string"
              ? candidate.errorMessage
              : typeof candidate?.error === "string"
                ? candidate.error
                : null,
          metrics: candidate?.metrics ?? candidate?.result ?? null,
          rank: typeof candidate?.rank === "number" ? candidate.rank : null,
          backtestRequest:
            candidate?.backtestRequest && typeof candidate.backtestRequest === "object"
              ? candidate.backtestRequest
              : candidate?.backtest_request && typeof candidate.backtest_request === "object"
                ? candidate.backtest_request
                : null,
        })),
      },
      { replaceCandidates: true }
    );

    return NextResponse.json({ ok: true, runId });
  } catch (error) {
    console.error("Failed to save batch run:", error);
    return NextResponse.json({ error: "Failed to save batch run" }, { status: 500 });
  }
}
