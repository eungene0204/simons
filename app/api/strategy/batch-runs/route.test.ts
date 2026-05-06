import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const runStore = new Map<string, any>();
const candidateStore = new Map<string, any[]>();

function cloneCandidates(runId: string) {
  return [...(candidateStore.get(runId) ?? [])].sort(
    (left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime()
  );
}

const batchRunFindUnique = vi.fn(async ({ where }: any) => {
  const run = runStore.get(where.id);
  if (!run) return null;
  return {
    ...run,
    Candidate: cloneCandidates(where.id),
  };
});

const batchRunFindMany = vi.fn(async ({ include }: any = {}) => {
  const runs = [...runStore.values()].sort(
    (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
  );

  if (!include?.Candidate) {
    return runs;
  }

  return runs.map((run) => ({
    ...run,
    Candidate: cloneCandidates(run.id),
  }));
});

const batchRunUpsert = vi.fn(async ({ where, create, update }: any) => {
  const existing = runStore.get(where.id);
  if (existing) {
    const next = {
      ...existing,
      ...update,
    };
    runStore.set(where.id, next);
    return next;
  }

  const created = {
    ...create,
    createdAt: create.createdAt ?? new Date(),
  };
  runStore.set(where.id, created);
  return created;
});

const batchRunCandidateDeleteMany = vi.fn(async ({ where }: any) => {
  candidateStore.set(where.runId, []);
  return { count: 1 };
});

const batchRunCandidateCreateMany = vi.fn(async ({ data }: any) => {
  const rows = data.map((row: any, index: number) => ({
    ...row,
    createdAt: row.createdAt ?? new Date(Date.now() + index),
  }));
  candidateStore.set(rows[0]?.runId ?? "unknown", rows);
  return { count: rows.length };
});

vi.mock("@/lib/prisma", () => ({
  prisma: {
    batchRun: {
      findUnique: batchRunFindUnique,
      findMany: batchRunFindMany,
    },
    $transaction: async (callback: any) =>
      callback({
        batchRun: {
          upsert: batchRunUpsert,
        },
        batchRunCandidate: {
          deleteMany: batchRunCandidateDeleteMany,
          createMany: batchRunCandidateCreateMany,
        },
      }),
  },
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const routeModule = await import("./route");
const { GET, POST } = routeModule;
const { __resetBatchRunExecutionStateForTests } = await import("./executionState");

function makeStreamResponse(events: Array<Record<string, any>>) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const event of events) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      }
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });

  return {
    ok: true,
    body,
  };
}

async function flushUntil(predicate: () => boolean, attempts = 40) {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  throw new Error("condition not satisfied");
}

