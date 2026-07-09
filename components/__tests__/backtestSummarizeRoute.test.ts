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

  it("캐시 히트 시 저장된 advisor 진단 필드(riskScore 등)도 함께 복원해야 함", async () => {
    mockFindUnique.mockResolvedValue({
      cacheKey: "cache-adv",
      metrics: JSON.stringify({
        aiSummary: "기존 요약",
        aiScore: 91,
        aiStrengths: ["강점"],
        aiWeaknesses: ["단점"],
        aiImprovements: ["개선점"],
        advisorScore: 64,
        riskScore: 38,
        overfitRisk: "medium",
      }),
    });

    const response = await POST(
      makeRequest({ cacheKey: "cache-adv", metrics: { totalReturn: 10 } })
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackend).not.toHaveBeenCalled();
    const data = await response.json();
    expect(data.advisorScore).toBe(64);
    expect(data.riskScore).toBe(38);
    expect(data.overfitRisk).toBe("medium");
    expect(data.cached).toBe(true);
  });

  it("force=true면 저장된 리포트를 무시하고 새로 생성하며 advisor 필드도 DB에 저장해야 함", async () => {
    mockFindUnique.mockResolvedValue({
      cacheKey: "cache-force",
      metrics: JSON.stringify({
        aiSummary: "기존 요약",
        aiScore: 50,
      }),
    });
    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 77,
        summary: "재생성 요약",
        strengths: ["강점 B"],
        weaknesses: ["단점 B"],
        improvements: ["개선점 B"],
        advisorScore: 60,
        riskScore: 30,
        overfitRisk: "low",
      }),
    });

    const response = await POST(
      makeRequest({
        cacheKey: "cache-force",
        metrics: { totalReturn: 11 },
        force: true,
      })
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackend).toHaveBeenCalledOnce();
    const data = await response.json();
    expect(data.summary).toBe("재생성 요약");
    expect(data.cached).toBe(false);

    const savedMetrics = JSON.parse(mockUpdate.mock.calls[0][0].data.metrics);
    expect(savedMetrics.aiSummary).toBe("재생성 요약");
    expect(savedMetrics.advisorScore).toBe(60);
    expect(savedMetrics.riskScore).toBe(30);
    expect(savedMetrics.overfitRisk).toBe("low");
  });

  it("degraded(파싱 실패 폴백) 리포트는 DB에 저장하지 않고 degraded를 전달해야 함", async () => {
    mockFindUnique.mockResolvedValue({
      cacheKey: "cache-degraded",
      metrics: JSON.stringify({ totalReturn: 5 }),
    });
    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 40,
        summary: "모델 출력 형식이 올바르지 않아 요약을 생성하지 못했습니다. 다시 시도해 주세요.",
        strengths: [],
        weaknesses: [],
        improvements: [],
        degraded: true,
      }),
    });

    const response = await POST(
      makeRequest({ cacheKey: "cache-degraded", metrics: { totalReturn: 5 } })
    );

    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.degraded).toBe(true);
    // 실패 폴백이 캐시로 남으면 이후 캐시 히트로 계속 서빙되므로 저장 금지
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("저장된 총평이 프롬프트 지시문 복창으로 오염됐으면 캐시로 서빙하지 않고 재생성해야 함", async () => {
    mockFindUnique.mockResolvedValue({
      cacheKey: "cache-poisoned",
      metrics: JSON.stringify({
        aiSummary:
          "[중요] 위 JSON 규칙을 따르되, 아래 'advisor 진단 근거'에 명시된 문제만 weaknesses에 반영하세요. <think> Analyze the Request...",
        aiScore: 70,
      }),
    });
    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 72,
        summary: "정상 재생성 요약",
        strengths: ["강점"],
        weaknesses: ["단점"],
        improvements: ["개선점"],
      }),
    });

    const response = await POST(
      makeRequest({ cacheKey: "cache-poisoned", metrics: { totalReturn: 7 } })
    );

    expect(response.status).toBe(200);
    expect(mockFetchBackend).toHaveBeenCalledOnce();
    const data = await response.json();
    expect(data.summary).toBe("정상 재생성 요약");
    expect(data.cached).toBe(false);
  });

  it("parsedStrategy/userPrompt를 백엔드로 전달하고 advisor 부가 필드를 반환해야 함", async () => {
    mockFindUnique.mockResolvedValue(null);
    mockFetchBackend.mockResolvedValue({
      ok: true,
      json: async () => ({
        score: 70,
        summary: "advisor 요약",
        strengths: ["강점"],
        weaknesses: ["단점"],
        improvements: ["손절 8% 설정을 고려해보세요."],
        advisorScore: 64,
        riskScore: 38,
        overfitRisk: "medium",
      }),
    });

    const response = await POST(
      makeRequest({
        metrics: { cagr: 16 },
        strategySummary: { strategyName: "전략" },
        parsedStrategy: { entry_signals: [] },
        userPrompt: "안정적인 전략",
      })
    );

    expect(response.status).toBe(200);
    // 백엔드 호출 바디에 snake_case 로 전달
    const sentBody = JSON.parse(mockFetchBackend.mock.calls[0][1].body);
    expect(sentBody.parsed_strategy).toEqual({ entry_signals: [] });
    expect(sentBody.user_prompt).toBe("안정적인 전략");

    await expect(response.json()).resolves.toEqual({
      score: 70,
      summary: "advisor 요약",
      strengths: ["강점"],
      weaknesses: ["단점"],
      improvements: ["손절 8% 설정을 고려해보세요."],
      advisorScore: 64,
      riskScore: 38,
      overfitRisk: "medium",
      cached: false,
    });
  });
});
