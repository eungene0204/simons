// @ts-nocheck
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

const { POST } = await import("@/app/api/backtest/summarize/route");

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/summarize", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("cacheKey에 저장된 AI 리포트가 있으면 백엔드 재요청 없이 그대로 반환해야 함", async () => {
    mockFindUnique.mockResolvedValue({
      cacheKey: "cache-1",
      metrics: JSON.stringify({
        aiSummary: "기존 요약",
        aiScore: 91,
        aiStrengths: ["강점"],
        aiWeaknesses: ["단점"],
        aiImprovements: ["개선점"],
      }),
    });

    const response = await POST(
      makeRequest({
        cacheKey: "cache-1",
        metrics: { totalReturn: 10 },
        strategySummary: { strategyName: "전략" },
      })
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackend).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
    await expect(response.json()).resolves.toEqual({
      score: 91,
      summary: "기존 요약",
      strengths: ["강점"],
      weaknesses: ["단점"],
      improvements: ["개선점"],
      cached: true,
    });
  });

  it("저장된 AI 리포트가 없으면 한 번 생성하고 cacheKey 기준으로 DB에 저장해야 함", async () => {
    mockFindUnique
      .mockResolvedValueOnce({
        cacheKey: "cache-2",
        metrics: JSON.stringify({ totalReturn: 12 }),
      })
      .mockResolvedValueOnce({
        cacheKey: "cache-2",
        metrics: JSON.stringify({ totalReturn: 12 }),
      });

    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 76,
        summary: "새 요약",
        strengths: ["강점 A"],
        weaknesses: ["단점 A"],
        improvements: ["개선점 A"],
      }),
    });

    const response = await POST(
      makeRequest({
        cacheKey: "cache-2",
        metrics: { totalReturn: 12 },
        strategySummary: { strategyName: "전략" },
      })
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackend).toHaveBeenCalledOnce();
    expect(mockUpdate).toHaveBeenCalledWith({
      where: { cacheKey: "cache-2" },
      data: {
        metrics: JSON.stringify({
          totalReturn: 12,
          aiSummary: "새 요약",
          aiScore: 76,
          aiStrengths: ["강점 A"],
          aiWeaknesses: ["단점 A"],
          aiImprovements: ["개선점 A"],
        }),
      },
    });
    await expect(response.json()).resolves.toEqual({
      score: 76,
      summary: "새 요약",
      strengths: ["강점 A"],
      weaknesses: ["단점 A"],
      improvements: ["개선점 A"],
      cached: false,
    });
  });
});