describe("app/api/strategy/batch-runs/route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    runStore.clear();
    candidateStore.clear();
    __resetBatchRunExecutionStateForTests();

    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = JSON.parse((init?.body as string) ?? "{}");

      if (url.endsWith("/api/strategy/parse")) {
        const prompt = String(body.prompt ?? "");
        return Promise.resolve({
          ok: true,
          json: async () => ({
            parsed: {
              description: prompt.includes("모멘텀") ? "모멘텀 전략" : "가치 전략",
            },
            backtest_request: {
              symbols: ["005930"],
              period: "3Y",
              strategy_id: prompt.includes("모멘텀") ? "hash_momentum" : "hash_value",
            },
          }),
        });
      }

      if (url.endsWith("/api/strategy/backtest-stream")) {
        if (body.strategy_id === "hash_momentum") {
          return Promise.resolve(
            makeStreamResponse([
              { type: "status", message: "전략 실행 중..." },
              {
                type: "result",
                data: {
                  strategy_id: "hash_momentum",
                  totalReturn: 41.2,
                  cagr: 17.5,
                  sharpe: 1.4,
                  maxDrawdown: -9.2,
                  profitFactor: 1.7,
                  trades: 20,
                  equity: [10000000, 14120000],
                  dates: ["2024-01-01", "2025-01-01"],
                  signals: [],
                },
              },
            ])
          );
        }

        return Promise.resolve(
          makeStreamResponse([
            { type: "status", message: "캐시에서 결과를 불러옵니다..." },
            {
              type: "result",
              data: {
                strategy_id: "hash_value",
                totalReturn: 28.3,
                cagr: 11.2,
                sharpe: 1.0,
                maxDrawdown: -7.8,
                profitFactor: 1.2,
                trades: 12,
                equity: [10000000, 12830000],
                dates: ["2024-01-01", "2025-01-01"],
                signals: [],
                fromCache: true,
              },
            },
          ])
        );
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  it("process restart 이후 incomplete run을 DB 기준으로 다시 이어서 완료한다", async () => {
    runStore.set("batch_run_resume", {
      id: "batch_run_resume",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 2,
      completedCount: 0,
      failedCount: 0,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: JSON.stringify(["총 2개 프롬프트 실행 대기열 등록"]),
    });
    candidateStore.set("batch_run_resume", [
      {
        id: "resume-1",
        runId: "batch_run_resume",
        strategyId: null,
        prompt: "모멘텀 전략 프롬프트",
        strategyName: "모멘텀 전략",
        status: "running",
        errorMessage: null,
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
      {
        id: "resume-2",
        runId: "batch_run_resume",
        strategyId: null,
        prompt: "가치 전략 프롬프트",
        strategyName: "가치 전략",
        status: "waiting",
        errorMessage: null,
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:02.000Z"),
      },
    ]);

    __resetBatchRunExecutionStateForTests();

    const response = await GET(
      new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_resume")
    );
    expect(response.status).toBe(200);

    await flushUntil(() => {
      const run = runStore.get("batch_run_resume");
      return !!run && run.completedCount === 2;
    });

    const detail = await response.json();
    expect(detail.runId).toBe("batch_run_resume");

    const storedRun = runStore.get("batch_run_resume");
    expect(storedRun.completedCount).toBe(2);
    expect(storedRun.failedCount).toBe(0);

    const storedCandidates = candidateStore.get("batch_run_resume") ?? [];
    expect(storedCandidates.some((candidate) => candidate.status === "computed")).toBe(true);
    expect(storedCandidates.some((candidate) => candidate.status === "cache_hit")).toBe(true);
  });

  it("cancel marker가 있는 run은 재개하지 않고 남은 항목을 skipped로 정리한다", async () => {
    runStore.set("batch_run_canceled", {
      id: "batch_run_canceled",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 2,
      completedCount: 0,
      failedCount: 0,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: JSON.stringify([
        "[batch-run-cancel-requested]",
        "사용자 요청으로 배치 실행 취소를 요청했습니다.",
      ]),
    });
    candidateStore.set("batch_run_canceled", [
      {
        id: "cancel-1",
        runId: "batch_run_canceled",
        strategyId: null,
        prompt: "모멘텀 전략 프롬프트",
        strategyName: "모멘텀 전략",
        status: "running",
        errorMessage: null,
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
      {
        id: "cancel-2",
        runId: "batch_run_canceled",
        strategyId: null,
        prompt: "가치 전략 프롬프트",
        strategyName: "가치 전략",
        status: "waiting",
        errorMessage: null,
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:02.000Z"),
      },
    ]);

    __resetBatchRunExecutionStateForTests();

    const response = await GET(
      new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_canceled")
    );
    expect(response.status).toBe(200);

    const payload = await response.json();
    expect(payload.status).toBe("CANCELED");

    const storedCandidates = candidateStore.get("batch_run_canceled") ?? [];
    expect(storedCandidates.every((candidate) => candidate.status === "skipped")).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("prompt 기반 POST는 기존처럼 queued 응답을 주고 run을 저장한다", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/batch-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            prompts: ["모멘텀 전략 프롬프트"],
          }),
        })
      )
    );

    expect(response.status).toBe(202);
    const payload = await response.json();
    expect(payload.status).toBe("queued");
    expect(runStore.has(payload.runId)).toBe(true);
  });
});
