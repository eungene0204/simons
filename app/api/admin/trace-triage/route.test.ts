// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// 실패 분류 프록시 — 권한 게이트(404 은닉), 기간 파라미터 전달, 백엔드 실패 시 502를 검증한다.

const requireAdmin = vi.fn();
const fetchBackend = vi.fn();

vi.mock("@/lib/server/adminAuth", () => ({
  requireAdmin: (...a) => requireAdmin(...a),
}));
vi.mock("@/lib/server/backend", () => ({
  fetchBackend: (...a) => fetchBackend(...a),
}));

import { GET } from "./route";

const admin = { id: 1, email: "admin@example.com", name: "Admin" };
const BODY = { range: ["2026-10-11", "2026-10-11"], total: 1, groups: [], tiers: [], retention_days: 3 };
const req = (qs = "") => new Request(`http://localhost/api/admin/trace-triage${qs}`);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/admin/trace-triage", () => {
  it("비관리자에게는 404로 존재를 숨기고 백엔드를 부르지 않는다", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await GET(req());
    expect(res.status).toBe(404);
    expect(fetchBackend).not.toHaveBeenCalled();
  });

  it("기간을 전달하고 결과를 그대로 돌려준다", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockResolvedValue({ ok: true, json: async () => BODY });
    const res = await GET(req("?days=2"));
    expect(await res.json()).toEqual(BODY);
    expect(fetchBackend).toHaveBeenCalledWith("/admin/trace-triage?days=2", expect.anything());
  });

  it("기간이 없거나 잘못되면 백엔드 기본값(보관 기간 전체)을 쓴다", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockResolvedValue({ ok: true, json: async () => BODY });
    await GET(req("?days=abc"));
    expect(fetchBackend).toHaveBeenCalledWith("/admin/trace-triage", expect.anything());
  });

  it("백엔드 오류·연결 실패는 502", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockResolvedValue({ ok: false });
    expect((await GET(req())).status).toBe(502);
    fetchBackend.mockRejectedValue(new Error("down"));
    expect((await GET(req())).status).toBe(502);
  });
});
