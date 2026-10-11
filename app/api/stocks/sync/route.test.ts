// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 종목 명부 동기화 — 권한 확인 없이 열려 있던 운영 엔드포인트(2026-10-11 보안 점검).
const requireAdmin = vi.fn();
vi.mock("@/lib/server/adminAuth", () => ({ requireAdmin: (...a) => requireAdmin(...a) }));
vi.mock("@/lib/krx-stocks", () => ({ loadStockList: async () => [] }));

const { POST } = await import("./route");

describe("POST /api/stocks/sync", () => {
  const backendFetch = vi.fn();
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", backendFetch);
  });

  it("비관리자에게는 404이고 백엔드 동기화를 부르지 않는다", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await POST({});
    expect(res.status).toBe(404);
    expect(backendFetch).not.toHaveBeenCalled();
  });

  it("관리자는 백엔드 동기화를 호출한다", async () => {
    requireAdmin.mockResolvedValue({ id: 1 });
    backendFetch.mockResolvedValue(new Response(JSON.stringify({ total: 0 }), { status: 200 }));
    await POST({});
    expect(String(backendFetch.mock.calls[0][0])).toMatch(/\/sync-stocks$/);
  });
});
