// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cache } from "@/lib/cache";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

vi.mock("@/lib/krx-stocks", () => ({
  loadStockList: vi.fn().mockResolvedValue([
    {
      symbol: "005930",
      name: "삼성전자",
      sector: "정보기술",
      industry: "반도체",
      market: "KOSPI",
    },
  ]),
}));

const { GET } = await import("@/app/api/stock/[symbol]/detail/route");

describe("GET /api/stock/[symbol]/detail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cache.clear();
  });

  it("KIS 상세 시세가 있으면 시가총액과 거래량에 mock 값을 쓰지 않는다", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 69000 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          symbol: "005930",
          name: "삼성전자",
          currentPrice: 70100,
          changePercent: 1.59,
          open: 69500,
          high: 70300,
          low: 69400,
          volume: 12345678,
          marketCap: 418474470500000,
          previousClose: 69000,
          source: "kis_inquire_price",
        }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(fetchMock.mock.calls[0][0]).toContain("/stock/005930/ohlcv");
    expect(fetchMock.mock.calls[1][0]).toContain("/market/stock-detail/005930");
    expect(body.marketCap).toBe(418474470500000);
    expect(body.volume).toBe(12345678);
    expect(body.currentPrice).toBe(70100);
    expect(body.previousClose).toBe(69000);
  });
});
