// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGetOwnershipContext = vi.fn();
const mockGetUserPlan = vi.fn();

vi.mock("@/lib/get-user", () => ({
  getOwnershipContext: mockGetOwnershipContext,
  isUnauthorizedAccessError: () => false,
}));

vi.mock("@/lib/prisma", () => ({ prisma: {} }));

vi.mock("@/lib/server/planLimits", () => ({
  getUserPlan: mockGetUserPlan,
}));

const { POST } = await import("@/app/api/backtest/export/route");

const payload = {
  metadata: {
    strategyName: "볼린저 전략",
    backtestId: "bt-1",
    exportedAt: "2026-07-08T15:30:00+09:00",
    period: { from: "2022-01-01", to: "2026-07-08" },
    universe: "KOSPI",
    initialCapital: 10_000_000,
    finalEquity: 12_000_000,
  },
  stockAnalysis: [{ symbol: "005930", name: "삼성전자", tradeCount: 1, winRate: 1, totalReturn: 0.1, totalProfit: 1000 }],
  tradeHistory: [],
};

function makeRequest(body: object): Request {
  return new Request("http://localhost/api/backtest/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/backtest/export 플랜 게이트", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("비로그인 사용자는 401 이고 파일을 만들지 않는다", async () => {
    mockGetOwnershipContext.mockResolvedValue({ userId: null });
    const res = await POST(makeRequest({ format: "csv", payload }));
    expect(res.status).toBe(401);
    expect(res.headers.get("Content-Disposition")).toBeNull();
    expect(mockGetUserPlan).not.toHaveBeenCalled();
  });

  it("무료 플랜은 403 이고 파일을 만들지 않는다", async () => {
    mockGetOwnershipContext.mockResolvedValue({ userId: 7 });
    mockGetUserPlan.mockResolvedValue({ planId: "FREE" });
    const res = await POST(makeRequest({ format: "csv", payload }));
    expect(res.status).toBe(403);
    expect(res.headers.get("Content-Disposition")).toBeNull();
  });

  it("Pro 플랜은 200 + 첨부파일 CSV 를 반환한다", async () => {
    mockGetOwnershipContext.mockResolvedValue({ userId: 7 });
    mockGetUserPlan.mockResolvedValue({ planId: "PRO" });
    const res = await POST(makeRequest({ format: "csv", payload }));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("text/csv");
    expect(res.headers.get("Content-Disposition")).toContain("attachment");
    // 바이트 레벨에서 UTF-8 BOM(EF BB BF) 확인 — Response.text()는 디코딩 시 BOM을 제거한다.
    const bytes = new Uint8Array(await res.arrayBuffer());
    expect([bytes[0], bytes[1], bytes[2]]).toEqual([0xef, 0xbb, 0xbf]);
    expect(new TextDecoder().decode(bytes)).toContain("볼린저 전략");
  });

  it("Premium 플랜은 200 + JSON 을 반환한다", async () => {
    mockGetOwnershipContext.mockResolvedValue({ userId: 7 });
    mockGetUserPlan.mockResolvedValue({ planId: "PREMIUM" });
    const res = await POST(makeRequest({ format: "json", payload }));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toContain("application/json");
    const parsed = JSON.parse(await res.text());
    expect(parsed.metadata.strategyName).toBe("볼린저 전략");
  });

  it("지원하지 않는 형식은 400 이다", async () => {
    mockGetOwnershipContext.mockResolvedValue({ userId: 7 });
    mockGetUserPlan.mockResolvedValue({ planId: "PRO" });
    const res = await POST(makeRequest({ format: "pdf", payload }));
    expect(res.status).toBe(400);
  });
});
