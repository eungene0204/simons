// @ts-nocheck
/**
 * /api/backtest/walk-forward(단발·SSE) 회귀 테스트 — 프리미엄 전용 게이트.
 *
 * 2026-09-03 감사: 두 프록시 라우트에 로그인·플랜 검사가 없어 비로그인도 워크포워드를
 * 돌릴 수 있었다. 요금제 페이지는 워크포워드를 프리미엄 전용으로 안내한다.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const { getCurrentUser, getUserPlan } = vi.hoisted(() => ({
  getCurrentUser: vi.fn(),
  getUserPlan: vi.fn(),
}));

vi.mock("@/lib/get-user", () => ({ getCurrentUser }));
vi.mock("@/lib/prisma", () => ({ prisma: {} }));
vi.mock("@/lib/server/planLimits", () => ({ getUserPlan }));

const { POST } = await import("./route");
const { POST: POST_STREAM } = await import("./stream/route");

function makeRequest(path: string) {
  const req = new Request(`http://localhost${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_strategy: {}, ranges: {} }),
  });
  // NextRequest 전용 필드 — 라우트는 req.signal·req.json만 쓴다.
  return req as any;
}

describe("워크포워드 프록시 플랜 게이트", () => {
  const originalFetch = globalThis.fetch;
  const backendFetch = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    globalThis.fetch = backendFetch;
    getCurrentUser.mockResolvedValue({ id: 3 });
    getUserPlan.mockResolvedValue({ planId: "PREMIUM" });
    backendFetch.mockResolvedValue(
      new Response(JSON.stringify({ windows: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("비로그인은 401이고 백엔드를 호출하지 않는다", async () => {
    getCurrentUser.mockResolvedValue(null);

    const res = await POST(makeRequest("/api/backtest/walk-forward"));
    const stream = await POST_STREAM(makeRequest("/api/backtest/walk-forward/stream"));

    expect(res.status).toBe(401);
    expect(stream.status).toBe(401);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it.each(["FREE", "PRO"])("%s 플랜은 403과 안내 문구(detail)를 준다", async (planId) => {
    getUserPlan.mockResolvedValue({ planId });

    const res = await POST(makeRequest("/api/backtest/walk-forward"));
    const stream = await POST_STREAM(makeRequest("/api/backtest/walk-forward/stream"));

    expect(res.status).toBe(403);
    expect(stream.status).toBe(403);
    await expect(res.json()).resolves.toMatchObject({ detail: expect.stringContaining("프리미엄") });
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("프리미엄 플랜은 백엔드로 프록시한다", async () => {
    const res = await POST(makeRequest("/api/backtest/walk-forward"));

    expect(res.status).toBe(200);
    expect(backendFetch).toHaveBeenCalledTimes(1);
    expect(String(backendFetch.mock.calls[0][0])).toContain("/walk-forward");
  });
});
