import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

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

type BatchExecutionJob = {
  runId: string;
  origin: string;
  backend: "mlx" | "ollama";
  concurrency: number;
  createdAt: string;
  candidates: BatchRunCandidatePayload[];
  logs: string[];
  persistChain: Promise<void>;
};

type BatchExecutionState = {
  queue: BatchExecutionJob[];
  activeRunIds: Set<string>;
  activeJobs: Map<string, BatchExecutionJob>;
  canceledRunIds: Set<string>;
};

const MAX_ACTIVE_BATCH_RUNS = 2;
const DEFAULT_CANDIDATE_CONCURRENCY = 2;
const MAX_CANDIDATE_CONCURRENCY = 4;
const CANCEL_REQUEST_LOG_MARKER = "[batch-run-cancel-requested]";

function getExecutionState(): BatchExecutionState {
  const globalScope = globalThis as typeof globalThis & {
    __strategyBatchExecutionState?: BatchExecutionState;
  };

  if (!globalScope.__strategyBatchExecutionState) {
    globalScope.__strategyBatchExecutionState = {
      queue: [],
      activeRunIds: new Set<string>(),
      activeJobs: new Map<string, BatchExecutionJob>(),
      canceledRunIds: new Set<string>(),
    };
  }

  return globalScope.__strategyBatchExecutionState;
}

export function __resetBatchRunExecutionStateForTests() {
  const state = getExecutionState();
  state.queue.length = 0;
  state.activeRunIds.clear();
  state.activeJobs.clear();
  state.canceledRunIds.clear();
}

function parseJsonField<T>(value: string | null | undefined, fallback: T): T {
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function hasCancelMarker(logs: string[]) {
  return logs.some((log) => log.includes(CANCEL_REQUEST_LOG_MARKER));
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

function buildRankingSnapshot(candidates: BatchRunCandidatePayload[]) {
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
      profitFactor: Number(candidate.metrics?.profitFactor ?? 0),
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

async function saveBatchRunSnapshot(snapshot: BatchRunSnapshotPayload) {
  await prisma.$transaction(async (tx) => {
    const createData: Record<string, any> = {
      id: snapshot.runId,
      totalPrompts: Number(snapshot.totalPrompts ?? snapshot.candidates.length ?? 0),
      completedCount: Number(snapshot.completedCount ?? 0),
      failedCount: Number(snapshot.failedCount ?? 0),
      skippedCount: Number(snapshot.skippedCount ?? 0),
      rankingSnapshot: JSON.stringify(snapshot.rankingSnapshot ?? []),
      logs: JSON.stringify(snapshot.logs ?? []),
    };

    if (snapshot.createdAt) {
      createData.createdAt = new Date(snapshot.createdAt);
    }

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

    await tx.batchRunCandidate.deleteMany({
      where: { runId: snapshot.runId },
    });

    if (snapshot.candidates.length > 0) {
      await tx.batchRunCandidate.createMany({
        data: snapshot.candidates.map((candidate, index) => ({
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
        })),
      });
    }
  });
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
        metrics: parseJsonField(candidate.metrics, null),
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
  const logs = parseJsonField(run.logs, []);
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
    backend: "mlx",
    concurrency: 1,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: logs.includes("취소 요청을 반영해 남은 배치 실행을 종료했습니다.")
      ? logs
      : [...logs, "취소 요청을 반영해 남은 배치 실행을 종료했습니다."],
    persistChain: Promise.resolve(),
  });

  await saveBatchRunSnapshot(snapshot);

  return prisma.batchRun.findUnique({
    where: { id: run.id },
    include: {
      Candidate: {
        orderBy: [{ rank: "asc" }, { createdAt: "asc" }],
      },
    },
  });
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
    backend: "mlx",
    concurrency: DEFAULT_CANDIDATE_CONCURRENCY,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: candidates.some((candidate) => candidate.status === "waiting") &&
      (run.Candidate ?? []).some((candidate: any) => candidate.status === "running")
        ? [...logs, "서버 재시작 후 중단된 전략을 다시 대기열에 복구했습니다."]
        : logs,
    persistChain: Promise.resolve(),
  };
}

