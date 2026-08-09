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

const batchRunCandidateUpsert = vi.fn(async ({ where, create, update }: any) => {
  const runId = create.runId;
  const rows = candidateStore.get(runId) ?? [];
  const existingIndex = rows.findIndex((row) => row.id === where.id);
  if (existingIndex >= 0) {
    const next = {
      ...rows[existingIndex],
      ...update,
    };
    rows[existingIndex] = next;
    candidateStore.set(runId, rows);
    return next;
  }

  const created = {
    ...create,
    createdAt: create.createdAt ?? new Date(Date.now() + rows.length),
  };
  candidateStore.set(runId, [...rows, created]);
  return created;
});

const batchRunCandidateFindMany = vi.fn(async ({ where, orderBy = [], skip = 0, take, select }: any) => {
  const rows = [...(candidateStore.get(where.runId) ?? [])].sort((left, right) => {
    for (const order of orderBy) {
      const [field, direction] = Object.entries(order)[0] as [string, string];
      const leftValue = field === "createdAt" ? new Date(left[field]).getTime() : left[field];
      const rightValue = field === "createdAt" ? new Date(right[field]).getTime() : right[field];
      const normalizedLeft = leftValue ?? Number.MAX_SAFE_INTEGER;
      const normalizedRight = rightValue ?? Number.MAX_SAFE_INTEGER;
      if (normalizedLeft === normalizedRight) continue;
      return direction === "desc"
        ? normalizedRight > normalizedLeft
          ? 1
          : -1
        : normalizedLeft > normalizedRight
          ? 1
          : -1;
    }
    return 0;
  });
  const page = rows.slice(skip, take ? skip + take : undefined);
  if (!select) return page;
  return page.map((row) =>
    Object.fromEntries(Object.entries(select).filter(([, enabled]) => enabled).map(([key]) => [key, row[key]]))
  );
});

