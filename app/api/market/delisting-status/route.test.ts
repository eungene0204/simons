import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /api/market/delisting-status", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("combines confirmed delisted symbols and warning notices", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ delisted: ["005930"] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          notices: [
            { stock_code: "005930" },
            { stock_code: "000660" },
            { stock_code: "" },
          ],
        }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      delisted: ["005930"],
      warning: ["000660"],
    });
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/market/delist", { next: { revalidate: 300 } });
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/market/dart/notices?days=30", { next: { revalidate: 300 } });
  });

  it("falls back to empty status when backend requests fail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("backend unavailable")));

    const response = await GET();

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ delisted: [], warning: [] });
  });
});
