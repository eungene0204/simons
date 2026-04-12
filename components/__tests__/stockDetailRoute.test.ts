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
    {
      symbol: "042660",
      name: "한화오션",
      sector: "산업재",
      industry: "조선",
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
        json: async () => ({ subscribed: ["005930"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          "005930": {
            close: 70100,
            open: 69500,
            high: 70300,
            low: 69400,
            volume: 12345678,
            source: "kis_total",
            prev_close: 69000,
            change_rate: 1.59,
            date: "2026-04-08",
          },
        }),
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
          week52High: 88800,
          week52HighDate: "2025-07-11",
          week52HighChangePercent: 78.95,
          week52Low: 61200,
          week52LowDate: "2025-11-19",
          week52LowChangePercent: 14.54,
          newHighLowCode: "1",
          isNew52WeekHigh: true,
          isNew52WeekLow: false,
          source: "kis_inquire_price",
        }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(fetchMock.mock.calls[0][0]).toContain("/stock/005930/ohlcv");
    expect(fetchMock.mock.calls[1][0]).toContain("/market/subscribe");
    expect(fetchMock.mock.calls[2][0]).toContain("/market/prices");
    expect(fetchMock.mock.calls[3][0]).toContain("/market/stock-detail/005930");
    expect(body.marketCap).toBe(418474470500000);
    expect(body.volume).toBe(12345678);
    expect(body.currentPrice).toBe(70100);
    expect(body.previousClose).toBe(69000);
    expect(body.week52High).toBe(88800);
    expect(body.week52HighDate).toBe("2025-07-11");
    expect(body.week52HighChangePercent).toBe(78.95);
    expect(body.week52Low).toBe(61200);
    expect(body.week52LowDate).toBe("2025-11-19");
    expect(body.week52LowChangePercent).toBe(14.54);
    expect(body.newHighLowCode).toBe("1");
    expect(body.isNew52WeekHigh).toBe(true);
    expect(body.isNew52WeekLow).toBe(false);
  });

  it("KIS 상세 시세가 비어도 기존 유효한 시가총액과 거래량을 0으로 덮어쓰지 않는다", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 69000 }),
      })
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({}),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(body.marketCap).toBe(432000000000000);
    expect(body.volume).toBe(12500000);
    expect(body.name).toBe("삼성전자");
    expect(body.week52High).toBeNull();
    expect(body.week52Low).toBeNull();
    expect(body.newHighLowCode).toBeNull();
    expect(body.isNew52WeekHigh).toBe(false);
    expect(body.isNew52WeekLow).toBe(false);
  });

  it("same symbol reuses the last valid market cap when KIS detail temporarily drops it", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 82000 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ subscribed: ["042660"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          "042660": {
            close: 82100,
            open: 81000,
            high: 82500,
            low: 80800,
            volume: 7654321,
            source: "kis_total",
            prev_close: 82000,
            change_rate: 0.12,
            date: "2026-04-08",
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          symbol: "042660",
          name: "한화오션",
          currentPrice: 82100,
          changePercent: 0.12,
          open: 81000,
          high: 82500,
          low: 80800,
          volume: 7654321,
          marketCap: 16700000000000,
          previousClose: 82000,
          source: "kis_inquire_price",
        }),
      });

    const firstResponse = await GET(
      new Request("http://localhost/api/stock/042660/detail"),
      { params: { symbol: "042660" } }
    );
    const firstBody = await firstResponse.json();

    expect(firstBody.marketCap).toBe(16700000000000);

    cache.delete("stock:detail:042660");
    fetchMock.mockReset();

    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 82000 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ subscribed: ["042660"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          "042660": {
            close: 82300,
            open: 81000,
            high: 82800,
            low: 80900,
            volume: 8765432,
            source: "kis_total",
            prev_close: 82000,
            change_rate: 0.37,
            date: "2026-04-08",
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          symbol: "042660",
          name: "한화오션",
          currentPrice: 82300,
          changePercent: 0.37,
          open: 81000,
          high: 82800,
          low: 80900,
          volume: 8765432,
          marketCap: 0,
          previousClose: 82000,
          source: "kis_inquire_price",
        }),
      });

    const secondResponse = await GET(
      new Request("http://localhost/api/stock/042660/detail"),
      { params: { symbol: "042660" } }
    );
    const secondBody = await secondResponse.json();

    expect(secondBody.marketCap).toBe(16700000000000);
    expect(secondBody.name).toBe("한화오션");
  });
});
