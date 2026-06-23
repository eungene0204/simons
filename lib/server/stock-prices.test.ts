import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cache } from "@/lib/cache";
import { fetchStockPriceSnapshots } from "./stock-prices";

describe("fetchStockPriceSnapshots — 프로덕션 WS 프록시 (로컬 개발)", () => {
  beforeEach(() => {
    cache.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    delete process.env.STOCK_REALTIME_PROXY_URL;
  });

  it("STOCK_REALTIME_PROXY_URL이 설정되면 프로덕션 공개 가격 API에서 시세를 가져온다", async () => {
    process.env.STOCK_REALTIME_PROXY_URL = "https://www.nullstock.im/";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        price: 124200,
        change: -9800,
        changePercent: -7.31,
        open: 133300,
        high: 133300,
        low: 123500,
        volume: 1882814,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchStockPriceSnapshots(["080220"], { mode: "stream" });

    // 프로덕션 공개 API를 호출했는가 (트레일링 슬래시 정규화 포함)
    expect(fetchMock).toHaveBeenCalledWith(
      "https://www.nullstock.im/api/stock/080220/price",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(result["080220"].price).toBe(124200);
    expect(result["080220"].changePercent).toBe(-7.31);
    // previousClose가 응답에 없으면 price - change로 역산
    expect(result["080220"].previousClose).toBe(134000);
    expect(result["080220"].source).toBe("prod_proxy");
  });

  it("프록시 응답에 previousClose가 있으면 그 값을 그대로 쓴다", async () => {
    process.env.STOCK_REALTIME_PROXY_URL = "https://www.nullstock.im";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          price: 70000,
          change: 3333,
          changePercent: 5.0,
          previousClose: 66667,
        }),
      })
    );

    const result = await fetchStockPriceSnapshots(["005930"], { mode: "stream" });

    expect(result["005930"].previousClose).toBe(66667);
    expect(result["005930"].price).toBe(70000);
  });

  it("프록시가 404를 주면 빈 스냅샷으로 폴백한다", async () => {
    process.env.STOCK_REALTIME_PROXY_URL = "https://www.nullstock.im";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404 })
    );

    const result = await fetchStockPriceSnapshots(["005930"], { mode: "stream" });

    expect(result["005930"]).toEqual({ price: 0, changePercent: 0, volume: 0 });
  });

  it("STOCK_REALTIME_PROXY_URL이 없으면 로컬 백엔드(/market/prices)를 호출한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        "005930": { close: 70000, prev_close: 66667, change_rate: 5.0, volume: 10 },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchStockPriceSnapshots(["005930"], {
      mode: "stream",
      subscribe: false,
    });

    const calledUrls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calledUrls.some((u) => u.includes("/market/prices"))).toBe(true);
    expect(result["005930"].price).toBe(70000);
  });
});
