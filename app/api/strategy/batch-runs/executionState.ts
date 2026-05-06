type BatchRunCandidatePayload = {
  id?: string;
  strategyId?: string | null;
  prompt: string;
  strategyName: string;
  status: string;
  errorMessage?: string | null;
  metrics?: any;
  rank?: number | null;
};

export type BatchExecutionJob = {
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

export function getExecutionState(): BatchExecutionState {
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
