import { beforeEach, describe, expect, it, vi } from "vitest";
import { prisma } from "@/lib/prisma";
import { GET } from "./route";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    stock: {
      findMany: vi.fn(),
    },
  },
}));

const mockFindMany = vi.mocked(prisma.stock.findMany);

function makeRequest(url = "http://localhost:3000/api/market/delisting-status") {
  return new Request(url);
}

describe("GET /api/market/delisting-status", () => {
  beforeEach(() => {
    mockFindMany.mockResolvedValue([]);
  });

  it("분류별로 DB 상태를 올바르게 반환한다", async () => {
    mockFindMany.mockResolvedValue([
      { symbol: "001570", name: "금양", listingStatus: "DELISTED", lastTradableDate: null, delistingDate: null, suspensionReason: null },
      { symbol: "418250", name: "시큐레터", listingStatus: "WARNING", lastTradableDate: null, delistingDate: null, suspensionReason: null },
      { symbol: "393970", name: "대진첨단소재", listingStatus: "TRADING_SUSPENDED", lastTradableDate: null, delistingDate: null, suspensionReason: "감사의견 거절" },
      { symbol: "069460", name: "대호에이엘", listingStatus: "DELISTING_REVIEW", lastTradableDate: null, delistingDate: null, suspensionReason: null },
      { symbol: "204210", name: "스타에스엠리츠", listingStatus: "DELISTING_SCHEDULED", lastTradableDate: "2026-06-10", delistingDate: null, suspensionReason: null },
    ] as any);

    const response = await GET(makeRequest());

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.delisted).toContain("001570");
    expect(body.warning).toContain("418250");
    expect(body.tradingSuspended).toContain("393970");
    expect(body.delistingReview).toContain("069460");
    expect(body.delistingScheduled).toContain("204210");
    expect(body.names["001570"]).toBe("금양");
    expect(body.details["393970"].suspensionReason).toBe("감사의견 거절");
    expect(body.details["204210"].lastTradableDate).toBe("2026-06-10");
  });

  it("symbols 파라미터로 필터링한다", async () => {
    mockFindMany.mockResolvedValue([
      { symbol: "001570", name: "금양", listingStatus: "DELISTED", lastTradableDate: null, delistingDate: null, suspensionReason: null },
      { symbol: "418250", name: "시큐레터", listingStatus: "WARNING", lastTradableDate: null, delistingDate: null, suspensionReason: null },
    ] as any);

    const response = await GET(makeRequest("http://localhost:3000/api/market/delisting-status?symbols=001570"));

    const body = await response.json();
    expect(body.delisted).toContain("001570");
    expect(body.warning).not.toContain("418250");
  });

  it("DB 오류 시 빈 상태를 반환한다", async () => {
    mockFindMany.mockRejectedValue(new Error("DB connection failed"));

    const response = await GET(makeRequest());

    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.delisted).toEqual([]);
    expect(body.warning).toEqual([]);
    expect(body.tradingSuspended).toEqual([]);
  });
});
