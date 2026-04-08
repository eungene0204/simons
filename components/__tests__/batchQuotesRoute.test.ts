// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const { POST } = await import("@/app/api/stock/batch-quotes/route");

function makeRequest(symbols: string[]): Request {
  return new Request("http://localhost/api/stock/batch-quotes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  });
}

describe("POST /api/stock/batch-quotes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("실시간 현재가 조회 전에 종목 구독을 먼저 요청해야 한다", async () => {
    fetchMock
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
            volume: 123456,
            source: "kis_total",
            prev_close: 69000,
            change_rate: 1.59,
            date: "2026-04-08",
          },
        }),
      });

    const response = await POST(makeRequest(["005930"]));
    const body = await response.json();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain("/market/subscribe");
    expect(fetchMock.mock.calls[1][0]).toContain("/market/prices");
    expect(body["005930"]).toEqual({
      price: 70100,
      changePercent: 1.59,
      volume: 123456,
      source: "kis_total",
      open: 69500,
      high: 70300,
      low: 69400,
      previousClose: 69000,
      date: "2026-04-08",
    });
  });
});
