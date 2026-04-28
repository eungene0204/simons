import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFindUnique = vi.fn();
const mockUpdate = vi.fn();
const mockFetchBackend = vi.fn();

vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: {
      findUnique: mockFindUnique,
      update: mockUpdate,
    },
  },
}));

vi.mock("@/lib/server/backend", () => ({
  fetchBackend: mockFetchBackend,
}));

const { POST, __resetSummaryCacheForTests } = await import("./route");

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/summarize cache", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetSummaryCacheForTests();
  });

  it("reuses the memory cache for identical payloads without a DB cacheKey", async () => {
    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 82,
        summary: "반복 요약",
        strengths: ["강점"],
        weaknesses: ["약점"],
        improvements: ["개선"],
      }),
    });

    const body = {
      metrics: { totalReturn: 12, sharpe: 1.2 },
      strategySummary: { strategyName: "전략" },
    };

    const first = await POST(makeRequest(body));
    const second = await POST(makeRequest(body));

    expect(mockFetchBackend).toHaveBeenCalledOnce();
    await expect(first.json()).resolves.toMatchObject({ summary: "반복 요약", cached: false });
    await expect(second.json()).resolves.toMatchObject({ summary: "반복 요약", cached: true });
  });

  it("deduplicates concurrent identical payloads while a summary is in flight", async () => {
    let resolveBackend: (value: any) => void = () => {};
    mockFetchBackend.mockReturnValue(
      new Promise((resolve) => {
        resolveBackend = resolve;
      })
    );

    const body = {
      metrics: { totalReturn: 21, cagr: 8 },
      strategySummary: { strategyName: "동시 요청 전략" },
    };

    const first = POST(makeRequest(body));
    const second = POST(makeRequest(body));

    resolveBackend({
      ok: true,
      json: async () => ({
        score: 88,
        summary: "동시 요약",
        strengths: ["강점"],
        weaknesses: ["약점"],
        improvements: ["개선"],
      }),
    });

    const responses = await Promise.all([first, second]);

    expect(mockFetchBackend).toHaveBeenCalledOnce();
    await expect(responses[0].json()).resolves.toMatchObject({ summary: "동시 요약" });
    await expect(responses[1].json()).resolves.toMatchObject({ summary: "동시 요약" });
  });
});