async function ensureRunScheduled(runId: string, origin: string) {
  const state = getExecutionState();
  if (state.activeRunIds.has(runId) || state.queue.some((job) => job.runId === runId)) {
    return;
  }

  const run = await prisma.batchRun.findUnique({
    where: { id: runId },
    include: {
      Candidate: {
        orderBy: [{ createdAt: "asc" }],
      },
    },
  });

  if (!run) return;

  const recoveredRun = await recoverCanceledRun(run);
  if (!recoveredRun || !shouldResumeRun(recoveredRun)) {
    return;
  }

  enqueueBatchRun(hydrateJobFromStoredRun(recoveredRun, origin));
  pumpBatchRunQueue();
}

async function resumeIncompleteRuns(origin: string) {
  const runs = await prisma.batchRun.findMany({
    orderBy: { createdAt: "desc" },
    take: 20,
    include: {
      Candidate: {
        orderBy: [{ createdAt: "asc" }],
      },
    },
  });

  for (const run of runs) {
    if (shouldResumeRun(run)) {
      await ensureRunScheduled(run.id, origin);
    } else if (hasCancelMarker(parseJsonField(run.logs, []))) {
      await recoverCanceledRun(run);
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
  const run = await prisma.batchRun.findUnique({
    where: { id: runId },
    include: {
      Candidate: {
        orderBy: [{ createdAt: "asc" }],
      },
    },
  });

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
  }));

  const snapshot = buildSnapshotFromJob({
    runId,
    origin: "",
    backend: "mlx",
    concurrency: 1,
    createdAt: run.createdAt.toISOString(),
    candidates,
    logs: nextLogs,
    persistChain: Promise.resolve(),
  });

  await saveBatchRunSnapshot(snapshot);
}

async function persistJobState(job: BatchExecutionJob) {
  const snapshot = buildSnapshotFromJob(job);
  job.persistChain = job.persistChain
    .catch(() => undefined)
    .then(() => saveBatchRunSnapshot(snapshot));
  await job.persistChain;
}

async function executeBatchRun(job: BatchExecutionJob) {
  const state = getExecutionState();
  let cursor = 0;

  const appendLog = (message: string) => {
    job.logs = [...job.logs, message];
  };

  const updateCandidate = (index: number, patch: Partial<BatchRunCandidatePayload>) => {
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
      updateCandidate(index, { status: "running", errorMessage: null });
      appendLog(`${index + 1}/${job.candidates.length} 전략 실행 시작`);
      await persistJobState(job);

      try {
        const parsedPayload = await fetchJsonFromApp(job.origin, "/api/strategy/parse", {
          prompt: candidate.prompt,
          backend: job.backend,
        });

        const parsed = parsedPayload?.parsed;
        const backtestRequest = parsedPayload?.backtest_request;
        const strategyName = inferStrategyName(candidate.prompt, parsed, index);

        if (!backtestRequest) {
          throw new Error(parsedPayload?.clarification_question ?? "백테스트 요청을 만들지 못했습니다.");
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
    await resumeIncompleteRuns(req.nextUrl.origin);
    const runId = req.nextUrl.searchParams.get("runId");

    if (runId) {
      const scheduled = await prisma.batchRun.findUnique({
        where: { id: runId },
        include: {
          Candidate: {
            orderBy: [{ rank: "asc" }, { createdAt: "asc" }],
          },
        },
      });

      if (!scheduled) {
        return NextResponse.json({ error: "BatchRun not found" }, { status: 404 });
      }

      const run = await recoverCanceledRun(scheduled);
      return NextResponse.json(formatRunResponse(run));
    }

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

      const run = await prisma.batchRun.findUnique({
        where: { id: runId },
        include: {
          Candidate: {
            orderBy: [{ createdAt: "asc" }],
          },
        },
      });

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
            backend: "mlx",
            concurrency: 1,
            createdAt: run.createdAt.toISOString(),
            candidates,
            logs: hasCancelMarker(logs)
              ? logs
              : [...logs, CANCEL_REQUEST_LOG_MARKER, "사용자 요청으로 배치 실행 취소를 요청했습니다."],
            persistChain: Promise.resolve(),
          })
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
        backend: body.backend === "ollama" ? "ollama" : "mlx",
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
      };

      await saveBatchRunSnapshot(buildSnapshotFromJob(job));
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

    await saveBatchRunSnapshot({
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
      })),
    });

    return NextResponse.json({ ok: true, runId });
  } catch (error) {
    console.error("Failed to save batch run:", error);
    return NextResponse.json({ error: "Failed to save batch run" }, { status: 500 });
  }
}
