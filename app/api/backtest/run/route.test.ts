// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// /api/backtest/run 회귀 테스트 — 비로그인은 쿼터를 셀 주체가 없으므로 실행하지 않는다(2026-09-03 감사).
const { getCurrentUser, consumeBacktestQuota } = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  consumeBacktestQuota: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({ getCurrentUser }));
vi.mock("@/lib/prisma", () => ({ prisma: {} }));
vi.mock("@/lib/server/backtestCache", () => ({
  computeCacheKey: () => "ck",
  saveCachedResult: vi.fn(),
}));
vi.mock("@/lib/server/planLimits", () => ({
  consumeBacktestQuota,
  PLAN_LIMIT_BACKTESTS: "PLAN_LIMIT_BACKTESTS",
  PLAN_LIMIT_MESSAGES: { PLAN_LIMIT_BACKTESTS: "한도 초과" },
}));

const { POST } = await import("./route");

function makeRequest(body: object) {
  return { json: async () => body } as any;
}

describe("POST /api/backtest/run", () => {
  const engineFetch = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", engineFetch);
  });

  it("비로그인은 401이고 엔진·쿼터를 건드리지 않는다", async () => {
    getCurrentUser.mockResolvedValue(null);

    const res = await POST(makeRequest({ symbols: ["005930"] }));

    expect(res.status).toBe(401);
    expect(consumeBacktestQuota).not.toHaveBeenCalled();
    expect(engineFetch).not.toHaveBeenCalled();
  });

  it("로그인 사용자는 쿼터를 1회 소비하고 엔진을 호출한다", async () => {
    getCurrentUser.mockResolvedValue({ id: 3 });
    consumeBacktestQuota.mockResolvedValue(undefined);
    engineFetch.mockResolvedValue({ ok: true, json: async () => ({ totalReturn: 1 }) });

    const res = await POST(makeRequest({ symbols: ["005930"] }));

    expect(res.status).toBe(200);
    expect(consumeBacktestQuota).toHaveBeenCalledWith(expect.anything(), 3);
    expect(engineFetch).toHaveBeenCalledTimes(1);
  });

  it("한도 초과는 429", async () => {
    getCurrentUser.mockResolvedValue({ id: 3 });
    consumeBacktestQuota.mockRejectedValue(new Error("PLAN_LIMIT_BACKTESTS"));

    const res = await POST(makeRequest({ symbols: ["005930"] }));

    expect(res.status).toBe(429);
    expect(engineFetch).not.toHaveBeenCalled();
  });
});
