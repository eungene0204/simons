import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const runStore = new Map<string, any>();
const candidateStore = new Map<string, any[]>();

const batchRunFindUnique = vi.fn(async ({ where }: any) => {
  const run = runStore.get(where.id);
  if (!run) return null;
  return {
    ...run,
    Candidate: [...(candidateStore.get(where.id) ?? [])],
  };
});

const batchRunFindMany = vi.fn(async () =>
  [...runStore.values()].sort(
    (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
  )
);

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
  const rows = data.map((row: any) => ({
    ...row,
    createdAt: new Date(),
  }));
  candidateStore.set(rows[0]?.runId ?? "unknown", rows);
  return { count: rows.length };
});

vi.mock("@/lib/prisma", () => {
  return {
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
  };
});

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const routeModule = await import("@/app/api/strategy/batch-runs/route");
const { GET, POST, __resetBatchRunExecutionStateForTests } = routeModule;

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

function makePostRequest(body: object) {
  return new Request("http://localhost/api/strategy/batch-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function flushUntil(predicate: () => boolean, attempts = 30) {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  throw new Error("condition not satisfied");
}

describe("POST /api/strategy/batch-runs", () => {
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
              canonical_strategy_dsl: {
                universe: ["KOSPI"],
                entry_signals: [{ indicator: prompt.includes("모멘텀") ? "momentum" : "value" }],
              },
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

  it("prompts 배열을 받으면 서버 비동기 배치 실행을 시작하고 완료 결과를 저장한다", async () => {
    const response = await POST(
      new NextRequest(
        makePostRequest({
          prompts: ["모멘텀 전략 프롬프트", "가치 전략 프롬프트"],
          concurrency: 2,
        })
      )
    );

    expect(response.status).toBe(202);
    const payload = await response.json();
    expect(payload.status).toBe("queued");
    expect(typeof payload.runId).toBe("string");

    await flushUntil(() => {
      const run = runStore.get(payload.runId);
      return !!run && run.completedCount === 2;
    });

    const storedRun = runStore.get(payload.runId);
    expect(storedRun.failedCount).toBe(0);
    expect(storedRun.skippedCount).toBe(0);

    const storedCandidates = candidateStore.get(payload.runId) ?? [];
    expect(storedCandidates).toHaveLength(2);
    expect(storedCandidates.some((candidate) => candidate.status === "computed")).toBe(true);
    expect(storedCandidates.some((candidate) => candidate.status === "cache_hit")).toBe(true);

    const detailResponse = await GET(
      new NextRequest(`http://localhost/api/strategy/batch-runs?runId=${payload.runId}`)
    );
    expect(detailResponse.status).toBe(200);

    const detail = await detailResponse.json();
    expect(detail.status).toBe("COMPLETED");
    expect(detail.rankingSnapshot[0].name).toBe("모멘텀 전략");
    expect(detail.candidates[0].strategyName).toBeTruthy();
  });
});
