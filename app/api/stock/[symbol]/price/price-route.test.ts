import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const fetchStockPriceSnapshots = vi.fn();

vi.mock("@/lib/server/stock-prices", () => ({
  fetchStockPriceSnapshots: (...args: unknown[]) =>
    fetchStockPriceSnapshots(...args),
}));

import { GET } from "./route";

function makeRequest(symbol = "005930") {
  return new NextRequest(`http://localhost/api/stock/${symbol}/price`);
}

describe("stock price route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the KIS changePercent and derives previousClose from it when prev_close is missing", async () => {
    // previousClose 없이 KIS 등락률만 있는 snapshot — KIS 등락률(%)을 그대로 쓰고
    // 전일종가는 그 등락률로 역산한다. change(원)는 항상 derived previousClose와 일치한다.
    fetchStockPriceSnapshots.mockResolvedValue({
      "005930": {
        price: 70000,
        changePercent: 5.3,
        volume: 1000,
        open: 66500,
      },
    });

    const response = await GET(makeRequest(), { params: { symbol: "005930" } });
    const body = await response.json();

    const expectedPrev = Math.round(70000 / 1.053);
    expect(body.changePercent).toBe(5.3);
    expect(body.previousClose).toBe(expectedPrev);
    expect(body.change).toBe(70000 - expectedPrev);
  });

  it("uses KIS prev_close directly and keeps change/changePercent consistent", async () => {
    fetchStockPriceSnapshots.mockResolvedValue({
      "005930": {
        price: 70000,
        changePercent: 5.0,
        previousClose: 66667,
        volume: 1000,
      },
    });

    const response = await GET(makeRequest(), { params: { symbol: "005930" } });
    const body = await response.json();

    expect(body.previousClose).toBe(66667);
    expect(body.change).toBe(70000 - 66667);
    expect(body.changePercent).toBe(5.0);
  });
});
