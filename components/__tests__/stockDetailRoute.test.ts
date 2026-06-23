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

  it("KIS 시세가 있으면 전일종가·등락률을 로컬 OHLCV와 섞지 않고 KIS 값 기준으로 일치시킨다", async () => {
    // 실시간 시세(KIS)에 prev_close가 빠지고 change_rate만 오는 경우,
    // 로컬 OHLCV lastClose(66667)를 전일종가로 끌어다 쓰면 KIS 현재가와 기준이 어긋난다.
    // KIS 등락률(5.0%)을 그대로 쓰고 전일종가는 그 등락률로 역산해야 한다.
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 66667 }),
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
            source: "naver",
            // prev_close 없음 — change_rate만 제공되는 경우
            change_rate: 5.0,
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
        }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    const expectedPrev = Math.round(70100 / 1.05);
    expect(body.currentPrice).toBe(70100);
    expect(body.changePercent).toBe(5.0); // KIS 등락률 그대로
    expect(body.previousClose).toBe(expectedPrev); // OHLCV(66667)가 아니라 KIS 등락률로 역산
    expect(body.change).toBe(70100 - expectedPrev);
  });

  it("KIS prev_close가 있으면 그대로 전일종가로 쓰고 OHLCV로 덮지 않는다", async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ lastClose: 114300 }), // 하루 뒤처진 OHLCV
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ subscribed: ["005930"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          "005930": {
            close: 124700,
            open: 133300,
            high: 133300,
            low: 123500,
            volume: 1487773,
            source: "kis_total",
            prev_close: 134000,
            change_rate: -6.94,
            date: "2026-06-23",
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ symbol: "005930", name: "삼성전자" }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(body.currentPrice).toBe(124700);
    expect(body.previousClose).toBe(134000); // KIS prev_close, OHLCV 114300 아님
    expect(body.change).toBe(124700 - 134000);
    expect(body.changePercent).toBe(-6.94);
  });

  it("백엔드 시세가 없으면 marketCap과 volume은 0이고 이름은 종목 목록에서 온다", async () => {
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

    expect(body.marketCap).toBe(0);
    expect(body.volume).toBe(0);
    expect(body.name).toBe("삼성전자");
    expect(body.week52High).toBeNull();
    expect(body.week52Low).toBeNull();
    expect(body.newHighLowCode).toBeNull();
    expect(body.isNew52WeekHigh).toBe(false);
    expect(body.isNew52WeekLow).toBe(false);
  });

  it("sector와 industry를 분리해서 유지한다", async () => {
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
          volume: 12345678,
          previousClose: 69000,
          sector: "반도체",
          industry: "반도체 제조업",
          source: "fsc_public_company_info",
        }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(body.sector).toBe("반도체");
    expect(body.industry).toBe("반도체 제조업");
  });

  it("공공데이터 industry가 비어 있으면 오래된 fallback 값을 섹터로 쓰지 않는다", async () => {
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
          volume: 12345678,
          previousClose: 69000,
          sector: "",
          industry: "",
          source: "fsc_public_company_info",
        }),
      });

    const response = await GET(
      new Request("http://localhost/api/stock/005930/detail"),
      { params: { symbol: "005930" } }
    );
    const body = await response.json();

    expect(body.sector).toBe("");
    expect(body.industry).toBe("");
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
