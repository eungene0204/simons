import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "../stocks/[symbol]/news/route";

function makeRequest(symbol = "088350", query = "limit=30") {
  return new NextRequest(`http://localhost/api/stocks/${symbol}/news?${query}`);
}

describe("stock news proxy route", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("maps transient backend 500 to collecting without exposing raw backend errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(makeRequest(), { params: { symbol: "088350" } });
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body).toMatchObject({
      symbol: "088350",
      items: [],
      lastUpdatedAt: null,
      isStale: false,
      status: "COLLECTING",
      source: "queue",
      message: "뉴스 서비스가 일시적으로 응답하지 않아 다시 시도하고 있습니다.",
    });
    expect(body.message).not.toContain("백엔드 응답 오류");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/v2/news/088350?limit=30",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("forwards successful backend news responses", async () => {
    const payload = {
      symbol: "088350",
      items: [],
      lastUpdatedAt: null,
      isStale: false,
      status: "READY",
      source: "postgres",
      message: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => payload,
      })
    );

    const response = await GET(makeRequest(), { params: { symbol: "088350" } });

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual(payload);
  });
});
