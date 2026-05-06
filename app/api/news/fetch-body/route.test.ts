import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

import { GET } from "./route";

function makeRequest(url: string) {
  return new NextRequest(`http://localhost/api/news/fetch-body?url=${encodeURIComponent(url)}`);
}

describe("news fetch-body proxy", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it.each([
    "http://localhost/admin",
    "http://127.0.0.1:8000/news",
    "http://10.1.2.3/news",
    "http://172.16.0.1/news",
    "http://192.168.0.1/news",
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
  ])("rejects private or unsupported article URL %s", async (url) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(makeRequest(url));

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ body: null });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards allowed public article URLs to the backend", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ body: "article body" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const response = await GET(makeRequest("https://example.com/news/1"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ body: "article body" });
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/news/fetch-body?url=https%3A%2F%2Fexample.com%2Fnews%2F1",
      { cache: "no-store" }
    );
  });
});