vi.mock("@/lib/prisma", () => ({
  prisma: {
    batchRun: {
      findUnique: batchRunFindUnique,
      findMany: batchRunFindMany,
    },
    batchRunCandidate: {
      findMany: batchRunCandidateFindMany,
    },
    $transaction: async (callback: any) =>
      callback({
        batchRun: {
          upsert: batchRunUpsert,
        },
        batchRunCandidate: {
          findMany: batchRunCandidateFindMany,
          deleteMany: batchRunCandidateDeleteMany,
          createMany: batchRunCandidateCreateMany,
          upsert: batchRunCandidateUpsert,
        },
      }),
  },
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const routeModule = await import("./route");
const { GET, POST } = routeModule;
const { buildRankingSnapshot } = await import("./rankingSnapshot");
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

  it("동시 조회가 incomplete run을 중복 재개하지 않는다", async () => {
    runStore.set("batch_run_resume_once", {
      id: "batch_run_resume_once",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 1,
      completedCount: 0,
      failedCount: 0,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: JSON.stringify(["총 1개 프롬프트 실행 대기열 등록"]),
    });
    candidateStore.set("batch_run_resume_once", [
      {
        id: "resume-once-1",
        runId: "batch_run_resume_once",
        strategyId: null,
        prompt: "모멘텀 전략 프롬프트",
        strategyName: "모멘텀 전략",
        status: "running",
        errorMessage: null,
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
    ]);

    __resetBatchRunExecutionStateForTests();

    const responses = await Promise.all([
      GET(new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_resume_once")),
      GET(new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_resume_once")),
      GET(new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_resume_once")),
    ]);
    expect(responses.every((response) => response.status === 200)).toBe(true);

    await flushUntil(() => {
      const run = runStore.get("batch_run_resume_once");
      return !!run && run.completedCount === 1;
    });

    const backtestCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/api/strategy/backtest-stream")
    );
    expect(backtestCalls).toHaveLength(1);
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

  it("저장된 batch run을 advisor learning 결과 payload로 export한다", async () => {
    runStore.set("batch_run_learning", {
      id: "batch_run_learning",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 3,
      completedCount: 2,
      failedCount: 1,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: "[]",
    });
    candidateStore.set("batch_run_learning", [
      {
        id: "advisor_smoke_0001",
        runId: "batch_run_learning",
        strategyId: "hash_momentum",
        prompt: "모멘텀 smoke sample",
        strategyName: "momentum sample",
        status: "computed",
        errorMessage: null,
        metrics: JSON.stringify({ cagr: 17.5, sharpe: 1.4, maxDrawdown: -9.2, trades: 20 }),
        rank: 1,
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
      {
        id: "candidate_with_metric_sample_id",
        runId: "batch_run_learning",
        strategyId: "hash_value",
        prompt: "가치 smoke sample",
        strategyName: "value sample",
        status: "cache_hit",
        errorMessage: null,
        metrics: JSON.stringify({ sample_id: "advisor_smoke_0002", cagr: 11.2, sharpe: 1.0, mdd: -7.8 }),
        rank: 2,
        createdAt: new Date("2026-04-22T00:00:02.000Z"),
      },
      {
        id: "advisor_smoke_0003",
        runId: "batch_run_learning",
        strategyId: null,
        prompt: "실패 sample",
        strategyName: "failed sample",
        status: "failed",
        errorMessage: "실행 실패",
        metrics: null,
        rank: null,
        createdAt: new Date("2026-04-22T00:00:03.000Z"),
      },
    ]);

    const response = await GET(
      new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_learning&format=advisor-learning-results")
    );

    expect(response.status).toBe(200);
    const payload = await response.json();
    expect(payload.runId).toBe("batch_run_learning");
    expect(payload.totalResults).toBe(2);
    const candidateFetchCall = batchRunCandidateFindMany.mock.calls.find(
      ([args]) => args?.orderBy?.[0]?.rank === "asc"
    );
    expect(candidateFetchCall?.[0]?.select).toEqual(
      expect.objectContaining({
        metrics: true,
        prompt: true,
      })
    );
    expect(candidateFetchCall?.[0]?.select).not.toHaveProperty("backtestRequest");
    expect(payload.results).toEqual([
      expect.objectContaining({
        sample_id: "advisor_smoke_0001",
        candidate_id: "advisor_smoke_0001",
        strategy_id: "hash_momentum",
        status: "computed",
        metrics: expect.objectContaining({ cagr: 17.5, maxDrawdown: -9.2 }),
      }),
      expect.objectContaining({
        sample_id: "advisor_smoke_0002",
        candidate_id: "candidate_with_metric_sample_id",
        strategy_id: "hash_value",
        status: "cache_hit",
        metrics: expect.objectContaining({ cagr: 11.2, mdd: -7.8 }),
      }),
    ]);
  });

  it("사전 구성된 backtestRequest 후보를 parse 없이 실행한다", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/batch-runs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "run_backtest_requests",
            runId: "batch_run_prebuilt",
            candidates: [
              {
                id: "advisor_smoke_0001",
                prompt: "사전 구성 smoke sample",
                strategyName: "prebuilt momentum",
                backtestRequest: {
                  strategy_id: "hash_momentum",
                  symbols: ["005930"],
                  period: "3Y",
                },
              },
            ],
          }),
        })
      )
    );

    expect(response.status).toBe(202);
    const payload = await response.json();
    expect(payload.runId).toBe("batch_run_prebuilt");

    await flushUntil(() => {
      const run = runStore.get("batch_run_prebuilt");
      return !!run && run.completedCount === 1;
    });

    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((url) => url.endsWith("/api/strategy/parse"))).toBe(false);
    expect(urls.some((url) => url.endsWith("/api/strategy/backtest-stream"))).toBe(true);

    const storedCandidates = candidateStore.get("batch_run_prebuilt") ?? [];
    expect(storedCandidates).toHaveLength(1);
    expect(storedCandidates[0]).toEqual(
      expect.objectContaining({
        id: "advisor_smoke_0001",
        strategyId: "hash_momentum",
        strategyName: "prebuilt momentum",
        status: "computed",
      })
    );
    expect(JSON.parse(storedCandidates[0].backtestRequest)).toEqual(
      expect.objectContaining({
        strategy_id: "hash_momentum",
        symbols: ["005930"],
        period: "3Y",
      })
    );
    expect(JSON.parse(storedCandidates[0].metrics)).toEqual(
      expect.objectContaining({ cagr: 17.5, sharpe: 1.4 })
    );
    expect(batchRunCandidateDeleteMany).toHaveBeenCalledTimes(1);
    expect(batchRunCandidateCreateMany).toHaveBeenCalledTimes(1);
    expect(batchRunCandidateUpsert).toHaveBeenCalled();
  });

  it("process restart 이후 저장된 backtestRequest 후보를 parse 없이 이어서 실행한다", async () => {
    runStore.set("batch_run_prebuilt_resume", {
      id: "batch_run_prebuilt_resume",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 1,
      completedCount: 0,
      failedCount: 0,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: JSON.stringify(["총 1개 사전 구성 백테스트 실행 대기열 등록"]),
    });
    candidateStore.set("batch_run_prebuilt_resume", [
      {
        id: "advisor_smoke_0001",
        runId: "batch_run_prebuilt_resume",
        strategyId: null,
        prompt: "사전 구성 smoke sample",
        strategyName: "prebuilt momentum",
        status: "running",
        errorMessage: null,
        metrics: null,
        rank: null,
        backtestRequest: JSON.stringify({
          strategy_id: "hash_momentum",
          symbols: ["005930"],
          period: "3Y",
        }),
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
    ]);

    __resetBatchRunExecutionStateForTests();

    const response = await GET(
      new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_prebuilt_resume")
    );
    expect(response.status).toBe(200);

    await flushUntil(() => {
      const run = runStore.get("batch_run_prebuilt_resume");
      return !!run && run.completedCount === 1;
    });

    const urls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(urls.some((url) => url.endsWith("/api/strategy/parse"))).toBe(false);
    expect(urls.some((url) => url.endsWith("/api/strategy/backtest-stream"))).toBe(true);

    const storedCandidates = candidateStore.get("batch_run_prebuilt_resume") ?? [];
    expect(storedCandidates[0]).toEqual(
      expect.objectContaining({
        id: "advisor_smoke_0001",
        strategyId: "hash_momentum",
        status: "computed",
      })
    );
  });

  it("process restart 이후 이미 완료된 후보는 재실행하지 않고 running 후보만 복구한다", async () => {
    runStore.set("batch_run_partial_resume", {
      id: "batch_run_partial_resume",
      createdAt: new Date("2026-04-22T00:00:00.000Z"),
      totalPrompts: 2,
      completedCount: 1,
      failedCount: 0,
      skippedCount: 0,
      rankingSnapshot: "[]",
      logs: JSON.stringify(["총 2개 사전 구성 백테스트 실행 대기열 등록"]),
    });
    candidateStore.set("batch_run_partial_resume", [
      {
        id: "partial-complete",
        runId: "batch_run_partial_resume",
        strategyId: "hash_value",
        prompt: "완료된 smoke sample",
        strategyName: "completed value",
        status: "cache_hit",
        errorMessage: null,
        metrics: JSON.stringify({
          strategy_id: "hash_value",
          cagr: 11.2,
          sharpe: 1.0,
          equity: [10000000, 11120000],
          dates: ["2025-01-01", "2025-12-31"],
          signals: [{ date: "2025-01-02", symbol: "005930", type: "buy" }],
        }),
        rank: 1,
        backtestRequest: JSON.stringify({
          strategy_id: "hash_value",
          symbols: ["005930"],
          period: "3Y",
        }),
        createdAt: new Date("2026-04-22T00:00:01.000Z"),
      },
      {
        id: "partial-running",
        runId: "batch_run_partial_resume",
        strategyId: null,
        prompt: "정체된 smoke sample",
        strategyName: "running momentum",
        status: "running",
        errorMessage: null,
        metrics: null,
        rank: null,
        backtestRequest: JSON.stringify({
          strategy_id: "hash_momentum",
          symbols: ["005930"],
          period: "3Y",
        }),
        createdAt: new Date("2026-04-22T00:00:02.000Z"),
      },
    ]);

    __resetBatchRunExecutionStateForTests();

    const response = await GET(
      new NextRequest("http://localhost/api/strategy/batch-runs?runId=batch_run_partial_resume")
    );
    expect(response.status).toBe(200);
    const detail = await response.json();
    expect(detail.candidates[0].metrics).toEqual(
      expect.objectContaining({ cagr: 11.2, sharpe: 1.0 })
    );
    expect(detail.candidates[0].metrics).not.toHaveProperty("equity");
    expect(detail.candidates[0].metrics).not.toHaveProperty("dates");
    expect(detail.candidates[0].metrics).not.toHaveProperty("signals");

    await flushUntil(() => {
      const run = runStore.get("batch_run_partial_resume");
      return !!run && run.completedCount === 2;
    });

    const backtestCalls = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/api/strategy/backtest-stream")
    );
    expect(backtestCalls).toHaveLength(1);
    expect(JSON.parse(backtestCalls[0][1]?.body as string).strategy_id).toBe("hash_momentum");

    const storedCandidates = candidateStore.get("batch_run_partial_resume") ?? [];
    expect(storedCandidates[0]).toEqual(
      expect.objectContaining({
        id: "partial-complete",
        status: "cache_hit",
        strategyId: "hash_value",
      })
    );
    expect(storedCandidates[1]).toEqual(
      expect.objectContaining({
        id: "partial-running",
        status: "computed",
        strategyId: "hash_momentum",
      })
    );
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

  it("랭킹 스냅샷은 손익비 null(=손실 0건, ∞)을 0이 아니라 999 상한으로 접는다", () => {
    // 회귀: Number(pf ?? 0)이 null을 0(최악)으로 저장해 전승 전략이 스냅샷에서 왜곡됐다
    const { rankingSnapshot } = buildRankingSnapshot([
      {
        id: "c1",
        prompt: "무손실 전략",
        strategyName: "무손실 전략",
        status: "computed",
        metrics: { cagr: 10, totalReturn: 20, sharpe: 1.1, maxDrawdown: -5, profitFactor: null, trades: 3 },
      },
    ] as any);
    expect(rankingSnapshot[0].profitFactor).toBe(999);
  });
});
