import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { canonicalizeStrategyDsl, createStrategyId } from "./hash";

const experimentStore = new Map<string, any>();
const candidateStore = new Map<string, any[]>();
const backtestResultFindFirst = vi.fn();
const backtestHistoryFindFirst = vi.fn();
const insightDeleteMany = vi.fn(async () => ({ count: 0 }));
const insightCreateMany = vi.fn(async ({ data }: any) => ({ count: data.length }));

function cloneCandidates(experimentId: string) {
  return [...(candidateStore.get(experimentId) ?? [])].sort(
    (left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime()
  );
}

const strategyPromptExperimentCreate = vi.fn(async ({ data }: any) => {
  experimentStore.set(data.id, { ...data });
  return data;
});

const strategyPromptExperimentUpdate = vi.fn(async ({ where, data }: any) => {
  const existing = experimentStore.get(where.id);
  const next = { ...existing, ...data };
  experimentStore.set(where.id, next);
  return next;
});

const strategyPromptExperimentFindUnique = vi.fn(async ({ where, include }: any) => {
  const row = experimentStore.get(where.id);
  if (!row) return null;
  if (!include?.candidates) return row;
  return { ...row, candidates: cloneCandidates(where.id) };
});

const strategyPromptExperimentFindMany = vi.fn(async () => Array.from(experimentStore.values()));

const candidateCreateMany = vi.fn(async ({ data }: any) => {
  const rows = data.map((row: any, index: number) => ({
    ...row,
    id: row.id ?? `${row.experimentId}_${row.promptId}`,
    createdAt: row.createdAt ?? new Date(Date.now() + index),
    updatedAt: row.updatedAt ?? new Date(Date.now() + index),
  }));
  candidateStore.set(rows[0]?.experimentId ?? "unknown", rows);
  return { count: rows.length };
});

const candidateFindMany = vi.fn(async ({ where }: any) => cloneCandidates(where.experimentId));

const candidateUpdate = vi.fn(async ({ where, data }: any) => {
  const key = where.experimentId_promptId;
  const rows = cloneCandidates(key.experimentId);
  const index = rows.findIndex((row) => row.promptId === key.promptId);
  if (index < 0) throw new Error("candidate not found");
  rows[index] = { ...rows[index], ...data };
  candidateStore.set(key.experimentId, rows);
  return rows[index];
});

const candidateUpdateMany = vi.fn(async ({ where, data }: any) => {
  const rows = cloneCandidates(where.experimentId).map((row) =>
    !where.status ||
    row.status === where.status ||
    (Array.isArray(where.status?.in) && where.status.in.includes(row.status))
      ? { ...row, ...data }
      : row
  );
  candidateStore.set(where.experimentId, rows);
  return { count: rows.length };
});

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategyPromptExperiment: {
      create: strategyPromptExperimentCreate,
      update: strategyPromptExperimentUpdate,
      findUnique: strategyPromptExperimentFindUnique,
      findMany: strategyPromptExperimentFindMany,
    },
    strategyPromptExperimentCandidate: {
      createMany: candidateCreateMany,
      findMany: candidateFindMany,
      update: candidateUpdate,
      updateMany: candidateUpdateMany,
    },
    strategyAdvisorLearningInsight: {
      deleteMany: insightDeleteMany,
      createMany: insightCreateMany,
    },
    backtestResult: {
      findFirst: backtestResultFindFirst,
    },
    backtestHistory: {
      findFirst: backtestHistoryFindFirst,
    },
  },
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

let POST: any;

beforeAll(async () => {
  const routeModule = await import("./route");
  POST = routeModule.POST;
});

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
  return { ok: true, body };
}

