import { beforeEach, describe, expect, it, vi } from "vitest";

const fetchBackend = vi.fn();

vi.mock("@/lib/server/backend", () => ({
  fetchBackend,
}));

const metricsRoute = await import("./route");
const resetRoute = await import("./reset/route");

describe("AI runtime metrics proxy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });

  it("proxies runtime metrics snapshots from the backend", async () => {
    fetchBackend.mockResolvedValueOnce({
      status: 200,
      json: async () => ({
        stages: {
          parse: {
            count: 2,
            cache_hits: 1,
            avg_total_ms: 120,
          },
        },
        recent: [],
      }),
    });

    const response = await metricsRoute.GET();

    expect(fetchBackend).toHaveBeenCalledWith("/ai/runtime/metrics", {
      cache: "no-store",
      timeoutMs: 30_000,
    });
    await expect(response.json()).resolves.toMatchObject({
      stages: {
        parse: {
          count: 2,
          cache_hits: 1,
        },
      },
    });
  });

  it("proxies runtime metrics reset requests", async () => {
    fetchBackend.mockResolvedValueOnce({
      status: 200,
      json: async () => ({ ok: true }),
    });

    const response = await resetRoute.POST();

    expect(fetchBackend).toHaveBeenCalledWith("/ai/runtime/metrics/reset", {
      method: "POST",
      cache: "no-store",
      timeoutMs: 30_000,
    });
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  it("blocks runtime metrics reset in production", async () => {
    vi.stubEnv("NODE_ENV", "production");

    const response = await resetRoute.POST();

    expect(response.status).toBe(403);
    expect(fetchBackend).not.toHaveBeenCalled();
    await expect(response.json()).resolves.toEqual({
      error: "AI runtime metrics reset is disabled in production",
    });
  });
});
