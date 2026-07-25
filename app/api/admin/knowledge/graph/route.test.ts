// @ts-nocheck
import { beforeEach, describe, expect, it, vi } from "vitest";

// KG 시각화 프록시(FR-STR-070c) — 권한 게이트(404 은닉)와 백엔드 합성 그래프
// 패스스루, 백엔드 미가용 시 502 변환을 검증한다.

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

const GRAPH = {
  nodes: [{ id: "hbm", name: "HBM", category: "technology" }],
  edges: [{ source: "hbm", type: "belongs_to", target: "sector:반도체" }],
  issues: [],
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("GET /api/admin/knowledge/graph", () => {
  it("비관리자에게는 404로 존재를 숨긴다", async () => {
    requireAdmin.mockResolvedValue(null);
    const res = await GET();
    expect(res.status).toBe(404);
    expect(fetchBackend).not.toHaveBeenCalled();
  });

  it("백엔드 합성 그래프를 그대로 패스스루한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockResolvedValue({ ok: true, json: async () => GRAPH });
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(GRAPH);
    expect(fetchBackend).toHaveBeenCalledWith("/knowledge/graph", expect.anything());
  });

  it("백엔드 연결 실패는 502로 변환한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockRejectedValue(new Error("ECONNREFUSED"));
    const res = await GET();
    expect(res.status).toBe(502);
  });

  it("백엔드 비정상 응답도 502로 변환한다", async () => {
    requireAdmin.mockResolvedValue(admin);
    fetchBackend.mockResolvedValue({ ok: false, status: 500 });
    const res = await GET();
    expect(res.status).toBe(502);
  });
});