async function flushUntil(predicate: () => boolean, attempts = 80) {
  for (let index = 0; index < attempts; index += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  throw new Error("condition not satisfied");
}

describe("app/api/strategy/prompt-experiments/route", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    experimentStore.clear();
    candidateStore.clear();
    backtestResultFindFirst.mockResolvedValue(null);
    backtestHistoryFindFirst.mockResolvedValue(null);
    (globalThis as any).__strategyPromptExperimentState = {
      queue: [],
      activeJobs: new Map(),
      canceledIds: new Set(),
    };
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body = JSON.parse(String(init?.body ?? "{}"));
      if (url.endsWith("/api/strategy/parse")) {
        if (String(body.prompt).includes("실패")) {
          return Promise.resolve({
            ok: false,
            json: async () => ({ error: "parse failed" }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: async () => ({
            parsed: { description: body.prompt },
            backtest_request: {
              universe: "KOSPI200",
              entry: [{ block: String(body.prompt).includes("RSI") ? "rsi" : "pbr" }],
              exit: [{ block: "take_profit", pct: 10 }],
            },
          }),
        });
      }
      if (url.endsWith("/api/strategy/backtest-stream")) {
        return Promise.resolve(
          makeStreamResponse([
            {
              type: "result",
              data: {
                cagr: 12,
                totalReturn: 40,
                sharpe: 1.2,
                maxDrawdown: -12,
                profitFactor: 1.5,
                winRate: 55,
                trades: 36,
                volatility: 18,
                calmar: 1,
                buyAndHoldReturn: 20,
              },
            },
          ])
        );
      }
      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  it("generates 300 non-empty prompts with the required category distribution", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/prompt-experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "generate", seed: 7 }),
        })
      )
    );
    const payload = await response.json();
    const prompts: any[] = payload.prompts;
    const counts = prompts.reduce((acc: Record<string, number>, prompt: any) => {
      acc[prompt.category] = (acc[prompt.category] ?? 0) + 1;
      return acc;
    }, {});

    expect(prompts).toHaveLength(300);
    expect(new Set(prompts.map((prompt) => prompt.text)).size).toBeGreaterThan(285);
    expect(prompts.every((prompt: any) => prompt.text.trim() && prompt.expected_blocks.length > 0)).toBe(true);
    expect(counts).toMatchObject({
      technical_momentum: 45,
      technical_mean_reversion: 45,
      value_fundamental: 45,
      hybrid_value_technical: 60,
      breakout_volume: 35,
      ai_hybrid: 25,
      risk_management_variants: 30,
      ambiguous_beginner_prompts: 15,
    });
  });

  it("creates a stable strategy_id for semantically identical DSL key ordering", () => {
    const left = { entry: [{ block: "rsi", threshold: 30 }], universe: "KOSPI200", metadata: { ignored: true } };
    const right = { metadata: { ignored: false }, universe: "KOSPI200", entry: [{ threshold: 30, block: "rsi" }] };

    expect(canonicalizeStrategyDsl(left)).toBe(canonicalizeStrategyDsl(right));
    expect(createStrategyId(left)).toBe(createStrategyId(right));
  });

  it("does not call backtest-stream when canonical strategy cache exists", async () => {
    backtestResultFindFirst.mockResolvedValue({
      summary: JSON.stringify({
        cagr: 8,
        totalReturn: 24,
        sharpe: 0.9,
        maxDrawdown: -8,
        profitFactor: 1.3,
        winRate: 53,
        trades: 42,
      }),
    });

    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/prompt-experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            experimentId: "prompt_exp_cache",
            prompts: [
              {
                id: "prompt_001",
                text: "KOSPI200에서 RSI 30 이하 전략을 테스트해줘.",
                category: "technical_mean_reversion",
                complexity: "intermediate",
                risk_profile: "moderate",
                expected_blocks: ["rsi", "take_profit"],
                notes: "cache hit path",
              },
            ],
          }),
        })
      )
    );

    expect(response.status).toBe(202);
    await flushUntil(() => cloneCandidates("prompt_exp_cache")[0]?.status === "cache_hit");
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/api/strategy/backtest-stream"))).toHaveLength(0);
  });

  it("keeps running remaining candidates when one prompt fails", async () => {
    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/prompt-experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            experimentId: "prompt_exp_partial_failure",
            prompts: [
              {
                id: "prompt_001",
                text: "파싱 실패 프롬프트",
                category: "ambiguous_beginner_prompts",
                complexity: "beginner",
                risk_profile: "moderate",
                expected_blocks: ["rsi"],
                notes: "failure path",
              },
              {
                id: "prompt_002",
                text: "KOSPI200에서 PBR 1 이하 전략을 테스트해줘.",
                category: "value_fundamental",
                complexity: "intermediate",
                risk_profile: "conservative",
                expected_blocks: ["pbr", "take_profit"],
                notes: "success path",
              },
            ],
          }),
        })
      )
    );

    expect(response.status).toBe(202);
    await flushUntil(() => {
      const rows = cloneCandidates("prompt_exp_partial_failure");
      return rows.some((row) => row.status === "failed") && rows.some((row) => row.status === "computed");
    });

    const rows = cloneCandidates("prompt_exp_partial_failure");
    expect(rows.find((row) => row.promptId === "prompt_001")?.errorType).toBe("parse_error");
    expect(rows.find((row) => row.promptId === "prompt_002")?.status).toBe("computed");
  });

  it("starts an existing waiting experiment without recreating prompt samples", async () => {
    await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/prompt-experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            experimentId: "prompt_exp_existing",
            start: false,
            prompts: [
              {
                id: "prompt_001",
                text: "KOSPI200에서 RSI 30 이하 전략을 테스트해줘.",
                category: "technical_mean_reversion",
                complexity: "intermediate",
                risk_profile: "moderate",
                expected_blocks: ["rsi", "take_profit"],
                notes: "waiting sample",
              },
            ],
          }),
        })
      )
    );

    expect(cloneCandidates("prompt_exp_existing")[0]?.status).toBe("waiting");

    const response = await POST(
      new NextRequest(
        new Request("http://localhost/api/strategy/prompt-experiments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: "start",
            experimentId: "prompt_exp_existing",
          }),
        })
      )
    );

    expect(response.status).toBe(202);
    await flushUntil(() => cloneCandidates("prompt_exp_existing")[0]?.status === "computed");
  });
});
