import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import { getSessionUserId } from "@/lib/get-user";
import { PATCH } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    backtestHistory: {
      findUnique: vi.fn(),
      update: vi.fn(),
    },
  },
}));

vi.mock("@/lib/get-user", () => ({
  getSessionUserId: vi.fn(),
}));

const mockFindUnique = vi.mocked(prisma.backtestHistory.findUnique);
const mockUpdate = vi.mocked(prisma.backtestHistory.update);
const mockGetSessionUserId = vi.mocked(getSessionUserId);

function makeRequest(): Request {
  return new Request("http://localhost/api/backtest/ai-report", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cacheKey: "cache-1", aiSummary: "덮어쓰기 시도" }),
  });
}

describe("/api/backtest/ai-report PATCH 인증", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFindUnique.mockResolvedValue({ id: "hist-1", metrics: "{}" } as any);
    mockUpdate.mockResolvedValue({} as any);
  });

  it("비로그인 요청은 기록을 건드리지 않고 401", async () => {
    mockGetSessionUserId.mockResolvedValue(null);

    const response = await PATCH(makeRequest());

    expect(response.status).toBe(401);
    expect(mockFindUnique).not.toHaveBeenCalled();
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it("로그인 사용자는 리포트를 저장한다", async () => {
    mockGetSessionUserId.mockResolvedValue(7);

    const response = await PATCH(makeRequest());

    expect(response.status).toBe(200);
    expect(mockUpdate).toHaveBeenCalledTimes(1);
  });
});
